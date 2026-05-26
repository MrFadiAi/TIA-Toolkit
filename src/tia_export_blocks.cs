using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;

/// <summary>
/// TIA Portal Block Exporter
/// Connects to running TIA Portal and exports all PLC blocks and tag tables to XML files.
/// The exported folder can be used as input for extract_plc_full.py (Python offline parser).
///
/// Compile for TIA Portal V18–V19 (single DLL):
///   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
///     /reference:"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll" ^
///     /out:tia_export_blocks.exe tia_export_blocks.cs
///
/// Compile for TIA Portal V21+ (split DLLs under net48/):
///   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
///     /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" ^
///     /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Step7.dll" ^
///     /out:tia_export_blocks.exe tia_export_blocks.cs
///
/// Run (TIA Portal must be open with project loaded):
///   tia_export_blocks.exe --list
///     List ALL devices (PLC + HMI) in the project
///
///   tia_export_blocks.exe [output_folder] [device_filter]
///     Export PLC blocks to XML files
///     output_folder  - target directory (default: Doc_OUTPUT/DATA_Program blocks)
///     device_filter  - substring of PLC device name (use "" to export all PLCs)
/// </summary>
class Program
{
    static int exportedBlocks = 0;
    static int skippedBlocks = 0;
    static int exportedTagTables = 0;
    static int exportedTags = 0;
    static int exportedTypes = 0;
    static List<string> blockList = new List<string>();

    static int Main(string[] args)
    {
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine("  TIA Portal Block Exporter");
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

        // --list mode: show all devices and exit
        if (args.Length > 0 && args[0] == "--list")
        {
            return ListAllDevices(project);
        }

        // Normal export mode
        string outputFolder = Path.GetFullPath((args.Length > 0) ? args[0] : "Doc_OUTPUT/DATA_Program blocks");
        string deviceFilter = (args.Length > 1) ? args[1] : "";

        Console.WriteLine("Device filter: " + (string.IsNullOrEmpty(deviceFilter) ? "(all)" : deviceFilter));
        Console.WriteLine("Output: " + Path.GetFullPath(outputFolder));
        Console.WriteLine();

        // Find ALL PLC software instances across all devices
        var plcSoftwareList = new List<object>();
        foreach (Device device in project.Devices)
        {
            if (!string.IsNullOrEmpty(deviceFilter) && !device.Name.Contains(deviceFilter)) continue;
            Console.WriteLine("Device: " + device.Name);

            foreach (DeviceItem item in device.DeviceItems)
            {
                FindAllPlcSoftware(item, plcSoftwareList);
            }
        }

        if (plcSoftwareList.Count == 0)
        {
            Console.WriteLine("ERROR: No PLC software found. Check device filter.");
            return 1;
        }

        Console.WriteLine("Found {0} PLC software instance(s)", plcSoftwareList.Count);

        // Export blocks from each PLC software
        foreach (var plcSoftware in plcSoftwareList)
        {
            string plcName = (GetProp(plcSoftware, "Name") ?? "PLC").ToString();
            Console.WriteLine();
            Console.WriteLine("--- PLC: {0} ---", plcName);

            var blockGroup = GetProp(plcSoftware, "BlockGroup");
            if (blockGroup != null)
            {
                WalkBlockGroup(blockGroup, outputFolder, "");
            }
            else
            {
                Console.WriteLine("  WARNING: BlockGroup not found, trying PlcSoftware directly");
                WalkBlockGroup(plcSoftware, outputFolder, "");
            }

            // Export tag tables for this PLC
            Console.WriteLine();
            Console.WriteLine("--- Tag tables: {0} ---", plcName);
            var tagTableGroup = GetProp(plcSoftware, "TagTableGroup");
            if (tagTableGroup != null)
            {
                ExportTagTables(tagTableGroup, outputFolder);
            }
            else
            {
                Console.WriteLine("  WARNING: TagTableGroup not found, trying PlcSoftware directly");
                ExportTagTables(plcSoftware, outputFolder);
            }

            // Export PLC data types (UDTs)
            Console.WriteLine();
            Console.WriteLine("--- PLC Data Types: {0} ---", plcName);
            ExportPlcTypes(plcSoftware, outputFolder);
        }

        // Summary
        Console.WriteLine();
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine("  EXPORT COMPLETE");
        Console.WriteLine("=".PadRight(70, '='));
        Console.WriteLine("  Blocks exported:  {0}", exportedBlocks);
        if (skippedBlocks > 0)
            Console.WriteLine("  Blocks skipped:   {0}", skippedBlocks);
        Console.WriteLine("  Tag tables:       {0}", exportedTagTables);
        Console.WriteLine("  PLC tags:         {0}", exportedTags);
        Console.WriteLine("  PLC data types:   {0}", exportedTypes);
        Console.WriteLine("  Output folder:    {0}", Path.GetFullPath(outputFolder));
        Console.WriteLine("=".PadRight(70, '='));

        // Block detail table
        if (blockList.Count > 0)
        {
            Console.WriteLine();
            Console.WriteLine("{0,-36} {1,4} {2,5} {3,6}  {4}", "Block", "Type", "Num", "Lang", "Folder");
            Console.WriteLine("-".PadRight(80, '-'));
            foreach (string line in blockList)
                Console.WriteLine(line);
        }

        return 0;
    }

