#!/usr/bin/env python3
"""
HMI Data Merger
===============
Combines three data sources into one comprehensive per-screen, per-element output:

  1. Python offline (hmi_offline_data.json)    → 30 screens, elements, JS events, navigation, IO roles
  2. C# online  (hmi_online_data.json)         → PLC tag bindings (Dynamizations), positions, text, PLC names
  3. HMITags.xlsx (via hmi_offline_data.json)  → Full tag details for any tags not in C# output

Matching strategy:
  - Screen match: by screen_name (normalized)
  - Element match: by element name (Button_9, Circle_1, etc.)
  - Tag enrichment: HMI tag names from C# → resolve via tag table for any missing PLC tags

Usage:
    python merge_hmi_data.py
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PYTHON_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", "hmi_offline_data.json")
CSHARP_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", ".hmi_online_data.json")
MERGED_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", ".hmi_merged.json")


def normalize_name(name):
    """Normalize screen/element name for matching."""
    return name.strip().upper().replace(" ", "_")


def load_json(path):
    if not os.path.exists(path):
        print(f"WARNING: {path} not found")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode('utf-8-sig'))


def build_tag_lookup(hmi_full):
    """Build a lookup of HMI tag name -> full tag details from the Python extraction."""
    lookup = {}
    # From plc_tag_index
    for tag_name, details in hmi_full.get("plc_tag_index", {}).items():
        lookup[tag_name] = details

    # Also scan all elements for hmi_tags with more detail
    for screen in hmi_full.get("screens", []):
        for elem in screen.get("elements", []):
            for tag_info in elem.get("hmi_tags", []):
                tag_name = tag_info.get("hmi_tag", "")
                if tag_name and tag_name not in lookup:
                    lookup[tag_name] = tag_info
    return lookup


def build_csharp_tag_table(csharp):
    """Build HMI tag -> details lookup from C# tag table (from tag_bindings)."""
    lookup = {}
    for screen in csharp.get("screens", []):
        for elem in screen.get("elements", []):
            for binding in elem.get("tag_bindings", []):
                hmi_tag = binding.get("hmi_tag", "")
                if hmi_tag and hmi_tag not in lookup:
                    lookup[hmi_tag] = {
                        "plc_tag": binding.get("plc_tag", ""),
                        "plc_name": binding.get("plc_name", ""),
                        "data_type": binding.get("data_type", ""),
                        "connection": binding.get("connection", ""),
                    }
    return lookup


def merge_screens(py_screens, cs_screens, tag_lookup, cs_tag_table):
    """Merge Python and C# screen data."""

    # Index C# screens by normalized name
    cs_by_name = {}
    for s in cs_screens:
        key = normalize_name(s.get("screen_name", ""))
        cs_by_name[key] = s

    merged_screens = []
    stats = {"screens_from_python": 0, "screens_from_csharp_only": 0,
             "elements_merged": 0, "elements_csharp_only": 0,
             "tag_bindings_from_csharp": 0, "tag_bindings_from_python": 0,
             "plc_tags_resolved": 0}

    # Process all Python screens first (30 screens)
    all_screen_names = set()

    for py_screen in py_screens:
        py_name = py_screen.get("screen_name", "UNKNOWN")
        if py_name == "UNKNOWN":
            continue
        all_screen_names.add(py_name)

        key = normalize_name(py_name)
        cs_screen = cs_by_name.get(key)

        merged = merge_one_screen(py_screen, cs_screen, tag_lookup, cs_tag_table, stats)
        merged_screens.append(merged)
        stats["screens_from_python"] += 1

    # Add any C# screens not in Python
    for cs_screen in cs_screens:
        cs_name = cs_screen.get("screen_name", "")
        if cs_name not in all_screen_names:
            merged = merge_one_screen(None, cs_screen, tag_lookup, cs_tag_table, stats)
            merged_screens.append(merged)
            stats["screens_from_csharp_only"] += 1

    return merged_screens, stats


