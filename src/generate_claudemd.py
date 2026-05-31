#!/usr/bin/env python3
"""
CLAUDE.md Generator
===================
Reads PLC cache + HMI data and generates a project-specific CLAUDE.md
in Doc_OUTPUT/CLAUDE.md.

Usage:
    python generate_claudemd.py
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_json(path):
    """Load JSON with UTF-8 BOM handling."""
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def find_plc_cache():
    """Find .plc_cache.json by walking Doc_OUTPUT."""
    if not os.path.isdir(DOC_OUTPUT):
        return None
    for root, dirs, files in os.walk(DOC_OUTPUT):
        for f in files:
            if f == ".plc_cache.json":
                return os.path.join(root, f)
    return None


def find_hmi_data():
    """Find best HMI data: merged first, then online."""
    merged = os.path.join(DOC_OUTPUT, ".hmi_merged.json")
    online = os.path.join(DOC_OUTPUT, ".hmi_online_data.json")
    if os.path.exists(merged):
        return merged
    if os.path.exists(online):
        return online
    return None


def find_data():
    """Locate all available data sources."""
    plc_path = find_plc_cache()
    hmi_path = find_hmi_data()

    plc_data = load_json(plc_path) if plc_path else None
    hmi_data = load_json(hmi_path) if hmi_path else None

    return plc_data, hmi_data, plc_path, hmi_path


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def get_project_name(plc_data, hmi_data):
    """Extract project name from extraction info."""
    for data in (plc_data, hmi_data):
        if data:
            info = data.get("extraction_info", {})
            name = info.get("project", "")
            if name:
                return name
            plc = info.get("plc_name", "")
            if plc:
                return plc
            dev = info.get("device_filter", "")
            if dev:
                return dev
    return "Unknown TIA Portal Project"


def get_plc_name(plc_data):
    """Get PLC name from cache."""
    if not plc_data:
        return ""
    info = plc_data.get("extraction_info", {})
    return info.get("plc_name", "")


def count_blocks_by_type(blocks):
    """Count blocks by type (FB, FC, OB, DB, IDB)."""
    counter = Counter(b.get("block_type", "?") for b in blocks)
    return dict(counter)


def count_blocks_by_language(blocks):
    """Count blocks by programming language."""
    counter = Counter(b.get("programming_language", "?") for b in blocks)
    return dict(counter)


def detect_tag_patterns(plc_tags):
    """Analyze tag names for naming conventions."""
    if not plc_tags:
        return []

    patterns = []
    names = list(plc_tags.keys())

    # Check address prefix patterns (I/Q/M/DB) from the address field
    prefixes = Counter()
    for name, info in plc_tags.items():
        addr = info.get("address", "") if isinstance(info, dict) else ""
        if not addr:
            continue
        if re.match(r'^%I', addr):
            prefixes["I (Inputs)"] += 1
        elif re.match(r'^%Q', addr):
            prefixes["Q (Outputs)"] += 1
        elif re.match(r'^%M', addr):
            prefixes["M (Memory)"] += 1
        elif re.match(r'^DB', addr):
            prefixes["DB (Data Block)"] += 1

    if prefixes:
        total = len(names)
        top = prefixes.most_common(3)
        desc = ", ".join(f"{p} ({c})" for p, c in top)
        patterns.append(f"Tag address prefixes: {desc} (of {total} tags)")

    # Check table grouping
    tables = Counter()
    for name, info in plc_tags.items():
        if isinstance(info, dict) and info.get("table"):
            tables[info["table"]] += 1
    if tables:
        top = tables.most_common(5)
        desc = ", ".join(f"{t} ({c})" for t, c in top)
        patterns.append(f"Tag tables: {desc}")

    # Check naming style
    upper_count = sum(1 for n in names if n.isupper() or '_' in n)
    if upper_count > len(names) * 0.7:
        patterns.append("Tags use UPPER_SNAKE_CASE naming")

    # Check DB.Structure pattern
    db_dot = sum(1 for n in names if '.' in n)
    if db_dot > 0:
        patterns.append(f"Tags use DBx.Structure.Member format ({db_dot} tags)")

    return patterns


def detect_block_conventions(blocks):
    """Analyze block numbering and naming patterns."""
    if not blocks:
        return []

    conventions = []
    by_type = defaultdict(list)
    for b in blocks:
        btype = b.get("block_type", "?")
        bnum = b.get("block_number")
        if bnum:
            by_type[btype].append(bnum)

    for btype, numbers in sorted(by_type.items()):
        if numbers:
            lo, hi = min(numbers), max(numbers)
            conventions.append(f"{btype} range: {btype}{lo} – {btype}{hi} ({len(numbers)} blocks)")

    # Check naming style
    names = [b.get("block_name", "") for b in blocks]
    upper_count = sum(1 for n in names if n.isupper() or '_' in n)
    if upper_count > len(names) * 0.7:
        conventions.append("Block names use UPPER_SNAKE_CASE")

    return conventions


def build_folder_tree(blocks):
    """Build folder -> block list tree."""
    folders = defaultdict(list)
    for b in blocks:
        folder = b.get("folder", "/") or "/"
        btype = b.get("block_type", "?")
        bnum = b.get("block_number", "")
        bname = b.get("block_name", "?")
        label = f"{btype}{bnum}_{bname}" if bnum else bname
        folders[folder].append(label)

    return dict(sorted(folders.items()))


def build_hmi_summary(hmi_data):
    """Summarize HMI screens: name, element count, tag count."""
    screens = []
    if not hmi_data:
        return screens

    for scr in hmi_data.get("screens", []):
        name = scr.get("screen_name", "?")
        elements = scr.get("elements", [])
        elem_count = len(elements)
        tag_count = sum(len(e.get("tag_bindings", [])) for e in elements)
        event_count = sum(len(e.get("events", [])) for e in elements)

        # Element type breakdown
        types = Counter(e.get("type", e.get("type_raw", "?")) for e in elements)
        type_str = ", ".join(f"{c}x {t}" for t, c in types.most_common(5))

        screens.append({
            "name": name,
            "elements": elem_count,
            "tags": tag_count,
            "events": event_count,
            "types": type_str,
        })

    return screens


def get_key_blocks(blocks):
    """Get important blocks: OBs, and blocks with most calls/references."""
    if not blocks:
        return []

    key = []

    # All OBs
    for b in blocks:
        if b.get("block_type") == "OB":
            key.append(b)

    # Blocks with most calls (top 10)
    by_calls = sorted(blocks, key=lambda b: len(b.get("calls", [])), reverse=True)
    for b in by_calls[:10]:
        if b not in key:
            key.append(b)

    # Blocks referenced by most other blocks
    by_refs = sorted(blocks, key=lambda b: len(b.get("tag_references", [])), reverse=True)
    for b in by_refs[:5]:
        if b not in key:
            key.append(b)

    return key


# ---------------------------------------------------------------------------
# Smart analysis helpers
# ---------------------------------------------------------------------------

def _find_main_ob(blocks):
    """Find the main cyclic OB — prefer OB1, fallback to first ProgramCycle OB."""
    for b in blocks:
        if b.get("block_type") == "OB" and b.get("block_number") == 1:
            return b
    # Fallback: find first OB with SecondaryType=ProgramCycle
    for b in blocks:
        if b.get("block_type") == "OB" and b.get("secondary_type") == "ProgramCycle":
            return b
    # Last resort: first OB by number
    obs = [b for b in blocks if b.get("block_type") == "OB"]
    if obs:
        return min(obs, key=lambda b: b.get("block_number", 999))
    return None


def build_execution_order(plc_data):
    """Extract main program execution order from the primary cyclic OB."""
    if not plc_data:
        return []
    blocks = plc_data.get("blocks", [])
    main_ob = _find_main_ob(blocks)
    if main_ob:
        return main_ob.get("calls", [])
    # Fallback to call_tree
    call_tree = plc_data.get("call_tree", {})
    if call_tree:
        return list(list(call_tree.values())[0]) if call_tree else []
    return []


def build_instance_db_map(blocks):
    """Map FBs to their instance DBs."""
    idbs = []
    for b in blocks:
        if b.get("block_type") == "IDB":
            inst_of = b.get("instance_of_name", "")
            if inst_of:
                idbs.append({
                    "idb_name": b.get("block_name", "?"),
                    "idb_num": b.get("block_number", ""),
                    "fb_name": inst_of,
                    "fb_type": b.get("instance_of_type", ""),
                    "folder": b.get("folder", ""),
                })
    return idbs


def detect_step_sequencers(blocks):
    """Detect step sequencer blocks (STAPPEN/STEP/SEQ patterns) and pair DBs with FCs."""
    sequencers = []
    step_kw = ("STAP", "STAPPEN", "STEP", "SEQ", "SEQUENCE")
    step_dbs = {}  # block_name -> label

    # First pass: find step DBs
    for b in blocks:
        btype = b.get("block_type", "")
        if btype not in ("DB",):
            continue
        name_upper = b.get("block_name", "").upper()
        if any(kw in name_upper for kw in step_kw):
            bnum = b.get("block_number", "")
            label = f"{btype}{bnum}_{b.get('block_name', '?')}" if bnum else b.get("block_name", "?")
            step_dbs[b.get("block_name", "")] = label

    # Second pass: find step FCs and pair with their DBs
    for b in blocks:
        btype = b.get("block_type", "")
        if btype in ("STRUCT", "UDT", "DB"):
            continue
        name_upper = b.get("block_name", "").upper()
        is_step = any(kw in name_upper for kw in step_kw)
        step_db = ""
        # Always try to find the step DB from tag references
        for ref in b.get("tag_references", []):
            if any(kw in ref.upper() for kw in step_kw):
                is_step = True
                if ref.startswith("DB_") and "." in ref:
                    step_db = ref.split(".")[0]
                    break
        if is_step:
            bnum = b.get("block_number", "")
            # Use the found step_db, or try to match by name convention
            if not step_db:
                for db_name, db_label in step_dbs.items():
                    # Match by shared keywords in name
                    db_parts = set(db_name.upper().replace("_", " ").split())
                    fc_parts = set(name_upper.replace("_", " ").split())
                    overlap = db_parts & fc_parts - set(kw.lower() for kw in ("STAP", "STAPPEN", "STEP", "SEQ", "SEQUENCE", "DB", "FC"))
                    if len(overlap) >= 1:
                        step_db = db_label
                        break
            sequencers.append({
                "label": f"{btype}{bnum}_{b.get('block_name', '?')}" if bnum else b.get("block_name", "?"),
                "type": btype,
                "language": b.get("programming_language", "?"),
                "step_db": step_db,
                "comment": (b.get("comment", "") or "").split("\n")[0][:80],
            })
    return sequencers


def build_subsystem_map(blocks):
    """Build functional subsystem map from folder structure."""
    subsystems = defaultdict(lambda: {"blocks": [], "types": Counter()})
    for b in blocks:
        folder = b.get("folder", "/") or "/"
        btype = b.get("block_type", "?")
        if btype in ("STRUCT", "UDT"):
            continue
        bnum = b.get("block_number", "")
        bname = b.get("block_name", "?")
        label = f"{btype}{bnum}_{bname}" if bnum else bname
        subsystems[folder]["blocks"].append(label)
        subsystems[folder]["types"][btype] += 1
    return dict(sorted(subsystems.items()))


def build_io_summary(plc_tags):
    """Build I/O hardware summary from PLC tags."""
    if not plc_tags:
        return {}

    result = {}
    for io_key, prefix, label in [
        ("inputs", "%I", "Inputs (%I)"),
        ("outputs", "%Q", "Outputs (%Q)"),
        ("memory", "%M", "Memory (%M)"),
    ]:
        tags = [(name, info) for name, info in plc_tags.items()
                if isinstance(info, dict) and info.get("address", "").startswith(prefix)]
        if not tags:
            continue

        bytes_used = set()
        for _, info in tags:
            m = re.match(r'%[IQM](\d+)', info.get("address", ""))
            if m:
                bytes_used.add(int(m.group(1)))

        dtypes = Counter(info.get("data_type", "?") for _, info in tags)
        tables = Counter(info.get("table", "") for _, info in tags if info.get("table"))

        result[io_key] = {
            "count": len(tags),
            "label": label,
            "bytes": f"{min(bytes_used)}–{max(bytes_used)}" if bytes_used else "N/A",
            "dtypes": dict(dtypes),
            "tables": dict(tables.most_common(5)),
        }

    return result


def detect_safety_blocks(blocks):
    """Flag alarm, safety, and interlock blocks."""
    safety_kw = ("ALARM", "NOODSTOP", "BEWAKING", "GUARD", "STOP", "VEILIG", "SAFETY", "INTERLOCK")
    safety_blocks = []
    for b in blocks:
        btype = b.get("block_type", "")
        if btype in ("STRUCT", "UDT"):
            continue
        name_upper = b.get("block_name", "").upper()
        folder_upper = (b.get("folder", "") or "").upper()

        reasons = []
        for kw in safety_kw:
            if kw in name_upper:
                reasons.append(f"name contains '{kw}'")
            elif kw in folder_upper:
                reasons.append(f"folder contains '{kw}'")

        if reasons:
            bnum = b.get("block_number", "")
            safety_blocks.append({
                "label": f"{btype}{bnum}_{b.get('block_name', '?')}" if bnum else b.get("block_name", "?"),
                "type": btype,
                "reasons": list(set(reasons)),
                "comment": (b.get("comment", "") or "").split("\n")[0][:60],
            })
    return safety_blocks


def build_data_flow(plc_data):
    """Map which executable blocks reference which DBs (data dependencies)."""
    if not plc_data:
        return {}

    blocks = plc_data.get("blocks", [])
    data_flow = {}
    for b in blocks:
        btype = b.get("block_type", "")
        if btype in ("DB", "IDB", "STRUCT", "UDT"):
            continue

        bname = b.get("block_name", "?")
        refs = b.get("tag_references", [])

        db_refs = set()
        for ref in refs:
            if "." in ref:
                db_name = ref.split(".")[0]
                db_refs.add(db_name)

        if db_refs:
            data_flow[bname] = sorted(db_refs)

    return data_flow


def build_reverse_data_flow(data_flow):
    """Invert data flow: DB -> list of blocks that reference it."""
    reverse = defaultdict(list)
    for block_name, dbs in data_flow.items():
        for db in dbs:
            reverse[db].append(block_name)
    return dict(sorted(reverse.items()))


def build_hmi_plc_bridge(hmi_data):
    """Cross-reference HMI screens with PLC tags they bind to."""
    if not hmi_data:
        return {}

    bridge = {}
    for scr in hmi_data.get("screens", []):
        screen_name = scr.get("screen_name", "?")
        plc_tags = {}  # plc_tag -> set of properties

        for elem in scr.get("elements", []):
            for binding in elem.get("tag_bindings", []):
                if isinstance(binding, dict):
                    tag = binding.get("plc_tag", binding.get("tag", ""))
                    prop = binding.get("property", "")
                else:
                    tag = str(binding)
                    prop = ""
                if tag and tag != "":
                    if tag not in plc_tags:
                        plc_tags[tag] = set()
                    if prop:
                        plc_tags[tag].add(prop)

        if plc_tags:
            bridge[screen_name] = {tag: sorted(props) for tag, props in sorted(plc_tags.items())}

    return bridge


def build_ob_summary(blocks):
    """Summarize all OBs with type, calls, and comments."""
    obs = []
    for b in blocks:
        if b.get("block_type") == "OB":
            bnum = b.get("block_number", 0)
            obs.append({
                "label": f"OB{bnum}_{b.get('block_name', '?')}",
                "number": bnum,
                "name": b.get("block_name", ""),
                "language": b.get("programming_language", "?"),
                "calls": b.get("calls", []),
                "comment": (b.get("comment", "") or "").split("\n")[0][:80],
                "folder": b.get("folder", ""),
            })
    return sorted(obs, key=lambda x: x.get("number", 0))


def build_udt_summary(blocks):
    """Extract UDT/STRUCT definitions with their top-level members."""
    udts = []
    for b in blocks:
        btype = b.get("block_type", "")
        if btype in ("STRUCT", "UDT"):
            iface = b.get("interface", {})
            # UDTs store members under 'members', DBs use 'static'
            raw_members = iface.get("members") or iface.get("static") or []
            members = []
            for m in raw_members[:20]:
                name = m.get("name", "")
                dtype = m.get("data_type", "")
                comment = (m.get("comment", "") or "").split("\n")[0][:40]
                members.append({"name": name, "data_type": dtype, "comment": comment})
            udts.append({
                "name": b.get("block_name", "?"),
                "type": btype,
                "members": members,
                "member_count": len(raw_members),
                "folder": b.get("folder", ""),
            })
    return sorted(udts, key=lambda x: x["name"])


def build_subsystem_overview(blocks):
    """Build a compact subsystem overview from top-level folders."""
    subsystems = defaultdict(lambda: {"blocks": 0, "types": Counter(), "key_blocks": []})
    for b in blocks:
        btype = b.get("block_type", "?")
        if btype in ("STRUCT", "UDT"):
            continue
        folder = b.get("folder", "/") or "/"
        # Get top-level folder (first segment)
        parts = folder.strip("/").split("/")
        top = parts[0] if parts and parts[0] else "(root)"

        subsystems[top]["blocks"] += 1
        subsystems[top]["types"][btype] += 1

        # Track executable blocks (FC, FB) as key blocks
        if btype in ("FC", "FB", "OB"):
            bnum = b.get("block_number", "")
            name = b.get("block_name", "")
            label = f"{btype}{bnum}_{name}" if bnum else name
            subsystems[top]["key_blocks"].append(label)

    return dict(sorted(subsystems.items()))


# ---------------------------------------------------------------------------
# DB purpose inference (generic — works for any project)
# ---------------------------------------------------------------------------

# Generic keyword -> purpose mapping (language-agnostic)
_DB_PURPOSE_KEYWORDS = [
    # English
    ("ALARM", "Alarm data"),
    ("SAFETY", "Safety data"),
    ("STATUS", "System status"),
    ("SETTING", "Settings/parameters"),
    ("CONFIG", "Configuration data"),
    ("HMI", "HMI interface"),
    ("VISUALISATIE", "Visualisation data"),
    ("VISUALISATION", "Visualisation data"),
    ("VISUALIZATION", "Visualization data"),
    ("COMMUNICAT", "Communication data"),
    ("COMMUNICATION", "Communication data"),
    ("INPUT_GUARD", "Hardware input monitoring"),
    ("GUARD", "Input monitoring"),
    ("MONITOR", "Monitoring data"),
    ("TIMER", "Timer data"),
    ("CLOCK", "Clock/time data"),
    ("TIME", "Time data"),
    ("SIMULATION", "Simulation data"),
    ("ANALOG", "Analog measurements"),
    ("MEASUREMENT", "Measurement data"),
    ("METING", "Measurement data"),
    ("SCALING", "Scaling data"),
    ("SCALE", "Scaling data"),
    ("AVERAGE", "Averaged values"),
    ("MIDDEL", "Averaged values"),
    ("WEIGH", "Weighing data"),
    ("WEGING", "Weighing data"),
    ("SPEED", "Speed reference data"),
    ("TOEREN", "Speed reference data"),
    ("STEP", "Step sequencer data"),
    ("STAP", "Step sequencer data"),
    ("SEQUENCE", "Sequence data"),
    ("INSTELLING", "Settings/parameters"),
    ("BEWAKING", "Monitoring/guard data"),
    ("STAPPEN", "Step sequencer data"),
    ("FILTER", "Filter data"),
    ("PLC_TIJD", "PLC time data"),
]


def infer_db_purpose(b):
    """Infer a short purpose description from DB name, comment, interface members, and folder."""
    name = b.get("block_name", "")
    name_upper = name.upper()
    comment = (b.get("comment", "") or "").split("\n")[0][:80]

    # 1. Inter-PLC communication patterns (PUT_TO / GET_FROM)
    if "PUT_TO" in name_upper:
        target = name_upper.replace("DB_PUT_TO_", "").replace("PUT_TO_", "")
        return f"Data sent to {target}"
    if "GET_FROM" in name_upper:
        source = name_upper.replace("DB_GET_FROM_", "").replace("GET_FROM_", "")
        return f"Data received from {source}"

    # 2. Match generic keywords
    for keyword, purpose in _DB_PURPOSE_KEYWORDS:
        if keyword in name_upper:
            # Try to add member names for context
            members = _get_top_members(b)
            if members:
                return f"{purpose} ({', '.join(members[:5])})"
            return purpose

    # 3. Use comment if available
    if comment:
        return comment

    # 4. Use top-level member names as hint
    members = _get_top_members(b)
    if members:
        return f"Data: {', '.join(members[:5])}"

    return ""


def _get_top_members(b):
    """Extract top-level static member names from a block's interface."""
    iface = b.get("interface", {})
    static = iface.get("static", [])
    if not static:
        return []
    return [m.get("name", "") for m in static[:8] if m.get("name")]


