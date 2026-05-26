#!/usr/bin/env python3
"""
Cross-Reference Search Tool
============================
Searches across PLC blocks, PLC tags, and HMI screen elements to trace
signal flow from HMI through PLC logic or vice versa.

Reads:
  - .plc_cache.json   (PLC blocks, tags, call tree, cross-references)
  - .hmi_merged.json  (HMI screens, elements, tag bindings, PLC links)
  - .hmi_online_data.json (fallback if merged not available)

Usage:
    python cross_reference.py "MyTag"                  # auto-detect query type
    python cross_reference.py "FC_Motor" --block       # force block query
    python cross_reference.py "Start_Button" --hmi     # force HMI query
    python cross_reference.py "Motor_Speed" --tag      # force tag query
    python cross_reference.py "Motor" --verbose        # show extra detail
    python cross_reference.py "IO_Field" --output Dir  # override output dir

Output:
    Console report + Doc_OUTPUT/analysis/cross_reference.md
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def load_json(path):
    """Read JSON with UTF-8 and BOM handling."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def normalize_name(name):
    """Normalize name for case-insensitive matching (uppercase, spaces to underscores)."""
    return name.strip().upper().replace(" ", "_")


def find_plc_cache():
    """Find the .plc_cache.json file anywhere under Doc_OUTPUT."""
    if not os.path.isdir(DOC_OUTPUT):
        return None
    for root, _dirs, files in os.walk(DOC_OUTPUT):
        for f in files:
            if f == ".plc_cache.json":
                return os.path.join(root, f)
    return None


def find_hmi_data():
    """Find best available HMI data source (merged first, then online-only)."""
    merged = os.path.join(DOC_OUTPUT, ".hmi_merged.json")
    if os.path.exists(merged):
        return merged
    online = os.path.join(DOC_OUTPUT, ".hmi_online_data.json")
    if os.path.exists(online):
        return online
    return None


def safe_filename(name):
    """Convert a name to a safe filename."""
    return re.sub(r'[^\w\-.]', '_', name)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_all_data(verbose=False):
    """Load both PLC and HMI data sources. Returns (plc_data, hmi_data)."""
    plc_path = find_plc_cache()
    hmi_path = find_hmi_data()

    plc_data = None
    hmi_data = None

    if plc_path:
        if verbose:
            print(f"  PLC data: {plc_path}")
        plc_data = load_json(plc_path)
        if plc_data:
            info = plc_data.get("extraction_info", {})
            summary = plc_data.get("summary", {})
            if verbose:
                print(f"    PLC: {info.get('plc_name', 'N/A')}, "
                      f"{summary.get('total_blocks', 0)} blocks, "
                      f"{summary.get('unique_tag_refs', 0)} unique tag refs")
    else:
        if verbose:
            print("  PLC data: not found")

    if hmi_path:
        if verbose:
            print(f"  HMI data: {hmi_path}")
        hmi_data = load_json(hmi_path)
        if hmi_data:
            hmi_summary = hmi_data.get("summary", {})
            if verbose:
                print(f"    HMI: {hmi_summary.get('total_screens', 0)} screens, "
                      f"{hmi_summary.get('total_elements', 0)} elements, "
                      f"{hmi_summary.get('bindings_with_plc_tag', 0)} PLC bindings")
    else:
        if verbose:
            print("  HMI data: not found")

    return plc_data, hmi_data