    static int ListAllDevices(Project project)
    {
        Console.WriteLine("ALL DEVICES IN PROJECT");
        Console.WriteLine("-".PadRight(70, '-'));
        Console.WriteLine();

        int plcCount = 0;
        int hmiCount = 0;

        foreach (Device device in project.Devices)
        {
            Console.WriteLine("Device: " + device.Name);

            foreach (DeviceItem item in device.DeviceItems)
            {
                var info = GetSoftwareInfo(item);
                if (info != null)
                {
                    Console.WriteLine("  -> [{0}] {1}", info.Type, info.Name);
                    if (info.IsPlc) plcCount++;
                    if (info.IsHmi) hmiCount++;
                }
            }
            Console.WriteLine();
        }

        Console.WriteLine("-".PadRight(70, '-'));
        Console.WriteLine("Total: {0} PLC(s), {1} HMI(s)", plcCount, hmiCount);
        Console.WriteLine();
        Console.WriteLine("To export a PLC, run:");
        Console.WriteLine("  tia_export_blocks.exe \"Doc_OUTPUT/DATA_Program blocks\" \"DEVICE_NAME\"");
        Console.WriteLine();
        Console.WriteLine("To export ALL PLCs, run:");
        Console.WriteLine("  tia_export_blocks.exe \"Doc_OUTPUT/DATA_Program blocks\"");
        return 0;
    }

    class SwInfo
    {
        public string Type;
        public string Name;
        public bool IsPlc;
        public bool IsHmi;
    }

    static SwInfo GetSoftwareInfo(DeviceItem item)
    {
        try
        {
            var swc = item.GetService<SoftwareContainer>();
            if (swc != null && swc.Software != null)
            {
                string swType = swc.Software.GetType().Name;
                string swName = (GetProp(swc.Software, "Name") ?? "").ToString();
                bool isPlc = swType.Contains("Plc");
                bool isHmi = swType.Contains("Hmi") || swType.Contains("HMI");

                // Also search sub-items
                if (!isPlc && !isHmi)
                {
                    foreach (DeviceItem sub in item.DeviceItems)
                    {
                        var subInfo = GetSoftwareInfo(sub);
                        if (subInfo != null) return subInfo;
                    }
                    return null;
                }

                return new SwInfo { Type = isPlc ? "PLC" : "HMI", Name = swName, IsPlc = isPlc, IsHmi = isHmi };
            }
        }
        catch { }

        foreach (DeviceItem sub in item.DeviceItems)
        {
            var subInfo = GetSoftwareInfo(sub);
            if (subInfo != null) return subInfo;
        }
        return null;
    }