def _infer_fb_purpose(fb_name):
    """Infer purpose for an FB from its name (generic)."""
    fb_upper = fb_name.upper()
    # Check against same keyword table
    for keyword, purpose in _DB_PURPOSE_KEYWORDS:
        if keyword in fb_upper:
            return purpose
    # Additional FB-specific patterns
    fb_patterns = [
        ("DANFOSS", "VFD drive control"),
        ("VFD", "VFD drive control"),
        ("DRIVE", "Drive control"),
        ("MOTOR", "Motor control"),
        ("PUMP", "Pump control"),
        ("VETPOMP", "Grease pump control"),
        ("BAND", "Belt/conveyor control"),
        ("BELT", "Belt/conveyor control"),
        ("HYDR", "Hydraulic control"),
        ("VALVE", "Valve control"),
        ("KLEP", "Valve control"),
        ("LINIAAL", "Linear positioning"),
        ("LINEAR", "Linear positioning"),
        ("SUPERVISION", "Supervision"),
        ("TIMEZONE", "Timezone"),
        ("PUT_GET", "Inter-PLC communication"),
    ]
    for keyword, purpose in fb_patterns:
        if keyword in fb_upper:
            return purpose
    return f"Instance DBs for {fb_name}"


def _detect_comment_language(blocks):
    """Detect the natural language of block comments and tag names."""
    # Language fingerprint: common words/patterns per language
    _LANG_MARKERS = {
        "Dutch": ("de", "het", "een", "van", "met", "voor", "door", "naar",
                   "ALARM", "BEWAKING", "NOODSTOP", "INSTELLING", "STAPPEN",
                   "STROOM", "DRUK", "OLIE", "VET", "BAND", "LINIAAL"),
        "German": ("der", "die", "das", "und", "mit", "fuer", "von", "nach",
                   "ALARM", "UEBERWACHUNG", "NOTSTOPP", "EINSTELLUNG"),
        "French": ("le", "la", "les", "de", "du", "des", "avec", "pour",
                   "ALARME", "SURVEILLANCE", "ARRET", "PARAMETRE"),
    }
    # Collect all comment text and tag names
    text_pool = []
    for b in blocks[:50]:
        c = b.get("comment", "") or ""
        if c:
            text_pool.append(c.upper())
        n = b.get("block_name", "")
        if n:
            text_pool.append(n.upper())
        for m in (_get_top_members(b) or [])[:5]:
            text_pool.append(m.upper())

    combined = " ".join(text_pool)
    if not combined.strip():
        return "English"  # default fallback

    best_lang = "English"
    best_score = 0
    for lang, markers in _LANG_MARKERS.items():
        score = sum(1 for m in markers if m in combined)
        if score > best_score:
            best_score = score
            best_lang = lang

    return best_lang if best_score >= 3 else "English"