# ---------------------------------------------------------------------------
# Query type detection
# ---------------------------------------------------------------------------
def detect_query_type(query, plc_data, hmi_data):
    """
    Auto-detect whether the query matches a tag, block, or HMI element.
    Returns list of (category, matched_key) tuples.
    """
    matches = []
    q_upper = query.upper()
    q_norm = normalize_name(query)

    # --- TAG matches ---
    if plc_data:
        tag_xref = plc_data.get("tag_xref", {})
        plc_tags = plc_data.get("plc_tags", {})
        # Check tag_xref keys (exact and substring)
        for tag_name in tag_xref:
            if q_norm == normalize_name(tag_name) or q_upper in tag_name.upper():
                matches.append(("tag", tag_name))
        # Also check plc_tags for tags not in xref
        for tag_name in plc_tags:
            if q_norm == normalize_name(tag_name) or q_upper in tag_name.upper():
                if not any(m[0] == "tag" and m[1] == tag_name for m in matches):
                    matches.append(("tag", tag_name))

    # --- BLOCK matches ---
    if plc_data:
        blocks = plc_data.get("blocks", [])
        call_tree = plc_data.get("call_tree", {})
        called_by = plc_data.get("called_by", {})
        # Check block names from blocks array (most complete)
        seen_block_names = set()
        for block in blocks:
            bname = block.get("block_name", "")
            if bname and (q_norm == normalize_name(bname) or q_upper in bname.upper()):
                matches.append(("block", bname))
                seen_block_names.add(bname)
        # Check call_tree and called_by keys for block names not in blocks[]
        for bname in list(call_tree.keys()) + list(called_by.keys()):
            if bname not in seen_block_names:
                if q_norm == normalize_name(bname) or q_upper in bname.upper():
                    matches.append(("block", bname))
                    seen_block_names.add(bname)

    # --- HMI matches ---
    if hmi_data:
        screens = hmi_data.get("screens", [])
        tag_index = hmi_data.get("tag_index", {})
        # Check screen element names and types
        for screen in screens:
            sname = screen.get("screen_name", "")
            for elem in screen.get("elements", []):
                ename = elem.get("name", "")
                etype = elem.get("type", "")
                # Match element name
                if ename and (q_norm == normalize_name(ename) or q_upper in ename.upper()):
                    matches.append(("hmi", f"{sname}/{ename}"))
                # Match element type
                elif q_upper == etype.upper():
                    matches.append(("hmi", f"{sname}/{ename}"))
            # Match screen name
            if q_norm == normalize_name(sname) or q_upper in sname.upper():
                # Add all elements from this screen as HMI matches
                for elem in screen.get("elements", []):
                    ename = elem.get("name", "")
                    key = f"{sname}/{ename}"
                    if not any(m[0] == "hmi" and m[1] == key for m in matches):
                        matches.append(("hmi", key))
        # Check tag_index for HMI tag names
        for hmi_tag in tag_index:
            if q_norm == normalize_name(hmi_tag) or q_upper in hmi_tag.upper():
                for entry in tag_index[hmi_tag]:
                    key = f"{entry.get('screen', '')}/{entry.get('element', '')}"
                    if not any(m[0] == "hmi" and m[1] == key for m in matches):
                        matches.append(("hmi", key))

    return matches


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------
def find_networks_with_tag(tag_name, plc_data, verbose=False):
    """Find specific networks where a tag name appears in the code."""
    results = []
    tag_upper = tag_name.upper()
    tag_base = tag_name.split(".")[0] if "." in tag_name else tag_name

    for block in plc_data.get("blocks", []):
        bname = block.get("block_name", "")
        networks = block.get("networks", [])
        for i, net in enumerate(networks, 1):
            code = net.get("code", "")
            if not code:
                continue
            code_upper = code.upper()
            # Check if the tag (or its base name) appears in the code
            if tag_upper in code_upper or tag_base.upper() in code_upper:
                title = net.get("title", "")
                language = net.get("language", "?")
                # Extract the relevant lines
                relevant_lines = []
                for line in code.split("\n"):
                    if tag_upper in line.upper() or tag_base.upper() in line.upper():
                        relevant_lines.append(line.strip())
                results.append({
                    "block": bname,
                    "network_num": i,
                    "network_title": title,
                    "language": language,
                    "matching_lines": relevant_lines,
                })

    return results


def find_hmi_references_for_tag(tag_name, hmi_data):
    """Find HMI screens/elements that reference a PLC tag."""
    if not hmi_data:
        return []
    results = []
    tag_upper = tag_name.upper()
    tag_base = tag_name.split(".")[0] if "." in tag_name else tag_name

    # Check tag_index first (fast path)
    tag_index = hmi_data.get("tag_index", {})
    for hmi_tag, entries in tag_index.items():
        for entry in entries:
            plc_tag = entry.get("plc_tag", "")
            if plc_tag and (tag_upper == plc_tag.upper() or
                            tag_base.upper() == plc_tag.upper().split(".")[0]):
                results.append({
                    "screen": entry.get("screen", ""),
                    "element": entry.get("element", ""),
                    "hmi_tag": hmi_tag,
                    "plc_tag": plc_tag,
                })

    # Also scan tag_bindings directly for PLC tag references
    seen = set()
    for screen in hmi_data.get("screens", []):
        sname = screen.get("screen_name", "")
        for elem in screen.get("elements", []):
            ename = elem.get("name", "")
            for tb in elem.get("tag_bindings", []):
                plc_tag = tb.get("plc_tag", "")
                hmi_tag = tb.get("hmi_tag", "")
                key = f"{sname}/{ename}/{hmi_tag}"
                if key in seen:
                    continue
                if plc_tag and (tag_upper == plc_tag.upper() or
                                tag_base.upper() == plc_tag.upper().split(".")[0]):
                    seen.add(key)
                    results.append({
                        "screen": sname,
                        "element": ename,
                        "hmi_tag": hmi_tag,
                        "plc_tag": plc_tag,
                    })

    return results


def find_hmi_element(screen_name, element_name, hmi_data):
    """Find a specific HMI element by screen and element name."""
    if not hmi_data:
        return None, None
    for screen in hmi_data.get("screens", []):
        sname = screen.get("screen_name", "")
        if normalize_name(sname) == normalize_name(screen_name):
            for elem in screen.get("elements", []):
                ename = elem.get("name", "")
                if normalize_name(ename) == normalize_name(element_name):
                    return screen, elem
    return None, None


def build_call_chain(block_name, plc_data, direction="both", depth=0, visited=None):
    """
    Build the full call chain for a block.
    direction: "up" (callers), "down" (callees), "both"
    Returns dict with "calls" and "called_by" lists, each a list of (name, depth) tuples.
    """
    if visited is None:
        visited = set()

    result = {"calls": [], "called_by": []}
    call_tree = plc_data.get("call_tree", {})
    called_by = plc_data.get("called_by", {})

    if direction in ("down", "both"):
        _collect_chain(block_name, call_tree, result["calls"], depth, visited.copy(), "down")

    if direction in ("up", "both"):
        _collect_chain(block_name, called_by, result["called_by"], depth, visited.copy(), "up")

    return result