def merge_one_screen(py_screen, cs_screen, tag_lookup, cs_tag_table, stats):
    """Merge a single screen from both sources."""

    # Use Python screen as base (has more data), fall back to C#
    if py_screen:
        result = {
            "screen_name": py_screen.get("screen_name", ""),
            "file": py_screen.get("file", ""),
        }
    else:
        result = {
            "screen_name": cs_screen.get("screen_name", ""),
            "file": "",
        }

    # Build element index from C# by name
    cs_elements = {}
    if cs_screen:
        for elem in cs_screen.get("elements", []):
            cs_elements[normalize_name(elem.get("name", ""))] = elem

    # Build element index from Python by name
    py_elements = {}
    if py_screen:
        for elem in py_screen.get("elements", []):
            py_elements[normalize_name(elem.get("name", ""))] = elem

    # Merge elements
    merged_elements = []
    seen_names = set()

    # First: all Python elements (rich events, JS code, navigation)
    if py_screen:
        for py_elem in py_screen.get("elements", []):
            elem_name = py_elem.get("name", "")
            key = normalize_name(elem_name)
            seen_names.add(key)

            cs_elem = cs_elements.get(key)
            merged_elem = merge_one_element(py_elem, cs_elem, tag_lookup, cs_tag_table, stats)
            merged_elements.append(merged_elem)
            stats["elements_merged"] += 1

    # Add C# elements not in Python (elements with PLC tag bindings but no JS events)
    if cs_screen:
        for cs_elem in cs_screen.get("elements", []):
            key = normalize_name(cs_elem.get("name", ""))
            if key not in seen_names:
                merged_elem = merge_one_element(None, cs_elem, tag_lookup, cs_tag_table, stats)
                merged_elements.append(merged_elem)
                stats["elements_csharp_only"] += 1

    # Sort elements: buttons first, then by name
    type_order = {"button": 0, "switch": 1, "io_field": 2, "symbolic_io_field": 3,
                  "bar_graph": 4, "status_display": 5, "circle": 6, "rectangle": 7,
                  "text_display": 8, "screen_window": 9, "image": 10, "line": 11, "faceplate": 12}
    merged_elements.sort(key=lambda e: (type_order.get(e.get("type", ""), 99), e.get("name", "")))

    # Screen-level metadata
    result["element_count"] = len(merged_elements)
    result["elements"] = merged_elements

    # Screen-level data from Python
    if py_screen:
        result["javascript_functions"] = py_screen.get("javascript_functions", [])
        result["screen_navigations"] = py_screen.get("screen_navigations", [])
        result["on_loaded_event"] = py_screen.get("on_loaded_event")
        result["layers"] = py_screen.get("layers", [])
        result["element_summary"] = summarize_elements(merged_elements)
    elif cs_screen:
        result["javascript_functions"] = []
        result["screen_navigations"] = []
        result["on_loaded_event"] = None
        result["layers"] = []
        result["element_summary"] = summarize_elements(merged_elements)

    return result


def merge_one_element(py_elem, cs_elem, tag_lookup, cs_tag_table, stats):
    """Merge a single element from both sources."""

    # Start with whichever source we have
    if py_elem:
        result = {
            "name": py_elem.get("name", ""),
            "type": py_elem.get("type", ""),
            "io_role": py_elem.get("io_role", ""),
        }
    else:
        result = {
            "name": cs_elem.get("name", ""),
            "type": cs_elem.get("type", ""),
            "io_role": classify_io_role(cs_elem),
        }

    # Position: prefer C# (exact from API), fall back to Python
    if cs_elem:
        pos = cs_elem.get("position", {})
        result["position"] = pos
        result["text"] = cs_elem.get("text", "")
        result["type_raw"] = cs_elem.get("type_raw", "")
    elif py_elem:
        result["position"] = {}
        result["text"] = ""
        result["type_raw"] = ""

    # Tag bindings: C# is the gold source for Dynamization-based bindings
    tag_bindings = []
    if cs_elem:
        for binding in cs_elem.get("tag_bindings", []):
            hmi_tag = binding.get("hmi_tag", "")
            plc_tag = binding.get("plc_tag", "")

            # Enrich with tag lookup if PLC tag is missing
            if not plc_tag and hmi_tag in cs_tag_table:
                plc_tag = cs_tag_table[hmi_tag].get("plc_tag", "")

            if not plc_tag and hmi_tag in tag_lookup:
                detail = tag_lookup[hmi_tag]
                plc_tag = detail.get("plc_tag", "")

            tb = {
                "property": binding.get("property", ""),
                "hmi_tag": hmi_tag,
                "plc_tag": plc_tag,
                "plc_name": binding.get("plc_name", ""),
                "data_type": binding.get("data_type", ""),
                "connection": binding.get("connection", ""),
            }
            tag_bindings.append(tb)
            stats["tag_bindings_from_csharp"] += 1
            if plc_tag:
                stats["plc_tags_resolved"] += 1

    # Also add tag bindings from Python (JS-referenced tags that C# didn't have)
    py_hmi_tags = set()
    if py_elem:
        for ev in py_elem.get("events", []):
            for t in ev.get("plc_tags", []):
                py_hmi_tags.add(t)
        for t in py_elem.get("tag_references_in_region", []):
            py_hmi_tags.add(t)

    # Get existing HMI tags from C# bindings to avoid duplicates
    existing_hmi_tags = {tb["hmi_tag"] for tb in tag_bindings}

    for hmi_tag in sorted(py_hmi_tags):
        if hmi_tag in existing_hmi_tags:
            continue

        # Resolve PLC tag from available sources
        plc_tag = ""
        plc_name = ""
        data_type = ""
        connection = ""

        if hmi_tag in cs_tag_table:
            detail = cs_tag_table[hmi_tag]
            plc_tag = detail.get("plc_tag", "")
            plc_name = detail.get("plc_name", "")
            data_type = detail.get("data_type", "")
            connection = detail.get("connection", "")

        if not plc_tag and hmi_tag in tag_lookup:
            detail = tag_lookup[hmi_tag]
            plc_tag = detail.get("plc_tag", "")
            data_type = detail.get("data_type", detail.get("data_type", ""))
            connection = detail.get("connection", "")

        tag_bindings.append({
            "property": "js_reference",
            "hmi_tag": hmi_tag,
            "plc_tag": plc_tag,
            "plc_name": plc_name,
            "data_type": data_type,
            "connection": connection,
            "source": "python_js",
        })
        stats["tag_bindings_from_python"] += 1
        if plc_tag:
            stats["plc_tags_resolved"] += 1

    result["tag_bindings"] = tag_bindings

    # Events: from Python (has JS code, PLC tags, navigation)
    if py_elem:
        events = []
        for ev in py_elem.get("events", []):
            events.append({
                "function": ev.get("function", ""),
                "event_type": ev.get("event_type", ""),
                "plc_tags": ev.get("plc_tags", []),
                "resolved_plc_tags": ev.get("resolved_plc_tags", []),
                "navigates_to": ev.get("navigates_to", []),
                "code": ev.get("code", ""),
            })
        result["events"] = events
    elif cs_elem:
        result["events"] = cs_elem.get("events", [])

    # OCR match from Python
    if py_elem and py_elem.get("ocr_match"):
        result["ocr_match"] = py_elem["ocr_match"]

    return result