def _short_folder(folder):
    """Extract short folder name for display."""
    if not folder or folder == "/":
        return ""
    # Take last segment
    parts = folder.strip("/").split("/")
    return parts[-1].strip()


def _clean_idb_name(name):
    """Clean instance DB name by stripping common type prefixes dynamically."""
    # Strip known structural prefixes (FBDB_, DB_) but NOT project-specific ones
    for prefix in ("FBDB_", "IDB_"):
        if name.startswith(prefix):
            return name[len(prefix):]
    # For DB_ prefix, only strip if followed by a number (DB4_ → strip)
    if re.match(r'^DB\d+_', name):
        return re.sub(r'^DB\d+_', '', name)
    return name


# ---------------------------------------------------------------------------
# New section helpers
# ---------------------------------------------------------------------------

def build_quick_facts(plc_data, hmi_data, blocks):
    """Build compact Quick Facts section — adapts to available data."""
    lines = []
    project_name = get_project_name(plc_data, hmi_data)
    plc_name = get_plc_name(plc_data)

    lines.append(f"- **Project:** {project_name}")

    # PLC info
    if plc_data and blocks:
        summary = plc_data.get("summary", {})
        tags_c = summary.get("plc_tags_loaded", 0)
        lines.append(f"- **PLC:** {plc_name} ({summary.get('total_blocks', 0)} blocks, {tags_c} tags)")
        main_ob = _find_main_ob(blocks)
        if main_ob:
            lines.append(f"- **Main OB:** OB{main_ob.get('block_number', '?')}_{main_ob.get('block_name', '?')}")
        lang_counts = count_blocks_by_language(blocks)
        exec_langs = {k: v for k, v in lang_counts.items() if k not in ("DB", "STRUCT")}
        primary = max(exec_langs, key=exec_langs.get) if exec_langs else "SCL"
        lines.append(f"- **Language:** {primary} primary ({', '.join(f'{v} {k}' for k, v in sorted(exec_langs.items()))})")
        subsystems = build_subsystem_overview(blocks)
        if len(subsystems) > 1:
            top_subs = list(subsystems.keys())[:5]
            lines.append(f"- **Subsystems:** {', '.join(top_subs)}")
        safety = detect_safety_blocks(blocks)
        if safety:
            lines.append(f"- **Safety blocks:** {len(safety)} detected (see Safety-Critical Blocks)")
    else:
        lines.append("- **PLC:** ⚠ Not extracted — run PLC pipeline first")

    # HMI info
    if hmi_data:
        screens = hmi_data.get("screens", [])
        total_elements = sum(len(s.get("elements", [])) for s in screens)
        hmi_dev = hmi_data.get("extraction_info", {}).get("device_filter", "")
        lines.append(f"- **HMI:** {hmi_dev} ({len(screens)} screens, {total_elements} elements)" if hmi_dev
                     else f"- **HMI:** {len(screens)} screens, {total_elements} elements")

    # Start-here guidance
    if plc_data and blocks:
        lines.append(f"- **Start here:** Read the DB Purpose Table, then Execution Order, then HMI Tag Bridge")
    elif hmi_data:
        lines.append(f"- **Start here:** Read HMI Screens Overview and Navigation Map, then extract PLC data")
    return lines