def _collect_chain(name, tree, collector, max_depth, visited, direction):
    """Recursively collect call chain entries."""
    if max_depth > 0 and name in visited:
        return
    visited.add(name)
    targets = tree.get(name, [])
    for target in targets:
        collector.append((target, max_depth + 1))
        if max_depth < 10:  # Prevent infinite recursion
            _collect_chain(target, tree, collector, max_depth + 1, visited, direction)


# ---------------------------------------------------------------------------
# Report formatters
# ---------------------------------------------------------------------------
def format_tag_report(query, tag_name, plc_data, hmi_data, verbose=False):
    """Generate markdown report for a TAG query."""
    lines = []
    tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}
    plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}

    lines.append(f"# Tag Cross-Reference: `{tag_name}`")
    lines.append("")
    lines.append(f"*Query: `{query}`*")
    lines.append("")

    # Tag info table
    tag_detail = tag_xref.get(tag_name, {})
    tag_info = plc_tags.get(tag_name, plc_tags.get(tag_name.split(".")[0], {}))

    lines.append("## Tag Information")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Tag Name | `{tag_name}` |")
    if tag_info:
        lines.append(f"| Address | `{tag_info.get('address', tag_detail.get('plc_tag_address', ''))}` |")
        lines.append(f"| Data Type | `{tag_info.get('data_type', tag_detail.get('data_type', ''))}` |")
        lines.append(f"| Tag Table | `{tag_info.get('table', '')}` |")
        comment = tag_info.get("comment", "")
        if comment:
            lines.append(f"| Comment | {comment} |")
    elif tag_detail:
        lines.append(f"| Address | `{tag_detail.get('plc_tag_address', '')}` |")
        lines.append(f"| Data Type | `{tag_detail.get('data_type', '')}` |")
    else:
        lines.append("| Status | *(not found in tag tables)* |")
    lines.append("")

    # Blocks using this tag
    used_in = tag_detail.get("used_in", [])
    if used_in:
        lines.append(f"## PLC Blocks Using This Tag ({len(used_in)})")
        lines.append("")
        lines.append("| # | Block |")
        lines.append("|---|-------|")
        for i, block_name in enumerate(used_in, 1):
            lines.append(f"| {i} | `{block_name}` |")
        lines.append("")
    else:
        lines.append("## PLC Blocks Using This Tag")
        lines.append("")
        lines.append("*No blocks reference this tag in the extracted data.*")
        lines.append("")

    # Specific networks where the tag appears
    if plc_data:
        networks = find_networks_with_tag(tag_name, plc_data, verbose)
        if networks:
            lines.append(f"## Network Occurrences ({len(networks)})")
            lines.append("")
            for occ in networks:
                header = f"**`{occ['block']}`** — Network {occ['network_num']}"
                if occ["network_title"]:
                    header += f": {occ['network_title']}"
                lines.append(header)
                lines.append("")
                if verbose:
                    lines.append(f"Language: `{occ['language']}`")
                    lines.append("")
                    lines.append("```")
                    for ml in occ["matching_lines"]:
                        lines.append(f"  {ml}")
                    lines.append("```")
                else:
                    for ml in occ["matching_lines"][:5]:
                        lines.append(f"- `{ml}`")
                    if len(occ["matching_lines"]) > 5:
                        lines.append(f"- ... (+{len(occ['matching_lines']) - 5} more)")
                lines.append("")

    # HMI references
    hmi_refs = find_hmi_references_for_tag(tag_name, hmi_data) if hmi_data else []
    if hmi_refs:
        lines.append(f"## HMI References ({len(hmi_refs)})")
        lines.append("")
        lines.append("| Screen | Element | HMI Tag | PLC Tag |")
        lines.append("|--------|---------|---------|----------|")
        for ref in hmi_refs:
            lines.append(f"| {ref['screen']} | `{ref['element']}` | `{ref['hmi_tag']}` | `{ref['plc_tag']}` |")
        lines.append("")
    else:
        lines.append("## HMI References")
        lines.append("")
        lines.append("*No HMI elements reference this tag.*")
        lines.append("")

    return "\n".join(lines)


