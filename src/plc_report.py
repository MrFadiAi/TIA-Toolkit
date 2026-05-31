#!/usr/bin/env python3
"""
PLC Report Generator
====================
Reads .plc_cache.json and generates .md files organized like TIA Portal:
  - Doc_OUTPUT/Program_Blocks/{tia_folders}/   (OB, FB, FC, DB, IDB)
  - Doc_OUTPUT/Tags/                            (plc_tags.md)
  - Doc_OUTPUT/PLC_Data_Types/                  (UDT, STRUCT)

Usage:
    python plc_report.py
"""

import json
import os
import re
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")
PROGRAM_BLOCKS_DIR = os.path.join(DOC_OUTPUT, "Program_Blocks")
TYPES_DIR = os.path.join(PROGRAM_BLOCKS_DIR, "PLC_Data_Types")
TAGS_DIR = os.path.join(PROGRAM_BLOCKS_DIR, "PLC tags")


def find_cache():
    """Find the .plc_cache.json file."""
    if os.path.isdir(DOC_OUTPUT):
        for root, dirs, files in os.walk(DOC_OUTPUT):
            for f in files:
                if f == ".plc_cache.json":
                    return os.path.join(root, f)
    return None


def load_data(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def safe_filename(name):
    """Convert a name to a safe filename."""
    return re.sub(r'[^\w\-.]', '_', name)


def block_filename(block):
    """Generate filename: TYPE123_BlockName.md"""
    btype = block.get("block_type", "")
    bnum = block.get("block_number", "")
    bname = block.get("block_name", "UNKNOWN")
    if btype in ("STRUCT", "UDT") or not bnum:
        return safe_filename(bname) + ".md"
    return f"{btype}{bnum}_{safe_filename(bname)}.md"


def block_folder(block):
    """Get the TIA Portal folder for a block, normalized for filesystem."""
    folder = block.get("folder", "") or ""
    if folder == "/":
        return ""
    return safe_filename(folder)


def block_relpath_from_doc_output(block):
    """Get the relative path from Doc_OUTPUT to a block's .md file."""
    btype = block.get("block_type", "")
    if btype in ("STRUCT", "UDT"):
        return os.path.join("Program_Blocks", "PLC_Data_Types", block_filename(block))
    folder = block_folder(block)
    fname = block_filename(block)
    if folder:
        return os.path.join("Program_Blocks", folder, fname)
    return os.path.join("Program_Blocks", fname)


def md_link(name, target_relpath_from_doc, source_relpath_from_doc):
    """Generate a markdown link from source to target, both relative to Doc_OUTPUT."""
    # Compute relative path from source's directory to target
    source_dir = os.path.dirname(source_relpath_from_doc)
    rel = os.path.relpath(target_relpath_from_doc, source_dir).replace("\\", "/")
    return f"[{name}]({rel})"


# ── Block markdown ─────────────────────────────────────────────────────

def generate_block_md(block, called_by=None, tag_xref=None, path_map=None, plc_tags=None):
    """Generate markdown for a single block."""
    if called_by is None:
        called_by = {}
    if tag_xref is None:
        tag_xref = {}
    if path_map is None:
        path_map = {}
    if plc_tags is None:
        plc_tags = {}

    bname = block.get("block_name", "UNKNOWN")
    my_path = block_relpath_from_doc_output(block)

    lines = []
    btype = block.get("block_type", "?")
    bnum = block.get("block_number", "?")
    blang = block.get("programming_language", "?")
    bcomment = block.get("comment", "")
    bfolder = block.get("folder", "")
    iface = block.get("interface", {})
    code = block.get("code", "")
    calls = block.get("calls", [])
    tag_refs = block.get("tag_references", [])

    lines.append(f"# {btype} {bnum}: {bname}")
    lines.append("")

    # Info table
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Type | `{btype}` |")
    lines.append(f"| Number | {bnum} |")
    lines.append(f"| Language | `{blang}` |")
    if bcomment:
        lines.append(f"| Comment | {bcomment} |")
    block_title = block.get("block_title", "")
    if block_title:
        lines.append(f"| Title | {block_title} |")
    if bfolder:
        lines.append(f"| Folder | {bfolder} |")
    source_file = block.get("source_file", "")
    if source_file:
        lines.append(f"| Source File | `{source_file}` |")
    mem_layout = block.get("memory_layout", "")
    if mem_layout:
        lines.append(f"| Memory Layout | {mem_layout} |")
    header_author = block.get("header_author", "")
    if header_author:
        lines.append(f"| Author | {header_author} |")
    header_version = block.get("header_version", "")
    if header_version:
        lines.append(f"| Version | {header_version} |")
    header_family = block.get("header_family", "")
    if header_family:
        lines.append(f"| Family | {header_family} |")
    header_name = block.get("header_name", "")
    if header_name:
        lines.append(f"| Header Name | {header_name} |")
    if btype in ("DB", "GlobalDB", "IDB"):
        db_opc = block.get("db_opc_ua", "")
        if db_opc:
            lines.append(f"| OPC UA Access | {db_opc} |")
        db_web = block.get("db_webserver", "")
        if db_web:
            lines.append(f"| Webserver Access | {db_web} |")
    inst_of = block.get("instance_of_name", "")
    if inst_of:
        inst_type = block.get("instance_of_type", "")
        inst_label = f"{inst_type} " if inst_type else ""
        lines.append(f"| Instance Of | {inst_label}{inst_of} |")
    auto_num = block.get("auto_number", "")
    if auto_num:
        lines.append(f"| Auto Number | {auto_num} |")
    iec_check = block.get("iec_check_enabled", "")
    if iec_check:
        lines.append(f"| IEC Check | {iec_check} |")
    set_eno = block.get("set_eno_automatically", "")
    if set_eno:
        lines.append(f"| Set ENO Auto | {set_eno} |")
    uda_readback = block.get("uda_enable_tag_readback", "")
    if uda_readback:
        lines.append(f"| UDA Tag Readback | {uda_readback} |")
    load_mem = block.get("is_only_load_memory", "")
    if load_mem:
        lines.append(f"| Load Memory Only | {load_mem} |")
    retain_mem = block.get("is_retain_mem_res", "")
    if retain_mem:
        lines.append(f"| Retain Mem Reserve | {retain_mem} |")
    write_prot = block.get("is_write_protected", "")
    if write_prot:
        lines.append(f"| Write Protected | {write_prot} |")
    block_ns = block.get("namespace", "")
    if block_ns:
        lines.append(f"| Namespace | `{block_ns}` |")
    eng_ver = block.get("engineering_version", "")
    if eng_ver:
        lines.append(f"| Engineering Version | {eng_ver} |")
    sec_type = block.get("secondary_type", "")
    if sec_type:
        lines.append(f"| Secondary Type | {sec_type} |")
    mem_reserve = block.get("memory_reserve", "")
    if mem_reserve:
        lines.append(f"| Memory Reserve | {mem_reserve} |")
    failsafe = block.get("is_failsafe_compliant", "")
    if failsafe:
        lines.append(f"| Failsafe Compliant | {failsafe} |")
    has_uda = block.get("has_uda_properties", False)
    if has_uda:
        lines.append(f"| UDA Properties | Yes |")
    btitle = block.get("block_title", "")
    if btitle:
        lines.append(f"| Title | {btitle} |")
    export_set = block.get("export_setting", "")
    if export_set:
        lines.append(f"| Export Setting | {export_set} |")
    created_ts = block.get("created", "")
    if created_ts:
        lines.append(f"| Created | {created_ts} |")
    cultures = block.get("cultures", [])
    if cultures:
        lines.append(f"| Cultures | {', '.join(cultures)} |")
    installed = block.get("installed_products", [])
    if installed:
        prods = "; ".join(f"{p['name']} {p['version']}" for p in installed)
        lines.append(f"| Installed Products | {prods} |")
    lines.append(f"| Interface vars | {block.get('interface_count', 0)} |")
    networks = block.get("networks", [])
    lines.append(f"| Networks | {len(networks)} |")
    lines.append(f"| Calls | {len(calls)} |")
    lines.append(f"| Tag refs | {len(tag_refs)} |")
    lines.append("")

    # Interface
    section_labels = {
        "inputs": "Inputs", "outputs": "Outputs", "inouts": "In/Out",
        "statics": "Static", "temps": "Temp", "constants": "Constants",
        "members": "Members", "returns": "Return",
    }
    has_iface = False
    for key, label in section_labels.items():
        members = iface.get(key, [])
        if not members:
            continue
        has_iface = True
        total = sum(1 + _count_nested(m) for m in members)
        lines.append(f"## {label} ({total})")
        lines.append("")
        _render_members_md(lines, members)
        lines.append("")

    if not has_iface and iface:
        lines.append("*No interface variables.*")
        lines.append("")

    # Calls
    if calls:
        lines.append("## Calls")
        lines.append("")
        for c in calls:
            target = path_map.get(c)
            if target:
                lines.append(f"- {md_link(c, target, my_path)}")
            else:
                lines.append(f"- {c}")
        lines.append("")

    # Called by
    block_called_by = called_by.get(bname, [])
    if block_called_by:
        lines.append("## Called By")
        lines.append("")
        for c in block_called_by:
            target = path_map.get(c)
            if target:
                lines.append(f"- {md_link(c, target, my_path)}")
            else:
                lines.append(f"- {c}")
        lines.append("")

    # Tag references
    if tag_refs:
        lines.append(f"## Tag References ({len(tag_refs)})")
        lines.append("")
        lines.append("| Tag | Address | Data Type | Tag Table |")
        lines.append("|-----|---------|-----------|-----------|")
        for t in tag_refs:
            tag_detail = tag_xref.get(t, {})
            addr = tag_detail.get("plc_tag_address", "")
            dtype = tag_detail.get("data_type", "")
            if not addr or addr == "(not in tag table)":
                addr = ""
            # Look up tag table name from plc_tags
            base_name = t.split(".")[0] if "." in t else t
            tag_info = plc_tags.get(t) or plc_tags.get(base_name)
            tag_table = tag_info.get("table", "") if tag_info else ""
            lines.append(f"| `{t}` | {addr} | {dtype} | {tag_table} |")
        lines.append("")

    # Code — per-network sections
    if networks:
        lines.append(f"## Code ({len(networks)} networks)")
        lines.append("")
        for i, net in enumerate(networks, 1):
            net_lang = net.get("language", "?")
            net_title = net.get("title", "")
            net_comment = net.get("comment", "")
            net_code = net.get("code", "")
            if not net_code:
                continue
            header = f"### Network {i}"
            if net_title:
                header += f": {net_title}"
            lines.append(header)
            lines.append("")
            # Network metadata
            net_meta = []
            net_meta.append(f"Language: `{net_lang}`")
            if net_comment:
                net_meta.append(f"Comment: {net_comment}")
            raw_lang = net.get("net_lang", "")
            if raw_lang and raw_lang != net_lang:
                net_meta.append(f"Raw: `{raw_lang}`")
            lines.append("*" + " | ".join(net_meta) + "*")
            lines.append("")
            lines.append(f"```{net_lang.lower()}")
            for cl in net_code.split("\n"):
                lines.append(cl)
            lines.append("```")
            lines.append("")
    elif code:
        code_lines = code.split("\n")
        lines.append(f"## Code ({len(code_lines)} lines)")
        lines.append("")
        lines.append("```")
        for cl in code_lines:
            lines.append(cl)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _count_nested(member):
    """Count nested members recursively."""
    count = 0
    for child in member.get("members", []):
        count += 1 + _count_nested(child)
    return count


def _render_members_md(lines, members, depth=0):
    """Render interface members as markdown table rows with all extracted fields."""
    if depth == 0:
        lines.append("| Name | Data Type | Start Value | Remanence | Access | Ext-R | Ext-W | Ext-V | SetPoint | Version | Comment |")
        lines.append("|------|-----------|-------------|-----------|--------|-------|-------|-------|----------|---------|---------|")
    for m in members:
        name = m.get("name", "")
        dtype = m.get("data_type", "")
        comment = m.get("comment", "")
        start_val = m.get("start_value", "")
        remanence = m.get("remanence", "")
        accessibility = m.get("accessibility", "")
        version = m.get("version", "")
        informative = m.get("informative", "")
        setpoint = m.get("setpoint", "")
        sp_str = str(setpoint) if isinstance(setpoint, bool) else str(setpoint) if setpoint else ""
        # ExternalAccess flags (OPC UA visibility)
        ext_access = m.get("external_access", {})
        ext_r = "✓" if ext_access.get("ExternalAccessible") else ""
        ext_w = "✓" if ext_access.get("ExternalWritable") else ""
        ext_v = "✓" if ext_access.get("ExternalVisible") else ""
        prefix = "&emsp;" * depth
        # Show section name for sub-members of complex types (Input/Output/Static)
        section_label = m.get("section", "")
        if section_label and depth > 0:
            sec_prefix = "&emsp;" * (depth - 1)
            lines.append(f"| {sec_prefix}**{section_label}:** | | | | | | | | | | |")
        name_cell = f"{prefix}`{name}`"
        if informative:
            name_cell += " *(informative)*"
        lines.append(f"| {name_cell} | {dtype} | {start_val} | {remanence} | {accessibility} | {ext_r} | {ext_w} | {ext_v} | {sp_str} | {version} | {comment} |")
        # Subelement values (array/struct element defaults)
        sub_vals = m.get("subelement_values", [])
        if sub_vals:
            sv_prefix = "&emsp;" * (depth + 1)
            for sv in sub_vals:
                sv_path = sv.get("path", "")
                sv_val = sv.get("start_value", "")
                lines.append(f"| {sv_prefix}`[{sv_path}]` | | {sv_val} | | | | | | | | | |")
        children = m.get("members", [])
        if children:
            _render_members_md(lines, children, depth + 1)


# ── Tags markdown ──────────────────────────────────────────────────────

def generate_tags_md(data, path_map=None, tags_relpath=None):
    """Generate consolidated PLC tags markdown."""
    if path_map is None:
        path_map = {}

    lines = []
    tag_xref = data.get("tag_xref", {})
    tags_path = tags_relpath or os.path.join("Tags", "plc_tags.md")

    lines.append("# PLC Tags Reference")
    lines.append("")
    lines.append(f"Total unique tags: **{len(tag_xref)}**")
    lines.append("")

    if not tag_xref:
        lines.append("*No tag cross-reference data available.*")
        return "\n".join(lines)

    # Sort by usage count
    sorted_tags = sorted(tag_xref.items(), key=lambda kv: len(kv[1].get("used_in", [])), reverse=True)

    # Full tag table
    lines.append("## All Tags")
    lines.append("")
    lines.append("| Tag | Address | Data Type | Used In |")
    lines.append("|-----|---------|-----------|---------|")
    for tag_name, info in sorted_tags:
        addr = info.get("plc_tag_address", "")
        dtype = info.get("data_type", "")
        usage = info.get("used_in", [])
        usage_parts = []
        for u in usage[:5]:
            target = path_map.get(u)
            if target:
                usage_parts.append(md_link(u, target, tags_path))
            else:
                usage_parts.append(u)
        usage_str = ", ".join(usage_parts)
        if len(usage) > 5:
            usage_str += f" (+{len(usage) - 5})"
        lines.append(f"| `{tag_name}` | {addr} | {dtype} | {usage_str} |")
    lines.append("")

    # Tags by address range
    lines.append("## Tags by Address Range")
    lines.append("")
    groups = {"%I": [], "%Q": [], "%M": [], "DB": [], "Other": []}
    for tag_name, info in sorted_tags:
        addr = info.get("plc_tag_address", "")
        if addr.startswith("%I"):
            groups["%I"].append((tag_name, info))
        elif addr.startswith("%Q"):
            groups["%Q"].append((tag_name, info))
        elif addr.startswith("%M"):
            groups["%M"].append((tag_name, info))
        elif addr.startswith("DB"):
            groups["DB"].append((tag_name, info))
        else:
            groups["Other"].append((tag_name, info))

    labels = {"%I": "Inputs (%I)", "%Q": "Outputs (%Q)", "%M": "Markers (%M)",
              "DB": "Data Blocks (DB)", "Other": "Other"}
    for group_name, group_tags in groups.items():
        if not group_tags:
            continue
        lines.append(f"### {labels.get(group_name, group_name)} ({len(group_tags)})")
        lines.append("")
        lines.append("| Tag | Address | Type | Blocks |")
        lines.append("|-----|---------|------|--------|")
        for tag_name, info in group_tags:
            addr = info.get("plc_tag_address", "")
            dtype = info.get("data_type", "")
            usage = info.get("used_in", [])
            lines.append(f"| `{tag_name}` | {addr} | {dtype} | {', '.join(usage[:8])} |")
        lines.append("")

    return "\n".join(lines)


# ── Markdown report generation ─────────────────────────────────────────

def generate_markdown_reports(data):
    """Generate all markdown files with TIA Portal folder structure."""
    blocks = data.get("blocks", [])
    called_by = data.get("called_by", {})
    tag_xref = data.get("tag_xref", {})
    plc_tags = data.get("plc_tags", {})
    tags_relpath = os.path.relpath(TAGS_DIR, DOC_OUTPUT).replace("\\", "/")
    written = []

    # Build path map: block_name -> relpath from Doc_OUTPUT
    path_map = {}
    for block in blocks:
        bname = block.get("block_name", "")
        path_map[bname] = block_relpath_from_doc_output(block)

    # Per-block .md files
    for block in blocks:
        btype = block.get("block_type", "")

        # Determine output directory
        if btype in ("STRUCT", "UDT"):
            out_dir = TYPES_DIR
        else:
            folder = block_folder(block)
            if folder:
                out_dir = os.path.join(PROGRAM_BLOCKS_DIR, folder)
            else:
                out_dir = PROGRAM_BLOCKS_DIR

        os.makedirs(out_dir, exist_ok=True)

        md = generate_block_md(block, called_by, tag_xref, path_map, plc_tags)
        fname = block_filename(block)
        fpath = os.path.join(out_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)
        written.append(fpath)

    # Tags .md
    os.makedirs(TAGS_DIR, exist_ok=True)
    tags_path = os.path.join(TAGS_DIR, "plc_tags.md")
    tags_md = generate_tags_md(data, path_map, os.path.join(tags_relpath, "plc_tags.md"))
    with open(tags_path, "w", encoding="utf-8") as f:
        f.write(tags_md)
    written.append(tags_path)

    # Summary index .md
    index_md = generate_index_md(data, path_map)
    index_path = os.path.join(PROGRAM_BLOCKS_DIR, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_md)
    written.append(index_path)

    return written


def generate_index_md(data, path_map=None):
    """Generate a summary index .md for Program_Blocks with extraction info, block table, and folder tree."""
    if path_map is None:
        path_map = {}

    blocks = data.get("blocks", [])
    summary = data.get("summary", {})
    info = data.get("extraction_info", {})
    call_tree = data.get("call_tree", {})
    called_by = data.get("called_by", {})

    lines = []
    lines.append("# Program Blocks Index")
    lines.append("")

    # Extraction info
    lines.append("## Extraction Info")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Tool | `{info.get('tool', '')}` |")
    lines.append(f"| Source Path | `{info.get('source_path', '')}` |")
    lines.append(f"| PLC Name | {info.get('plc_name', '') or 'N/A'} |")
    lines.append(f"| Timestamp | {info.get('timestamp', '')} |")
    src = info.get("data_sources", {})
    if src:
        lines.append(f"| Block XML files | {src.get('block_xml_files', '')} |")
        lines.append(f"| Blocks parsed | {src.get('blocks_parsed', '')} |")
        lines.append(f"| Parse errors | {src.get('errors', '')} |")
        lines.append(f"| PLC tags loaded | {src.get('plc_tags_loaded', '')} |")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    for k, v in sorted(summary.items()):
        label = k.replace("_", " ").title()
        lines.append(f"| {label} | {v} |")
    lines.append("")

    # All blocks table
    lines.append("## All Blocks")
    lines.append("")
    lines.append("| # | Block | Type | # | Lang | Folder | Interface | Calls | Tags | Comment |")
    lines.append("|---|-------|------|---|------|--------|-----------|-------|------|---------|")
    for i, b in enumerate(blocks, 1):
        bname = b.get("block_name", "?")
        btype = b.get("block_type", "?")
        bnum = b.get("block_number", "")
        blang = b.get("programming_language", "?")
        bfolder = b.get("folder", "")
        iface = b.get("interface_count", 0)
        n_calls = len(b.get("calls", []))
        n_tags = len(b.get("tag_references", []))
        bcomment = (b.get("comment", "") or "").split("\n")[0][:50]
        target = path_map.get(bname)
        if target:
            bfolder_short = bfolder if len(bfolder) <= 30 else "..." + bfolder[-27:]
            link = md_link(f"{btype}{bnum} {bname}", target, "Program_Blocks/index.md")
            lines.append(f"| {i} | {link} | {btype} | {bnum} | {blang} | {bfolder_short} | {iface} | {n_calls} | {n_tags} | {bcomment} |")
        else:
            lines.append(f"| {i} | {bname} | {btype} | {bnum} | {blang} | {bfolder} | {iface} | {n_calls} | {n_tags} | {bcomment} |")
    lines.append("")

    # Folder tree
    from collections import OrderedDict
    folders = OrderedDict()
    for b in blocks:
        bfolder = b.get("folder", "/") or "/"
        if bfolder not in folders:
            folders[bfolder] = []
        btype = b.get("block_type", "?")
        bnum = b.get("block_number", "")
        bname = b.get("block_name", "?")
        label = f"{btype}{bnum}_{bname}" if bnum else bname
        target = path_map.get(bname)
        folders[bfolder].append((label, target))

    lines.append("## Folder Structure")
    lines.append("")
    lines.append("```")
    for folder, block_labels in sorted(folders.items()):
        display = folder if folder != "/" else "(root)"
        lines.append(f"{display}/")
        for label, target in sorted(block_labels):
            lines.append(f"  {label}")
    lines.append("```")
    lines.append("")

    # Call tree roots (entry points)
    all_called = set(called_by.keys())
    all_callers = set(call_tree.keys())
    roots = sorted(all_callers - all_called)
    if roots:
        lines.append("## Call Tree Roots (Entry Points)")
        lines.append("")
        lines.append("Blocks not called by any other block:")
        lines.append("")
        for r in roots:
            calls = call_tree.get(r, [])
            calls_str = ", ".join(calls[:8]) if calls else "(no calls)"
            if len(calls) > 8:
                calls_str += f" (+{len(calls)-8})"
            lines.append(f"- **{r}** -> {calls_str}")
        lines.append("")

    # Parse errors
    errors = data.get("errors", [])
    if errors:
        lines.append("## Parse Errors")
        lines.append("")
        for e in errors:
            lines.append(f"- `{e.get('file', '?')}`: {e.get('error', 'unknown')}")
        lines.append("")

    return "\n".join(lines)


def main():
    import sys

    input_path = find_cache()
    if not input_path:
        print("ERROR: No .plc_cache.json found. Run extract_plc_full.py first.")
        return
    print("Loading data...")
    data = load_data(input_path)

    print("Generating markdown reports...")
    written = generate_markdown_reports(data)
    for f in written:
        print(f"  Written: {os.path.relpath(f, SCRIPT_DIR)}")

    summary = data.get("summary", {})
    print(f"\n  {summary.get('total_blocks', 0)} blocks -> {len(written)} .md files")


if __name__ == "__main__":
    main()
