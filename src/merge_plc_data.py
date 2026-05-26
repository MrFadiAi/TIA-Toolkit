#!/usr/bin/env python3
"""
PLC Data Merger
===============
Combines two data sources into one comprehensive per-block output:

  1. Python offline (plc_full.json)    → parsed from exported XML, full code, tag xref, call tree
  2. C# online  (plc_elements.json)    → exact offsets, compiled code, tag bindings from API

Matching strategy:
  - Block match: by block_name (normalized)
  - Interface: prefer C# for exact offsets, Python for comments
  - Code: prefer C# (latest compiled), fallback to Python XML
  - Calls/tags: union of both sources

Usage:
    python merge_plc_data.py
"""

import json
import os
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PYTHON_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", "plc_full.json")
CSHARP_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", "plc_elements.json")
MERGED_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", "plc_merged.json")


def normalize_name(name):
    """Normalize block name for matching."""
    return name.strip().upper().replace(" ", "_")


def load_json(path):
    if not os.path.exists(path):
        print(f"WARNING: {path} not found")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def merge_interface(py_iface, cs_iface):
    """Merge interface from both sources."""
    if py_iface is None and cs_iface is None:
        return {"inputs": [], "outputs": [], "inouts": [],
                "statics": [], "temps": [], "constants": []}

    # Use whichever is richer
    base = py_iface or cs_iface
    other = cs_iface if base is py_iface else py_iface

    if other is None:
        return base

    # Merge: prefer base, add missing from other
    merged = {}
    for key in ("inputs", "outputs", "inouts", "statics", "temps", "constants"):
        base_list = base.get(key, [])
        other_list = other.get(key, [])
        if len(other_list) > len(base_list):
            merged[key] = other_list
        else:
            merged[key] = base_list

    return merged


def merge_blocks(py_blocks, cs_blocks):
    """Merge Python and C# block data."""
    cs_by_name = {}
    for b in cs_blocks:
        key = normalize_name(b.get("block_name", ""))
        cs_by_name[key] = b

    merged_blocks = []
    stats = {"blocks_from_python": 0, "blocks_from_csharp_only": 0,
             "blocks_merged": 0, "calls_merged": 0, "tag_refs_merged": 0}

    seen = set()

    # Process Python blocks first (richer data)
    for py_block in py_blocks:
        name = py_block.get("block_name", "")
        key = normalize_name(name)
        seen.add(key)

        cs_block = cs_by_name.get(key)
        merged = merge_one_block(py_block, cs_block, stats)
        merged_blocks.append(merged)
        stats["blocks_from_python"] += 1
        if cs_block:
            stats["blocks_merged"] += 1

    # Add C# blocks not in Python
    for cs_block in cs_blocks:
        name = cs_block.get("block_name", "")
        key = normalize_name(name)
        if key not in seen:
            merged = merge_one_block(None, cs_block, stats)
            merged_blocks.append(merged)
            stats["blocks_from_csharp_only"] += 1

    return merged_blocks, stats


def merge_one_block(py_block, cs_block, stats):
    """Merge a single block from both sources."""
    # Use Python as base (has folder, source_file, richer interface)
    if py_block:
        result = {
            "block_name": py_block.get("block_name", ""),
            "block_number": py_block.get("block_number", 0),
            "block_type": py_block.get("block_type", ""),
            "programming_language": py_block.get("programming_language", ""),
            "comment": py_block.get("comment", ""),
            "folder": py_block.get("folder", ""),
            "source_file": py_block.get("source_file", ""),
        }
    else:
        result = {
            "block_name": cs_block.get("block_name", ""),
            "block_number": cs_block.get("block_number", 0),
            "block_type": cs_block.get("block_type", ""),
            "programming_language": cs_block.get("programming_language", ""),
            "comment": cs_block.get("comment", ""),
            "folder": cs_block.get("folder", ""),
            "source_file": "",
        }

    # Interface: merge both
    py_iface = py_block.get("interface") if py_block else None
    cs_iface = cs_block.get("interface") if cs_block else None
    result["interface"] = merge_interface(py_iface, cs_iface)
    result["interface_count"] = sum(len(result["interface"].get(k, []))
                                     for k in ("inputs", "outputs", "inouts", "statics", "temps", "constants"))

    # Code: prefer C# (compiled = latest), fallback to Python
    cs_code = cs_block.get("code", "") if cs_block else ""
    py_code = py_block.get("code", "") if py_block else ""
    result["code"] = cs_code if cs_code else py_code

    # Networks from Python (structured)
    result["networks"] = py_block.get("networks", []) if py_block else []

    # Tag references: union
    py_tags = set(py_block.get("tag_references", [])) if py_block else set()
    cs_tags = set(cs_block.get("tag_references", [])) if cs_block else set()
    result["tag_references"] = sorted(py_tags | cs_tags)
    stats["tag_refs_merged"] += len(result["tag_references"])

    # Calls: union
    py_calls = py_block.get("calls", []) if py_block else []
    cs_calls = cs_block.get("calls", []) if cs_block else []
    result["calls"] = sorted(set(py_calls) | set(cs_calls))
    stats["calls_merged"] += len(result["calls"])

    return result