def build_hmi_screen_table(hmi_data):
    """Build compact HMI screen summary table."""
    if not hmi_data:
        return []

    screens = hmi_data.get("screens", [])
    if not screens:
        return []

    lines = []
    lines.append("| Screen | Elements | Tags | Events | Key Types |")
    lines.append("|--------|----------|------|--------|-----------|")

    for scr in sorted(screens, key=lambda s: s.get("screen_name", "")):
        name = scr.get("screen_name", "?")
        elements = scr.get("elements", [])

        # Count by element type
        type_counts = Counter(e.get("type", "?") for e in elements)
        tag_count = sum(len(e.get("tag_bindings", [])) for e in elements)
        event_count = sum(len(e.get("events", [])) for e in elements)

        # Show top 3 element types
        top_types = type_counts.most_common(3)
        type_str = ", ".join(f"{c}x {t}" for t, c in top_types)

        lines.append(f"| {name} | {len(elements)} | {tag_count} | {event_count} | {type_str} |")

    return lines


def build_hmi_navigation_map(hmi_data):
    """Build HMI screen navigation map from navigation_map or per-screen navigations."""
    if not hmi_data:
        return []

    # Prefer top-level navigation_map (from merged data)
    nav_map = hmi_data.get("navigation_map", {})
    if not nav_map:
        # Build from per-screen screen_navigations
        nav_map = {}
        for scr in hmi_data.get("screens", []):
            navs = scr.get("screen_navigations", [])
            if navs:
                nav_map[scr.get("screen_name", "?")] = navs

    if not nav_map:
        return []

    lines = []
    for source, targets in sorted(nav_map.items()):
        target_str = ", ".join(targets) if isinstance(targets, list) else str(targets)
        lines.append(f"- **{source}** → {target_str}")

    return lines


def build_compact_hmi_bridge(hmi_data):
    """Build compact HMI-PLC tag bridge table with type summaries and DB references."""
    if not hmi_data:
        return []

    screens = hmi_data.get("screens", [])
    if not screens:
        return []

    lines = []
    lines.append("| Screen | Tags | Data Types | Key DB References |")
    lines.append("|--------|------|------------|-------------------|")

    screen_stats = []
    for scr in screens:
        name = scr.get("screen_name", "?")
        elements = scr.get("elements", [])

        # Collect all tag_bindings
        all_bindings = []
        for elem in elements:
            all_bindings.extend(elem.get("tag_bindings", []))

        if not all_bindings:
            screen_stats.append((name, 0, {}, set()))
            continue

        # Group by data_type
        dtype_counts = Counter()
        db_refs = set()
        for b in all_bindings:
            if isinstance(b, dict):
                dt = b.get("data_type", "?")
                if dt:
                    dtype_counts[dt] += 1
                plc_tag = b.get("plc_tag", "")
                if plc_tag and "." in plc_tag:
                    db_refs.add(plc_tag.split(".")[0])
                elif plc_tag:
                    db_refs.add(plc_tag)

        screen_stats.append((name, len(all_bindings), dtype_counts, db_refs))

    # Sort by tag count descending, show top 15
    screen_stats.sort(key=lambda x: x[1], reverse=True)
    for name, tag_count, dtype_counts, db_refs in screen_stats[:15]:
        if tag_count == 0:
            continue
        dt_str = ", ".join(f"{c}x {dt}" for dt, c in dtype_counts.most_common(4))
        db_str = ", ".join(sorted(db_refs)[:4])
        if len(db_refs) > 4:
            db_str += f" (+{len(db_refs)-4})"
        lines.append(f"| {name} | {tag_count} | {dt_str} | {db_str or '—'} |")

    if len(screen_stats) > 15:
        remaining = sum(1 for _, tc, _, _ in screen_stats[15:] if tc > 0)
        if remaining:
            lines.append(f"| *(+{remaining} more screens)* | | | |")

    return lines


