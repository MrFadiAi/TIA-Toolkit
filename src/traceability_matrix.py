#!/usr/bin/env python3
"""
HMI-PLC Traceability Matrix Generator
======================================
Maps HMI screen elements to PLC tags to PLC blocks to physical addresses.

Creates a complete traceability chain:
  HMI Screen -> Element -> Tag Binding -> PLC Tag -> PLC Block(s) -> Physical Address

Data sources (from Doc_OUTPUT/):
  - .hmi_merged.json (or .hmi_online_data.json fallback): HMI screens, elements, tag bindings
  - .plc_cache.json: PLC blocks, tag cross-references, tag addresses

Output:
  - Doc_OUTPUT/analysis/traceability_matrix.md   (per-screen + consolidated tables)
  - Doc_OUTPUT/analysis/traceability_matrix.csv   (semicolon-delimited, UTF-8 BOM for Excel)

Usage:
    python traceability_matrix.py [--verbose] [--output DIR]
"""

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")

MERGED_INPUT = os.path.join(DOC_OUTPUT, ".hmi_merged.json")
ONLINE_INPUT = os.path.join(DOC_OUTPUT, ".hmi_online_data.json")


def load_json(path):
    """Load JSON with UTF-8 BOM handling."""
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def find_hmi_input():
    """Find best available HMI data source: merged first, then online-only."""
    if os.path.exists(MERGED_INPUT):
        return MERGED_INPUT
    if os.path.exists(ONLINE_INPUT):
        return ONLINE_INPUT
    return None


def find_plc_cache():
    """Find the .plc_cache.json file under Doc_OUTPUT/."""
    if not os.path.isdir(DOC_OUTPUT):
        return None
    for root, dirs, files in os.walk(DOC_OUTPUT):
        for f in files:
            if f == ".plc_cache.json":
                return os.path.join(root, f)
    return None


def resolve_tag_in_xref(plc_tag, tag_xref):
    """Look up a PLC tag in the tag cross-reference to find used_in blocks.

    Tries exact match first, then base name (before first dot).
    Returns the list of block names or an empty list.
    """
    if not plc_tag:
        return []
    info = tag_xref.get(plc_tag)
    if info is not None:
        return info.get("used_in", [])
    # Try base name (e.g. "DB_MyDB".member -> "DB_MyDB")
    base = plc_tag.split(".")[0] if "." in plc_tag else plc_tag
    info = tag_xref.get(base)
    if info is not None:
        return info.get("used_in", [])
    return []


def resolve_tag_address(plc_tag, plc_tags):
    """Look up a PLC tag in plc_tags to find its physical address.

    Tries exact match first, then base name.
    Returns the address string (e.g. '%I0.5') or empty string.
    """
    if not plc_tag:
        return ""
    detail = plc_tags.get(plc_tag)
    if detail is not None:
        addr = detail.get("address", "")
        if addr and addr != "(not in tag table)":
            return addr
    base = plc_tag.split(".")[0] if "." in plc_tag else plc_tag
    detail = plc_tags.get(base)
    if detail is not None:
        addr = detail.get("address", "")
        if addr and addr != "(not in tag table)":
            return addr
    return ""


def compute_status(plc_tag, blocks, address):
    """Compute traceability completeness status.

    FULL:   plc_tag found, blocks found, address found
    PARTIAL: plc_tag found but blocks or address missing
    BROKEN: plc_tag not found or empty
    """
    if not plc_tag:
        return "BROKEN"
    has_blocks = bool(blocks)
    has_address = bool(address)
    if has_blocks and has_address:
        return "FULL"
    if has_blocks or has_address:
        return "PARTIAL"
    return "PARTIAL"