def format_block_report(query, block_name, plc_data, hmi_data, verbose=False):
    """Generate markdown report for a BLOCK query."""
    lines = []
    blocks = plc_data.get("blocks", []) if plc_data else []
    call_tree = plc_data.get("call_tree", {}) if plc_data else {}
    called_by_map = plc_data.get("called_by", {}) if plc_data else {}
    tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}
    plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}

    # Find the block
    block = None
    for b in blocks:
        if b.get("block_name", "") == block_name:
            block = b
            break

    lines.append(f"# Block Cross-Reference: `{block_name}`")
    lines.append("")
    lines.append(f"*Query: `{query}`*")
    lines.append("")

    # Block info
    if block:
        lines.append("## Block Information")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        btype = block.get("block_type", "?")
        bnum = block.get("block_number", "?")
        blang = block.get("programming_language", "?")
        bfolder = block.get("folder", "")
        bcomment = block.get("comment", "")
        btitle = block.get("block_title", "")
        source_file = block.get("source_file", "")

        lines.append(f"| Type | `{btype}` |")
        lines.append(f"| Number | {bnum} |")
        lines.append(f"| Language | `{blang}` |")
        if bcomment:
            lines.append(f"| Comment | {bcomment} |")
        if btitle:
            lines.append(f"| Title | {btitle} |")
        if bfolder:
            lines.append(f"| Folder | `{bfolder}` |")
        if source_file:
            lines.append(f"| Source File | `{source_file}` |")
        inst_of = block.get("instance_of_name", "")
        if inst_of:
            inst_type = block.get("instance_of_type", "")
            lines.append(f"| Instance Of | `{inst_type} {inst_of}` |")
        lines.append(f"| Interface vars | {block.get('interface_count', 0)} |")
        lines.append(f"| Networks | {len(block.get('networks', []))} |")
        lines.append(f"| Calls | {len(block.get('calls', []))} |")
        lines.append(f"| Tag refs | {len(block.get('tag_references', []))} |")
        lines.append("")
    else:
        lines.append("## Block Information")
        lines.append("")
        lines.append(f"*Block `{block_name}` found in call tree but not in parsed block data.*")
        lines.append("")

    # Call chain
    chain = build_call_chain(block_name, plc_data, direction="both") if plc_data else {"calls": [], "called_by": []}

    calls_direct = call_tree.get(block_name, [])
    callers_direct = called_by_map.get(block_name, [])

    lines.append("## Call Structure")
    lines.append("")

    # What this block calls
    if calls_direct:
        lines.append(f"### Calls ({len(calls_direct)})")
        lines.append("")
        for c in calls_direct:
            # Try to find block type
            c_block = None
            for b in blocks:
                if b.get("block_name") == c:
                    c_block = b
                    break
            if c_block:
                lines.append(f"- `{c_block['block_type']}{c_block.get('block_number', '')} {c}` "
                             f"(`{c_block.get('programming_language', '')}`)")
            else:
                lines.append(f"- `{c}`")
        lines.append("")

        # Transitive callees (verbose)
        if verbose:
            deep_calls = chain["calls"]
            if deep_calls:
                lines.append("#### Transitive Callees")
                lines.append("")
                for target, depth in deep_calls:
                    indent = "  " * min(depth, 6)
                    lines.append(f"{indent}- `{target}` (depth {depth})")
                lines.append("")
    else:
        lines.append("### Calls")
        lines.append("")
        lines.append("*This block does not call any other blocks.*")
        lines.append("")

    # What calls this block
    if callers_direct:
        lines.append(f"### Called By ({len(callers_direct)})")
        lines.append("")
        for c in callers_direct:
            c_block = None
            for b in blocks:
                if b.get("block_name") == c:
                    c_block = b
                    break
            if c_block:
                lines.append(f"- `{c_block['block_type']}{c_block.get('block_number', '')} {c}` "
                             f"(`{c_block.get('programming_language', '')}`)")
            else:
                lines.append(f"- `{c}`")
        lines.append("")
    else:
        lines.append("### Called By")
        lines.append("")
        lines.append("*No blocks call this block (entry point).*")
        lines.append("")

    # Tag references
    if block:
        tag_refs = block.get("tag_references", [])
        if tag_refs:
            lines.append(f"## Tag References ({len(tag_refs)})")
            lines.append("")
            lines.append("| Tag | Address | Data Type | Tag Table | Comment |")
            lines.append("|-----|---------|-----------|-----------|---------|")
            for t in tag_refs:
                tag_detail = tag_xref.get(t, {})
                tag_info = plc_tags.get(t, plc_tags.get(t.split(".")[0] if "." in t else t, {}))
                addr = tag_detail.get("plc_tag_address", "")
                if not addr or addr == "(not in tag table)":
                    addr = tag_info.get("address", "") if tag_info else ""
                dtype = tag_detail.get("data_type", "")
                if not dtype or dtype == "?":
                    dtype = tag_info.get("data_type", "") if tag_info else ""
                tag_table = tag_info.get("table", "") if tag_info else ""
                comment = tag_info.get("comment", "") if tag_info else ""
                lines.append(f"| `{t}` | {addr} | {dtype} | {tag_table} | {comment} |")
            lines.append("")

    # Interface summary
    if block:
        iface = block.get("interface", {})
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
            count = sum(1 + _count_nested(m) for m in members)
            lines.append(f"## Interface: {label} ({count})")
            lines.append("")
            if verbose:
                lines.append("| Name | Data Type | Comment |")
                lines.append("|------|-----------|---------|")
                _render_iface_members(lines, members)
            else:
                for m in members[:10]:
                    mname = m.get("name", "")
                    mdtype = m.get("data_type", "")
                    mcomment = m.get("comment", "")
                    detail = f"`{mname}` : `{mdtype}`"
                    if mcomment:
                        detail += f" — {mcomment}"
                    lines.append(f"- {detail}")
                if len(members) > 10:
                    lines.append(f"- ... (+{len(members) - 10} more)")
            lines.append("")

        if not has_iface and not iface:
            lines.append("## Interface")
            lines.append("")
            lines.append("*No interface data.*")
            lines.append("")

    # HMI traces: find HMI elements that reference tags used in this block
    if block and hmi_data:
        tag_refs = block.get("tag_references", [])
        hmi_traces = []
        for t in tag_refs:
            refs = find_hmi_references_for_tag(t, hmi_data)
            for ref in refs:
                hmi_traces.append({
                    "plc_tag": t,
                    "screen": ref["screen"],
                    "element": ref["element"],
                    "hmi_tag": ref["hmi_tag"],
                })
        if hmi_traces:
            lines.append(f"## HMI Trace ({len(hmi_traces)} connections)")
            lines.append("")
            lines.append("| PLC Tag (in block) | HMI Screen | Element | HMI Tag |")
            lines.append("|-------------------|------------|---------|---------|")
            for trace in hmi_traces:
                lines.append(f"| `{trace['plc_tag']}` | {trace['screen']} | "
                             f"`{trace['element']}` | `{trace['hmi_tag']}` |")
            lines.append("")

    return "\n".join(lines)


