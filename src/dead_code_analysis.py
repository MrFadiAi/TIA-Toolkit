#!/usr/bin/env python3
"""
Dead Code & Unused Tag Analyzer
================================
Reads existing JSON cache files (.plc_cache.json, .hmi_merged.json) and detects:

  1. Unused PLC tags — defined but never referenced in code or HMI
  2. Dead blocks    — FCs/FBs that are never called by any other block
  3. HMI tag gaps   — unresolved bindings or tags missing from the PLC tag table

Usage:
    python dead_code_analysis.py [options]

Options:
    --output PATH     Output directory (default: Doc_OUTPUT/analysis/)
    --verbose         Print detailed progress
"""

import os
import sys
import json
import argparse
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def load_json(path):
    """Load JSON with UTF-8 BOM handling."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def normalize_name(name):
    """Normalize a name for case-insensitive matching."""
    return name.strip().upper().replace(" ", "_")


def banner(title, width=70):
    """Print a banner with = separators."""
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def sub_banner(title, width=70):
    """Print a sub-section banner with - separators."""
    print()
    dash_count = max(1, (width - len(title) - 5) // 2)
    print(f"--- {title} {'-' * dash_count}")


def progress(msg, verbose=False):
    """Print progress message."""
    print(f"  {msg}")


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------
def find_plc_cache():
    """Find .plc_cache.json in Doc_OUTPUT tree."""
    if not os.path.isdir(DOC_OUTPUT):
        return None
    for root, dirs, files in os.walk(DOC_OUTPUT):
        for f in files:
            if f == ".plc_cache.json":
                return os.path.join(root, f)
    return None


def find_hmi_data():
    """Find best available HMI data: merged first, then online-only."""
    merged = os.path.join(DOC_OUTPUT, ".hmi_merged.json")
    if os.path.exists(merged):
        return merged
    online = os.path.join(DOC_OUTPUT, ".hmi_online_data.json")
    if os.path.exists(online):
        return online
    return None


# ---------------------------------------------------------------------------
# HMI Tag Collection
# ---------------------------------------------------------------------------
def collect_hmi_tags(hmi_data):
    """Collect all PLC tags referenced by HMI screens.

    Returns:
        used_plc_tags: set of normalized PLC tag names referenced by HMI
        tag_bindings_detail: list of dicts with screen/element/tag info
        unresolved: list of dicts for bindings with no plc_tag
    """
    used_plc_tags = set()
    tag_bindings_detail = []
    unresolved = []

    screens = hmi_data.get("screens", [])
    # Support both merged and online format
    # Some formats nest under extraction_info
    if not screens and "extraction_info" in hmi_data:
        screens = hmi_data.get("screens", [])

    for screen in screens:
        screen_name = screen.get("screen_name", "unknown")
        for elem in screen.get("elements", []):
            elem_name = elem.get("name", "unknown")
            for binding in elem.get("tag_bindings", []):
                plc_tag = binding.get("plc_tag", "").strip()
                hmi_tag = binding.get("hmi_tag", "").strip()

                if not plc_tag and not hmi_tag:
                    continue

                if plc_tag:
                    used_plc_tags.add(normalize_name(plc_tag))
                    tag_bindings_detail.append({
                        "plc_tag": plc_tag,
                        "hmi_tag": hmi_tag,
                        "screen": screen_name,
                        "element": elem_name,
                    })
                else:
                    unresolved.append({
                        "hmi_tag": hmi_tag,
                        "screen": screen_name,
                        "element": elem_name,
                        "issue": "No PLC tag resolved",
                    })

    # Also scan tag_index if present (merged format)
    tag_index = hmi_data.get("tag_index", {})
    for tag_name, details in tag_index.items():
        if isinstance(details, dict):
            plc_tag = details.get("plc_tag", "").strip()
            if plc_tag:
                used_plc_tags.add(normalize_name(plc_tag))

    return used_plc_tags, tag_bindings_detail, unresolved


# ---------------------------------------------------------------------------
# Analysis: Unused Tags
# ---------------------------------------------------------------------------
def analyze_unused_tags(plc_data, hmi_plc_tags, verbose=False):
    """Find PLC tags that are defined but never used.

    Returns:
        unused_tags: list of tag dicts with category "Unused"
        low_usage_tags: list of tag dicts with category "Low usage"
        by_table: dict of table_name -> list of unused tags
    """
    plc_tags = plc_data.get("plc_tags", {})
    tag_xref = plc_data.get("tag_xref", {})

    unused_tags = []
    low_usage_tags = []
    by_table = defaultdict(list)

    total_tags = len(plc_tags)
    checked = 0

    if verbose:
        progress(f"Checking {total_tags} PLC tags against code xref and HMI bindings...")

    for tag_name, tag_info in plc_tags.items():
        checked += 1
        if verbose and checked % 200 == 0:
            progress(f"  Checked {checked}/{total_tags} tags...")

        norm_name = normalize_name(tag_name)

        # Check if tag is referenced in PLC code
        in_xref = norm_name in {normalize_name(k) for k in tag_xref.keys()}
        xref_entry = None
        if in_xref:
            for k, v in tag_xref.items():
                if normalize_name(k) == norm_name:
                    xref_entry = v
                    break

        used_in_blocks = xref_entry.get("used_in", []) if xref_entry else []

        # Check if tag is referenced by HMI
        in_hmi = norm_name in hmi_plc_tags

        table = tag_info.get("table", "Unknown")
        entry = {
            "tag_name": tag_name,
            "address": tag_info.get("address", ""),
            "data_type": tag_info.get("data_type", ""),
            "table": table,
            "comment": tag_info.get("comment", ""),
            "used_in_blocks": used_in_blocks,
            "in_hmi": in_hmi,
        }

        if not in_xref and not in_hmi:
            entry["category"] = "Unused"
            unused_tags.append(entry)
            by_table[table].append(entry)
        elif in_xref and len(used_in_blocks) <= 1 and not in_hmi:
            entry["category"] = "Low usage"
            low_usage_tags.append(entry)

    if verbose:
        progress(f"  Found {len(unused_tags)} unused tags, {len(low_usage_tags)} low-usage tags")

    return unused_tags, low_usage_tags, by_table


# ---------------------------------------------------------------------------
# Analysis: Dead Blocks
# ---------------------------------------------------------------------------
def analyze_dead_blocks(plc_data, verbose=False):
    """Find blocks that are never called.

    Returns:
        dead_blocks: list of block dicts with dead-code info
        orphan_with_deps: list of dead blocks that call other blocks
    """
    blocks = plc_data.get("blocks", [])
    called_by = plc_data.get("called_by", {})
    call_tree = plc_data.get("call_tree", {})

    # Build lookup of normalized block names
    called_by_norm = {}
    for block_name, callers in called_by.items():
        called_by_norm[normalize_name(block_name)] = callers

    dead_blocks = []
    orphan_with_deps = []

    total_blocks = len(blocks)
    if verbose:
        progress(f"Checking {total_blocks} blocks for reachability...")

    for i, block in enumerate(blocks):
        if verbose and (i + 1) % 100 == 0:
            progress(f"  Checked {i + 1}/{total_blocks} blocks...")

        block_name = block.get("block_name", "")
        block_type = block.get("block_type", "")
        folder = block.get("folder", "")
        language = block.get("programming_language", "")
        norm_name = normalize_name(block_name)

        # OBs are entry points — never dead
        if block_type == "OB":
            continue

        # DBs and IDBs are data containers — never dead
        if block_type in ("DB", "IDB"):
            continue

        # UDTs and STRUCTs are type definitions — not callable
        if block_type in ("UDT", "STRUCT"):
            continue

        # Check if this block is called by anyone
        callers = called_by_norm.get(norm_name)
        if callers and len(callers) > 0:
            continue  # Has callers, not dead

        # Block has no callers — potentially dead
        calls = block.get("calls", [])
        tag_refs = block.get("tag_references", [])

        entry = {
            "block_name": block_name,
            "block_type": block_type,
            "language": language,
            "folder": folder,
            "has_tag_refs": bool(tag_refs),
            "calls": calls,
        }

        dead_blocks.append(entry)

        # Check if this dead block itself calls other blocks
        if calls:
            orphan_with_deps.append(entry)

    if verbose:
        progress(f"  Found {len(dead_blocks)} potentially dead blocks")
        if orphan_with_deps:
            progress(f"  {len(orphan_with_deps)} dead blocks have downstream dependencies")

    return dead_blocks, orphan_with_deps


# ---------------------------------------------------------------------------
# Analysis: HMI Tag Gaps
# ---------------------------------------------------------------------------
def analyze_hmi_gaps(hmi_data, plc_data, verbose=False):
    """Find HMI tag binding issues.

    Returns:
        unresolved: HMI bindings with no resolved PLC tag
        missing_from_table: PLC tags referenced by HMI but not in plc_tags
    """
    plc_tags = plc_data.get("plc_tags", {})
    plc_tags_norm = {normalize_name(k) for k in plc_tags.keys()}

    unresolved = []
    missing_from_table = []
    seen_missing = set()

    screens = hmi_data.get("screens", [])

    if verbose:
        progress(f"Scanning {len(screens)} HMI screens for tag gaps...")

    for screen in screens:
        screen_name = screen.get("screen_name", "unknown")
        for elem in screen.get("elements", []):
            elem_name = elem.get("name", "unknown")

            for binding in elem.get("tag_bindings", []):
                plc_tag = binding.get("plc_tag", "").strip()
                hmi_tag = binding.get("hmi_tag", "").strip()

                # Unresolved: HMI tag with no PLC tag at all
                if hmi_tag and not plc_tag:
                    unresolved.append({
                        "hmi_tag": hmi_tag,
                        "screen": screen_name,
                        "element": elem_name,
                        "issue": "No PLC tag resolved",
                    })

                # Missing from table: PLC tag referenced by HMI but not in plc_tags
                if plc_tag:
                    norm_plc = normalize_name(plc_tag)
                    if norm_plc not in plc_tags_norm and norm_plc not in seen_missing:
                        seen_missing.add(norm_plc)
                        missing_from_table.append({
                            "plc_tag": plc_tag,
                            "screen": screen_name,
                            "element": elem_name,
                            "issue": "Not found in PLC tag table",
                        })

    if verbose:
        progress(f"  Found {len(unresolved)} unresolved HMI bindings")
        progress(f"  Found {len(missing_from_table)} HMI-referenced tags missing from PLC tag table")

    return unresolved, missing_from_table


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------
def generate_report(unused_tags, low_usage_tags, by_table,
                    dead_blocks, orphan_with_deps,
                    unresolved, missing_from_table,
                    plc_data, hmi_data,
                    output_dir, verbose=False):
    """Generate markdown report."""

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "dead_code.md")

    plc_tags = plc_data.get("plc_tags", {})
    blocks = plc_data.get("blocks", [])
    tag_xref = plc_data.get("tag_xref", {})

    total_tags = len(plc_tags)
    total_blocks = len(blocks)
    total_callable = sum(1 for b in blocks if b.get("block_type") in ("FC", "FB"))
    ob_count = sum(1 for b in blocks if b.get("block_type") == "OB")

    # Count HMI screens
    hmi_screens = 0
    if hmi_data:
        hmi_screens = len(hmi_data.get("screens", []))

    lines = []
    lines.append("# Dead Code & Unused Tag Analysis")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # ---- Summary ----
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total PLC tags defined | {total_tags} |")
    lines.append(f"| Tags referenced in code | {len(tag_xref)} |")
    lines.append(f"| **Unused tags** | **{len(unused_tags)}** |")
    lines.append(f"| Low-usage tags (1 block only) | {len(low_usage_tags)} |")
    lines.append(f"| Total blocks | {total_blocks} |")
    lines.append(f"| Callable blocks (FC+FB) | {total_callable} |")
    lines.append(f"| OB entry points | {ob_count} |")
    lines.append(f"| **Potentially dead blocks** | **{len(dead_blocks)}** |")
    lines.append(f"| Dead blocks with dependencies | {len(orphan_with_deps)} |")
    lines.append(f"| HMI screens analyzed | {hmi_screens} |")
    lines.append(f"| Unresolved HMI bindings | {len(unresolved)} |")
    lines.append(f"| HMI tags missing from PLC table | {len(missing_from_table)} |")
    lines.append("")

    # ---- Unused Tags by Table ----
    lines.append("## Unused Tags")
    lines.append("")
    if unused_tags:
        lines.append("Tags defined in PLC tag tables but never referenced in code or HMI screens.")
        lines.append("")

        # Grouped summary by table
        lines.append("### By Tag Table")
        lines.append("")
        lines.append("| Tag Table | Unused Count |")
        lines.append("|-----------|-------------|")
        for table in sorted(by_table.keys()):
            lines.append(f"| {table} | {len(by_table[table])} |")
        lines.append("")

        # Full table
        lines.append("### All Unused Tags")
        lines.append("")
        lines.append("| Tag | Address | Type | Table | Comment |")
        lines.append("|-----|---------|------|-------|---------|")
        for tag in sorted(unused_tags, key=lambda t: (t["table"], t["tag_name"])):
            comment = tag["comment"].replace("|", "/") if tag["comment"] else ""
            lines.append(
                f"| {tag['tag_name']} | {tag['address']} | {tag['data_type']} "
                f"| {tag['table']} | {comment} |"
            )
        lines.append("")
    else:
        lines.append("No unused tags found. All defined tags are referenced somewhere.")
        lines.append("")

    # ---- Low Usage Tags ----
    if low_usage_tags:
        lines.append("## Low-Usage Tags (Single Block)")
        lines.append("")
        lines.append("Tags referenced by only one block. May be candidates for consolidation.")
        lines.append("")
        lines.append("| Tag | Address | Type | Table | Used In | Comment |")
        lines.append("|-----|---------|------|-------|---------|---------|")
        for tag in sorted(low_usage_tags, key=lambda t: (t["table"], t["tag_name"])):
            comment = tag["comment"].replace("|", "/") if tag["comment"] else ""
            used_in = ", ".join(tag["used_in_blocks"]) if tag["used_in_blocks"] else ""
            lines.append(
                f"| {tag['tag_name']} | {tag['address']} | {tag['data_type']} "
                f"| {tag['table']} | {used_in} | {comment} |"
            )
        lines.append("")

    # ---- Dead Blocks ----
    lines.append("## Potentially Dead Blocks")
    lines.append("")
    if dead_blocks:
        lines.append("FCs and FBs that are never called by any other block. "
                      "OBs (entry points), DBs, and IDBs (data) are excluded.")
        lines.append("")

        # Flag orphans separately
        orphan_names = {normalize_name(b["block_name"]) for b in orphan_with_deps}

        lines.append("| Block | Type | Language | Folder | Tag Refs | Calls | Note |")
        lines.append("|-------|------|----------|--------|----------|-------|------|")
        for block in sorted(dead_blocks, key=lambda b: (b["block_type"], b["block_name"])):
            tag_ref_str = "Yes" if block["has_tag_refs"] else ""
            calls_str = ", ".join(block["calls"]) if block["calls"] else ""
            note = ""
            if normalize_name(block["block_name"]) in orphan_names:
                note = "**Orphan with deps**"
            elif block["has_tag_refs"]:
                note = "Has tag refs"
            lines.append(
                f"| {block['block_name']} | {block['block_type']} "
                f"| {block['language']} | {block['folder']} "
                f"| {tag_ref_str} | {calls_str} | {note} |"
            )
        lines.append("")

        # Orphan detail
        if orphan_with_deps:
            lines.append("### Orphan Blocks with Dependencies")
            lines.append("")
            lines.append("These dead blocks call other blocks. Removing them may cascade.")
            lines.append("")
            for block in sorted(orphan_with_deps, key=lambda b: b["block_name"]):
                calls_list = ", ".join(block["calls"])
                lines.append(f"- **{block['block_name']}** calls: {calls_list}")
            lines.append("")
    else:
        lines.append("No dead blocks found. All FCs and FBs are called by at least one block.")
        lines.append("")

    # ---- HMI Gaps ----
    lines.append("## HMI Tag Gaps")
    lines.append("")

    if unresolved or missing_from_table:
        if unresolved:
            lines.append("### Unresolved HMI Bindings")
            lines.append("")
            lines.append("HMI elements with tag bindings that could not be resolved to a PLC tag.")
            lines.append("")
            lines.append("| HMI Tag | Screen | Element | Issue |")
            lines.append("|---------|--------|---------|-------|")
            for entry in sorted(unresolved, key=lambda e: (e["screen"], e["element"])):
                lines.append(
                    f"| {entry['hmi_tag']} | {entry['screen']} "
                    f"| {entry['element']} | {entry['issue']} |"
                )
            lines.append("")

        if missing_from_table:
            lines.append("### Tags Missing from PLC Tag Table")
            lines.append("")
            lines.append("PLC tags referenced by HMI but not found in the PLC tag definitions.")
            lines.append("")
            lines.append("| PLC Tag | Screen | Element | Issue |")
            lines.append("|---------|--------|---------|-------|")
            for entry in sorted(missing_from_table, key=lambda e: e["plc_tag"]):
                lines.append(
                    f"| {entry['plc_tag']} | {entry['screen']} "
                    f"| {entry['element']} | {entry['issue']} |"
                )
            lines.append("")
    else:
        lines.append("No HMI tag gaps found. All HMI bindings resolve to valid PLC tags.")
        lines.append("")

    # ---- Write ----
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if verbose:
        progress(f"Report written to {report_path}")

    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Dead Code & Unused Tag Analyzer for TIA Portal projects"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(DOC_OUTPUT, "analysis"),
        help="Output directory (default: Doc_OUTPUT/analysis/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress",
    )
    args = parser.parse_args()

    verbose = args.verbose
    output_dir = args.output

    banner("Dead Code & Unused Tag Analyzer")

    # ---- Load PLC data ----
    progress("Locating PLC cache...", verbose)
    plc_cache_path = find_plc_cache()
    if not plc_cache_path:
        print(f"ERROR: .plc_cache.json not found in {DOC_OUTPUT}/")
        print("  Run the PLC extraction pipeline first.")
        sys.exit(1)

    progress(f"Loading PLC data from {plc_cache_path}", verbose)
    plc_data = load_json(plc_cache_path)
    if not plc_data:
        print(f"ERROR: Failed to load {plc_cache_path}")
        sys.exit(1)

    plc_name = plc_data.get("extraction_info", {}).get("plc_name", "unknown")
    total_tags = len(plc_data.get("plc_tags", {}))
    total_blocks = len(plc_data.get("blocks", []))
    progress(f"  PLC: {plc_name}  |  {total_tags} tags  |  {total_blocks} blocks", verbose)

    # ---- Load HMI data (optional) ----
    hmi_data = None
    hmi_plc_tags = set()
    progress("Locating HMI data...", verbose)
    hmi_path = find_hmi_data()
    if hmi_path:
        progress(f"Loading HMI data from {hmi_path}", verbose)
        hmi_data = load_json(hmi_path)
        if hmi_data:
            hmi_plc_tags, _, _ = collect_hmi_tags(hmi_data)
            progress(f"  Found {len(hmi_plc_tags)} unique PLC tags referenced by HMI", verbose)
    else:
        progress("  No HMI data found — skipping HMI cross-check", verbose)

    # ---- Analyze: Unused Tags ----
    sub_banner("Unused Tag Analysis")
    unused_tags, low_usage_tags, by_table = analyze_unused_tags(
        plc_data, hmi_plc_tags, verbose=verbose
    )
    print(f"  Unused tags:       {len(unused_tags)} / {total_tags}")
    print(f"  Low-usage tags:    {len(low_usage_tags)}")

    # ---- Analyze: Dead Blocks ----
    sub_banner("Dead Block Analysis")
    dead_blocks, orphan_with_deps = analyze_dead_blocks(plc_data, verbose=verbose)
    callable_count = sum(
        1 for b in plc_data.get("blocks", []) if b.get("block_type") in ("FC", "FB")
    )
    print(f"  Dead blocks:       {len(dead_blocks)} / {callable_count} callable")
    print(f"  Orphans w/ deps:   {len(orphan_with_deps)}")

    # ---- Analyze: HMI Gaps ----
    sub_banner("HMI Tag Gap Analysis")
    unresolved = []
    missing_from_table = []
    if hmi_data:
        unresolved, missing_from_table = analyze_hmi_gaps(hmi_data, plc_data, verbose=verbose)
    print(f"  Unresolved HMI:    {len(unresolved)}")
    print(f"  Missing from table: {len(missing_from_table)}")

    # ---- Generate Report ----
    sub_banner("Generating Report")
    report_path = generate_report(
        unused_tags, low_usage_tags, by_table,
        dead_blocks, orphan_with_deps,
        unresolved, missing_from_table,
        plc_data, hmi_data,
        output_dir, verbose=verbose,
    )

    banner("Analysis Complete")
    print(f"  Report: {report_path}")
    print(f"  Unused tags: {len(unused_tags)} / {total_tags}")
    print(f"  Dead blocks: {len(dead_blocks)} / {callable_count} callable")
    print()


if __name__ == "__main__":
    main()