    static void FindAllPlcSoftware(DeviceItem item, List<object> results)
    {
        try
        {
            var swc = item.GetService<SoftwareContainer>();
            if (swc != null && swc.Software != null)
            {
                string swType = swc.Software.GetType().Name;
                if (swType == "PlcSoftware" || swType.Contains("Plc"))
                {
                    string swName = (GetProp(swc.Software, "Name") ?? "").ToString();
                    Console.WriteLine("  PLC Software found: " + swType + " Name=" + swName);
                    results.Add(swc.Software);
                }
            }
        }
        catch { }
        foreach (DeviceItem sub in item.DeviceItems)
        {
            FindAllPlcSoftware(sub, results);
        }
    }

    static void WalkBlockGroup(object container, string outputBase, string groupPath)
    {
        // Create group folder
        string folderPath = Path.Combine(outputBase, groupPath.Trim('/', '\\'));
        if (!string.IsNullOrEmpty(groupPath) && !Directory.Exists(folderPath))
            Directory.CreateDirectory(folderPath);

        string containerType = container.GetType().Name;

        // Export blocks in this group
        IEnumerable blocks = GetCollection(container, "Blocks", containerType);
        if (blocks != null)
        {
            int blockCount = 0;
            foreach (var block in blocks)
            {
                blockCount++;
                ExportBlock(block, outputBase, groupPath);
            }
            if (blockCount > 0 && !string.IsNullOrEmpty(groupPath))
                Console.WriteLine("    -> {0} blocks in {1}", blockCount, groupPath);
        }

        // Walk sub-groups (user folders)
        IEnumerable groups = GetCollection(container, "Groups", containerType);
        if (groups != null)
        {
            int groupCount = 0;
            foreach (var group in groups)
            {
                groupCount++;
                string gName = (GetProp(group, "Name") ?? "").ToString();
                Console.WriteLine("  Group: " + gName);
                WalkBlockGroup(group, outputBase, groupPath + "/" + gName);
            }
            if (string.IsNullOrEmpty(groupPath))
                Console.WriteLine("  Found {0} user groups at root", groupCount);
        }

        // Walk system block groups (e.g. "Program blocks", "System blocks")
        IEnumerable sysGroups = GetCollection(container, "SystemBlockGroups", containerType);
        if (sysGroups != null)
        {
            int sysCount = 0;
            foreach (var sysGroup in sysGroups)
            {
                sysCount++;
                string sgName = (GetProp(sysGroup, "Name") ?? "").ToString();
                Console.WriteLine("  SystemGroup: " + sgName);
                // FIX: use system group name in path to avoid file collisions
                string sysPath = string.IsNullOrEmpty(groupPath) ? "[System] " + sgName : groupPath + "/[System] " + sgName;
                WalkBlockGroup(sysGroup, outputBase, sysPath);
            }
            if (string.IsNullOrEmpty(groupPath))
                Console.WriteLine("  Found {0} system groups at root", sysCount);
        }
    }

    static void ExportBlock(object block, string outputBase, string groupPath)
    {
        string bName = (GetProp(block, "Name") ?? "").ToString();
        string bType = MapBlockType(block.GetType().Name);
        int bNumber = GetInt(block, "Number");
        string progLang = GetStr(block, "ProgrammingLanguage");

        // Build output path
        string subFolder = groupPath.Trim('/', '\\');
        string targetDir = string.IsNullOrEmpty(subFolder) ? outputBase : Path.Combine(outputBase, subFolder);
        string xmlPath = Path.Combine(targetDir, SanitizeFileName(bName) + ".xml");

        Console.Write("  {0} {1} {2} ({3}) ... ", bType, bNumber, bName, progLang);

        try
        {
            // Ensure directory exists
            if (!Directory.Exists(targetDir))
                Directory.CreateDirectory(targetDir);

            // Delete existing file (V21 Export won't overwrite)
            if (File.Exists(xmlPath))
                File.Delete(xmlPath);

            // Export block to XML - try concrete type first, then interfaces
            var exportMethod = block.GetType().GetMethod("Export", new Type[] { typeof(FileInfo), typeof(ExportOptions) });
            if (exportMethod == null)
            {
                foreach (var iface in block.GetType().GetInterfaces())
                {
                    exportMethod = iface.GetMethod("Export", new Type[] { typeof(FileInfo), typeof(ExportOptions) });
                    if (exportMethod != null) break;
                }
            }

            if (exportMethod != null)
            {
                exportMethod.Invoke(block, new object[] { new FileInfo(xmlPath), ExportOptions.WithDefaults });
                exportedBlocks++;
                Console.WriteLine("OK");

                string folder = string.IsNullOrEmpty(groupPath) ? "/" : groupPath;
                blockList.Add(string.Format("  {0,-34} {1,4} {2,5} {3,6}  {4}", bName, bType, bNumber, progLang, folder));
            }
            else
            {
                Console.WriteLine("SKIP (no Export method on {0})", block.GetType().Name);
                skippedBlocks++;
            }
        }
        catch (Exception ex)
        {
            string msg = ex.InnerException != null ? ex.InnerException.Message : ex.Message;
            Console.WriteLine("ERROR: " + msg);
            skippedBlocks++;
        }
    }