def _count_nested(member):
    """Count nested members recursively."""
    count = 0
    for child in member.get("members", []):
        count += 1 + _count_nested(child)
    return count


def _render_iface_members(lines, members, depth=0):
    """Render interface members as markdown table rows."""
    for m in members:
        name = m.get("name", "")
        dtype = m.get("data_type", "")
        comment = m.get("comment", "")
        prefix = "&emsp;" * depth
        lines.append(f"| {prefix}`{name}` | `{dtype}` | {comment} |")
        children = m.get("members", [])
        if children:
            _render_iface_members(lines, children, depth + 1)


def format_hmi_report(query, screen_name, element_name, plc_data, hmi_data, verbose=False):
    """Generate markdown report for an HMI element query."""
    lines = []
    tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}
    plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}

    screen, elem = find_hmi_element(screen_name, element_name, hmi_data)

    lines.append(f"# HMI Element Cross-Reference: `{element_name}`")
    lines.append("")
    lines.append(f"*Query: `{query}`*")
    lines.append("")

    # Element info
    if elem:
        etype = elem.get("type", "")
        text = elem.get("text", "")
        pos = elem.get("position", {})
        io_role = elem.get("io_role", "")

        lines.append("## Element Information")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Screen | `{screen_name}` |")
        lines.append(f"| Element | `{element_name}` |")
        lines.append(f"| Type | `{etype}` |")
        if text:
            lines.append(f"| Text | {text} |")
        if pos and (pos.get("x") or pos.get("y")):
            lines.append(f"| Position | x={pos.get('x', 0)}, y={pos.get('y', 0)}, "
                         f"w={pos.get('w', 0)}, h={pos.get('h', 0)} |")
        if io_role:
            lines.append(f"| Role | `{io_role}` |")
        lines.append("")
    else:
        lines.append("## Element Information")
        lines.append("")
        lines.append(f"*Element `{element_name}` on screen `{screen_name}` not found in HMI data.*")
        lines.append("")

    # Tag bindings
    if elem:
        bindings = elem.get("tag_bindings", [])
        if bindings:
            lines.append(f"## Tag Bindings ({len(bindings)})")
            lines.append("")
            lines.append("| Property | HMI Tag | PLC Tag | PLC Name | Data Type |")
            lines.append("|----------|---------|---------|----------|-----------|")
            for b in bindings:
                prop = b.get("property", "")
                if prop == "js_reference":
                    prop = "*(js)*"
                hmi_tag = b.get("hmi_tag", "")
                plc_tag = b.get("plc_tag", "") or "*(not resolved)*"
                plc_name = b.get("plc_name", "")
                data_type = b.get("data_type", "")
                lines.append(f"| {prop} | `{hmi_tag}` | `{plc_tag}` | {plc_name} | {data_type} |")
            lines.append("")
        else:
            lines.append("## Tag Bindings")
            lines.append("")
            lines.append("*No tag bindings for this element.*")
            lines.append("")

        # Events
        events = elem.get("events", [])
        if events:
            lines.append(f"## Events ({len(events)})")
            lines.append("")
            for ev in events:
                ev_type = ev.get("event_type", ev.get("function", ""))
                navs = ev.get("navigates_to", [])
                ev_tags = ev.get("plc_tags", ev.get("tags_used", []))
                script = ev.get("script", ev.get("code", ""))
                lines.append(f"**{ev_type}**")
                lines.append("")
                if navs:
                    lines.append(f"- Navigates to: {', '.join(f'`{n}`' for n in navs)}")
                if ev_tags:
                    for t in ev_tags:
                        lines.append(f"- Tag: `{t}`")
                if script and len(script) > 5:
                    excerpt = script[:200].replace("\n", " ").strip()
                    lines.append(f"- Script: `{excerpt}{'...' if len(script) > 200 else ''}`")
                lines.append("")
        else:
            lines.append("## Events")
            lines.append("")
            lines.append("*No events for this element.*")
            lines.append("")

    # Trace to PLC: for each resolved PLC tag, show which blocks use it
    if elem and plc_data:
        bindings = elem.get("tag_bindings", [])
        plc_traces = []
        for b in bindings:
            plc_tag = b.get("plc_tag", "")
            if not plc_tag:
                continue
            # Find blocks using this PLC tag
            tag_base = plc_tag.split(".")[0] if "." in plc_tag else plc_tag
            # Check tag_xref for exact and base-name matches
            xref_entry = tag_xref.get(plc_tag) or tag_xref.get(tag_base)
            if xref_entry:
                for block_name in xref_entry.get("used_in", []):
                    plc_traces.append({
                        "hmi_tag": b.get("hmi_tag", ""),
                        "plc_tag": plc_tag,
                        "property": b.get("property", ""),
                        "block": block_name,
                    })

        if plc_traces:
            lines.append(f"## PLC Trace ({len(plc_traces)} connections)")
            lines.append("")
            lines.append("The following PLC tags used by this element are referenced in PLC blocks:")
            lines.append("")
            lines.append("| HMI Tag | PLC Tag | Property | PLC Block |")
            lines.append("|---------|---------|----------|-----------|")
            for trace in plc_traces:
                prop = trace["property"]
                if prop == "js_reference":
                    prop = "*(js)*"
                lines.append(f"| `{trace['hmi_tag']}` | `{trace['plc_tag']}` | {prop} | `{trace['block']}` |")
            lines.append("")

            # Verbose: show network occurrences for each traced PLC tag
            if verbose:
                seen_tags = set()
                for trace in plc_traces:
                    plc_tag = trace["plc_tag"]
                    if plc_tag in seen_tags:
                        continue
                    seen_tags.add(plc_tag)
                    networks = find_networks_with_tag(plc_tag, plc_data, verbose)
                    if networks:
                        lines.append(f"### Network occurrences for `{plc_tag}`")
                        lines.append("")
                        for occ in networks:
                            header = f"**`{occ['block']}`** — Network {occ['network_num']}"
                            if occ["network_title"]:
                                header += f": {occ['network_title']}"
                            lines.append(header)
                            lines.append("")
                            for ml in occ["matching_lines"][:5]:
                                lines.append(f"- `{ml}`")
                            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Multi-result report