def build_traceability_rows(hmi_data, plc_data, verbose=False):
    """Build the flat traceability table from HMI and PLC data.

    Returns a list of dicts, each with:
      screen_name, element_name, element_type, binding_property,
      hmi_tag, plc_tag, plc_name, data_type,
      plc_blocks, physical_address, status
    """
    tag_xref = plc_data.get("tag_xref", {}) if plc_data else {}
    plc_tags = plc_data.get("plc_tags", {}) if plc_data else {}

    screens = hmi_data.get("screens", [])
    rows = []

    for screen in screens:
        screen_name = screen.get("screen_name", "UNKNOWN")
        elements = screen.get("elements", [])

        if verbose:
            print(f"  Processing screen: {screen_name} ({len(elements)} elements)")

        for elem in elements:
            elem_name = elem.get("name", "")
            elem_type = elem.get("type", "")
            bindings = elem.get("tag_bindings", [])

            if not bindings:
                continue

            for binding in bindings:
                prop = binding.get("property", "")
                hmi_tag = binding.get("hmi_tag", "")
                plc_tag = binding.get("plc_tag", "")
                plc_name = binding.get("plc_name", "")
                data_type = binding.get("data_type", "")

                # Resolve PLC blocks that use this tag
                blocks = resolve_tag_in_xref(plc_tag, tag_xref)
                blocks_str = ", ".join(blocks) if blocks else ""

                # Resolve physical address
                address = resolve_tag_address(plc_tag, plc_tags)

                # Compute status
                status = compute_status(plc_tag, blocks, address)

                rows.append({
                    "screen_name": screen_name,
                    "element_name": elem_name,
                    "element_type": elem_type,
                    "binding_property": prop,
                    "hmi_tag": hmi_tag,
                    "plc_tag": plc_tag,
                    "plc_name": plc_name,
                    "data_type": data_type,
                    "plc_blocks": blocks_str,
                    "physical_address": address,
                    "status": status,
                })

    return rows


def compute_statistics(rows):
    """Compute summary statistics from the traceability rows."""
    total = len(rows)
    with_plc_tag = sum(1 for r in rows if r["plc_tag"])
    with_blocks = sum(1 for r in rows if r["plc_blocks"])
    with_address = sum(1 for r in rows if r["physical_address"])
    unresolved = total - with_plc_tag

    status_counts = defaultdict(int)
    for r in rows:
        status_counts[r["status"]] += 1

    # Unique elements
    unique_elements = set((r["screen_name"], r["element_name"]) for r in rows)

    # Unique screens
    unique_screens = set(r["screen_name"] for r in rows)

    return {
        "total_bindings": total,
        "unique_screens": len(unique_screens),
        "unique_elements": len(unique_elements),
        "with_plc_tag": with_plc_tag,
        "with_blocks": with_blocks,
        "with_address": with_address,
        "unresolved": unresolved,
        "full": status_counts.get("FULL", 0),
        "partial": status_counts.get("PARTIAL", 0),
        "broken": status_counts.get("BROKEN", 0),
    }