def classify_io_role(elem):
    """Classify element IO role from C# data."""
    bindings = elem.get("tag_bindings", [])
    elem_type = elem.get("type", "")

    if elem_type == "button":
        if bindings:
            return "control_button"
        return "navigation_button"

    if elem_type == "io_field":
        return "input_output"

    if elem_type == "symbolic_io_field":
        return "selection_input"

    if elem_type == "screen_window":
        return "screen_container"

    if elem_type in ("text_display", "rectangle", "line", "circle", "image"):
        if bindings:
            return "output (PLC status)"
        return "display/static"

    if elem_type == "bar_graph":
        return "output (PLC value)"

    if elem_type == "status_display":
        return "output (PLC status)"

    if elem_type == "switch":
        return "input (writes to PLC)"

    return "display/static"


def summarize_elements(elements):
    """Create a summary of element types and IO roles."""
    summary = defaultdict(int)
    for e in elements:
        summary[e.get("type", "unknown")] += 1
        if e.get("tag_bindings"):
            summary["with_tag_bindings"] += 1
        if e.get("events"):
            summary["with_events"] += 1
        io = e.get("io_role", "")
        if "input" in io:
            summary["inputs"] += 1
        elif "output" in io or "display" in io:
            summary["outputs"] += 1
        elif "control" in io or "navigation" in io:
            summary["controls"] += 1
    return dict(summary)


