using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;

/// <summary>
/// TIA Portal PLC Block Extractor
/// Connects to running TIA Portal and extracts all PLC block data with interfaces, code, and tag references.
///
/// Compile for TIA Portal V18–V19 (single DLL):
///   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
///     /reference:"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll" ^
///     /out:tia_extract_plc.exe tia_extract_plc.cs
///
/// Compile for TIA Portal V21+ (split DLLs under net48/):
///   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
///     /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" ^
///     /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Step7.dll" ^
///     /out:tia_extract_plc.exe tia_extract_plc.cs
///
/// Run (TIA Portal must be open with project loaded):
///   tia_extract_plc.exe [output_path] [device_filter]
/// </summary>
class Program
{
    static int Main(string[] args)
    {
        string outputPath = (args.Length > 0) ? args[0] : "Doc_OUTPUT/plc_elements.json";
        string deviceFilter = (args.Length > 1) ? args[1] : "PLC";

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
        Console.WriteLine("Filter: " + deviceFilter);

        var json = new StringBuilder();
        json.AppendLine("{");
        json.AppendLine("  \"extraction_info\": {");
        json.AppendLine("    \"tool\": \"tia_extract_plc.cs\",");
        json.AppendLine("    \"project\": " + J(project.Name) + ",");
        json.AppendLine("    \"device_filter\": " + J(deviceFilter) + ",");
        json.AppendLine("    \"timestamp\": " + J(DateTime.Now.ToString("o")));
        json.AppendLine("  },");
        json.AppendLine("  \"blocks\": [");

        bool firstBlock = true;
        int totalElements = 0;
        int totalCalls = 0;
        int totalTagRefs = 0;
        var allTagRefs = new HashSet<string>();
        var allCalls = new Dictionary<string, List<string>>();

        foreach (Device device in project.Devices)
        {
            if (!device.Name.Contains(deviceFilter)) continue;
            Console.WriteLine("Device: " + device.Name);

            foreach (DeviceItem item in device.DeviceItems)
            {
                WalkPlc(item, json, ref firstBlock, ref totalElements, ref totalCalls, ref totalTagRefs, allTagRefs, allCalls);
            }
        }

        json.AppendLine("\n  ],");

        // Call tree
        json.AppendLine("  \"call_tree\": {");
        bool firstEntry = true;
        foreach (var kv in allCalls)
        {
            if (!firstEntry) json.AppendLine(",");
            firstEntry = false;
            json.AppendLine("    " + J(kv.Key) + ": [" + string.Join(", ", kv.Value.Select(v => J(v))) + "]");
        }
        json.AppendLine("  },");

        json.AppendLine("  \"summary\": {");
        json.AppendLine("    \"total_blocks\": " + totalElements + ",");
        json.AppendLine("    \"total_calls\": " + totalCalls + ",");
        json.AppendLine("    \"total_tag_refs\": " + totalTagRefs + ",");
        json.AppendLine("    \"unique_tag_refs\": " + allTagRefs.Count);
        json.AppendLine("  }");
        json.AppendLine("}");

        string dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(outputPath, json.ToString(), Encoding.UTF8);

        Console.WriteLine("\nDone! " + totalElements + " blocks, " + totalCalls + " calls, " + totalTagRefs + " tag refs -> " + outputPath);
        return 0;
    }

    static void WalkPlc(DeviceItem item, StringBuilder json, ref bool firstBlock,
        ref int totalElements, ref int totalCalls, ref int totalTagRefs,
        HashSet<string> allTagRefs, Dictionary<string, List<string>> allCalls)
    {
        try
        {
            var swc = item.GetService<SoftwareContainer>();
            if (swc != null && swc.Software != null)
            {
                string swType = swc.Software.GetType().Name;
                if (swType == "PlcSoftware" || swType.Contains("Plc"))
                {
                    Console.WriteLine("  PLC Software found: " + swType);
                    WalkBlockGroup(swc.Software, json, ref firstBlock, ref totalElements, ref totalCalls, ref totalTagRefs, allTagRefs, allCalls, "");
                }
            }
        }
        catch { }
        foreach (DeviceItem sub in item.DeviceItems) WalkPlc(sub, json, ref firstBlock, ref totalElements, ref totalCalls, ref totalTagRefs, allTagRefs, allCalls);
    }