# ---------------------------------------------------------------------------
def format_multi_result_report(query, matches, plc_data, hmi_data, verbose=False):
    """Generate a summary report when the query matches multiple categories."""
    lines = []
    lines.append(f"# Cross-Reference Results: `{query}`")
    lines.append("")
    lines.append(f"*Query matched multiple categories. Showing all results.*")
    lines.append("")

    # Group matches by category
    by_category = defaultdict(list)
    for category, key in matches:
        by_category[category].append(key)

    # Summary table
    lines.append("## Match Summary")
    lines.append("")
    lines.append("| Category | Matches | Keys |")
    lines.append("|----------|---------|------|")
    for cat in ("tag", "block", "hmi"):
        if cat in by_category:
            keys = by_category[cat]
            sample = ", ".join(f"`{k}`" for k in keys[:5])
            if len(keys) > 5:
                sample += f" (+{len(keys) - 5})"
            label = cat.upper()
            lines.append(f"| {label} | {len(keys)} | {sample} |")
    lines.append("")

    # Per-category details
    if "tag" in by_category:
        lines.append("## Tag Matches")
        lines.append("")
        tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}
        plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}
        lines.append("| Tag | Address | Data Type | Used In | HMI Refs |")
        lines.append("|-----|---------|-----------|---------|----------|")
        for tag_name in sorted(set(by_category["tag"])):
            detail = tag_xref.get(tag_name, {})
            tag_info = plc_tags.get(tag_name, plc_tags.get(tag_name.split(".")[0] if "." in tag_name else tag_name, {}))
            addr = detail.get("plc_tag_address", "") or (tag_info.get("address", "") if tag_info else "")
            dtype = detail.get("data_type", "") or (tag_info.get("data_type", "") if tag_info else "")
            used_in = detail.get("used_in", [])
            usage = ", ".join(used_in[:3])
            if len(used_in) > 3:
                usage += f" (+{len(used_in) - 3})"
            hmi_refs = find_hmi_references_for_tag(tag_name, hmi_data) if hmi_data else []
            hmi_count = len(hmi_refs)
            lines.append(f"| `{tag_name}` | {addr} | {dtype} | {usage} | {hmi_count} |")
        lines.append("")

    if "block" in by_category:
        lines.append("## Block Matches")
        lines.append("")
        blocks = plc_data.get("blocks", []) if plc_data else []
        lines.append("| Block | Type | Language | Calls | Called By | Tags |")
        lines.append("|-------|------|----------|-------|-----------|------|")
        for block_name in sorted(set(by_category["block"])):
            block = None
            for b in blocks:
                if b.get("block_name") == block_name:
                    block = b
                    break
            call_tree = plc_data.get("call_tree", {}) if plc_data else {}
            called_by_map = plc_data.get("called_by", {}) if plc_data else {}
            if block:
                lines.append(f"| `{block_name}` | `{block.get('block_type', '')}` | "
                             f"`{block.get('programming_language', '')}` | "
                             f"{len(block.get('calls', []))} | "
                             f"{len(called_by_map.get(block_name, []))} | "
                             f"{len(block.get('tag_references', []))} |")
            else:
                n_calls = len(call_tree.get(block_name, []))
                n_callers = len(called_by_map.get(block_name, []))
                lines.append(f"| `{block_name}` | ? | ? | {n_calls} | {n_callers} | ? |")
        lines.append("")

    if "hmi" in by_category:
        lines.append("## HMI Element Matches")
        lines.append("")
        lines.append("| Screen | Element | Type | PLC Bindings |")
        lines.append("|--------|---------|------|-------------|")
        seen = set()
        for key in by_category["hmi"]:
            if key in seen:
                continue
            seen.add(key)
            parts = key.split("/", 1)
            if len(parts) == 2:
                sname, ename = parts
            else:
                continue
            _screen, elem = find_hmi_element(sname, ename, hmi_data)
            if elem:
                bindings = elem.get("tag_bindings", [])
                plc_count = sum(1 for b in bindings if b.get("plc_tag"))
                lines.append(f"| {sname} | `{ename}` | `{elem.get('type', '')}` | {plc_count} |")
            else:
                lines.append(f"| {sname} | `{ename}` | ? | ? |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------
def print_console_report(query, matches, plc_data, hmi_data, verbose=False):
    """Print a compact console summary of the search results."""
    by_category = defaultdict(list)
    for category, key in matches:
        by_category[category].append(key)

    total = len(matches)
    print(f"  Query: '{query}'")
    print(f"  Total matches: {total}")
    for cat in ("tag", "block", "hmi"):
        if cat in by_category:
            keys = by_category[cat]
            print(f"  {cat.upper():>6s}: {len(keys)} matches")
            for k in keys[:8]:
                print(f"          - {k}")
            if len(keys) > 8:
                print(f"          ... (+{len(keys) - 8} more)")

    # Print category-specific console details
    if "tag" in by_category:
        tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}
        plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}
        print(f"\n  --- Tag Details ---")
        for tag_name in sorted(set(by_category["tag"]))[:5]:
            detail = tag_xref.get(tag_name, {})
            tag_info = plc_tags.get(tag_name, plc_tags.get(tag_name.split(".")[0] if "." in tag_name else tag_name, {}))
            addr = detail.get("plc_tag_address", "") or (tag_info.get("address", "") if tag_info else "?")
            dtype = detail.get("data_type", "") or (tag_info.get("data_type", "") if tag_info else "?")
            used_in = detail.get("used_in", [])
            print(f"    {tag_name}")
            print(f"      address: {addr}, type: {dtype}")
            if used_in:
                print(f"      used_in: {', '.join(used_in[:6])}")

    if "block" in by_category:
        blocks = plc_data.get("blocks", []) if plc_data else []
        call_tree = plc_data.get("call_tree", {}) if plc_data else {}
        called_by_map = plc_data.get("called_by", {}) if plc_data else {}
        print(f"\n  --- Block Details ---")
        for block_name in sorted(set(by_category["block"]))[:5]:
            block = None
            for b in blocks:
                if b.get("block_name") == block_name:
                    block = b
                    break
            if block:
                print(f"    {block.get('block_type', '')}{block.get('block_number', '')} {block_name} "
                      f"({block.get('programming_language', '')})")
                calls = call_tree.get(block_name, [])
                callers = called_by_map.get(block_name, [])
                if calls:
                    print(f"      calls: {', '.join(calls[:6])}")
                if callers:
                    print(f"      called_by: {', '.join(callers[:6])}")
            else:
                calls = call_tree.get(block_name, [])
                callers = called_by_map.get(block_name, [])
                print(f"    {block_name} (not in parsed blocks)")
                if calls:
                    print(f"      calls: {', '.join(calls[:6])}")
                if callers:
                    print(f"      called_by: {', '.join(callers[:6])}")

    if "hmi" in by_category:
        print(f"\n  --- HMI Element Details ---")
        seen = set()
        for key in by_category["hmi"][:8]:
            if key in seen:
                continue
            seen.add(key)
            parts = key.split("/", 1)
            if len(parts) == 2:
                sname, ename = parts
                _screen, elem = find_hmi_element(sname, ename, hmi_data)
                if elem:
                    bindings = elem.get("tag_bindings", [])
                    plc_count = sum(1 for b in bindings if b.get("plc_tag"))
                    print(f"    {sname}/{ename} ({elem.get('type', '')}) "
                          f"- {plc_count} PLC bindings")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Cross-Reference Search Tool - Search PLC tags, blocks, and HMI elements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python cross_reference.py "Motor_Start"            # auto-detect query type
  python cross_reference.py "FC_Motor" --block        # search blocks only
  python cross_reference.py "Start_Button" --hmi      # search HMI elements
  python cross_reference.py "DI_5" --tag              # search PLC tags
  python cross_reference.py "Motor" --verbose          # show extra detail
  python cross_reference.py "IO_Field" --output ./out  # custom output dir