def main():
    print("=" * 70)
    print(" HMI Data Merger - Python Offline + C# Online")
    print("=" * 70)

    # Load data sources
    print("\nLoading Python offline data...")
    hmi_full = load_json(PYTHON_OUTPUT)
    if not hmi_full:
        print("ERROR: Python output not found. Run extract_hmi_full.py first.")
        return

    print("Loading C# online data...")
    csharp = load_json(CSHARP_OUTPUT)
    if not csharp:
        print("ERROR: C# output not found. Run tia_extract.exe first.")
        return

    py_screens = hmi_full.get("screens", [])
    cs_screens = csharp.get("screens", [])
    print(f"  Python: {len(py_screens)} screens")
    print(f"  C#:     {len(cs_screens)} screens")

    # Build tag lookups
    print("\nBuilding tag lookups...")
    tag_lookup = build_tag_lookup(hmi_full)
    cs_tag_table = build_csharp_tag_table(csharp)
    print(f"  Python tag lookup: {len(tag_lookup)} tags")
    print(f"  C# tag table:      {len(cs_tag_table)} tags")

    # Merge
    print("\nMerging screens...")
    merged_screens, stats = merge_screens(py_screens, cs_screens, tag_lookup, cs_tag_table)

    # Build combined navigation map and tag index
    nav_map = {}
    for s in merged_screens:
        if s.get("screen_navigations"):
            nav_map[s["screen_name"]] = s["screen_navigations"]

    tag_index = defaultdict(list)
    for s in merged_screens:
        for elem in s.get("elements", []):
            for tb in elem.get("tag_bindings", []):
                hmi_tag = tb.get("hmi_tag", "")
                if hmi_tag:
                    tag_index[hmi_tag].append({
                        "screen": s["screen_name"],
                        "element": elem["name"],
                        "plc_tag": tb.get("plc_tag", ""),
                    })

    # Compile output
    total_elements = sum(s["element_count"] for s in merged_screens)
    total_bindings = sum(len(e.get("tag_bindings", [])) for s in merged_screens for e in s["elements"])
    total_with_plc = sum(
        1 for s in merged_screens for e in s["elements"]
        for tb in e.get("tag_bindings", []) if tb.get("plc_tag")
    )
    total_events = sum(len(e.get("events", [])) for s in merged_screens for e in s["elements"])

    output = {
        "extraction_info": {
            "tool": "merge_hmi_data.py",
            "sources": {
                "python_offline": PYTHON_OUTPUT,
                "csharp_online": CSHARP_OUTPUT,
            },
            "timestamp": datetime.now().isoformat(),
        },
        "summary": {
            "total_screens": len(merged_screens),
            "total_elements": total_elements,
            "total_tag_bindings": total_bindings,
            "bindings_with_plc_tag": total_with_plc,
            "total_events": total_events,
            "unique_hmi_tags": len(tag_index),
            "screens_from_python": stats["screens_from_python"],
            "screens_from_csharp_only": stats["screens_from_csharp_only"],
        },
        "navigation_map": nav_map,
        "tag_index": {k: v for k, v in sorted(tag_index.items())},
        "screens": merged_screens,
    }

    # Write output
    os.makedirs(os.path.dirname(MERGED_OUTPUT), exist_ok=True)
    with open(MERGED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print report
    print(f"\n{'=' * 70}")
    print(f" MERGE COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Screens:          {output['summary']['total_screens']}")
    print(f"  Elements:         {output['summary']['total_elements']}")
    print(f"  Tag bindings:     {output['summary']['total_tag_bindings']}")
    print(f"  With PLC tag:     {output['summary']['bindings_with_plc_tag']}")
    print(f"  Events:           {output['summary']['total_events']}")
    print(f"  Unique HMI tags:  {output['summary']['unique_hmi_tags']}")
    print(f"\n  Output: {MERGED_OUTPUT}")
    print(f"{'=' * 70}")

    # Per-screen detail
    print(f"\n{'Screen':<36s} {'Elem':>5s} {'Binds':>5s} {'PLC':>4s} {'Evts':>4s} {'IO'}")
    print("-" * 90)
    for s in merged_screens:
        n_binds = sum(len(e.get("tag_bindings", [])) for e in s["elements"])
        n_plc = sum(1 for e in s["elements"] for tb in e.get("tag_bindings", []) if tb.get("plc_tag"))
        n_evts = sum(len(e.get("events", [])) for e in s["elements"])
        n_in = sum(1 for e in s["elements"] if "input" in e.get("io_role", ""))
        n_out = sum(1 for e in s["elements"] if "output" in e.get("io_role", ""))
        n_ctrl = sum(1 for e in s["elements"] if "control" in e.get("io_role", "") or "navigation" in e.get("io_role", ""))
        print(f"  {s['screen_name']:<34s} {s['element_count']:>4d} {n_binds:>5d} {n_plc:>4d} {n_evts:>4d}  {n_in}i/{n_out}o/{n_ctrl}c")

    # Sample elements with PLC tags
    print(f"\n--- Sample elements with PLC tag bindings ---")
    count = 0
    for s in merged_screens:
        for e in s["elements"]:
            for tb in e.get("tag_bindings", []):
                if tb.get("plc_tag") and count < 15:
                    print(f"  {s['screen_name']}/{e['name']}:")
                    print(f"    hmi_tag:  {tb['hmi_tag']}")
                    print(f"    plc_tag:  {tb['plc_tag']}")
                    print(f"    plc_name: {tb.get('plc_name', '')}")
                    print(f"    type:     {tb.get('data_type', '')}")
                    count += 1

    return output


if __name__ == "__main__":
    main()