    static void WalkBlockGroup(object container, StringBuilder json, ref bool firstBlock,
        ref int totalElements, ref int totalCalls, ref int totalTagRefs,
        HashSet<string> allTagRefs, Dictionary<string, List<string>> allCalls, string groupPath)
    {
        // Walk blocks in this group
        var blocksProp = container.GetType().GetProperty("Blocks");
        IEnumerable blocks = (blocksProp != null) ? blocksProp.GetValue(container) as IEnumerable : null;
        if (blocks != null)
        {
            foreach (var block in blocks)
            {
                ProcessBlock(block, json, ref firstBlock, ref totalElements, ref totalCalls, ref totalTagRefs, allTagRefs, allCalls, groupPath);
            }
        }

        // Walk sub-groups
        var groupsProp = container.GetType().GetProperty("Groups");
        IEnumerable groups = (groupsProp != null) ? groupsProp.GetValue(container) as IEnumerable : null;
        if (groups != null)
        {
            foreach (var group in groups)
            {
                string gName = (GetProp(group, "Name") ?? "").ToString();
                Console.WriteLine("  Group: " + gName);
                WalkBlockGroup(group, json, ref firstBlock, ref totalElements, ref totalCalls, ref totalTagRefs, allTagRefs, allCalls, groupPath + "/" + gName);
            }
        }
    }

