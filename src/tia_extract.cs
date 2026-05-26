using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using Siemens.Engineering;
using Siemens.Engineering.HmiUnified;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;

/// <summary>
/// TIA Portal HMI Element Extractor
/// Connects to running TIA Portal and extracts all element data with tag bindings,
/// events (EventType + Script), navigation map, and ScreenWindow content.
///
/// Compile for V21+:
///   csc /reference:Base.dll /reference:WinCCUnified.dll /reference:Step7.dll /out:tia_extract.exe tia_extract.cs
///
/// Run:
///   tia_extract.exe [output_path] [device_filter]
/// </summary>
class Program
{
    // ── Shared state ────────────────────────────────────────────────────
    static Dictionary<string, TagInfo> tagTable = new Dictionary<string, TagInfo>();
    static Dictionary<string, List<string>> navMap = new Dictionary<string, List<string>>();
    static int totalEvents = 0;
    static int totalNavigations = 0;

    // ── Reflection cache: TypeName -> PropName -> PropertyInfo ──────────
    static Dictionary<string, Dictionary<string, PropertyInfo>> propCache =
        new Dictionary<string, Dictionary<string, PropertyInfo>>();

    static PropertyInfo CachedProp(object obj, string name)
    {
        Type t = obj.GetType();
        string key = t.FullName ?? t.Name;
        Dictionary<string, PropertyInfo> dict;
        if (!propCache.TryGetValue(key, out dict))
        {
            dict = new Dictionary<string, PropertyInfo>();
            propCache[key] = dict;
        }
        PropertyInfo pi;
        if (!dict.TryGetValue(name, out pi))
        {
            pi = t.GetProperty(name);
            dict[name] = pi;
        }
        return pi;
    }

    static object FastGet(object obj, string name)
    {
        var pi = CachedProp(obj, name);
        return (pi != null) ? pi.GetValue(obj) : null;
    }

    static int FastGetInt(object obj, string name)
    {
        var pi = CachedProp(obj, name);
        try { return (pi != null) ? Convert.ToInt32(pi.GetValue(obj)) : 0; }
        catch { return 0; }
    }

    static string FastGetStr(object obj, string name)
    {
        var pi = CachedProp(obj, name);
        try { var v = (pi != null) ? pi.GetValue(obj) : null; return (v != null) ? v.ToString() : ""; }
        catch { return ""; }
    }

    // ── Static compiled regex ───────────────────────────────────────────
    static Regex reNav = new Regex(@"ChangeScreen\(""\s*([^""]+?)\s*""", RegexOptions.Compiled);
    static Regex[] reTags = new Regex[]
    {
        new Regex(@"GetTagValue\(""\s*([^""]+)", RegexOptions.Compiled),
        new Regex(@"SetTagValue\(""\s*([^""]+)", RegexOptions.Compiled),
        new Regex(@"SetBitInTag\(""\s*([^""]+)", RegexOptions.Compiled),
        new Regex(@"ResetBitInTag\(""\s*([^""]+)", RegexOptions.Compiled),
        new Regex(@"InvertBitInTag\(""\s*([^""]+)", RegexOptions.Compiled),
        new Regex(@"TagValue\(""\s*([^""]+)", RegexOptions.Compiled),
    };

    // ── Entry point ─────────────────────────────────────────────────────