""",
    )
    parser.add_argument("query", help="Search term (tag name, block name, or HMI element name)")
    parser.add_argument("--tag", "-t", action="store_true",
                        help="Force query type to PLC tag")
    parser.add_argument("--block", "-b", action="store_true",
                        help="Force query type to PLC block")
    parser.add_argument("--hmi", "-m", action="store_true",
                        help="Force query type to HMI element")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show extra detail (network code, full interface, transitive callees)")
    parser.add_argument("--output", "-o", default=None,
                        help="Override output directory (default: Doc_OUTPUT/analysis/)")

    args = parser.parse_args()

    # --- Banner ---
    print(f"{'=' * 70}")
    print(f" Cross-Reference Search Tool")
    print(f"{'=' * 70}")
    print(f" Query: {args.query}")
    print("")

    # --- Load data ---
    print("Loading data sources...")
    plc_data, hmi_data = load_all_data(verbose=args.verbose)

    if not plc_data and not hmi_data:
        print("\nERROR: No data sources found. Run PLC/HMI extraction first.")
        print(f"  Expected: {os.path.join(DOC_OUTPUT, '.plc_cache.json')}")
        print(f"       and: {os.path.join(DOC_OUTPUT, '.hmi_merged.json')}")
        sys.exit(1)

    # --- Determine query type ---
    force_type = None
    if args.tag:
        force_type = "tag"
    elif args.block:
        force_type = "block"
    elif args.hmi:
        force_type = "hmi"

    if force_type:
        print(f"  Query type: {force_type} (forced)")
        matches = detect_query_type(args.query, plc_data, hmi_data)
        # Filter to forced type only
        matches = [(cat, key) for cat, key in matches if cat == force_type]
        if not matches:
            # For forced types, do a broader search
            matches = _broad_search(args.query, force_type, plc_data, hmi_data)
    else:
        matches = detect_query_type(args.query, plc_data, hmi_data)
        print(f"  Query type: auto-detected")

    if not matches:
        print(f"\n  No matches found for '{args.query}'.")
        print(f"  Try a different search term or use --tag/--block/--hmi to narrow the search.")
        sys.exit(0)

    # --- Print console report ---
    print(f"\n{'=' * 70}")
    print(f" SEARCH RESULTS")
    print(f"{'=' * 70}")
    print_console_report(args.query, matches, plc_data, hmi_data, args.verbose)

    # --- Generate markdown report ---
    # Determine primary match for detailed report
    by_category = defaultdict(list)
    for category, key in matches:
        by_category[category].append(key)

    categories = list(by_category.keys())

    if len(categories) == 1:
        # Single category: generate detailed report
        cat = categories[0]
        if cat == "tag":
            # Use first tag match for detailed report
            md = format_tag_report(args.query, by_category["tag"][0], plc_data, hmi_data, args.verbose)
            if len(by_category["tag"]) > 1:
                # Add summary of additional tag matches
                md += "\n\n## Additional Tag Matches\n\n"
                for extra_tag in by_category["tag"][1:]:
                    md += f"- `{extra_tag}`\n"
        elif cat == "block":
            md = format_block_report(args.query, by_category["block"][0], plc_data, hmi_data, args.verbose)
            if len(by_category["block"]) > 1:
                md += "\n\n## Additional Block Matches\n\n"
                for extra_block in by_category["block"][1:]:
                    md += f"- `{extra_block}`\n"
        elif cat == "hmi":
            # For HMI, pick the first match
            first_key = by_category["hmi"][0]
            parts = first_key.split("/", 1)
            if len(parts) == 2:
                sname, ename = parts
            else:
                sname, ename = first_key, ""
            md = format_hmi_report(args.query, sname, ename, plc_data, hmi_data, args.verbose)
            if len(by_category["hmi"]) > 1:
                md += "\n\n## Additional HMI Matches\n\n"
                seen = set()
                for extra_key in by_category["hmi"][1:]:
                    if extra_key not in seen:
                        seen.add(extra_key)
                        md += f"- `{extra_key}`\n"
    else:
        # Multiple categories: generate summary report
        md = format_multi_result_report(args.query, matches, plc_data, hmi_data, args.verbose)

    # Add timestamp footer
    md += f"\n\n---\n\n*Generated by cross_reference.py on {datetime.now().isoformat()}*\n"

    # --- Write markdown report ---
    output_dir = args.output or os.path.join(DOC_OUTPUT, "analysis")
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, "cross_reference.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n{'=' * 70}")
    print(f" Report written: {report_path}")
    print(f"{'=' * 70}")


def _broad_search(query, force_type, plc_data, hmi_data):
    """Perform a broader search when forced type yields no exact matches."""
    matches = []
    q_upper = query.upper()

    if force_type == "tag" and plc_data:
        tag_xref = plc_data.get("tag_xref", {})
        plc_tags = plc_data.get("plc_tags", {})
        # Broader substring match
        for tag_name in list(tag_xref.keys()) + list(plc_tags.keys()):
            # Check if any word in the query matches any word in the tag name
            query_parts = q_upper.replace("_", " ").split()
            tag_parts = tag_name.upper().replace("_", " ").replace(".", " ").split()
            for qp in query_parts:
                if len(qp) >= 2 and any(qp in tp for tp in tag_parts):
                    if not any(m[0] == "tag" and m[1] == tag_name for m in matches):
                        matches.append(("tag", tag_name))

    elif force_type == "block" and plc_data:
        blocks = plc_data.get("blocks", [])
        for block in blocks:
            bname = block.get("block_name", "")
            query_parts = q_upper.replace("_", " ").split()
            block_parts = bname.upper().replace("_", " ").split()
            for qp in query_parts:
                if len(qp) >= 2 and any(qp in bp for bp in block_parts):
                    if not any(m[0] == "block" and m[1] == bname for m in matches):
                        matches.append(("block", bname))

    elif force_type == "hmi" and hmi_data:
        screens = hmi_data.get("screens", [])
        query_parts = q_upper.replace("_", " ").split()
        for screen in screens:
            sname = screen.get("screen_name", "")
            for elem in screen.get("elements", []):
                ename = elem.get("name", "")
                elem_parts = ename.upper().replace("_", " ").split()
                screen_parts = sname.upper().replace("_", " ").split()
                all_parts = elem_parts + screen_parts
                for qp in query_parts:
                    if len(qp) >= 2 and any(qp in p for p in all_parts):
                        key = f"{sname}/{ename}"
                        if not any(m[0] == "hmi" and m[1] == key for m in matches):
                            matches.append(("hmi", key))

    return matches


if __name__ == "__main__":
    main()