def build_data_sources_report(plc_data, hmi_data, plc_path, hmi_path):
    """Build extraction quality report showing available data sources."""
    lines = []
    lines.append("| Source | Status | Records |")
    lines.append("|--------|--------|---------|")

    # PLC cache
    if plc_data:
        summary = plc_data.get("summary", {})
        total = summary.get("total_blocks", 0)
        tags = summary.get("plc_tags_loaded", 0)
        lines.append(f"| PLC blocks ({os.path.basename(plc_path or '')}) | ✓ | {total} blocks |")
        lines.append(f"| PLC tags | {'✓' if tags > 0 else '⚠'} | {tags} tags |")
    else:
        lines.append("| PLC blocks (.plc_cache.json) | ✗ | Not found — run PLC pipeline |")

    # HMI data
    if hmi_data:
        screens = hmi_data.get("screens", [])
        hmi_name = os.path.basename(hmi_path or "HMI data")
        elements = sum(len(s.get("elements", [])) for s in screens)
        lines.append(f"| HMI data ({hmi_name}) | ✓ | {len(screens)} screens, {elements} elements |")
    else:
        lines.append("| HMI data | ✗ | Not found |")

    # Check individual files
    for filename, label in [
        (".hmi_merged.json", "HMI merged"),
        (".hmi_online_data.json", "HMI online (C#)"),
        ("hmi_offline_data.json", "HMI offline (Python)"),
    ]:
        filepath = os.path.join(DOC_OUTPUT, filename)
        if os.path.exists(filepath):
            try:
                data = load_json(filepath)
                count = len(data.get("screens", [])) if data else 0
                lines.append(f"| {label} | ✓ | {count} screens |")
            except Exception:
                lines.append(f"| {label} | ✓ | Found |")
        else:
            lines.append(f"| {label} | ✗ | Not found |")

    return lines


# ---------------------------------------------------------------------------
# CLAUDE.md generation
# ---------------------------------------------------------------------------