    static int Main(string[] args)
    {
        string outputPath = (args.Length > 0) ? args[0] : "hmi_online_data.json";
        string deviceFilter = (args.Length > 1) ? args[1] : "";

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

        var json = new StringBuilder(1024 * 1024); // pre-allocate 1MB
        json.AppendLine("{");
        json.AppendLine("  \"extraction_info\": {");
        json.AppendLine("    \"tool\": \"tia_extract.cs\",");
        json.AppendLine("    \"project\": " + J(project.Name) + ",");
        json.AppendLine("    \"device_filter\": " + J(deviceFilter) + ",");
        json.AppendLine("    \"timestamp\": " + J(DateTime.Now.ToString("o")));
        json.AppendLine("  },");
        json.AppendLine("  \"screens\": [");

        bool firstScreen = true;
        int totalElements = 0;
        int totalBindings = 0;
        var sw = System.Diagnostics.Stopwatch.StartNew();

        foreach (Device device in project.Devices)
        {
            if (!string.IsNullOrEmpty(deviceFilter) && !device.Name.Contains(deviceFilter)) continue;
            Console.WriteLine("Device: " + device.Name);

            foreach (DeviceItem item in device.DeviceItems)
            {
                Walk(item, json, ref firstScreen, ref totalElements, ref totalBindings);
            }
        }

        sw.Stop();

        json.AppendLine("\n  ],");

        // Navigation map
        json.AppendLine("  \"navigation_map\": {");
        bool firstNav = true;
        foreach (var kv in navMap)
        {
            if (!firstNav) json.AppendLine(",");
            firstNav = false;
            json.Append("    " + J(kv.Key) + ": [" + string.Join(", ", kv.Value.Select(v => J(v))) + "]");
        }
        if (!firstNav) json.AppendLine();
        json.AppendLine("  },");

        json.AppendLine("  \"summary\": {");
        json.AppendLine("    \"total_screens\": " + (firstScreen ? "0" : "1") + ",");
        json.AppendLine("    \"total_elements\": " + totalElements + ",");
        json.AppendLine("    \"total_tag_bindings\": " + totalBindings + ",");
        json.AppendLine("    \"total_events\": " + totalEvents + ",");
        json.AppendLine("    \"total_navigations\": " + totalNavigations + ",");
        json.AppendLine("    \"tags_in_table\": " + tagTable.Count + ",");
        json.AppendLine("    \"extraction_seconds\": " + sw.Elapsed.TotalSeconds.ToString("F1"));
        json.AppendLine("  }");
        json.AppendLine("}");

        string dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(outputPath, json.ToString(), Encoding.UTF8);

        Console.WriteLine("\nDone! {0} elements, {1} bindings, {2} events in {3:F1}s -> {4}",
            totalElements, totalBindings, totalEvents, sw.Elapsed.TotalSeconds, outputPath);
        return 0;
    }

    // ── Walk device tree ────────────────────────────────────────────────

    static void Walk(DeviceItem item, StringBuilder json, ref bool firstScreen, ref int totalElements, ref int totalBindings)
    {
        try
        {
            var swc = item.GetService<SoftwareContainer>();
            if (swc != null && swc.Software != null && swc.Software.GetType().Name == "HmiSoftware")
            {
                LoadTagTable(swc.Software);

                // Top-level Screens
                var screens = FastGet(swc.Software, "Screens") as IEnumerable;
                if (screens != null)
                    foreach (var screen in screens)
                        ProcessScreen(screen, json, ref firstScreen, ref totalElements, ref totalBindings);

                // Screen Groups (popup/sub screens)
                var groups = FastGet(swc.Software, "ScreenGroups") as IEnumerable;
                if (groups != null)
                {
                    foreach (var group in groups)
                    {
                        string gName = (FastGet(group, "Name") ?? "").ToString();
                        Console.WriteLine("  ScreenGroup: " + gName);
                        var gScreens = FastGet(group, "Screens") as IEnumerable;
                        if (gScreens != null)
                            foreach (var screen in gScreens)
                                ProcessScreen(screen, json, ref firstScreen, ref totalElements, ref totalBindings);
                    }
                }
            }
        }
        catch { }
        foreach (DeviceItem sub in item.DeviceItems) Walk(sub, json, ref firstScreen, ref totalElements, ref totalBindings);
    }

    // ── Process one screen ──────────────────────────────────────────────