    static void ProcessBlock(object block, StringBuilder json, ref bool firstBlock,
        ref int totalElements, ref int totalCalls, ref int totalTagRefs,
        HashSet<string> allTagRefs, Dictionary<string, List<string>> allCalls, string groupPath)
    {
        string bName = (GetProp(block, "Name") ?? "").ToString();
        string bType = block.GetType().Name; // PlcBlock, FB, FC, OB, etc.
        int bNumber = GetInt(block, "Number");
        string progLang = GetStr(block, "ProgrammingLanguage");
        string comment = CleanText(GetMLComment(block, "Comment"));

        // Map type
        string typeStr = MapBlockType(bType);

        Console.WriteLine("  Block: " + typeStr + " " + bNumber + " " + bName + " (" + progLang + ")");

        if (!firstBlock) json.AppendLine(",");
        firstBlock = false;

        json.AppendLine("    {");
        json.AppendLine("      \"block_name\": " + J(bName) + ",");
        json.AppendLine("      \"block_number\": " + bNumber + ",");
        json.AppendLine("      \"block_type\": " + J(typeStr) + ",");
        json.AppendLine("      \"programming_language\": " + J(progLang) + ",");
        json.AppendLine("      \"comment\": " + J(comment) + ",");
        json.AppendLine("      \"folder\": " + J(groupPath) + ",");

        // Interface
        json.AppendLine("      \"interface\": " + ExtractInterface(block) + ",");

        // Export code to temp file and read it
        string code = "";
        var tagRefs = new List<string>();
        var calls = new List<string>();

        try
        {
            string tempFile = Path.GetTempFileName();
            try
            {
                var exportMethod = block.GetType().GetMethod("Export", new Type[] { typeof(FileInfo), typeof(ExportOptions) });
                if (exportMethod != null)
                {
                    exportMethod.Invoke(block, new object[] { new FileInfo(tempFile), ExportOptions.WithDefaults });
                    code = File.ReadAllText(tempFile);

                    // Extract tag references from code
                    foreach (Match m in Regex.Matches(code, @"""([A-Za-z_][A-Za-z0-9_ ]*)"""))
                    {
                        tagRefs.Add(m.Groups[1].Value);
                        allTagRefs.Add(m.Groups[1].Value);
                    }

                    // Extract calls
                    foreach (Match m in Regex.Matches(code, @"""([A-Za-z_][A-Za-z0-9_ ]*)""\s*\("))
                    {
                        calls.Add(m.Groups[1].Value);
                    }
                }
            }
            finally { if (File.Exists(tempFile)) File.Delete(tempFile); }
        }
        catch (Exception ex) { Console.WriteLine("    Code export warning: " + ex.Message); }

        // Build call tree entry
        if (calls.Count > 0)
        {
            allCalls[bName] = calls;
            totalCalls += calls.Count;
        }
        totalTagRefs += tagRefs.Count;

        json.AppendLine("      \"code\": " + J(code) + ",");
        json.AppendLine("      \"tag_references\": [" + string.Join(", ", tagRefs.Select(t => J(t))) + "],");
        json.AppendLine("      \"calls\": [" + string.Join(", ", calls.Select(c => J(c))) + "]");
        json.Append("    }");

        totalElements++;
    }

    static string ExtractInterface(object block)
    {
        var sb = new StringBuilder();
        sb.Append("{");

        try
        {
            var ifaceProp = block.GetType().GetProperty("Interface");
            if (ifaceProp == null) { sb.Append("}"); return sb.ToString(); }
            object iface = ifaceProp.GetValue(block);
            if (iface == null) { sb.Append("}"); return sb.ToString(); }

            // Interface sections
            string[] sections = { "Inputs", "Outputs", "InOuts", "Statics", "Temps", "Constants" };
            string[] jsonKeys = { "inputs", "outputs", "inouts", "statics", "temps", "constants" };
            bool firstSection = true;

            for (int i = 0; i < sections.Length; i++)
            {
                var secProp = iface.GetType().GetProperty(sections[i]);
                IEnumerable members = (secProp != null) ? secProp.GetValue(iface) as IEnumerable : null;
                if (members == null) continue;

                if (!firstSection) sb.Append(",");
                firstSection = false;
                sb.Append("\n        \"" + jsonKeys[i] + "\": [");

                bool firstMember = true;
                foreach (var member in members)
                {
                    string mName = (GetProp(member, "Name") ?? "").ToString();
                    string mType = GetStr(member, "DataTypeName");
                    if (string.IsNullOrEmpty(mType)) mType = GetStr(member, "DataType");
                    string mComment = CleanText(GetMLComment(member, "Comment"));
                    string mStartVal = GetStr(member, "StartValue");

                    if (!firstMember) sb.Append(",");
                    firstMember = false;
                    sb.Append("\n          {\"name\": " + J(mName) + ", \"data_type\": " + J(mType) +
                              ", \"comment\": " + J(mComment) +
                              (string.IsNullOrEmpty(mStartVal) ? "" : ", \"start_value\": " + J(mStartVal)) +
                              "}");
                }
                sb.Append("]");
            }
        }
        catch { }

        sb.Append("\n      }");
        return sb.ToString();
    }

    static string MapBlockType(string t)
    {
        if (t.Contains("FB") || t == "PlcBlockFB") return "FB";
        if (t.Contains("FC") || t == "PlcBlockFC") return "FC";
        if (t.Contains("OB") || t == "PlcBlockOB") return "OB";
        if (t.Contains("GlobalDB")) return "DB";
        if (t.Contains("InstanceDB") || t.Contains("IDB")) return "IDB";
        return t;
    }

    static object GetProp(object o, string n) { try { var p = o.GetType().GetProperty(n); return (p != null) ? p.GetValue(o) : null; } catch { return null; } }
    static int GetInt(object o, string n) { try { var p = o.GetType().GetProperty(n); return (p != null) ? Convert.ToInt32(p.GetValue(o)) : 0; } catch { return 0; } }
    static string GetStr(object o, string n) { try { var p = o.GetType().GetProperty(n); return (p != null && p.GetValue(o) != null) ? p.GetValue(o).ToString() : ""; } catch { return ""; } }

    static string GetMLComment(object o, string propName)
    {
        try
        {
            var mlProp = o.GetType().GetProperty(propName);
            object ml = (mlProp != null) ? mlProp.GetValue(o) : null;
            if (ml == null) return "";
            var itemsProp = ml.GetType().GetProperty("Items");
            IEnumerable items = (itemsProp != null) ? itemsProp.GetValue(ml) as IEnumerable : null;
            if (items == null) return "";
            foreach (var i in items)
            {
                var culture = GetStr(i, "Culture");
                var text = GetStr(i, "Text");
                if (culture == "en-US" && !string.IsNullOrEmpty(text)) return text;
            }
            foreach (var i in items)
            {
                var text = GetStr(i, "Text");
                if (!string.IsNullOrEmpty(text)) return text;
            }
        }
        catch { }
        return "";
    }

    static string CleanText(string s) { return string.IsNullOrEmpty(s) ? "" : s.Replace("\n", " ").Replace("\r", "").Replace("\"", "'").Trim(); }
    static string J(string s) { return "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", "") + "\""; }
}