def generate_claude_md(plc_data, hmi_data, hmi_path=""):
    """Assemble comprehensive CLAUDE.md with front-loaded critical info."""
    sections = []  # (title, lines) pairs for TOC generation

    def add_section(title, sec_lines):
        """Register a section for the document and TOC."""
        content_lines = [l for l in sec_lines if l.strip() and l.strip() != "## " + title]
        if content_lines:
            sections.append((title, sec_lines))

    project_name = get_project_name(plc_data, hmi_data)
    plc_name = get_plc_name(plc_data)

    blocks = plc_data.get("blocks", []) if plc_data else []
    summary = plc_data.get("summary", {}) if plc_data else {}
    call_tree = plc_data.get("call_tree", {}) if plc_data else {}
    plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}
    tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}

    block_counts = count_blocks_by_type(blocks) if plc_data else {}
    lang_counts = count_blocks_by_language(blocks) if plc_data else {}
    exec_langs = {k: v for k, v in lang_counts.items() if k not in ("DB", "STRUCT")} if lang_counts else {}
    primary_lang = max(exec_langs, key=exec_langs.get) if exec_langs else "SCL"

    hmi_screens_count = len(hmi_data.get("screens", [])) if hmi_data else 0

    # ===== 1. Header + Stats =====
    header_lines = []
    header_lines.append(f"# CLAUDE.md — {project_name}")
    header_lines.append("")
    header_lines.append("```yaml")
    header_lines.append("role: PLC/HMI Automation Engineer")
    header_lines.append("software: Siemens TIA Portal")
    if plc_name:
        header_lines.append(f"plc: {plc_name}")
    if hmi_data:
        dev = hmi_data.get("extraction_info", {}).get("device_filter", "")
        if dev:
            header_lines.append(f"hmi: {dev}")
    all_langs = sorted(set(lang_counts.keys())) if lang_counts else ["SCL", "STL", "DB"]
    header_lines.append(f"languages: {', '.join(all_langs)}")
    header_lines.append("```")
    header_lines.append("")

    total = summary.get("total_blocks", 0)
    fb_c = summary.get("fb_count", 0)
    fc_c = summary.get("fc_count", 0)
    ob_c = summary.get("ob_count", 0)
    db_c = summary.get("db_count", 0)
    idb_c = summary.get("idb_count", 0)
    tags_c = summary.get("plc_tags_loaded", 0)
    scl_c = summary.get("scl_count", 0)
    stl_c = summary.get("stl_count", 0)
    lad_c = lang_counts.get("LAD", 0) if lang_counts else 0
    lang_parts = []
    if scl_c: lang_parts.append(f"{scl_c} SCL")
    if stl_c: lang_parts.append(f"{stl_c} STL")
    if lad_c: lang_parts.append(f"{lad_c} LAD")
    lang_str = " / ".join(lang_parts)
    header_lines.append(f"**{total} blocks** ({fb_c} FB, {fc_c} FC, {ob_c} OB, {db_c} DB, {idb_c} IDB) · **{tags_c} PLC tags** · **{hmi_screens_count} HMI screens** · {lang_str}")
    header_lines.append("")

    # ===== 2. Missing Data Warning =====
    if not plc_data or not blocks:
        header_lines.append("> ⚠ **PLC data not extracted yet.** Most sections below will be empty.")
        header_lines.append("> Run the PLC pipeline to get full analysis:")
        header_lines.append(">   1. Export blocks: `tia_export_blocks.exe \"Doc_OUTPUT/DATA_Program blocks\" \"DEVICE_NAME\"`")
        header_lines.append(">   2. Parse: `python src/extract_plc_full.py \"Doc_OUTPUT/DATA_Program blocks\" --verbose`")
        header_lines.append(">   3. Report: `python src/plc_report.py`")
        header_lines.append(">   4. Regenerate: `python src/generate_claudemd.py`")
        header_lines.append("")

    # ===== 3. Quick Facts =====
    qf_lines = ["## Quick Facts", ""]
    qf_lines.extend(build_quick_facts(plc_data, hmi_data, blocks))
    qf_lines.append("")
    add_section("Quick Facts", qf_lines)

    # ===== 4. Rules for AI =====
    rules_lines = ["## Rules for AI", ""]
    rules_lines.append("### Safety")
    rules_lines.append("- NEVER change addresses of existing I/O tags without verification")
    rules_lines.append("- Preserve existing program structure — do not reorganize blocks without approval")
    rules_lines.append("- Always verify tag addresses match actual hardware configuration")
    rules_lines.append("- Never modify safety-critical blocks without explicit approval (see Safety-Critical Blocks)")
    rules_lines.append("")
    rules_lines.append("### Code Style")
    comment_lang = _detect_comment_language(blocks) if blocks else "English"
    lang_note = f"Comments in {comment_lang}" if comment_lang != "English" else "Comments in project language"
    rules_lines.append(f"- Primary language: **{primary_lang}** — Prefer {primary_lang} for new blocks (match project conventions)")
    rules_lines.append("- Use meaningful variable names matching existing conventions")
    rules_lines.append(f"- {lang_note}, UPPER_SNAKE_CASE for all tags and blocks")
    rules_lines.append("- Use symbolic names, never absolute addresses (`\"Tag_Name\"` not `%I0.0`)")
    rules_lines.append("- Keep interfaces minimal — only expose what is needed")
    rules_lines.append("- Mark changes with `// CHANGED:` or `// ADDED:` comments")
    rules_lines.append("")
    rules_lines.append("### Testing")
    rules_lines.append("- Verify changes in simulation before downloading to PLC")
    rules_lines.append("- Check cross-references before renaming or moving blocks")
    rules_lines.append("- Validate HMI tag bindings still work after PLC changes")
    rules_lines.append("")
    add_section("Rules for AI", rules_lines)

    # ===== 5. How to Help Me =====
    help_lines = ["## How to Help Me", ""]
    help_lines.append("### Block Report Format")
    help_lines.append("Each `.md` file in `Program_Blocks/` contains: block header (type, number, language, folder),")
    help_lines.append("full interface (inputs/outputs/inouts/statics/temps with types and start values),")
    help_lines.append("per-network code with titles/comments, call list, tag cross-references, and source file path.")
    help_lines.append("Read these first before suggesting any code changes.")
    help_lines.append("")

    help_lines.append("### Tracing Tags")
    help_lines.append("1. Start from the tag name — read the block's `.md` file in `Program_Blocks/`")
    help_lines.append("2. Use Tag Cross-References — check \"Tag References\" in block reports")
    help_lines.append("3. Check HMI bindings — look in `hmi_screens/` reports")
    example_tag = ""
    if plc_data and tag_xref:
        for tag_name in sorted(tag_xref.keys()):
            if "." in tag_name and len(tag_name) > 10:
                example_tag = tag_name
                break
    example_hint = f" — for `{example_tag}`, read the DB interface" if example_tag else ""
    help_lines.append(f"4. Trace full path{example_hint}")
    help_lines.append("")

    help_lines.append("### Modifying SCL/STL Code")
    help_lines.append("1. Read the block's `.md` first — has full code, interface, calls, tag refs")
    help_lines.append("2. Show exact code change — complete modified section, not just description")
    help_lines.append("3. Preserve structure — keep REGION/END_REGION blocks, network comments, indentation")
    help_lines.append("4. Verify interface — if adding parameters, update all call sites")
    help_lines.append("")

    help_lines.append("### Analyzing Call Chains")
    main_ob = _find_main_ob(blocks) if blocks else None
    ob_ref = f"OB{main_ob['block_number']}" if main_ob else "main cyclic OB"
    help_lines.append(f"1. Start from {ob_ref} Main (see Execution Order below)")
    help_lines.append("2. Follow calls downward via each block's \"Calls\" section")
    help_lines.append("3. Check data dependencies via Data Flow Map")
    help_lines.append("4. Use Instance DB Mapping for FB instance data blocks")
    help_lines.append("")

    # Dynamic: Working with Alarms & Safety
    if plc_data:
        safety_blocks_list = detect_safety_blocks(blocks)
        alarm_fcs = [s for s in safety_blocks_list if s["type"] == "FC" and "ALARM" in ";".join(s["reasons"]).upper()]
        alarm_fbs = [s for s in safety_blocks_list if s["type"] == "FB" and "ALARM" in ";".join(s["reasons"]).upper()]
        guard_blocks = [s for s in safety_blocks_list if "GUARD" in ";".join(s["reasons"]).upper() or "BEWAKING" in ";".join(s["reasons"]).upper()]
        safety_other = [s for s in safety_blocks_list if s not in alarm_fcs and s not in alarm_fbs and s not in guard_blocks]

        help_lines.append("### Working with Alarms & Safety")
        if alarm_fcs:
            fc_names = ", ".join(f"`{s['label']}`" for s in alarm_fcs[:3])
            help_lines.append(f"- Alarm FCs: {fc_names} — coordinate alarm collection and handling")
        if alarm_fbs:
            fb_names = ", ".join(f"`{s['label']}`" for s in alarm_fbs[:3])
            help_lines.append(f"- Alarm FBs: {fb_names} — process alarm instances per subsystem")
        if guard_blocks:
            guard_names = ", ".join(f"`{s['label']}`" for s in guard_blocks[:3])
            help_lines.append(f"- Guard/monitor blocks: {guard_names} — changes affect machine safety")
        if not alarm_fcs and not alarm_fbs and not guard_blocks and safety_other:
            for s in safety_other[:3]:
                reasons = "; ".join(s["reasons"][:2])
                help_lines.append(f"- `{s['label']}` — {reasons}")
        if not safety_blocks_list:
            help_lines.append("- Check Safety-Critical Blocks section below for flagged blocks")
        help_lines.append("")

    help_lines.append("### HMI Changes")
    help_lines.append("- Check tag bindings first via HMI <-> PLC Tag Bridge below")
    help_lines.append("- Verify PLC tag exists before adding HMI binding")
    help_lines.append("- Show affected screens when changing a PLC tag")
    help_lines.append("")
    help_lines.append("### Step Sequencers")
    help_lines.append("- Read the step DB first — step sequencers use dedicated DBs")
    help_lines.append("- Show full step transition: entry condition + actions + transition")
    help_lines.append("")

    # Dynamic: Communication
    if plc_data:
        comm_blocks = []
        for b in blocks:
            btype = b.get("block_type", "")
            if btype in ("STRUCT", "UDT"):
                continue
            name_upper = b.get("block_name", "").upper()
            if any(kw in name_upper for kw in ("PUT_TO", "GET_FROM", "COMM", "NETWERK", "NETWORK", "SEND", "RECEIVE")):
                bnum = b.get("block_number", "")
                comm_blocks.append(f"`{btype}{bnum}_{b.get('block_name', '?')}`" if bnum else f"`{b.get('block_name', '?')}`")

        if comm_blocks:
            help_lines.append("### Communication")
            for cb in comm_blocks[:6]:
                help_lines.append(f"- {cb}")
            if len(comm_blocks) > 6:
                help_lines.append(f"- (+{len(comm_blocks)-6} more communication blocks)")
            help_lines.append("")
    help_lines.append("")
    add_section("How to Help Me", help_lines)

    # ===== 6. HMI Screens Overview =====
    hmi_table_lines = build_hmi_screen_table(hmi_data)
    if hmi_table_lines:
        sec = ["## HMI Screens Overview", ""]
        sec.extend(hmi_table_lines)
        sec.append("")
        add_section("HMI Screens Overview", sec)

    # ===== 7. HMI Navigation Map =====
    nav_lines = build_hmi_navigation_map(hmi_data)
    if nav_lines:
        sec = ["## HMI Navigation Map", ""]
        sec.extend(nav_lines)
        sec.append("")
        add_section("HMI Navigation Map", sec)

    # ===== 8. I/O Hardware Summary =====
    if plc_data and plc_tags:
        io_summary = build_io_summary(plc_tags)
        if io_summary:
            sec = ["## I/O Hardware Summary", ""]
            sec.append("| Area | Count | Byte Range | Data Types |")
            sec.append("|------|-------|------------|------------|")
            for key in ("inputs", "outputs", "memory"):
                if key not in io_summary:
                    continue
                area = io_summary[key]
                dtypes_str = ", ".join(f"{dt}" for dt in list(area["dtypes"].keys())[:4])
                sec.append(f"| {area['label']} | {area['count']} | {area['bytes']} | {dtypes_str} |")
            sec.append("")
            add_section("I/O Hardware Summary", sec)

    # ===== 9. DB Purpose Table =====
    if plc_data:
        db_blocks = [b for b in blocks if b.get("block_type") == "DB"]
        if db_blocks:
            sec = ["## Quick Reference: DB Purpose Table", ""]
            sec.append("| DB | Type | Purpose | Folder |")
            sec.append("|----|------|---------|--------|")
            for b in sorted(db_blocks, key=lambda x: x.get("block_number", 0)):
                bnum = b.get("block_number", "")
                bname = b.get("block_name", "?")
                purpose = infer_db_purpose(b)
                folder = _short_folder(b.get("folder", ""))
                sec.append(f"| DB{bnum}_{bname} | DB | {purpose} | {folder} |")
            sec.append("")

            # Instance DB groupings
            idb_blocks = [b for b in blocks if b.get("block_type") == "IDB"]
            if idb_blocks:
                fb_groups = defaultdict(list)
                for b in idb_blocks:
                    fb_name = b.get("instance_of_name", "Unknown")
                    fb_groups[fb_name].append(b)

                sec.append("### Instance DBs — key groupings")
                sec.append("")
                sec.append("| FB | Instance DBs | Count | Purpose |")
                sec.append("|----|-------------|-------|---------|")
                for fb_name in sorted(fb_groups.keys()):
                    grp = fb_groups[fb_name]
                    count = len(grp)
                    idb_names = ", ".join(
                        _clean_idb_name(b.get("block_name", "?"))
                        for b in sorted(grp, key=lambda x: x.get("block_name", ""))[:5]
                    )
                    if count > 5:
                        idb_names += f" +{count-5} more"
                    purpose = _infer_fb_purpose(fb_name)
                    sec.append(f"| {fb_name} | {idb_names} | {count} | {purpose} |")
                sec.append("")
            add_section("Quick Reference: DB Purpose Table", sec)

    # ===== 10. Execution Order =====
    if plc_data:
        exec_order = build_execution_order(plc_data)
        if exec_order:
            main_ob = _find_main_ob(blocks)
            ob_label = f"OB{main_ob['block_number']}" if main_ob else "Main OB"
            sec = [f"## Execution Order ({ob_label} Main)", ""]
            sec.append(f"{ob_label} cyclic call sequence (PLC scan order):")
            sec.append("")
            for i, call in enumerate(exec_order, 1):
                sub_calls = call_tree.get(call, [])
                line = f"{i}. `{call}`"
                if sub_calls:
                    line += " -> " + ", ".join(f"`{c}`" for c in sub_calls[:5])
                    if len(sub_calls) > 5:
                        line += f" (+{len(sub_calls)-5})"
                sec.append(line)
            sec.append("")
            add_section(f"Execution Order ({ob_label} Main)", sec)

    # ===== 11. Organization Blocks =====
    if plc_data:
        all_obs = build_ob_summary(blocks)
        if len(all_obs) > 1:
            sec = ["## Organization Blocks", ""]
            sec.append("| OB | Language | Purpose | Calls |")
            sec.append("|----|----------|---------|-------|")
            for ob in all_obs:
                bnum = ob["number"]
                purpose = ob["comment"] or ob["name"]
                calls_str = ", ".join(ob["calls"][:5]) if ob["calls"] else "—"
                if len(ob["calls"]) > 5:
                    calls_str += f" (+{len(ob['calls'])-5})"
                sec.append(f"| OB{bnum} | {ob['language']} | {purpose} | {calls_str} |")
            sec.append("")
            add_section("Organization Blocks", sec)

    # ===== 12. Data Flow Map =====
    if plc_data:
        data_flow = build_data_flow(plc_data)
        if data_flow:
            sec = ["## Data Flow Map", ""]
            sec.append("Which executable blocks reference which DBs (data dependencies):")
            sec.append("")
            sec.append("| Block | DBs Referenced |")
            sec.append("|-------|---------------|")
            for bname, dbs in sorted(data_flow.items()):
                dbs_str = ", ".join(dbs[:8])
                if len(dbs) > 8:
                    dbs_str += f" (+{len(dbs)-8})"
                sec.append(f"| {bname} | {dbs_str} |")
            sec.append("")

            # Reverse Data Flow
            reverse_flow = build_reverse_data_flow(data_flow)
            if reverse_flow:
                sec.append("### Reverse Data Flow (DB -> Consumers)")
                sec.append("")
                sec.append("Which blocks consume each DB (modification impact):")
                sec.append("")
                sec.append("| DB | Referenced By |")
                sec.append("|----|--------------|")
                for db_name, consumers in sorted(reverse_flow.items()):
                    c_str = ", ".join(consumers[:6])
                    if len(consumers) > 6:
                        c_str += f" (+{len(consumers)-6})"
                    sec.append(f"| {db_name} | {c_str} |")
                sec.append("")
            add_section("Data Flow Map", sec)

    # ===== 13. Instance DB Mapping =====
    if plc_data:
        instance_map = build_instance_db_map(blocks)
        if instance_map:
            fb_idbs = defaultdict(list)
            for m in instance_map:
                fb_idbs[m["fb_name"]].append(m)

            sec = ["## Instance DB Mapping", ""]
            sec.append("| FB | Instance DB | Folder |")
            sec.append("|----|-------------|--------|")
            for fb_name in sorted(fb_idbs.keys()):
                grp = fb_idbs[fb_name]
                for m in sorted(grp, key=lambda x: x.get("folder", "")):
                    sec.append(f"| {fb_name} | {m['idb_name']} | {m['folder']} |")
            sec.append("")
            add_section("Instance DB Mapping", sec)

    # ===== 14. Safety-Critical Blocks =====
    if plc_data:
        safety_blocks = detect_safety_blocks(blocks)
        if safety_blocks:
            sec = ["## Safety-Critical Blocks", ""]
            sec.append("| Block | Type | Reason |")
            sec.append("|-------|------|--------|")
            for s in safety_blocks:
                reasons_str = "; ".join(s["reasons"][:2])
                sec.append(f"| {s['label']} | {s['type']} | {reasons_str} |")
            sec.append("")
            add_section("Safety-Critical Blocks", sec)

    # ===== 15. Key Tags & Compact HMI Tag Bridge =====
    tags_bridge_added = False
    if plc_data and tag_xref:
        def _xref_count(item):
            val = item[1]
            if isinstance(val, dict):
                return len(val.get("used_in", []))
            return len(val)
        top_tags = sorted(tag_xref.items(), key=_xref_count, reverse=True)[:10]
        if top_tags:
            sec = ["## Key Tags & HMI Bridge", ""]
            sec.append("### Most Referenced Tags")
            sec.append("")
            sec.append("| Tag | Used In |")
            sec.append("|-----|---------|")
            for tag, refs in top_tags:
                if isinstance(refs, dict):
                    block_list = refs.get("used_in", [])
                else:
                    block_list = refs
                blocks_str = ", ".join(str(b) for b in block_list[:4])
                if len(block_list) > 4:
                    blocks_str += f" (+{len(block_list)-4})"
                sec.append(f"| {tag} | {blocks_str} |")
            sec.append("")

            # Compact HMI Tag Bridge (append to same section)
            if hmi_data:
                bridge_lines = build_compact_hmi_bridge(hmi_data)
                if bridge_lines:
                    sec.append("### HMI <-> PLC Tag Bridge")
                    sec.append("")
                    sec.extend(bridge_lines)
                    sec.append("")

            add_section("Key Tags & HMI Bridge", sec)
            tags_bridge_added = True

    # Standalone HMI Tag Bridge if no PLC data
    if hmi_data and not tags_bridge_added:
        bridge_lines = build_compact_hmi_bridge(hmi_data)
        if bridge_lines:
            sec = ["## HMI <-> PLC Tag Bridge", ""]
            sec.extend(bridge_lines)
            sec.append("")
            add_section("HMI <-> PLC Tag Bridge", sec)

    # ===== 16. PLC Data Types =====
    if plc_data:
        udt_blocks_list = [b for b in blocks if b.get("block_type") in ("STRUCT", "UDT")]
        if udt_blocks_list:
            udt_summary = build_udt_summary(blocks)
            sec = ["## PLC Data Types (UDT/STRUCT)", ""]
            for udt in udt_summary:
                sec.append(f"### {udt['name']} ({udt['member_count']} members)")
                sec.append("")
                if udt["members"]:
                    sec.append("| Member | Data Type | Comment |")
                    sec.append("|--------|-----------|---------|")
                    for m in udt["members"]:
                        comment = m.get("comment", "")
                        sec.append(f"| {m['name']} | {m['data_type']} | {comment} |")
                    sec.append("")
            add_section("PLC Data Types (UDT/STRUCT)", sec)

    # ===== 17. Subsystem Overview =====
    if plc_data:
        subsystem_overview = build_subsystem_overview(blocks)
        if subsystem_overview and len(subsystem_overview) > 1:
            sec = ["## Subsystem Overview", ""]
            sec.append("Functional subsystems derived from program folder structure:")
            sec.append("")
            sec.append("| Subsystem | Blocks | Types | Key Executables |")
            sec.append("|-----------|--------|-------|-----------------|")
            for name, info in subsystem_overview.items():
                types_str = ", ".join(f"{c}x{t}" for t, c in info["types"].most_common(4))
                key_str = ", ".join(info["key_blocks"][:3])
                if len(info["key_blocks"]) > 3:
                    key_str += f" (+{len(info['key_blocks'])-3})"
                sec.append(f"| {name} | {info['blocks']} | {types_str} | {key_str or '—'} |")
            sec.append("")
            add_section("Subsystem Overview", sec)

    # ===== 18. Conventions =====
    if plc_data:
        sec = ["## Conventions", ""]

        i_tags = sum(1 for info in plc_tags.values()
                    if isinstance(info, dict) and re.match(r'^%I', info.get("address", "")))
        q_tags = sum(1 for info in plc_tags.values()
                    if isinstance(info, dict) and re.match(r'^%Q', info.get("address", "")))
        m_tags = sum(1 for info in plc_tags.values()
                    if isinstance(info, dict) and re.match(r'^%M', info.get("address", "")))

        tables = Counter()
        for info in plc_tags.values():
            if isinstance(info, dict) and info.get("table"):
                tables[info["table"]] += 1
        tables_str = ", ".join(f"{t} ({c})" for t, c in tables.most_common(5))

        prefixes = Counter()
        for b in blocks:
            name = b.get("block_name", "")
            parts = name.split("_")
            if len(parts) > 1:
                prefixes[parts[0]] += 1
        prefix_str = ", ".join(f"{p}_ ({c})" for p, c in prefixes.most_common(5))

        by_type = defaultdict(list)
        for b in blocks:
            bnum = b.get("block_number")
            if bnum:
                by_type[b.get("block_type", "?")].append(bnum)
        range_parts = []
        for btype in sorted(by_type.keys()):
            nums = by_type[btype]
            range_parts.append(f"{btype}{min(nums)}–{btype}{max(nums)}")

        sec.append(f"- Tags: UPPER_SNAKE_CASE, address prefixes I ({i_tags}), Q ({q_tags}), M ({m_tags})")
        sec.append(f"- Tag tables: {tables_str}")
        sec.append(f"- Blocks: UPPER_SNAKE_CASE, prefixes {prefix_str}")
        sec.append(f"- DB ranges: {', '.join(range_parts)}")

        udt_list = [b for b in blocks if b.get("block_type") in ("STRUCT", "UDT")]
        if udt_list:
            udt_names = ", ".join(b.get("block_name", "") for b in udt_list[:8])
            if len(udt_list) > 8:
                udt_names += f" (+{len(udt_list)-8})"
            sec.append(f"- PLC types ({len(udt_list)}): {udt_names}")
        sec.append("")
        add_section("Conventions", sec)

    # ===== 19. Project Structure =====
    if plc_data:
        folder_tree = build_folder_tree(blocks)
        sec = ["## Project Structure", ""]
        sec.append("```")
        for folder, block_names in sorted(folder_tree.items()):
            display = folder if folder != "/" else "(root)"
            sec.append(f"{display}/")
            for bn in sorted(block_names):
                sec.append(f"  {bn}")
        sec.append("```")
        sec.append("")
        add_section("Project Structure", sec)

    # ===== 20. Step Sequencers =====
    if plc_data:
        sequencers = detect_step_sequencers(blocks)
        if sequencers:
            sec = ["## Step Sequencers (State Machines)", ""]
            sec.append("| Step DB | Sequence FC | Purpose |")
            sec.append("|---------|-------------|---------|")
            for s in sequencers:
                if s["type"] == "DB":
                    continue
                step_db = s.get("step_db", "") or s.get("comment", "")
                sec.append(f"| {step_db or '—'} | {s['label']} ({s['language']}) | {s['comment'] or '—'} |")
            sec.append("")
            add_section("Step Sequencers (State Machines)", sec)

    # ===== 21. Data Sources =====
    ds_lines = build_data_sources_report(plc_data, hmi_data, plc_path if plc_data else None, hmi_path)
    if ds_lines:
        sec = ["## Data Sources", ""]
        sec.extend(ds_lines)
        sec.append("")
        add_section("Data Sources", sec)

    # ===== 22. File Structure =====
    fs_lines = ["## File Structure (Doc_OUTPUT/)", ""]
    fs_lines.append("```")
    fs_lines.append("Doc_OUTPUT/")
    fs_lines.append("├── CLAUDE.md                              <- This file")
    fs_lines.append("├── Program_Blocks/                        <- PLC block .md reports")
    if plc_data:
        udt_list = [b for b in blocks if b.get("block_type") in ("STRUCT", "UDT")]
        if udt_list:
            fs_lines.append("│   ├── PLC_Data_Types/                    <- UDT/STRUCT reports")
    fs_lines.append("│   └── PLC tags/                          <- plc_tags.md")
    if hmi_data:
        fs_lines.append("├── hmi_screens/                           <- HMI screen .md reports + hmi_tags.md")
    fs_lines.append("├── .plc_cache.json                        <- PLC extraction cache")
    if hmi_data and hmi_path:
        hmi_name = os.path.basename(hmi_path)
        fs_lines.append(f"└── {hmi_name:39s} <- HMI data")
    fs_lines.append("```")
    fs_lines.append("")
    add_section("File Structure (Doc_OUTPUT/)", fs_lines)

    # ===== Assemble document with TOC =====
    toc_lines = ["## Contents", ""]
    for title, sec_lines in sections:
        anchor = title.lower().replace(" ", "-").replace("(", "").replace(")", "").replace(",", "")
        anchor = re.sub(r'[^a-z0-9-]', '', anchor)
        toc_lines.append(f"- [{title}](#{anchor})")
    toc_lines.append("")

    all_lines = list(header_lines)
    all_lines.extend(toc_lines)
    for title, sec_lines in sections:
        all_lines.extend(sec_lines)

    # Footer
    all_lines.append("---")
    all_lines.append("")
    all_lines.append("*Auto-generated by `python src/generate_claudemd.py` — regenerate after PLC/HMI extraction.*")
    all_lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(all_lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print(" CLAUDE.md Generator")
    print("=" * 70)

    plc_data, hmi_data, plc_path, hmi_path = find_data()

    print(f" PLC cache:  {plc_path or 'NOT FOUND'}")
    print(f" HMI data:   {hmi_path or 'NOT FOUND'}")

    if not plc_data and not hmi_data:
        print("\nERROR: No data found. Run extract_plc_full.py and/or HMI extraction first.")
        print(f"Expected files in: {DOC_OUTPUT}")
        return 1

    content = generate_claude_md(plc_data, hmi_data, hmi_path or "")

    os.makedirs(DOC_OUTPUT, exist_ok=True)
    output_path = os.path.join(DOC_OUTPUT, "CLAUDE.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    line_count = content.count("\n") + 1
    print(f"\nGenerated: {output_path}")
    print(f"Lines: {line_count}")
    print("Done.")
    return 0


if __name__ == "__main__":
    exit(main())