    static void ProcessScreen(object screen, StringBuilder json, ref bool firstScreen, ref int totalElements, ref int totalBindings)
    {
        string sName = (FastGet(screen, "Name") ?? "").ToString();
        if (sName == "") sName = "Unknown";
        Console.WriteLine("  Screen: " + sName);

        if (!firstScreen) json.AppendLine(",");
        firstScreen = false;
        json.AppendLine("    {");
        json.AppendLine("      \"screen_name\": " + J(sName) + ",");
        json.AppendLine("      \"elements\": [");

        var items = FastGet(screen, "ScreenItems") as IEnumerable;
        bool firstItem = true;
        int elemCount = 0;

        if (items != null)
        {
            foreach (var si in items)
            {
                try
                {
                    string iName = (FastGet(si, "Name") ?? "").ToString();
                    string iType = si.GetType().Name;
                    int l = FastGetInt(si, "Left"), t = FastGetInt(si, "Top");
                    int w = FastGetInt(si, "Width"), h = FastGetInt(si, "Height");
                    string txt = CleanText(GetMLText(si, "Text"));
                    if (string.IsNullOrEmpty(txt)) txt = CleanText(FastGetStr(si, "Graphic"));

                    if (!firstItem) json.AppendLine(",");
                    firstItem = false;
                    json.AppendLine("        {");
                    json.AppendLine("          \"name\": " + J(iName) + ",");
                    json.AppendLine("          \"type\": " + J(MapType(iType)) + ",");
                    json.AppendLine("          \"type_raw\": " + J(iType) + ",");
                    json.AppendLine("          \"position\": { \"x\": " + l + ", \"y\": " + t + ", \"w\": " + w + ", \"h\": " + h + " },");
                    json.AppendLine("          \"text\": " + J(txt) + ",");

                    // ScreenWindow: which screen it shows
                    if (iType.Contains("ScreenWindow"))
                    {
                        string screenName = FastGetStr(si, "ScreenName");
                        if (!string.IsNullOrEmpty(screenName))
                            json.AppendLine("          \"window_screen\": " + J(screenName) + ",");
                    }

                    // Tag bindings from Dynamizations
                    json.AppendLine("          \"tag_bindings\": [");
                    int bindCount = 0;
                    try
                    {
                        var dyns = FastGet(si, "Dynamizations") as IEnumerable;
                        if (dyns != null)
                        {
                            foreach (var d in dyns)
                            {
                                try
                                {
                                    string prop = (FastGet(d, "PropertyName") ?? "").ToString();
                                    string tagName = "";

                                    object tagObj = FastGet(d, "Tag");
                                    if (tagObj != null) tagName = tagObj.ToString();

                                    if (string.IsNullOrEmpty(tagName))
                                    {
                                        object src = FastGet(d, "Source");
                                        if (src != null)
                                        {
                                            object srcTag = FastGet(src, "Tag");
                                            if (srcTag != null) tagName = srcTag.ToString();
                                        }
                                    }

                                    if (!string.IsNullOrEmpty(tagName))
                                    {
                                        if (bindCount > 0) json.AppendLine(",");
                                        bindCount++;
                                        totalBindings++;

                                        TagInfo info;
                                        tagTable.TryGetValue(tagName, out info);

                                        json.AppendLine("            {");
                                        json.AppendLine("              \"property\": " + J(prop) + ",");
                                        json.AppendLine("              \"hmi_tag\": " + J(tagName) + ",");
                                        json.AppendLine("              \"plc_tag\": " + J(info != null ? info.plc_tag : "") + ",");
                                        json.AppendLine("              \"plc_name\": " + J(info != null ? info.plc_name : "") + ",");
                                        json.AppendLine("              \"data_type\": " + J(info != null ? (info.hmi_data_type != "" ? info.hmi_data_type : info.plc_data_type) : "") + ",");
                                        json.AppendLine("              \"connection\": " + J(info != null ? info.connection : ""));
                                        json.Append("            }");
                                    }
                                }
                                catch { }
                            }
                        }
                    }
                    catch { }
                    if (bindCount > 0) json.AppendLine();
                    json.AppendLine("          ],");

                    // Events — EventType + Script
                    json.AppendLine("          \"events\": [");
                    int evCount = WriteEvents(json, si, sName);
                    if (evCount > 0) json.AppendLine();
                    json.AppendLine("          ]");

                    json.Append("        }");
                    elemCount++;
                    totalElements++;
                }
                catch { }
            }
        }
        if (elemCount > 0) json.AppendLine();
        json.AppendLine("      ],");
        json.AppendLine("      \"element_count\": " + elemCount + ",");

        // Screen-level events (OnLoaded, etc.)
        json.AppendLine("      \"screen_events\": [");
        int sEvCount = WriteEvents(json, screen, sName);
        if (sEvCount > 0) json.AppendLine();
        json.Append("      ]");

        // Screen-level navigations
        if (navMap.ContainsKey(sName) && navMap[sName].Count > 0)
        {
            json.AppendLine(",");
            json.AppendLine("      \"screen_navigations\": [" + string.Join(", ", navMap[sName].Select(n => J(n))) + "]");
        }
        else
        {
            json.AppendLine();
        }

        json.Append("    }");
    }

