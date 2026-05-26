#!/usr/bin/env python3
"""TIA Portal Hardware Catalog Report Generator"""

import os
import sys
import json
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")


def load_json(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None


def find_hardware_json():
    for name in (".hardware.json", "hardware.json"):
        p = os.path.join(DOC_OUTPUT, name)
        if os.path.exists(p):
            return p
    for root, dirs, files in os.walk(DOC_OUTPUT):
        for f in files:
            if f == ".hardware.json" or f == "hardware.json":
                return os.path.join(root, f)
    return None


def generate_report(data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    devices = data.get("devices", [])
    info = data.get("extraction_info", {})

    lines = []
    lines.append("# Hardware Catalog")
    lines.append("")
    lines.append(f"**Project:** {info.get('project', 'N/A')}")
    lines.append(f"**Extracted:** {info.get('timestamp', 'N/A')}")
    if info.get("device_filter"):
        lines.append(f"**Filter:** {info['device_filter']}")
    lines.append("")

    # Summary
    total_modules = sum(len(d.get("modules", [])) for d in devices)
    ips = []
    for d in devices:
        for m in d.get("modules", []):
            if m.get("ip_address"):
                ips.append((m["ip_address"], m.get("module_name", ""), d["device_name"]))

    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Devices | {len(devices)} |")
    lines.append(f"| Modules | {total_modules} |")
    lines.append(f"| IP Addresses | {len(ips)} |")
    lines.append("")

    # Per-device detail
    for dev in devices:
        dname = dev["device_name"]
        modules = dev.get("modules", [])
        lines.append(f"## {dname}")
        lines.append("")

        if not modules:
            lines.append("*No modules extracted.*")
            lines.append("")
            continue

        lines.append("| Module | Order Number | Firmware | IP Address | Subnet | PROFINET Name | Network | Position |")
        lines.append("|--------|-------------|----------|------------|--------|--------------|---------|----------|")
        for m in modules:
            lines.append(
                f"| {m.get('module_name', '')} "
                f"| {m.get('order_number', '')} "
                f"| {m.get('firmware', '')} "
                f"| {m.get('ip_address', '')} "
                f"| {m.get('subnet_mask', '')} "
                f"| {m.get('profinet_name', '')} "
                f"| {m.get('network_type', '')} "
                f"| {m.get('position', '')} |"
            )
        lines.append("")

    # IP Address Inventory
    if ips:
        lines.append("## IP Address Inventory")
        lines.append("")
        lines.append("| IP Address | Module | Device |")
        lines.append("|-----------|--------|--------|")
        for ip, mod, dev in sorted(ips):
            lines.append(f"| {ip} | {mod} | {dev} |")
        lines.append("")

    # Write output
    out_path = os.path.join(output_dir, "hardware.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Report written: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Hardware catalog report generator")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    output_dir = args.output or os.path.join(DOC_OUTPUT, "analysis")

    print("=" * 70)
    print("  Hardware Catalog Report Generator")
    print("=" * 70)
    print()

    hw_path = find_hardware_json()
    if not hw_path:
        print("ERROR: No hardware JSON found. Run tia_extract_hardware.exe first.")
        print("  Expected: Doc_OUTPUT/.hardware.json")
        return 1

    print(f"Loading: {hw_path}")
    data = load_json(hw_path)
    if not data:
        print("ERROR: Could not parse hardware JSON.")
        return 1

    devices = data.get("devices", [])
    modules = sum(len(d.get("modules", [])) for d in devices)
    print(f"Found {len(devices)} device(s), {modules} module(s)")
    print()

    out_path = generate_report(data, output_dir)

    print()
    print("=" * 70)
    print("  DONE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
