using System;
using System.Linq;
using System.Collections;
using System.IO;
using System.Text;
using Siemens.Engineering;
using Siemens.Engineering.HW;

/// <summary>
/// TIA Portal Hardware Catalog Extractor
/// Extracts hardware configuration (modules, order numbers, firmware, IPs, PROFINET names).
///
/// Compile for TIA Portal V18-V19:
///   csc.exe /reference:"...\Siemens.Engineering.dll" /out:tia_extract_hardware.exe tia_extract_hardware.cs
///
/// Compile for TIA Portal V21+:
///   csc.exe /reference:"...\Siemens.Engineering.Base.dll" /reference:"...\Siemens.Engineering.Step7.dll"
///     /out:tia_extract_hardware.exe tia_extract_hardware.cs
///
/// Run (TIA Portal must be open with project loaded):
///   tia_extract_hardware.exe [output_json] [device_filter]
/// </summary>
class Program
{
    static StringBuilder json = new StringBuilder();
    static int deviceCount = 0;
    static int moduleCount = 0;

    static int Main(string[] args)
    {
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine("  TIA Portal Hardware Catalog Extractor");
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine();

        Console.WriteLine("Connecting to TIA Portal...");
        var processes = TiaPortal.GetProcesses();
        if (processes.Count == 0)
        {
            Console.WriteLine("ERROR: No TIA Portal found. Open TIA Portal first.");
            return 1;
        }

        TiaPortal tia = null;
        try { tia = processes[0].Attach(); }
        catch (Exception ex) { Console.WriteLine("ERROR attaching: " + ex.Message); return 1; }

        var project = tia.Projects.FirstOrDefault();
        if (project == null) { Console.WriteLine("ERROR: No project open."); return 1; }

        Console.WriteLine("Project: " + project.Name);
        Console.WriteLine();

        string outputPath = (args.Length > 0) ? args[0] : "Doc_OUTPUT/.hardware.json";
        string deviceFilter = (args.Length > 1) ? args[1] : "";

        if (!string.IsNullOrEmpty(deviceFilter))
            Console.WriteLine("Device filter: " + deviceFilter);

        json.AppendLine("{");
        json.AppendLine("  \"extraction_info\": {");
        json.AppendLine("    \"tool\": \"tia_extract_hardware.cs\",");
        json.AppendLine("    \"project\": " + J(project.Name) + ",");
        if (!string.IsNullOrEmpty(deviceFilter))
            json.AppendLine("    \"device_filter\": " + J(deviceFilter) + ",");
        json.AppendLine("    \"timestamp\": " + J(DateTime.Now.ToString("o")) + "");
        json.AppendLine("  },");
        json.AppendLine("  \"devices\": [");

        bool firstDevice = true;
        foreach (Device device in project.Devices)
        {
            if (!string.IsNullOrEmpty(deviceFilter) && !device.Name.Contains(deviceFilter))
                continue;

            Console.WriteLine("Device: " + device.Name);

            if (!firstDevice) json.AppendLine(",");
            firstDevice = false;

            json.AppendLine("    {");
            json.AppendLine("      \"device_name\": " + J(device.Name) + ",");
            json.AppendLine("      \"modules\": [");

            bool firstModule = true;
            foreach (DeviceItem item in device.DeviceItems)
            {
                WalkDeviceItem(item, ref firstModule, 0);
            }

            json.AppendLine("      ]");
            json.Append("    }");
            deviceCount++;
        }

        json.AppendLine();
        json.AppendLine("  ]");
        json.AppendLine("}");

        string outputDir = Path.GetDirectoryName(Path.GetFullPath(outputPath));
        if (!string.IsNullOrEmpty(outputDir) && !Directory.Exists(outputDir))
            Directory.CreateDirectory(outputDir);

        File.WriteAllText(outputPath, json.ToString(), new UTF8Encoding(true));
        Console.WriteLine();
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine("  HARDWARE EXTRACTION COMPLETE");
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine("  Devices:  {0}", deviceCount);
        Console.WriteLine("  Modules:  {0}", moduleCount);
        Console.WriteLine("  Output:   {0}", Path.GetFullPath(outputPath));
        Console.WriteLine("=".PadRight(70, '='));

        return 0;
    }