    // ── Shared event extraction (used for both elements and screens) ─────

    static string TryGetAny(object obj, params string[] names)
    {
        foreach (string name in names)
        {
            object val = FastGet(obj, name);
            if (val != null) return val.ToString();
        }
        return "";
    }

    static int WriteEvents(StringBuilder json, object obj, string screenName)
    {
        int count = 0;
        try
        {
            IEnumerable evs = FastGet(obj, "EventHandlers") as IEnumerable;
            if (evs == null) return 0;

            foreach (var ev in evs)
            {
                try
                {
                    // EventType
                    string evType = "";
                    object etVal = FastGet(ev, "EventType");
                    if (etVal != null)
                    {
                        evType = etVal.ToString();
                        int dot = evType.LastIndexOf('.');
                        if (dot >= 0) evType = evType.Substring(dot + 1);
                    }

                    // Script — get ScriptCode from the ScriptDynamization object
                    string script = "";
                    object scrObj = FastGet(ev, "Script");
                    if (scrObj != null)
                    {
                        // ScriptDynamization.ScriptCode contains the actual JS
                        object codeObj = FastGet(scrObj, "ScriptCode");
                        if (codeObj != null) script = codeObj.ToString();
                    }

                    // Only parse JS if script is non-empty
                    List<string> navs = null;
                    List<string> jsTags = null;
                    if (!string.IsNullOrEmpty(script))
                    {
                        navs = ExtractNavigations(script);
                        jsTags = ExtractJsTags(script);
                    }

                    if (count > 0) json.AppendLine(",");
                    count++;
                    totalEvents++;

                    json.AppendLine("            {");
                    json.AppendLine("              \"event_type\": " + J(evType) + ",");
                    if (script.Length > 10000) script = script.Substring(0, 10000);
                    json.AppendLine("              \"script\": " + J(script) + ",");
                    json.AppendLine("              \"navigates_to\": [" + (navs != null ? string.Join(", ", navs.Select(n => J(n))) : "") + "],");
                    json.AppendLine("              \"tags_used\": [" + (jsTags != null ? string.Join(", ", jsTags.Select(t => J(t))) : "") + "]");
                    json.Append("            }");

                    // Track navigation map
                    if (navs != null && navs.Count > 0)
                    {
                        totalNavigations += navs.Count;
                        if (!navMap.ContainsKey(screenName)) navMap[screenName] = new List<string>();
                        navMap[screenName].AddRange(navs);
                    }
                }
                catch { }
            }
        }
        catch { }
        return count;
    }

    // ── Tag table loading ───────────────────────────────────────────────