def main():
    print("=" * 70)
    print(" PLC Data Merger - Python Offline + C# Online")
    print("=" * 70)

    # Load data sources
    print("\nLoading Python offline data...")
    plc_full = load_json(PYTHON_OUTPUT)
    if not plc_full:
        print("ERROR: Python output not found. Run extract_plc_full.py first.")
        return

    print("Loading C# online data...")
    csharp = load_json(CSHARP_OUTPUT)

    py_blocks = plc_full.get("blocks", [])
    cs_blocks = csharp.get("blocks", []) if csharp else []
    print(f"  Python: {len(py_blocks)} blocks")
    print(f"  C#:     {len(cs_blocks)} blocks")

    # Merge blocks
    print("\nMerging blocks...")
    merged_blocks, stats = merge_blocks(py_blocks, cs_blocks)

    # Merge call tree
    py_call_tree = plc_full.get("call_tree", {})
    cs_call_tree = csharp.get("call_tree", {}) if csharp else {}
    merged_call_tree = {}
    for name in set(list(py_call_tree.keys()) + list(cs_call_tree.keys())):
        py_calls = set(py_call_tree.get(name, []))
        cs_calls = set(cs_call_tree.get(name, []))
        merged_call_tree[name] = sorted(py_calls | cs_calls)

    # Build reverse call tree (called_by)
    called_by = defaultdict(list)
    for caller, callees in merged_call_tree.items():
        for callee in callees:
            called_by[callee].append(caller)
    called_by = {k: sorted(set(v)) for k, v in called_by.items()}

    # Merge PLC tags
    py_tags = plc_full.get("plc_tags", {})
    cs_tags = csharp.get("plc_tags", {}) if csharp else {}
    merged_tags = {**cs_tags, **py_tags}  # Python tags are richer (have addresses from XML)

    # Merge tag xref
    py_xref = plc_full.get("tag_xref", {})

    # Compute summary
    total_calls = sum(len(v) for v in merged_call_tree.values())
    total_tag_refs = sum(len(b.get("tag_references", [])) for b in merged_blocks)

    summary = {
        "total_blocks": len(merged_blocks),
        "blocks_from_python": stats["blocks_from_python"],
        "blocks_from_csharp_only": stats["blocks_from_csharp_only"],
        "blocks_merged": stats["blocks_merged"],
        "total_interfaces": sum(b.get("interface_count", 0) for b in merged_blocks),
        "total_calls": total_calls,
        "total_tag_refs": total_tag_refs,
        "unique_tag_refs": len(py_xref),
        "plc_tags_loaded": len(merged_tags),
    }

    output = {
        "extraction_info": {
            "tool": "merge_plc_data.py",
            "sources": {
                "python_offline": PYTHON_OUTPUT,
                "csharp_online": CSHARP_OUTPUT,
            },
            "timestamp": datetime.now().isoformat(),
        },
        "summary": summary,
        "call_tree": merged_call_tree,
        "called_by": called_by,
        "tag_xref": py_xref,
        "plc_tags": merged_tags,
        "blocks": merged_blocks,
    }

    # Write output
    os.makedirs(os.path.dirname(MERGED_OUTPUT), exist_ok=True)
    with open(MERGED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print report
    print(f"\n{'=' * 70}")
    print(f" MERGE COMPLETE")
    print(f"{'=' * 70}")
    for k, v in summary.items():
        print(f"  {k:<30s} {v}")
    print(f"\n  Output: {MERGED_OUTPUT}")
    print(f"{'=' * 70}")

    # Per-block detail
    print(f"\n{'Block':<36s} {'Type':>4s} {'#':>5s} {'Lang':>4s} {'Iface':>5s} {'Calls':>5s} {'Tags':>5s} {'Folder'}")
    print("-" * 110)
    for b in merged_blocks:
        folder = b.get("folder", "")
        if len(folder) > 40:
            folder = "..." + folder[-37:]
        print(f"  {b['block_name']:<34s} {b.get('block_type', '?'):>4s} {str(b.get('block_number', '?')):>5s} "
              f"{b.get('programming_language', '?'):>4s} {b.get('interface_count', 0):>5d} "
              f"{len(b.get('calls', [])):>5d} {len(b.get('tag_references', [])):>5d}  {folder}")


if __name__ == "__main__":
    main()
