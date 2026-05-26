using System;
using System.Linq;
using System.Collections;
using System.IO;
using System.Text;
using Siemens.Engineering;
using Siemens.Engineering.HW;

/// <summary>
/// TIA Portal Hardware Catalog Extractor (Diagnostic)
/// Dumps ALL DeviceItem properties/attributes to discover correct API names.
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

            // Dump device properties for first device only
            if (deviceCount == 0)
            {
                Console.WriteLine("  [DEBUG Device properties]");
                DumpProperties(device, "  ");
            }

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
        string comment = "";
        int slot = -1;

        // Type identifier
        try { typeId = item.TypeIdentifier ?? ""; } catch { }

        // Try all possible attribute/property names
        string[] orderProps = { "OrderNumber", "ArticleNumber", "CatalogNumber", "HardwareIdentifier" };
        string[] fwProps = { "FirmwareVersion", "Firmware", "Version", "ModuleVersion" };
        string[] ipProps = { "IpAddress", "IpV4Address", "IPAddress" };
        string[] subnetProps = { "SubnetMask", "IpV4SubnetMask" };
        string[] pnProps = { "ProfinetName", "DeviceName", "ProfiNetName" };
        string[] commentProps = { "Comment" };

        orderNum = TryGetAny(item, orderProps);
        firmware = TryGetAny(item, fwProps);
        ipAddress = TryGetAny(item, ipProps);
        subnet = TryGetAny(item, subnetProps);
        profinetName = TryGetAny(item, pnProps);
        comment = TryGetAny(item, commentProps);

        // Try GetAttribute approach
        if (string.IsNullOrEmpty(orderNum))
        {
            try { var v = item.GetAttribute("OrderNumber"); if (v != null) orderNum = v.ToString(); } catch { }
        }

        // Try NetworkInterface service via runtime reflection for IP
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
                                ipAddress = TryGetAny(node, new[] { "IpV4Address", "IpAddress", "IPAddress" });
                                subnet = TryGetAny(node, new[] { "IpV4SubnetMask", "SubnetMask" });
                                if (string.IsNullOrEmpty(profinetName))
                                    profinetName = TryGetAny(node, new[] { "Name" });
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

        // Debug dump for first module of first few devices
        if (moduleCount < 5)
        {
            Console.WriteLine("  [DEBUG DeviceItem: {0}]", itemName);
            Console.WriteLine("    TypeIdentifier: {0}", typeId);
            DumpProperties(item, "    ");
            Console.WriteLine("    [Attributes]");
            DumpAttributes(item, "    ");
            Console.WriteLine("    [Services]");
            DumpServices(item, "    ");
            Console.WriteLine();
        }

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
            if (!string.IsNullOrEmpty(comment))
                json.AppendLine(indent + "  \"comment\": " + J(comment) + ",");
            if (slot >= 0)
                json.AppendLine(indent + "  \"slot\": " + slot + ",");

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

    // ── Diagnostic helpers ──────────────────────────────────────────────

    static void DumpProperties(object o, string prefix)
    {
        try
        {
            foreach (var p in o.GetType().GetProperties())
            {
                try
                {
                    var val = p.GetValue(o);
                    string valStr = (val != null) ? val.ToString() : "(null)";
                    if (valStr.Length > 120) valStr = valStr.Substring(0, 120) + "...";
                    Console.WriteLine("{0}{1} ({2}): {3}", prefix, p.Name, p.PropertyType.Name, valStr);
                }
                catch (Exception ex)
                {
                    Console.WriteLine("{0}{1} ({2}): ERROR: {3}", prefix, p.Name, p.PropertyType.Name, ex.Message);
                }
            }
        }
        catch { }
    }

    static void DumpAttributes(DeviceItem item, string prefix)
    {
        try
        {
            // Try common attribute names
            string[] attrs = { "OrderNumber", "FirmwareVersion", "Firmware", "Version",
                "IpAddress", "SubnetMask", "PositionInParent", "Comment",
                "ArticleNumber", "CatalogNumber", "DeviceName", "ProfinetName" };
            foreach (var attr in attrs)
            {
                try
                {
                    var val = item.GetAttribute(attr);
                    if (val != null)
                        Console.WriteLine("{0}{1} = {2}", prefix, attr, val);
                }
                catch { }
            }
        }
        catch { }
    }

    static void DumpServices(DeviceItem item, string prefix)
    {
        try
        {
            // List what GetService overloads return for known service types
            string[] serviceNames = {
                "Siemens.Engineering.HW.Features.NetworkInterface",
                "Siemens.Engineering.HW.Features.DeviceFirmware",
                "Siemens.Engineering.SW.SoftwareContainer",
            };
            foreach (var sn in serviceNames)
            {
                try
                {
                    var svc = ReflectGetService(item, sn);
                    string shortName = sn.Substring(sn.LastIndexOf('.') + 1);
                    Console.WriteLine("{0}{1}: {2}", prefix, shortName,
                        svc != null ? "found" : "null");
                }
                catch (Exception ex)
                {
                    string shortName = sn.Substring(sn.LastIndexOf('.') + 1);
                    Console.WriteLine("{0}{1}: ERROR: {2}", prefix, shortName, ex.Message);
                }
            }
        }
        catch { }
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
                    var method = item.GetType().GetMethod("GetService", new Type[] { });
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

    static string TryGetAny(object o, string[] names)
    {
        foreach (var n in names)
        {
            string val = FastGet(o, n);
            if (!string.IsNullOrEmpty(val)) return val;
        }
        return "";
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