    static void WalkDeviceItem(DeviceItem item, ref bool firstModule, int depth)
    {
        string itemName = item.Name;
        string typeId = "";
        string orderNum = "";
        string firmware = "";
        string ipAddress = "";
        string subnet = "";
        string profinetName = "";
        string comment = "";
        int positionNumber = 0;

        // TypeIdentifier property
        try { typeId = item.TypeIdentifier ?? ""; } catch { }

        // Order number — GetAttribute, not property
        try
        {
            var v = item.GetAttribute("OrderNumber");
            if (v != null) orderNum = v.ToString();
        }
        catch { }

        // Fallback: parse from TypeIdentifier (format: "OrderNumber:6ES7 xxx/SW Vx.x ...")
        if (string.IsNullOrEmpty(orderNum) && typeId.StartsWith("OrderNumber:"))
        {
            int slash = typeId.IndexOf('/');
            orderNum = (slash > 0) ? typeId.Substring(12, slash - 12) : typeId.Substring(12);
        }

        // Firmware version — GetAttribute
        try
        {
            var v = item.GetAttribute("FirmwareVersion");
            if (v != null) firmware = v.ToString();
        }
        catch { }

        // Comment — GetAttribute
        try
        {
            var v = item.GetAttribute("Comment");
            if (v != null) comment = v.ToString();
        }
        catch { }

        // Position number — property
        try { positionNumber = item.PositionNumber; } catch { }

        // Network interface via runtime reflection for IP address
        try
        {
            var niObj = ReflectGetService(item, "Siemens.Engineering.HW.Features.NetworkInterface");
            if (niObj != null)
            {
                var nodesProp = niObj.GetType().GetProperty("Nodes");
                if (nodesProp != null)
                {
                    var nodes = nodesProp.GetValue(niObj) as IEnumerable;
                    if (nodes != null)
                    {
                        foreach (var node in nodes)
                        {
                            // Dump all node properties for first few modules
                            if (moduleCount < 8)
                            {
                                Console.WriteLine("    [NetworkInterface Node for: {0}]", itemName);
                                foreach (var p in node.GetType().GetProperties())
                                {
                                    try
                                    {
                                        var pv = p.GetValue(node);
                                        string pvs = (pv != null) ? pv.ToString() : "(null)";
                                        if (pvs.Length > 80) pvs = pvs.Substring(0, 80) + "...";
                                        Console.WriteLine("      {0} ({1}): {2}", p.Name, p.PropertyType.Name, pvs);
                                    }
                                    catch (Exception ex)
                                    {
                                        Console.WriteLine("      {0}: ERROR: {1}", p.Name, ex.Message);
                                    }
                                }
                            }

                            // Try ALL possible property names for IP and subnet
                            ipAddress = TryGet(node, new[] { "IpV4Address", "IpAddress", "IPAddress", "Address" });
                            subnet = TryGet(node, new[] { "IpV4SubnetMask", "SubnetMask", "Subnet" });
                            profinetName = TryGet(node, new[] { "Name", "DeviceName", "ProfinetName" });

                            // Also try GetAttribute on the node
                            if (string.IsNullOrEmpty(ipAddress))
                            {
                                try
                                {
                                    var ga = node.GetType().GetMethod("GetAttribute");
                                    if (ga != null)
                                    {
                                        var result = ga.Invoke(node, new object[] { "IpV4Address" });
                                        if (result != null) ipAddress = result.ToString();
                                    }
                                }
                                catch { }
                            }

                            break;
                        }
                    }
                }
            }
        }
        catch { }

        // Include items with useful info OR PROFINET/network interfaces
        bool hasInfo = !string.IsNullOrEmpty(orderNum) || !string.IsNullOrEmpty(ipAddress)
                     || !string.IsNullOrEmpty(firmware) || !string.IsNullOrEmpty(profinetName)
                     || (!string.IsNullOrEmpty(typeId) && !typeId.StartsWith("System:"));

        if (hasInfo || depth == 0)
        {
            if (!firstModule) json.AppendLine(",");
            firstModule = false;

            string indent = new string(' ', 8);
            json.AppendLine(indent + "{");
            json.AppendLine(indent + "  \"module_name\": " + J(itemName) + ",");
            if (!string.IsNullOrEmpty(typeId))
                json.AppendLine(indent + "  \"type_identifier\": " + J(typeId) + ",");
            if (!string.IsNullOrEmpty(orderNum))
                json.AppendLine(indent + "  \"order_number\": " + J(orderNum) + ",");
            if (!string.IsNullOrEmpty(firmware))
                json.AppendLine(indent + "  \"firmware\": " + J(firmware) + ",");
            if (!string.IsNullOrEmpty(ipAddress))
                json.AppendLine(indent + "  \"ip_address\": " + J(ipAddress) + ",");
            if (!string.IsNullOrEmpty(subnet))
                json.AppendLine(indent + "  \"subnet_mask\": " + J(subnet) + ",");
            if (!string.IsNullOrEmpty(profinetName))
                json.AppendLine(indent + "  \"profinet_name\": " + J(profinetName) + ",");
            if (!string.IsNullOrEmpty(comment))
                json.AppendLine(indent + "  \"comment\": " + J(comment) + ",");
            if (positionNumber > 0)
                json.AppendLine(indent + "  \"position\": " + positionNumber + ",");

            // Remove trailing comma
            string lastLine = json.ToString().TrimEnd();
            if (lastLine.EndsWith(","))
            {
                json.Length -= 3;
                json.AppendLine();
            }

            json.Append(indent + "}");

            Console.WriteLine("  {0}{1} {2} {3}",
                new string(' ', depth * 2),
                itemName,
                !string.IsNullOrEmpty(orderNum) ? "[" + orderNum + "]" : "",
                !string.IsNullOrEmpty(ipAddress) ? ipAddress : "");
            moduleCount++;
        }

        // Recurse into sub-items
        foreach (DeviceItem sub in item.DeviceItems)
        {
            WalkDeviceItem(sub, ref firstModule, depth + 1);
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    static object ReflectGetService(DeviceItem item, string typeName)
    {
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            try
            {
                var t = asm.GetType(typeName);
                if (t != null)
                {
                    var method = item.GetType().GetMethod("GetService");
                    if (method != null)
                    {
                        var generic = method.MakeGenericMethod(t);
                        return generic.Invoke(item, null);
                    }
                }
            }
            catch { }
        }
        return null;
    }

    static string TryGet(object o, string[] names)
    {
        foreach (var n in names)
        {
            try
            {
                var p = o.GetType().GetProperty(n);
                if (p != null)
                {
                    var v = p.GetValue(o);
                    if (v != null) return v.ToString();
                }
            }
            catch { }
        }
        return "";
    }

    static string J(string s)
    {
        if (s == null) return "\"\"";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "") + "\"";
    }
}