def generate_markdown(rows, stats, output_path, verbose=False):
    """Generate the traceability matrix markdown report."""
    lines = []

    lines.append("# HMI-PLC Traceability Matrix")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Summary stats
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total tag bindings | {stats['total_bindings']} |")
    lines.append(f"| Unique screens | {stats['unique_screens']} |")
    lines.append(f"| Unique elements | {stats['unique_elements']} |")
    lines.append(f"| Bindings with PLC tag | {stats['with_plc_tag']} |")
    lines.append(f"| Bindings with block info | {stats['with_blocks']} |")
    lines.append(f"| Bindings with address | {stats['with_address']} |")
    lines.append(f"| Unresolved bindings | {stats['unresolved']} |")
    lines.append("")

    # Completeness breakdown
    lines.append("## Completeness")
    lines.append("")
    lines.append("| Status | Count | Description |")
    lines.append("|--------|-------|-------------|")
    lines.append(f"| FULL | {stats['full']} | PLC tag, block usage, and physical address all resolved |")
    lines.append(f"| PARTIAL | {stats['partial']} | PLC tag found but block usage or address missing |")
    lines.append(f"| BROKEN | {stats['broken']} | PLC tag not found or empty |")
    lines.append("")

    # Per-screen sections
    screen_rows = defaultdict(list)
    for r in rows:
        screen_rows[r["screen_name"]].append(r)

    lines.append("## Per-Screen Traceability")
    lines.append("")

    for screen_name in sorted(screen_rows.keys()):
        screen_bindings = screen_rows[screen_name]
        lines.append(f"### {screen_name}")
        lines.append("")
        lines.append(f"Bindings: **{len(screen_bindings)}**")
        lines.append("")
        lines.append("| Element | Type | Property | HMI Tag | PLC Tag | PLC Blocks | Address | Status |")
        lines.append("|---------|------|----------|---------|---------|------------|---------|--------|")
        for r in screen_bindings:
            elem = r["element_name"]
            etype = r["element_type"]
            prop = r["binding_property"]
            if prop == "js_reference":
                prop = "*(js)*"
            hmi_tag = f"`{r['hmi_tag']}`" if r["hmi_tag"] else ""
            plc_tag = f"`{r['plc_tag']}`" if r["plc_tag"] else "*(none)*"
            blocks = r["plc_blocks"] or "*(none)*"
            addr = r["physical_address"] or "*(none)*"
            status = r["status"]
            lines.append(f"| {elem} | `{etype}` | {prop} | {hmi_tag} | {plc_tag} | {blocks} | {addr} | {status} |")
        lines.append("")

    # Consolidated full table
    lines.append("## Consolidated Traceability Table")
    lines.append("")
    lines.append("| Screen | Element | Type | Property | HMI Tag | PLC Tag | PLC Name | Data Type | PLC Blocks | Physical Address | Status |")
    lines.append("|--------|---------|------|----------|---------|---------|----------|-----------|------------|------------------|--------|")
    for r in rows:
        prop = r["binding_property"]
        if prop == "js_reference":
            prop = "*(js)*"
        plc_tag = f"`{r['plc_tag']}`" if r["plc_tag"] else ""
        plc_name = r["plc_name"]
        blocks = r["plc_blocks"]
        addr = r["physical_address"]
        lines.append(
            f"| {r['screen_name']} | {r['element_name']} | `{r['element_type']}` "
            f"| {prop} | `{r['hmi_tag']}` | {plc_tag} | {plc_name} "
            f"| {r['data_type']} | {blocks} | {addr} | {r['status']} |"
        )
    lines.append("")

    # Unresolved bindings detail
    unresolved = [r for r in rows if r["status"] == "BROKEN"]
    if unresolved:
        lines.append("## Unresolved Bindings (BROKEN)")
        lines.append("")
        lines.append("These HMI tag bindings could not be resolved to a PLC tag:")
        lines.append("")
        lines.append("| Screen | Element | Property | HMI Tag |")
        lines.append("|--------|---------|----------|---------|")
        for r in unresolved:
            prop = r["binding_property"]
            if prop == "js_reference":
                prop = "*(js)*"
            lines.append(f"| {r['screen_name']} | {r['element_name']} | {prop} | `{r['hmi_tag']}` |")
        lines.append("")

    # Write file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def generate_csv(rows, output_path):
    """Generate the traceability matrix as semicolon-delimited CSV with UTF-8 BOM."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fieldnames = [
        "Screen", "Element", "Type", "Property",
        "HMI Tag", "PLC Tag", "PLC Name", "Data Type",
        "PLC Blocks", "Physical Address", "Status",
    ]

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writerow(fieldnames)
        for r in rows:
            prop = r["binding_property"]
            writer.writerow([
                r["screen_name"],
                r["element_name"],
                r["element_type"],
                prop,
                r["hmi_tag"],
                r["plc_tag"],
                r["plc_name"],
                r["data_type"],
                r["plc_blocks"],
                r["physical_address"],
                r["status"],
            ])

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="HMI-PLC Traceability Matrix Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed progress per screen")
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: Doc_OUTPUT/analysis/)")
    args = parser.parse_args()

    output_dir = args.output or os.path.join(DOC_OUTPUT, "analysis")

    print("=" * 70)
    print(" HMI-PLC Traceability Matrix Generator")
    print("=" * 70)

    # --- Load HMI data ---
    print("\nLoading HMI data...")
    hmi_path = find_hmi_input()
    if not hmi_path:
        print("ERROR: No HMI data found. Run merge_hmi_data.py or tia_extract.exe first.")
        return
    print(f"  Source: {os.path.basename(hmi_path)}")
    hmi_data = load_json(hmi_path)
    if not hmi_data:
        print("ERROR: Failed to load HMI data.")
        return

    screens = hmi_data.get("screens", [])
    hmi_summary = hmi_data.get("summary", {})
    print(f"  Screens: {hmi_summary.get('total_screens', len(screens))}")
    print(f"  Elements: {hmi_summary.get('total_elements', '?')}")
    print(f"  Tag bindings: {hmi_summary.get('total_tag_bindings', '?')}")

    # --- Load PLC data ---
    print("\nLoading PLC data...")
    plc_path = find_plc_cache()
    if plc_path:
        print(f"  Source: {os.path.basename(plc_path)}")
        plc_data = load_json(plc_path)
        if plc_data:
            plc_summary = plc_data.get("summary", {})
            print(f"  Blocks: {plc_summary.get('total_blocks', '?')}")
            print(f"  Tag refs: {plc_summary.get('unique_tag_refs', '?')}")
            print(f"  PLC tags loaded: {plc_summary.get('plc_tags_loaded', '?')}")
        else:
            print("  WARNING: Failed to load PLC data. Block and address resolution disabled.")
            plc_data = None
    else:
        print("  WARNING: No .plc_cache.json found. Block and address resolution disabled.")
        print("  Run extract_plc_full.py first for full traceability.")
        plc_data = None

    # --- Build traceability rows ---
    print("\nBuilding traceability matrix...")
    rows = build_traceability_rows(hmi_data, plc_data, verbose=args.verbose)
    print(f"  {len(rows)} tag bindings processed")

    # --- Compute statistics ---
    stats = compute_statistics(rows)

    # --- Generate outputs ---
    print("\nGenerating outputs...")

    md_path = os.path.join(output_dir, "traceability_matrix.md")
    csv_path = os.path.join(output_dir, "traceability_matrix.csv")

    generate_markdown(rows, stats, md_path, verbose=args.verbose)
    print(f"  Markdown: {md_path}")

    generate_csv(rows, csv_path)
    print(f"  CSV: {csv_path}")

    # --- Console report ---
    print(f"\n{'=' * 70}")
    print(f" TRACEABILITY MATRIX COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Total tag bindings:    {stats['total_bindings']}")
    print(f"  Unique screens:        {stats['unique_screens']}")
    print(f"  Unique elements:       {stats['unique_elements']}")
    print(f"  With PLC tag:          {stats['with_plc_tag']}")
    print(f"  With block info:       {stats['with_blocks']}")
    print(f"  With address:          {stats['with_address']}")
    print(f"  Unresolved bindings:   {stats['unresolved']}")
    print(f"")
    print(f"  Completeness:")
    print(f"    FULL:                {stats['full']}")
    print(f"    PARTIAL:             {stats['partial']}")
    print(f"    BROKEN:              {stats['broken']}")
    print(f"{'=' * 70}")

    # Per-screen detail table
    screen_rows_map = defaultdict(list)
    for r in rows:
        screen_rows_map[r["screen_name"]].append(r)

    print(f"\n{'Screen':<36s} {'Binds':>5s} {'PLC':>4s} {'Blks':>4s} {'Addr':>4s} {'Broken':>6s}")
    print("-" * 70)
    for sname in sorted(screen_rows_map.keys()):
        s_rows = screen_rows_map[sname]
        n = len(s_rows)
        n_plc = sum(1 for r in s_rows if r["plc_tag"])
        n_blk = sum(1 for r in s_rows if r["plc_blocks"])
        n_addr = sum(1 for r in s_rows if r["physical_address"])
        n_broken = sum(1 for r in s_rows if r["status"] == "BROKEN")
        print(f"  {sname:<34s} {n:>5d} {n_plc:>4d} {n_blk:>4d} {n_addr:>4d} {n_broken:>6d}")

    return {"stats": stats, "md_path": md_path, "csv_path": csv_path}


if __name__ == "__main__":
    main()