    static void ExportTagTables(object plcSoftware, string outputBase)
    {
        string tagsFolder = Path.Combine(outputBase, "PLC tags");
        if (!Directory.Exists(tagsFolder))
            Directory.CreateDirectory(tagsFolder);

        // Try direct TagTables property on PlcSoftware
        IEnumerable tagTables = GetCollection(plcSoftware, "TagTables", "PlcSoftware");

        if (tagTables != null)
        {
            foreach (var tt in tagTables)
            {
                ExportOneTagTable(tt, tagsFolder);
            }
        }

        // Also try walking TagTableGroups
        IEnumerable groups = GetCollection(plcSoftware, "TagTableGroups", "PlcSoftware");
        if (groups != null)
        {
            foreach (var group in groups)
            {
                IEnumerable grpTagTables = GetCollection(group, "TagTables", "TagTableGroup");
                if (grpTagTables != null)
                {
                    foreach (var tt in grpTagTables)
                    {
                        ExportOneTagTable(tt, tagsFolder);
                    }
                }

                // Recurse into sub-groups
                IEnumerable subGroups = GetCollection(group, "Groups", "TagTableGroup");
                if (subGroups != null)
                {
                    WalkTagGroups(subGroups, tagsFolder);
                }
            }
        }
    }

    static void WalkTagGroups(IEnumerable groups, string tagsFolder)
    {
        foreach (var group in groups)
        {
            IEnumerable grpTagTables = GetCollection(group, "TagTables", "TagTableGroup");
            if (grpTagTables != null)
            {
                foreach (var tt in grpTagTables)
                {
                    ExportOneTagTable(tt, tagsFolder);
                }
            }

            IEnumerable subGroups = GetCollection(group, "Groups", "TagTableGroup");
            if (subGroups != null)
            {
                WalkTagGroups(subGroups, tagsFolder);
            }
        }
    }

    static void ExportOneTagTable(object tagTable, string tagsFolder)
    {
        string ttName = (GetProp(tagTable, "Name") ?? "").ToString();
        string xmlPath = Path.Combine(tagsFolder, SanitizeFileName(ttName) + ".xml");

        Console.Write("  Tag table: {0} ... ", ttName);

        try
        {
            // Delete existing file (V21 Export won't overwrite)
            if (File.Exists(xmlPath))
                File.Delete(xmlPath);

            var exportMethod = tagTable.GetType().GetMethod("Export", new Type[] { typeof(FileInfo), typeof(ExportOptions) });
            if (exportMethod != null)
            {
                exportMethod.Invoke(tagTable, new object[] { new FileInfo(xmlPath), ExportOptions.WithDefaults });
                exportedTagTables++;

                // Count tags in this table
                var tagsProp = tagTable.GetType().GetProperty("Tags");
                IEnumerable tags = (tagsProp != null) ? tagsProp.GetValue(tagTable) as IEnumerable : null;
                int tagCount = 0;
                if (tags != null)
                {
                    foreach (var t in tags) tagCount++;
                }
                exportedTags += tagCount;
                Console.WriteLine("OK ({0} tags)", tagCount);
            }
            else
            {
                Console.WriteLine("SKIP (no Export method)");
            }
        }
        catch (Exception ex)
        {
            string msg = ex.InnerException != null ? ex.InnerException.Message : ex.Message;
            Console.WriteLine("ERROR: " + msg);
        }
    }

