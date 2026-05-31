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

def build_execution_order(plc_data):
    """Extract OB1 main program execution order."""
    if not plc_data:
        return []
    blocks = plc_data.get("blocks", [])
    for b in blocks:
        if b.get("block_type") == "OB" and b.get("block_number") == 1:
            return b.get("calls", [])
    return plc_data.get("call_tree", {}).get("Main", [])


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


# ---------------------------------------------------------------------------
# CLAUDE.md generation
# ---------------------------------------------------------------------------

def generate_claude_md(plc_data, hmi_data):
    """Assemble comprehensive CLAUDE.md with front-loaded critical info."""
    lines = []

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
    lines.append(f"# CLAUDE.md — {project_name}")
    lines.append("")
    lines.append("```yaml")
    lines.append("role: PLC/HMI Automation Engineer")
    lines.append("software: Siemens TIA Portal")
    if plc_name:
        lines.append(f"plc: {plc_name}")
    if hmi_data:
        dev = hmi_data.get("extraction_info", {}).get("device_filter", "")
        if dev:
            lines.append(f"hmi: {dev}")
    # Dynamic languages from actual data
    all_langs = sorted(set(lang_counts.keys())) if lang_counts else ["SCL", "STL", "DB"]
    lines.append(f"languages: {', '.join(all_langs)}")
    lines.append("```")
    lines.append("")

    # One-line stats
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
    lines.append(f"**{total} blocks** ({fb_c} FB, {fc_c} FC, {ob_c} OB, {db_c} DB, {idb_c} IDB) · **{tags_c} PLC tags** · **{hmi_screens_count} HMI screens** · {lang_str}")
    lines.append("")

    # ===== 2. Rules for AI =====
    lines.append("## Rules for AI")
    lines.append("")
    lines.append("### Safety")
    lines.append("- NEVER change addresses of existing I/O tags without verification")
    lines.append("- Preserve existing program structure — do not reorganize blocks without approval")
    lines.append("- Always verify tag addresses match actual hardware configuration")
    lines.append("- Never modify safety-critical blocks without explicit approval (see Safety-Critical Blocks)")
    lines.append("")
    lines.append("### Code Style")
    comment_lang = _detect_comment_language(blocks) if blocks else "English"
    lang_note = f"Comments in {comment_lang}" if comment_lang != "English" else "Comments in project language"
    lines.append(f"- Primary language: **{primary_lang}** — Prefer SCL for new blocks (structured, readable)")
    lines.append("- Use meaningful variable names matching existing conventions")
    lines.append(f"- {lang_note}, UPPER_SNAKE_CASE for all tags and blocks")
    lines.append("- Use symbolic names, never absolute addresses (`\"Tag_Name\"` not `%I0.0`)")
    lines.append("- Keep interfaces minimal — only expose what's needed")
    lines.append("- Mark changes with `// CHANGED:` or `// ADDED:` comments")
    lines.append("")
    lines.append("### Testing")
    lines.append("- Verify changes in simulation before downloading to PLC")
    lines.append("- Check cross-references before renaming or moving blocks")
    lines.append("- Validate HMI tag bindings still work after PLC changes")
    lines.append("")

    # ===== 3. How to Help Me =====
    lines.append("## How to Help Me")
    lines.append("")
    lines.append("### Block Report Format")
    lines.append("Each `.md` file in `Program_Blocks/` contains: block header (type, number, language, folder),")
    lines.append("full interface (inputs/outputs/inouts/statics/temps with types and start values),")
    lines.append("per-network code with titles/comments, call list, tag cross-references, and source file path.")
    lines.append("Read these first before suggesting any code changes.")
    lines.append("")

    lines.append("### Tracing Tags")
    lines.append("1. Start from the tag name — read the block's `.md` file in `Program_Blocks/`")
    lines.append("2. Use Tag Cross-References — check \"Tag References\" in block reports")
    lines.append("3. Check HMI bindings — look in `hmi_screens/` reports")
    # Dynamic example tag from actual data
    example_tag = ""
    if plc_data and tag_xref:
        for tag_name in sorted(tag_xref.keys()):
            if "." in tag_name and len(tag_name) > 10:
                example_tag = tag_name
                break
    example_hint = f" — for `{example_tag}`, read the DB interface" if example_tag else ""
    lines.append(f"4. Trace full path{example_hint}")
    lines.append("")

    lines.append("### Modifying SCL/STL Code")
    lines.append("1. Read the block's `.md` first — has full code, interface, calls, tag refs")
    lines.append("2. Show exact code change — complete modified section, not just description")
    lines.append("3. Preserve structure — keep REGION/END_REGION blocks, network comments, indentation")
    lines.append("4. Verify interface — if adding parameters, update all call sites")
    lines.append("")

    lines.append("### Analyzing Call Chains")
    lines.append("1. Start from OB1 Main (see Execution Order below)")
    lines.append("2. Follow calls downward via each block's \"Calls\" section")
    lines.append("3. Check data dependencies via Data Flow Map")
    lines.append("4. Use Instance DB Mapping for FB instance data blocks")
    lines.append("")

    # Dynamic: Working with Alarms & Safety (auto-detected blocks)
    if plc_data:
        safety_blocks_list = detect_safety_blocks(blocks)
        alarm_fcs = [s for s in safety_blocks_list if s["type"] == "FC" and "ALARM" in ";".join(s["reasons"]).upper()]
        alarm_fbs = [s for s in safety_blocks_list if s["type"] == "FB" and "ALARM" in ";".join(s["reasons"]).upper()]
        guard_blocks = [s for s in safety_blocks_list if "GUARD" in ";".join(s["reasons"]).upper() or "BEWAKING" in ";".join(s["reasons"]).upper()]
        safety_other = [s for s in safety_blocks_list if s not in alarm_fcs and s not in alarm_fbs and s not in guard_blocks]

        lines.append("### Working with Alarms & Safety")
        if alarm_fcs:
            fc_names = ", ".join(f"`{s['label']}`" for s in alarm_fcs[:3])
            lines.append(f"- Alarm FCs: {fc_names} — coordinate alarm collection and handling")
        if alarm_fbs:
            fb_names = ", ".join(f"`{s['label']}`" for s in alarm_fbs[:3])
            lines.append(f"- Alarm FBs: {fb_names} — process alarm instances per subsystem")
        if guard_blocks:
            guard_names = ", ".join(f"`{s['label']}`" for s in guard_blocks[:3])
            lines.append(f"- Guard/monitor blocks: {guard_names} — changes affect machine safety")
        if not alarm_fcs and not alarm_fbs and not guard_blocks and safety_other:
            for s in safety_other[:3]:
                reasons = "; ".join(s["reasons"][:2])
                lines.append(f"- `{s['label']}` — {reasons}")
        if not safety_blocks_list:
            lines.append("- Check Safety-Critical Blocks section below for flagged blocks")
        lines.append("")

    lines.append("### HMI Changes")
    lines.append("- Check tag bindings first via HMI <-> PLC Tag Bridge below")
    lines.append("- Verify PLC tag exists before adding HMI binding")
    lines.append("- Show affected screens when changing a PLC tag")
    lines.append("")
    lines.append("### Step Sequencers")
    lines.append("- Read the step DB first — step sequencers use dedicated DBs")
    lines.append("- Show full step transition: entry condition + actions + transition")
    lines.append("")

    # Dynamic: Communication (auto-detected)
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
            lines.append("### Communication")
            for cb in comm_blocks[:6]:
                lines.append(f"- {cb}")
            if len(comm_blocks) > 6:
                lines.append(f"- (+{len(comm_blocks)-6} more communication blocks)")
            lines.append("")
    lines.append("")

    # ===== 4. I/O Hardware Summary =====
    if plc_data and plc_tags:
        io_summary = build_io_summary(plc_tags)
        if io_summary:
            lines.append("## I/O Hardware Summary")
            lines.append("")
            lines.append("| Area | Count | Byte Range | Data Types |")
            lines.append("|------|-------|------------|------------|")
            for key in ("inputs", "outputs", "memory"):
                if key not in io_summary:
                    continue
                area = io_summary[key]
                dtypes_str = ", ".join(f"{dt}" for dt in list(area["dtypes"].keys())[:4])
                lines.append(f"| {area['label']} | {area['count']} | {area['bytes']} | {dtypes_str} |")
            lines.append("")

    # ===== 5. DB Purpose Table =====
    udt_blocks = []
    if plc_data:
        db_blocks = [b for b in blocks if b.get("block_type") == "DB"]
        if db_blocks:
            lines.append("## Quick Reference: DB Purpose Table")
            lines.append("")
            lines.append("| DB | Type | Purpose | Folder |")
            lines.append("|----|------|---------|--------|")
            for b in sorted(db_blocks, key=lambda x: x.get("block_number", 0)):
                bnum = b.get("block_number", "")
                bname = b.get("block_name", "?")
                purpose = infer_db_purpose(b)
                folder = _short_folder(b.get("folder", ""))
                lines.append(f"| DB{bnum}_{bname} | DB | {purpose} | {folder} |")
            lines.append("")

            # Instance DB groupings
            idb_blocks = [b for b in blocks if b.get("block_type") == "IDB"]
            if idb_blocks:
                fb_groups = defaultdict(list)
                for b in idb_blocks:
                    fb_name = b.get("instance_of_name", "Unknown")
                    fb_groups[fb_name].append(b)

                lines.append("### Instance DBs — key groupings")
                lines.append("")
                lines.append("| FB | Instance DBs | Count | Purpose |")
                lines.append("|----|-------------|-------|---------|")
                for fb_name in sorted(fb_groups.keys()):
                    grp = fb_groups[fb_name]
                    count = len(grp)
                    idb_names = ", ".join(
                        b.get("block_name", "?").replace("DB_LIJN_", "").replace("DB_", "").replace("FBDB_", "")
                        for b in sorted(grp, key=lambda x: x.get("block_name", ""))[:5]
                    )
                    if count > 5:
                        idb_names += f" +{count-5} more"
                    purpose = _infer_fb_purpose(fb_name)
                    lines.append(f"| {fb_name} | {idb_names} | {count} | {purpose} |")
                lines.append("")

    # ===== 6. Execution Order =====
    if plc_data:
        exec_order = build_execution_order(plc_data)
        if exec_order:
            lines.append("## Execution Order (OB1 Main)")
            lines.append("")
            lines.append("OB1 cyclic call sequence (PLC scan order):")
            lines.append("")
            for i, call in enumerate(exec_order, 1):
                sub_calls = call_tree.get(call, [])
                line = f"{i}. `{call}`"
                if sub_calls:
                    line += " -> " + ", ".join(f"`{c}`" for c in sub_calls[:5])
                    if len(sub_calls) > 5:
                        line += f" (+{len(sub_calls)-5})"
                lines.append(line)
            lines.append("")

    # ===== 7. Organization Blocks =====
    if plc_data:
        all_obs = build_ob_summary(blocks)
        if len(all_obs) > 1:
            lines.append("## Organization Blocks")
            lines.append("")
            lines.append("| OB | Language | Purpose | Calls |")
            lines.append("|----|----------|---------|-------|")
            for ob in all_obs:
                bnum = ob["number"]
                purpose = ob["comment"] or ob["name"]
                calls_str = ", ".join(ob["calls"][:5]) if ob["calls"] else "—"
                if len(ob["calls"]) > 5:
                    calls_str += f" (+{len(ob['calls'])-5})"
                lines.append(f"| OB{bnum} | {ob['language']} | {purpose} | {calls_str} |")
            lines.append("")

    # ===== 8. Data Flow Map =====
    if plc_data:
        data_flow = build_data_flow(plc_data)
        if data_flow:
            lines.append("## Data Flow Map")
            lines.append("")
            lines.append("Which executable blocks reference which DBs (data dependencies):")
            lines.append("")
            lines.append("| Block | DBs Referenced |")
            lines.append("|-------|---------------|")
            for bname, dbs in sorted(data_flow.items()):
                dbs_str = ", ".join(dbs[:8])
                if len(dbs) > 8:
                    dbs_str += f" (+{len(dbs)-8})"
                lines.append(f"| {bname} | {dbs_str} |")
            lines.append("")

            # ===== 9. Reverse Data Flow (DB -> Consumers) =====
            reverse_flow = build_reverse_data_flow(data_flow)
            if reverse_flow:
                lines.append("### Reverse Data Flow (DB -> Consumers)")
                lines.append("")
                lines.append("Which blocks consume each DB (modification impact):")
                lines.append("")
                lines.append("| DB | Referenced By |")
                lines.append("|----|--------------|")
                for db_name, consumers in sorted(reverse_flow.items()):
                    c_str = ", ".join(consumers[:6])
                    if len(consumers) > 6:
                        c_str += f" (+{len(consumers)-6})"
                    lines.append(f"| {db_name} | {c_str} |")
                lines.append("")

    # ===== 10. Instance DB Mapping =====
    if plc_data:
        instance_map = build_instance_db_map(blocks)
        if instance_map:
            fb_idbs = defaultdict(list)
            for m in instance_map:
                fb_idbs[m["fb_name"]].append(m)

            lines.append("## Instance DB Mapping")
            lines.append("")
            lines.append("| FB | Instance DB | Folder |")
            lines.append("|----|-------------|--------|")
            for fb_name in sorted(fb_idbs.keys()):
                grp = fb_idbs[fb_name]
                for m in sorted(grp, key=lambda x: x.get("folder", "")):
                    lines.append(f"| {fb_name} | {m['idb_name']} | {m['folder']} |")
            lines.append("")

    # ===== 11. Safety-Critical Blocks =====
    if plc_data:
        safety_blocks = detect_safety_blocks(blocks)
        if safety_blocks:
            lines.append("## Safety-Critical Blocks")
            lines.append("")
            lines.append("| Block | Type | Reason |")
            lines.append("|-------|------|--------|")
            for s in safety_blocks:
                reasons_str = "; ".join(s["reasons"][:2])
                lines.append(f"| {s['label']} | {s['type']} | {reasons_str} |")
            lines.append("")

    # ===== 12. Key Tags & HMI Bridge =====
    if plc_data and tag_xref:
        def _xref_count(item):
            val = item[1]
            if isinstance(val, dict):
                return len(val.get("used_in", []))
            return len(val)
        top_tags = sorted(tag_xref.items(), key=_xref_count, reverse=True)[:10]
        if top_tags:
            lines.append("## Key Tags & HMI Bridge")
            lines.append("")
            lines.append("### Most Referenced Tags")
            lines.append("")
            lines.append("| Tag | Used In |")
            lines.append("|-----|---------|")
            for tag, refs in top_tags:
                if isinstance(refs, dict):
                    block_list = refs.get("used_in", [])
                else:
                    block_list = refs
                blocks_str = ", ".join(str(b) for b in block_list[:4])
                if len(block_list) > 4:
                    blocks_str += f" (+{len(block_list)-4})"
                lines.append(f"| {tag} | {blocks_str} |")
            lines.append("")

    if hmi_data:
        hmi_bridge = build_hmi_plc_bridge(hmi_data)
        if hmi_bridge:
            screen_sorted = sorted(hmi_bridge.items(), key=lambda x: len(x[1]), reverse=True)
            lines.append("### HMI <-> PLC Tag Bridge (top screens)")
            lines.append("")
            for screen, tags in screen_sorted[:10]:
                tag_names = list(tags.keys())
                if len(tag_names) <= 5:
                    tags_str = ", ".join(f"`{t}`" for t in tag_names)
                else:
                    tags_str = ", ".join(f"`{t}`" for t in tag_names[:5])
                    tags_str += f" (+{len(tag_names)-5})"
                lines.append(f"- **{screen}** ({len(tag_names)} tags): {tags_str}")
            lines.append("")

    # ===== 13. PLC Data Types (UDT/STRUCT) =====
    if plc_data:
        udt_blocks = [b for b in blocks if b.get("block_type") in ("STRUCT", "UDT")]
        if udt_blocks:
            udt_summary = build_udt_summary(blocks)
            lines.append("## PLC Data Types (UDT/STRUCT)")
            lines.append("")
            for udt in udt_summary:
                lines.append(f"### {udt['name']} ({udt['member_count']} members)")
                lines.append("")
                if udt["members"]:
                    lines.append("| Member | Data Type | Comment |")
                    lines.append("|--------|-----------|---------|")
                    for m in udt["members"]:
                        comment = m.get("comment", "")
                        lines.append(f"| {m['name']} | {m['data_type']} | {comment} |")
                    lines.append("")

    # ===== 14. Subsystem Overview =====
    if plc_data:
        subsystem_overview = build_subsystem_overview(blocks)
        if subsystem_overview and len(subsystem_overview) > 1:
            lines.append("## Subsystem Overview")
            lines.append("")
            lines.append("Functional subsystems derived from program folder structure:")
            lines.append("")
            lines.append("| Subsystem | Blocks | Types | Key Executables |")
            lines.append("|-----------|--------|-------|-----------------|")
            for name, info in subsystem_overview.items():
                types_str = ", ".join(f"{c}x{t}" for t, c in info["types"].most_common(4))
                key_str = ", ".join(info["key_blocks"][:3])
                if len(info["key_blocks"]) > 3:
                    key_str += f" (+{len(info['key_blocks'])-3})"
                lines.append(f"| {name} | {info['blocks']} | {types_str} | {key_str or '—'} |")
            lines.append("")

    # ===== 15. Conventions =====
    if plc_data:
        lines.append("## Conventions")
        lines.append("")

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

        # Block ranges
        by_type = defaultdict(list)
        for b in blocks:
            bnum = b.get("block_number")
            if bnum:
                by_type[b.get("block_type", "?")].append(bnum)
        range_parts = []
        for btype in sorted(by_type.keys()):
            nums = by_type[btype]
            range_parts.append(f"{btype}{min(nums)}–{btype}{max(nums)}")

        lines.append(f"- Tags: UPPER_SNAKE_CASE, address prefixes I ({i_tags}), Q ({q_tags}), M ({m_tags})")
        lines.append(f"- Tag tables: {tables_str}")
        lines.append(f"- Blocks: UPPER_SNAKE_CASE, prefixes {prefix_str}")
        lines.append(f"- DB ranges: {', '.join(range_parts)}")

        # PLC types count
        udt_list = [b for b in blocks if b.get("block_type") in ("STRUCT", "UDT")]
        if udt_list:
            udt_names = ", ".join(b.get("block_name", "") for b in udt_list[:8])
            if len(udt_list) > 8:
                udt_names += f" (+{len(udt_list)-8})"
            lines.append(f"- PLC types ({len(udt_list)}): {udt_names}")
        lines.append("")

    # ===== 16. Project Structure =====
    if plc_data:
        folder_tree = build_folder_tree(blocks)
        lines.append("## Project Structure")
        lines.append("")
        lines.append("```")
        for folder, block_names in sorted(folder_tree.items()):
            display = folder if folder != "/" else "(root)"
            lines.append(f"{display}/")
            for bn in sorted(block_names):
                lines.append(f"  {bn}")
        lines.append("```")
        lines.append("")

    # ===== 17. Step Sequencers =====
    if plc_data:
        sequencers = detect_step_sequencers(blocks)
        if sequencers:
            lines.append("## Step Sequencers (State Machines)")
            lines.append("")
            lines.append("| Step DB | Sequence FC | Purpose |")
            lines.append("|---------|-------------|---------|")
            for s in sequencers:
                if s["type"] == "DB":
                    continue
                step_db = s.get("step_db", "") or s.get("comment", "")
                lines.append(f"| {step_db or '—'} | {s['label']} ({s['language']}) | {s['comment'] or '—'} |")
            lines.append("")

    # ===== 18. File Structure =====
    lines.append("## File Structure (Doc_OUTPUT/)")
    lines.append("")
    lines.append("```")
    lines.append("Doc_OUTPUT/")
    lines.append("├── CLAUDE.md                              <- This file")
    lines.append("├── Program_Blocks/                        <- PLC block .md reports")
    if plc_data:
        udt_list = [b for b in blocks if b.get("block_type") in ("STRUCT", "UDT")]
        if udt_list:
            lines.append("│   ├── PLC_Data_Types/                    <- UDT/STRUCT reports")
    lines.append("│   └── PLC tags/                          <- plc_tags.md")
    if hmi_data:
        lines.append("├── hmi_screens/                           <- HMI screen .md reports + hmi_tags.md")
    lines.append("├── .plc_cache.json                        <- PLC extraction cache")
    if hmi_data:
        lines.append("└── .hmi_merged.json                       <- Merged HMI data")
    lines.append("```")
    lines.append("")

    # ===== 19. Footer =====
    lines.append("---")
    lines.append("")
    lines.append("*Auto-generated by `python src/generate_claudemd.py` — regenerate after PLC/HMI extraction.*")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


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

    content = generate_claude_md(plc_data, hmi_data)

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
