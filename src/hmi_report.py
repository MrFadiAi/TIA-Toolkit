#!/usr/bin/env python3
"""
HMI Compact Report Generator
=============================
Reads hmi_merged.json and generates:
  - Markdown files per screen in Doc_OUTPUT/  - Consolidated tags file at Doc_OUTPUT/hmi_tags.md

Usage:
    python hmi_report.py [output_file]

Default: generates .md files in Doc_OUTPUT/hmi_screens/ (screens + hmi_tags.md)
"""

import json
import os
import re
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
MERGED_INPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", ".hmi_merged.json")
ONLINE_INPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", ".hmi_online_data.json")
SCREENS_DIR = os.path.join(PROJECT_ROOT, "Doc_OUTPUT", "hmi_screens")
TAGS_OUTPUT = os.path.join(SCREENS_DIR, "hmi_tags.md")


def find_input():
    """Find best available input: merged first, then online-only."""
    if os.path.exists(MERGED_INPUT):
        return MERGED_INPUT
    if os.path.exists(ONLINE_INPUT):
        return ONLINE_INPUT
    return MERGED_INPUT


def load_merged(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def safe_filename(name):
    """Convert a screen name to a safe filename."""
    return re.sub(r'[^\w\-.]', '_', name)


_EVENT_TYPE_MAP = {
    "Up": "Release",
    "Down": "Press",
    "Loaded": "Loaded",
}


def _norm_event(event):
    """Normalize event data from both online and merged formats."""
    ev_type = event.get("event_type", "") or event.get("function", "")
    ev_type = _EVENT_TYPE_MAP.get(ev_type, ev_type)
    navs = event.get("navigates_to", [])
    tags = event.get("plc_tags", event.get("tags_used", []))
    resolved = event.get("resolved_plc_tags", [])
    script = event.get("script", event.get("code", ""))
    return ev_type, navs, tags, resolved, script


# ── Markdown generation ──────────────────────────────────────────────────

def generate_screen_md(screen, nav_map=None, all_screen_names=None):
    """Generate markdown content for a single screen."""
    lines = []
    sname = screen.get("screen_name", "UNKNOWN")
    elements = screen.get("elements", [])
    elem_count = screen.get("element_count", 0)
    s_navigations = screen.get("screen_navigations", [])

    lines.append(f"# Screen: {sname}")
    lines.append("")

    # Summary table
    type_counts = defaultdict(int)
    for e in elements:
        type_counts[e.get("type", "unknown")] += 1

    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Elements | {elem_count} |")
    if s_navigations:
        nav_links = []
        for n in s_navigations:
            fn = safe_filename(n)
            nav_links.append(f"[{n}]({fn}.md)")
        lines.append(f"| Navigates to | {', '.join(nav_links)} |")
    parts = [f"{v}x `{k}`" for k, v in sorted(type_counts.items())]
    lines.append(f"| Types | {' &middot; '.join(parts)} |")
    lines.append("")

    # Per-element detail
    for elem in elements:
        ename = elem.get("name", "")
        etype = elem.get("type", "")
        text = elem.get("text", "")
        pos = elem.get("position", {})
        io_role = elem.get("io_role", "")
        bindings = elem.get("tag_bindings", [])
        events = elem.get("events", [])

        lines.append(f"## {ename}")
        lines.append("")

        # Element info table
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Type | `{etype}` |")
        if text:
            lines.append(f"| Text | {text} |")
        window_screen = elem.get("window_screen", "")
        if window_screen:
            fn = safe_filename(window_screen)
            lines.append(f"| Shows screen | [{window_screen}]({fn}.md) |")
        if pos and (pos.get("x") or pos.get("y")):
            lines.append(f"| Position | x={pos.get('x', 0)}, y={pos.get('y', 0)}, w={pos.get('w', 0)}, h={pos.get('h', 0)} |")
        if io_role:
            lines.append(f"| Role | `{io_role}` |")
        lines.append("")

        # Tag bindings
        if bindings:
            lines.append("### Tag Bindings")
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
            lines.append("*No tag bindings.*")
            lines.append("")

        # Events
        if events:
            lines.append("### Events")
            lines.append("")
            for ev in events:
                ev_type, navs, tags, resolved, script = _norm_event(ev)
                lines.append(f"**{ev_type}**")
                lines.append("")
                if navs:
                    nav_links = []
                    for n in navs:
                        fn = safe_filename(n)
                        nav_links.append(f"[{n}]({fn}.md)")
                    lines.append(f"- Navigates to: {', '.join(nav_links)}")
                if tags:
                    for i, tag in enumerate(tags):
                        plc = ""
                        if i < len(resolved):
                            plc = resolved[i].get("plc_tag", "") if isinstance(resolved[i], dict) else ""
                        if plc:
                            lines.append(f"- Tag: `{tag}` &rarr; `{plc}`")
                        else:
                            lines.append(f"- Tag: `{tag}`")
                if script and len(script) > 5:
                    excerpt = script[:200].replace("\n", " ").strip()
                    lines.append(f"- Script: `{excerpt}{'...' if len(script) > 200 else ''}`")
                if not navs and not tags and not (script and len(script) > 5):
                    lines.append("- *(empty event)*")
                lines.append("")
        else:
            lines.append("*No events.*")
            lines.append("")

    # Screen-level events
    screen_events = screen.get("screen_events", [])
    if screen_events:
        lines.append("## Screen Events")
        lines.append("")
        for ev in screen_events:
            ev_type, navs, tags, resolved, script = _norm_event(ev)
            lines.append(f"**{ev_type}**")
            lines.append("")
            if navs:
                nav_links = []
                for n in navs:
                    fn = safe_filename(n)
                    nav_links.append(f"[{n}]({fn}.md)")
                lines.append(f"- Navigates to: {', '.join(nav_links)}")
            if tags:
                for i, tag in enumerate(tags):
                    plc = ""
                    if i < len(resolved):
                        plc = resolved[i].get("plc_tag", "") if isinstance(resolved[i], dict) else ""
                    if plc:
                        lines.append(f"- Tag: `{tag}` &rarr; `{plc}`")
                    else:
                        lines.append(f"- Tag: `{tag}`")
            if script and len(script) > 5:
                excerpt = script[:200].replace("\n", " ").strip()
                lines.append(f"- Script: `{excerpt}{'...' if len(script) > 200 else ''}`")
            lines.append("")

    return "\n".join(lines)


def generate_tags_md(data):
    """Generate a consolidated tags markdown file."""
    lines = []
    screens = data.get("screens", [])
    summary = data.get("summary", {})
    nav_map = data.get("navigation_map", {})

    lines.append("# HMI Tags Overview")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Screens: **{summary.get('total_screens', 0)}**")
    lines.append(f"- Elements: **{summary.get('total_elements', 0)}**")
    lines.append(f"- Tag bindings: **{summary.get('total_tag_bindings', 0)}**")
    lines.append(f"- With PLC tag: **{summary.get('bindings_with_plc_tag', 0)}**")
    lines.append(f"- Events: **{summary.get('total_events', 0)}**")
    lines.append("")

    # Navigation map
    if nav_map:
        lines.append("## Navigation Map")
        lines.append("")
        for src, targets in sorted(nav_map.items()):
            fn_src = safe_filename(src)
            tgt_links = []
            for t in targets:
                fn_t = safe_filename(t)
                tgt_links.append(f"[{t}]({fn_t}.md)")
            lines.append(f"- [{src}]({fn_src}.md) &rarr; {', '.join(tgt_links)}")
        lines.append("")

    # Screen index
    lines.append("## Screens")
    lines.append("")
    for screen in screens:
        sname = screen.get("screen_name", "UNKNOWN")
        elem_count = screen.get("element_count", 0)
        fn = safe_filename(sname)
        lines.append(f"- [{sname}]({fn}.md) ({elem_count} elements)")
    lines.append("")

    # Collect all tag bindings across all screens
    all_tags = []
    for screen in screens:
        sname = screen.get("screen_name", "UNKNOWN")
        for elem in screen.get("elements", []):
            ename = elem.get("name", "")
            etype = elem.get("type", "")
            for b in elem.get("tag_bindings", []):
                all_tags.append({
                    "screen": sname,
                    "element": ename,
                    "element_type": etype,
                    "property": b.get("property", ""),
                    "hmi_tag": b.get("hmi_tag", ""),
                    "plc_tag": b.get("plc_tag", ""),
                    "plc_name": b.get("plc_name", ""),
                    "data_type": b.get("data_type", ""),
                    "connection": b.get("connection", ""),
                    "source": b.get("source", ""),
                })
            # Also collect tags from events
            for ev in elem.get("events", []):
                ev_tags = ev.get("plc_tags", ev.get("tags_used", []))
                resolved = ev.get("resolved_plc_tags", [])
                for i, tag in enumerate(ev_tags):
                    plc = ""
                    if i < len(resolved):
                        plc = resolved[i].get("plc_tag", "") if isinstance(resolved[i], dict) else ""
                    # Avoid duplicates already in tag_bindings
                    if not any(t["hmi_tag"] == tag and t["screen"] == sname and t["element"] == ename for t in all_tags):
                        all_tags.append({
                            "screen": sname,
                            "element": ename,
                            "element_type": etype,
                            "property": "event_tag",
                            "hmi_tag": tag,
                            "plc_tag": plc,
                            "plc_name": resolved[i].get("plc_name", "") if i < len(resolved) and isinstance(resolved[i], dict) else "",
                            "data_type": resolved[i].get("data_type", "") if i < len(resolved) and isinstance(resolved[i], dict) else "",
                            "connection": "",
                            "source": "event",
                        })

    # Tags table
    lines.append("## All Tags")
    lines.append("")
    lines.append("| Screen | Element | Type | Property | HMI Tag | PLC Tag | PLC Name | Data Type |")
    lines.append("|--------|---------|------|----------|---------|---------|----------|-----------|")
    for t in all_tags:
        prop = t["property"]
        if prop == "js_reference":
            prop = "*(js)*"
        elif prop == "event_tag":
            prop = "*(event)*"
        plc_tag = t["plc_tag"] or "*(unresolved)*"
        lines.append(f"| {t['screen']} | {t['element']} | `{t['element_type']}` | {prop} | `{t['hmi_tag']}` | `{plc_tag}` | {t['plc_name']} | {t['data_type']} |")
    lines.append("")

    # Unique tags index (grouped by HMI tag)
    unique_tags = defaultdict(list)
    for t in all_tags:
        key = t["hmi_tag"]
        unique_tags[key].append(t)

    if unique_tags:
        lines.append("## Unique Tags Index")
        lines.append("")
        lines.append("| HMI Tag | PLC Tag | Data Type | Used In |")
        lines.append("|---------|---------|-----------|---------|")
        for hmi_tag in sorted(unique_tags.keys()):
            entries = unique_tags[hmi_tag]
            plc_tag = entries[0]["plc_tag"] or "*(unresolved)*"
            data_type = entries[0]["data_type"] or ""
            locations = []
            for e in entries:
                locations.append(f"{e['screen']}/{e['element']}")
            lines.append(f"| `{hmi_tag}` | `{plc_tag}` | {data_type} | {' &middot; '.join(locations)} |")
        lines.append("")

    return "\n".join(lines)


def generate_markdown_reports(data):
    """Generate all markdown files: per-screen + consolidated tags."""
    screens = data.get("screens", [])
    written = []

    # Per-screen .md files
    os.makedirs(SCREENS_DIR, exist_ok=True)
    for screen in screens:
        sname = screen.get("screen_name", "UNKNOWN")
        md = generate_screen_md(screen, nav_map=data.get("navigation_map"))
        fname = safe_filename(sname) + ".md"
        fpath = os.path.join(SCREENS_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)
        written.append(fpath)

    # Consolidated tags .md
    tags_md = generate_tags_md(data)
    with open(TAGS_OUTPUT, "w", encoding="utf-8") as f:
        f.write(tags_md)
    written.append(TAGS_OUTPUT)

    return written


# ── Legacy text report (kept for backwards compat) ───────────────────────

def format_binding(binding):
    """Format a single tag binding compactly."""
    prop = binding.get("property", "")
    hmi_tag = binding.get("hmi_tag", "")
    plc_tag = binding.get("plc_tag", "")
    plc_name = binding.get("plc_name", "")
    data_type = binding.get("data_type", "")
    source = binding.get("source", "")

    lines = []
    label = f"{prop} tag" if prop and prop != "js_reference" else "tag"
    if prop == "js_reference":
        label = "js tag"

    lines.append(f"    hmi_tag ({label}): {hmi_tag}")
    if plc_tag:
        lines.append(f"    plc_tag: {plc_tag}")
    else:
        lines.append(f"    plc_tag: (not resolved)")
    if plc_name:
        lines.append(f"    plc_name: {plc_name}")
    if data_type:
        lines.append(f"    data_type: {data_type}")
    return lines


def format_event(event):
    """Format a single event compactly. Handles both online and merged formats."""
    lines = []
    ev_type, navs, tags, resolved, script = _norm_event(event)

    if ev_type:
        lines.append(f"    event: {ev_type}")
    if navs:
        for nav in navs:
            lines.append(f"      -> ChangeScreen: {nav}")
    if tags:
        for i, tag in enumerate(tags):
            plc = ""
            if i < len(resolved):
                plc = resolved[i].get("plc_tag", "") if isinstance(resolved[i], dict) else ""
            if plc:
                lines.append(f"      tag: {tag}  ->  {plc}")
            else:
                lines.append(f"      tag: {tag}")
    if script and len(script) > 5:
        excerpt = script[:120].replace("\n", " ").strip()
        lines.append(f"      script: {excerpt}{'...' if len(script) > 120 else ''}")
    if not navs and not tags and not (script and len(script) > 5):
        lines.append(f"      (empty event)")
    return lines


def generate_report(data):
    """Generate the compact text report (legacy)."""
    lines = []
    screens = data.get("screens", [])
    summary = data.get("summary", {})

    lines.append("=" * 80)
    lines.append("  HMI ELEMENT REPORT")
    lines.append("=" * 80)
    lines.append(f"  Screens: {summary.get('total_screens', 0)}")
    lines.append(f"  Elements: {summary.get('total_elements', 0)}")
    lines.append(f"  Tag bindings: {summary.get('total_tag_bindings', 0)}")
    lines.append(f"  With PLC tag: {summary.get('bindings_with_plc_tag', 0)}")
    lines.append(f"  Events: {summary.get('total_events', 0)}")
    lines.append("=" * 80)
    lines.append("")

    nav_map = data.get("navigation_map", {})
    if nav_map:
        lines.append("SCREEN NAVIGATION MAP")
        lines.append("-" * 60)
        for src, targets in sorted(nav_map.items()):
            for t in targets:
                lines.append(f"  {src}  ->  {t}")
        lines.append("")
        lines.append("")

    for screen in screens:
        sname = screen.get("screen_name", "UNKNOWN")
        elements = screen.get("elements", [])
        elem_count = screen.get("element_count", 0)
        s_navigations = screen.get("screen_navigations", [])

        lines.append("=" * 80)
        lines.append(f"  SCREEN: {sname}")
        lines.append(f"  Elements: {elem_count}")
        if s_navigations:
            lines.append(f"  Navigates to: {', '.join(s_navigations)}")

        type_counts = defaultdict(int)
        for e in elements:
            type_counts[e.get("type", "unknown")] += 1
        parts = [f"{v}x {k}" for k, v in sorted(type_counts.items())]
        lines.append(f"  Summary: {', '.join(parts)}")
        lines.append("-" * 80)

        for elem in elements:
            ename = elem.get("name", "")
            etype = elem.get("type", "")
            text = elem.get("text", "")
            pos = elem.get("position", {})
            io_role = elem.get("io_role", "")
            bindings = elem.get("tag_bindings", [])
            events = elem.get("events", [])

            lines.append("")
            lines.append(f"  {ename}  ({etype})")
            if text:
                lines.append(f"    text: {text}")
            window_screen = elem.get("window_screen", "")
            if window_screen:
                lines.append(f"    shows screen: {window_screen}")
            if pos and (pos.get("x") or pos.get("y")):
                lines.append(f"    position: x={pos.get('x', 0)}, y={pos.get('y', 0)}, w={pos.get('w', 0)}, h={pos.get('h', 0)}")
            if io_role:
                lines.append(f"    role: {io_role}")
            if bindings:
                lines.append(f"    --- tag bindings ({len(bindings)}) ---")
                for b in bindings:
                    lines.extend(format_binding(b))
            else:
                lines.append(f"    tag bindings: none")
            if events:
                lines.append(f"    --- events ({len(events)}) ---")
                for ev in events:
                    lines.extend(format_event(ev))
            else:
                lines.append(f"    events: none")

        lines.append("")
        screen_events = screen.get("screen_events", [])
        if screen_events:
            lines.append(f"  --- screen events ({len(screen_events)}) ---")
            for ev in screen_events:
                lines.extend(format_event(ev))
            lines.append("")

    return "\n".join(lines)


def main():
    import sys

    print("Loading data...")
    input_path = find_input()
    print(f"  Source: {os.path.basename(input_path)}")
    data = load_merged(input_path)

    # Generate markdown reports
    print("Generating markdown reports...")
    written = generate_markdown_reports(data)
    for f in written:
        print(f"  Written: {os.path.relpath(f, SCRIPT_DIR)}")

    print(f"\n  {len(written)} .md files generated.")


if __name__ == "__main__":
    main()