    static void ExportPlcTypes(object plcSoftware, string outputBase)
    {
        string typesFolder = Path.Combine(outputBase, "PLC types");
        if (!Directory.Exists(typesFolder))
            Directory.CreateDirectory(typesFolder);

        // Try TypeGroup.Types
        object typeGroup = GetProp(plcSoftware, "TypeGroup");
        IEnumerable types = null;

        if (typeGroup != null)
        {
            types = GetCollection(typeGroup, "Types", "PlcTypeGroup");
        }

        if (types == null)
        {
            // Try directly on PlcSoftware
            types = GetCollection(plcSoftware, "Types", "PlcSoftware");
        }

        if (types == null)
        {
            Console.WriteLine("  No PLC data types found (TypeGroup not available)");
            return;
        }

        int count = 0;
        foreach (var plcType in types)
        {
            string tName = (GetProp(plcType, "Name") ?? "").ToString();
            string xmlPath = Path.Combine(typesFolder, SanitizeFileName(tName) + ".xml");

            Console.Write("  {0} ... ", tName);

            try
            {
                if (File.Exists(xmlPath))
                    File.Delete(xmlPath);

                var exportMethod = plcType.GetType().GetMethod("Export", new Type[] { typeof(FileInfo), typeof(ExportOptions) });
                if (exportMethod == null)
                {
                    foreach (var iface in plcType.GetType().GetInterfaces())
                    {
                        exportMethod = iface.GetMethod("Export", new Type[] { typeof(FileInfo), typeof(ExportOptions) });
                        if (exportMethod != null) break;
                    }
                }

                if (exportMethod != null)
                {
                    exportMethod.Invoke(plcType, new object[] { new FileInfo(xmlPath), ExportOptions.WithDefaults });
                    exportedTypes++;
                    count++;
                    Console.WriteLine("OK");
                }
                else
                {
                    Console.WriteLine("SKIP (no Export method on {0})", plcType.GetType().Name);
                }
            }
            catch (Exception ex)
            {
                string msg = ex.InnerException != null ? ex.InnerException.Message : ex.Message;
                Console.WriteLine("ERROR: " + msg);
            }
        }

        if (count > 0)
            Console.WriteLine("  Exported {0} PLC data types", count);
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

    static string SanitizeFileName(string name)
    {
        foreach (char c in Path.GetInvalidFileNameChars())
            name = name.Replace(c, '_');
        return name;
    }

    static object GetProp(object o, string n)
    {
        try
        {
            var p = o.GetType().GetProperty(n);
            if (p != null) return p.GetValue(o);
            // Check explicit interface implementations
            foreach (var iface in o.GetType().GetInterfaces())
            {
                p = iface.GetProperty(n);
                if (p != null) return p.GetValue(o);
            }
        }
        catch { }
        return null;
    }

    static int GetInt(object o, string n) { try { return Convert.ToInt32(GetProp(o, n)); } catch { return 0; } }
    static string GetStr(object o, string n) { try { var v = GetProp(o, n); return (v != null) ? v.ToString() : ""; } catch { return ""; } }

    /// <summary>
    /// Get a collection property (Blocks, Groups, etc.) with interface fallback.
    /// Logs a warning if the property is not found.
    /// </summary>
    static IEnumerable GetCollection(object o, string propName, string context)
    {
        try
        {
            var p = o.GetType().GetProperty(propName);
            if (p != null) return p.GetValue(o) as IEnumerable;
            // Check interfaces
            foreach (var iface in o.GetType().GetInterfaces())
            {
                p = iface.GetProperty(propName);
                if (p != null) return p.GetValue(o) as IEnumerable;
            }
        }
        catch { }
        Console.WriteLine("  WARNING: {0} not found on {1}", propName, context);
        return null;
    }
}