    static void LoadTagTable(object hmiSoftware)
    {
        tagTable.Clear();
        try
        {
            var groups = FastGet(hmiSoftware, "TagGroups") as IEnumerable;
            if (groups != null)
            {
                foreach (var g in groups)
                {
                    var tags = FastGet(g, "Tags") as IEnumerable;
                    if (tags != null) LoadTags(tags);
                }
            }
            var topTags = FastGet(hmiSoftware, "Tags") as IEnumerable;
            if (topTags != null) LoadTags(topTags);
        }
        catch { }
        Console.WriteLine("  Tags loaded: " + tagTable.Count);
    }

    static void LoadTags(IEnumerable tags)
    {
        foreach (var tag in tags)
        {
            try
            {
                string name = (FastGet(tag, "Name") ?? "").ToString();
                if (string.IsNullOrEmpty(name) || tagTable.ContainsKey(name)) continue;

                var info = new TagInfo();
                var v = FastGet(tag, "PlcTag"); if (v != null) info.plc_tag = v.ToString();
                v = FastGet(tag, "PlcName"); if (v != null) info.plc_name = v.ToString();

                v = FastGet(tag, "HmiDataType"); if (v != null) info.hmi_data_type = v.ToString();
                v = FastGet(tag, "DataType"); if (v != null) info.plc_data_type = v.ToString();

                object conn = FastGet(tag, "Connection");
                if (conn != null)
                {
                    var cn = FastGet(conn, "Name");
                    info.connection = (cn != null) ? cn.ToString() : "";
                }

                tagTable[name] = info;
            }
            catch { }
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────

    static string MapType(string t)
    {
        if (t.Contains("Button")) return "button";
        if (t.Contains("TextBox") || t.Contains("Text")) return "text_display";
        if (t.Contains("IOField")) return "io_field";
        if (t.Contains("SymbolicIO")) return "symbolic_io_field";
        if (t.Contains("StatusDisplay")) return "status_display";
        if (t.Contains("Circle") || t.Contains("Ellipse")) return "circle";
        if (t.Contains("Rectangle")) return "rectangle";
        if (t.Contains("Line")) return "line";
        if (t.Contains("ScreenWindow")) return "screen_window";
        if (t.Contains("Bar")) return "bar_graph";
        if (t.Contains("Switch")) return "switch";
        if (t.Contains("Image")) return "image";
        if (t.Contains("Faceplate")) return "faceplate";
        if (t.Contains("AlarmControl")) return "alarm_control";
        return t;
    }

    static string GetMLText(object o, string p)
    {
        try
        {
            object ml = FastGet(o, p);
            if (ml == null) return "";
            var items = FastGet(ml, "Items") as IEnumerable;
            if (items == null) return "";
            foreach (var i in items)
            {
                object v = FastGet(i, "Text");
                if (v != null) return Regex.Replace(v.ToString(), "<.*?>", "");
            }
        }
        catch { }
        return "";
    }

    static string CleanText(string s) { return string.IsNullOrEmpty(s) ? "" : s.Replace("\n", " ").Replace("\r", "").Replace("\"", "'").Trim(); }
    static string J(string s) { return "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", "") + "\""; }

    // ── JS parsing (using static compiled regex) ────────────────────────

    static List<string> ExtractNavigations(string js)
    {
        var navs = new List<string>();
        foreach (Match m in reNav.Matches(js))
        {
            string target = m.Groups[1].Value.Trim();
            if (!navs.Contains(target)) navs.Add(target);
        }
        return navs;
    }

    static List<string> ExtractJsTags(string js)
    {
        var tags = new HashSet<string>();
        for (int i = 0; i < reTags.Length; i++)
        {
            foreach (Match m in reTags[i].Matches(js))
                tags.Add(m.Groups[1].Value.Trim());
        }
        return tags.OrderBy(t => t).ToList();
    }
}

class TagInfo
{
    public string plc_tag = "";
    public string plc_name = "";
    public string hmi_data_type = "";
    public string plc_data_type = "";
    public string connection = "";
}
