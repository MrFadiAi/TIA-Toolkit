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
/// Uses pure reflection for all property access — no compile-time dependency on HW.Features.
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
///     output_json   - output JSON file (default: Doc_OUTPUT/.hardware.json)
///     device_filter - substring of device name to filter (optional)
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

        // Build JSON
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

        // Ensure output directory exists
        string outputDir = Path.GetDirectoryName(Path.GetFullPath(outputPath));
        if (!string.IsNullOrEmpty(outputDir) && !Directory.Exists(outputDir))
            Directory.CreateDirectory(outputDir);

        // Write JSON
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
        int slot = -1;

        // Type identifier
        try { typeId = item.TypeIdentifier ?? ""; } catch { }

        // All properties via reflection — no HW.Features dependency
        try { orderNum = FastGet(item, "OrderNumber") ?? ""; } catch { }
        try { firmware = FastGet(item, "FirmwareVersion") ?? ""; } catch { }
        try { ipAddress = FastGet(item, "IpAddress") ?? ""; } catch { }
        try { subnet = FastGet(item, "SubnetMask") ?? ""; } catch { }
        try { profinetName = FastGet(item, "ProfinetName") ?? ""; } catch { }

        // Network interface via runtime reflection (avoids compile-time type reference)
        if (string.IsNullOrEmpty(ipAddress))
        {
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
                                try { ipAddress = FastGet(node, "IpV4Address") ?? FastGet(node, "IpAddress") ?? ipAddress; } catch { }
                                try { subnet = FastGet(node, "IpV4SubnetMask") ?? FastGet(node, "SubnetMask") ?? subnet; } catch { }
                                if (string.IsNullOrEmpty(profinetName))
                                {
                                    try { profinetName = FastGet(node, "Name") ?? profinetName; } catch { }
                                }
                                break;
                            }
                        }
                    }
                }
            }
            catch { }
        }

        // Position (rack/slot)
        try
        {
            var pos = item.GetAttribute("PositionInParent");
            if (pos != null) slot = Convert.ToInt32(pos);
        }
        catch { }

        // Only add modules that have useful info
        bool hasInfo = !string.IsNullOrEmpty(orderNum) || !string.IsNullOrEmpty(ipAddress)
                     || !string.IsNullOrEmpty(firmware) || !string.IsNullOrEmpty(typeId);

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
            if (slot >= 0)
                json.AppendLine(indent + "  \"slot\": " + slot + ",");

            // Remove trailing comma from last field
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

    /// <summary>
    /// Call GetService&lt;T&gt;() via reflection — avoids compile-time type reference
    /// that would trigger loading Siemens.Engineering V18 at JIT time.
    /// </summary>
    static object ReflectGetService(DeviceItem item, string typeName)
    {
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
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
        return null;
    }

    static string J(string s)
    {
        if (s == null) return "\"\"";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "") + "\"";
    }

    static string FastGet(object o, string n)
    {
        try
        {
            var p = o.GetType().GetProperty(n);
            if (p != null)
            {
                var v = p.GetValue(o);
                return (v != null) ? v.ToString() : null;
            }
            foreach (var iface in o.GetType().GetInterfaces())
            {
                p = iface.GetProperty(n);
                if (p != null)
                {
                    var v = p.GetValue(o);
                    return (v != null) ? v.ToString() : null;
                }
            }
        }
        catch { }
        return null;
    }
}
