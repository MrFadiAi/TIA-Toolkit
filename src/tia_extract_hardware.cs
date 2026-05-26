using System;
using System.Linq;
using System.Collections;
using System.IO;
using System.Text;
using Siemens.Engineering;
using Siemens.Engineering.HW;

/// <summary>
/// TIA Portal Hardware Catalog Extractor - IP Diagnostic
/// Focuses on finding where IP addresses are stored for PLC/HMI/IO devices.
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

        // ── IP DIAGNOSTIC: Walk ALL items and dump full network info ──
        Console.WriteLine("[IP DIAGNOSTIC - checking ALL network interfaces]");
        foreach (Device device in project.Devices)
        {
            Console.WriteLine("Device: " + device.Name);
            foreach (DeviceItem item in device.DeviceItems)
            {
                DumpNetworkInfo(item, "  ");
            }
        }
        Console.WriteLine("[END IP DIAGNOSTIC]");
        Console.WriteLine();

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

    static void DumpNetworkInfo(DeviceItem item, string prefix)
    {
        // Check if this item has NetworkInterface
        object niObj = null;
        try
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    var t = asm.GetType("Siemens.Engineering.HW.Features.NetworkInterface");
                    if (t != null)
                    {
                        var method = item.GetType().GetMethod("GetService");
                        if (method != null)
                        {
                            var generic = method.MakeGenericMethod(t);
                            niObj = generic.Invoke(item, null);
                        }
                        break;
                    }
                }
                catch { }
            }
        }
        catch { }

        if (niObj != null)
        {
            Console.WriteLine("{0}[NI] {1} has NetworkInterface", prefix, item.Name);

            var nodesProp = niObj.GetType().GetProperty("Nodes");
            if (nodesProp != null)
            {
                var nodes = nodesProp.GetValue(niObj) as IEnumerable;
                int nodeIdx = 0;
                foreach (var node in nodes)
                {
                    Console.WriteLine("{0}  Node[{1}]:", prefix, nodeIdx);

                    // Dump ALL properties including from interfaces
                    foreach (var p in node.GetType().GetProperties())
                    {
                        try
                        {
                            var val = p.GetValue(node);
                            string vs = (val != null) ? val.ToString() : "(null)";
                            if (vs.Length > 100) vs = vs.Substring(0, 100) + "...";
                            Console.WriteLine("{0}    {1} ({2}): {3}", prefix, p.Name, p.PropertyType.Name, vs);
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("{0}    {1}: ERROR: {2}", prefix, p.Name, ex.Message);
                        }
                    }

                    // Check interface properties too
                    foreach (var iface in node.GetType().GetInterfaces())
                    {
                        foreach (var p in iface.GetProperties())
                        {
                            try
                            {
                                var val = p.GetValue(node);
                                string vs = (val != null) ? val.ToString() : "(null)";
                                if (vs.Length > 100) vs = vs.Substring(0, 100) + "...";
                                Console.WriteLine("{0}    [I] {1} ({2}): {3}", prefix, p.Name, p.PropertyType.Name, vs);
                            }
                            catch { }
                        }
                    }

                    // If ConnectedSubnet is not null, dump it
                    try
                    {
                        var csProp = node.GetType().GetProperty("ConnectedSubnet");
                        if (csProp != null)
                        {
                            var cs = csProp.GetValue(node);
                            if (cs != null)
                            {
                                Console.WriteLine("{0}    ConnectedSubnet properties:", prefix);
                                foreach (var p in cs.GetType().GetProperties())
                                {
                                    try
                                    {
                                        var val = p.GetValue(cs);
                                        string vs = (val != null) ? val.ToString() : "(null)";
                                        if (vs.Length > 100) vs = vs.Substring(0, 100) + "...";
                                        Console.WriteLine("{0}      {1} ({2}): {3}", prefix, p.Name, p.PropertyType.Name, vs);
                                    }
                                    catch { }
                                }
                            }
                        }
                    }
                    catch { }

                    nodeIdx++;
                }
            }

            // Also dump NI object's own properties
            Console.WriteLine("{0}  NetworkInterface properties:", prefix);
            foreach (var p in niObj.GetType().GetProperties())
            {
                try
                {
                    var val = p.GetValue(niObj);
                    string vs = (val != null) ? val.ToString() : "(null)";
                    if (vs.Length > 80) vs = vs.Substring(0, 80) + "...";
                    Console.WriteLine("{0}    {1} ({2}): {3}", prefix, p.Name, p.PropertyType.Name, vs);
                }
                catch { }
            }
        }

        // Check Addresses collection
        try
        {
            var addrProp = item.GetType().GetProperty("Addresses");
            if (addrProp != null)
            {
                var addrs = addrProp.GetValue(item) as IEnumerable;
                if (addrs != null)
                {
                    int addrCount = 0;
                    foreach (var addr in addrs)
                    {
                        if (addrCount == 0)
                            Console.WriteLine("{0}[ADDR] {1} has addresses:", prefix, item.Name);
                        string addrStr = "";
                        foreach (var p in addr.GetType().GetProperties())
                        {
                            try
                            {
                                var v = p.GetValue(addr);
                                addrStr += p.Name + "=" + ((v != null) ? v.ToString() : "(null)") + " ";
                            }
                            catch { }
                        }
                        Console.WriteLine("{0}  {1}", prefix, addrStr.Trim());
                        addrCount++;
                    }
                }
            }
        }
        catch { }

        // Recurse
        foreach (DeviceItem sub in item.DeviceItems)
        {
            DumpNetworkInfo(sub, prefix + "  ");
        }
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
        string networkType = "";
        int positionNumber = 0;

        try { typeId = item.TypeIdentifier ?? ""; } catch { }

        try
        {
            var v = item.GetAttribute("OrderNumber");
            if (v != null) orderNum = v.ToString();
        }
        catch { }

        if (string.IsNullOrEmpty(orderNum) && typeId.StartsWith("OrderNumber:"))
        {
            int slash = typeId.IndexOf('/');
            orderNum = (slash > 0) ? typeId.Substring(12, slash - 12) : typeId.Substring(12);
        }

        try
        {
            var v = item.GetAttribute("FirmwareVersion");
            if (v != null) firmware = v.ToString();
        }
        catch { }

        try { positionNumber = item.PositionNumber; } catch { }

        // Network interface via runtime reflection
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
                            profinetName = TryGet(node, new[] { "Name" });
                            networkType = TryGet(node, new[] { "NodeType" });

                            // Try to get IP from ALL possible sources
                            ipAddress = TryGet(node, new[] { "IpV4Address", "IpAddress", "IPAddress" });
                            subnet = TryGet(node, new[] { "IpV4SubnetMask", "SubnetMask" });

                            // Try ConnectedSubnet
                            if (string.IsNullOrEmpty(ipAddress))
                            {
                                try
                                {
                                    var csProp = node.GetType().GetProperty("ConnectedSubnet");
                                    if (csProp != null)
                                    {
                                        var cs = csProp.GetValue(node);
                                        if (cs != null)
                                        {
                                            ipAddress = TryGet(cs, new[] { "IpV4SubnetAddress", "Address", "IpAddress" });
                                            subnet = TryGet(cs, new[] { "IpV4SubnetMask", "SubnetMask", "Mask" });
                                        }
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
            if (!string.IsNullOrEmpty(networkType))
                json.AppendLine(indent + "  \"network_type\": " + J(networkType) + ",");
            if (positionNumber > 0)
                json.AppendLine(indent + "  \"position\": " + positionNumber + ",");

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

        foreach (DeviceItem sub in item.DeviceItems)
        {
            WalkDeviceItem(sub, ref firstModule, depth + 1);
        }
    }

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
                foreach (var iface in o.GetType().GetInterfaces())
                {
                    p = iface.GetProperty(n);
                    if (p != null)
                    {
                        var v = p.GetValue(o);
                        if (v != null) return v.ToString();
                    }
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
