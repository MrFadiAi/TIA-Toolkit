#!/usr/bin/env python3
"""
Block Dependency Graph Generator
=================================
Reads .plc_cache.json call_tree data and generates:
  - Mermaid dependency diagram (color-coded by block type)
  - Text call tree (DFS from OB roots with cycle detection)
  - Statistics summary (roots, leaves, depth, edges)

Usage:
    python dependency_graph.py [options]

Options:
    --include-data    Include DB/IDB nodes in the Mermaid diagram
    --output PATH     Output file (default: Doc_OUTPUT/analysis/dependency_graph.md)
    --verbose         Print detailed progress
"""

import json
import os
import sys
import argparse
from collections import defaultdict, deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")

# Block type colors for Mermaid nodes
TYPE_COLORS = {
    "OB": "#3B82F6",   # blue
    "FB": "#F97316",   # orange
    "FC": "#10B981",   # green
    "DB": "#9CA3AF",   # gray
    "IDB": "#9CA3AF",  # gray
}

MAX_MERMAID_NODES = 50


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def load_json(path):
    """Load JSON with UTF-8 BOM handling."""
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read().encode().decode("utf-8-sig"))


def find_cache():
    """Find the .plc_cache.json file."""
    if os.path.isdir(DOC_OUTPUT):
        for root, dirs, files in os.walk(DOC_OUTPUT):
            for f in files:
                if f == ".plc_cache.json":
                    return os.path.join(root, f)
    return None


def mermaid_node_id(name):
    """Convert block name to a safe Mermaid node ID."""
    return name.replace(" ", "_").replace(".", "_").replace("-", "_").replace("/", "_")


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def build_block_lookup(blocks):
    """Build block_name -> {block_type, programming_language} lookup."""
    lookup = {}
    for block in blocks:
        bname = block.get("block_name", "")
        if bname:
            lookup[bname] = {
                "block_type": block.get("block_type", "?"),
                "programming_language": block.get("programming_language", "?"),
            }
    return lookup


def is_data_block(block_type):
    """Check if a block type is a data block (DB/IDB)."""
    return block_type in ("DB", "IDB", "GlobalDB")


def find_roots(call_tree, called_by):
    """Find root blocks: those that make calls but are never called themselves."""
    all_callers = set(call_tree.keys())
    all_called = set(called_by.keys())
    # OB roots: in call_tree but not in called_by
    roots = sorted(all_callers - all_called)
    # If no roots found, use all callers that look like OBs
    if not roots:
        roots = sorted(all_callers)
    return roots


def compute_max_depth(roots, call_tree):
    """Compute the maximum depth of the call tree via BFS."""
    max_depth = 0
    visited = set()
    queue = deque()

    for root in roots:
        queue.append((root, 1))

    while queue:
        node, depth = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        if depth > max_depth:
            max_depth = depth
        for child in call_tree.get(node, []):
            if child not in visited:
                queue.append((child, depth + 1))

    return max_depth


def collect_mermaid_nodes(roots, call_tree, called_by, block_lookup, include_data):
    """
    Collect nodes and edges for the Mermaid diagram.
    Returns (nodes_dict, edges_list) where nodes_dict is {name: block_type}.
    If total nodes exceed MAX_MERMAID_NODES, only include top-level relationships from roots.
    """
    # First pass: collect all blocks that appear in call relationships
    all_nodes = set()
    edges = []

    for caller, callees in call_tree.items():
        for callee in callees:
            all_nodes.add(caller)
            all_nodes.add(callee)
            edges.append((caller, callee))

    # Filter out data blocks unless --include-data
    if not include_data:
        filtered_nodes = set()
        filtered_edges = []
        for node in all_nodes:
            btype = block_lookup.get(node, {}).get("block_type", "?")
            if not is_data_block(btype):
                filtered_nodes.add(node)
        for caller, callee in edges:
            caller_type = block_lookup.get(caller, {}).get("block_type", "?")
            callee_type = block_lookup.get(callee, {}).get("block_type", "?")
            if not is_data_block(caller_type) and not is_data_block(callee_type):
                filtered_edges.append((caller, callee))
        all_nodes = filtered_nodes
        edges = filtered_edges

    # Build nodes dict with types
    nodes_dict = {}
    for name in all_nodes:
        btype = block_lookup.get(name, {}).get("block_type", "?")
        nodes_dict[name] = btype

    # If too many nodes, reduce to top-level relationships from OB roots
    if len(nodes_dict) > MAX_MERMAID_NODES:
        nodes_dict = {}
        edges = []
        for root in roots:
            rtype = block_lookup.get(root, {}).get("block_type", "?")
            if not include_data and is_data_block(rtype):
                continue
            nodes_dict[root] = rtype
            for callee in call_tree.get(root, []):
                ctype = block_lookup.get(callee, {}).get("block_type", "?")
                if not include_data and is_data_block(ctype):
                    continue
                nodes_dict[callee] = ctype
                edges.append((root, callee))

    return nodes_dict, edges


# ---------------------------------------------------------------------------
# Mermaid diagram
# ---------------------------------------------------------------------------

def generate_mermaid(nodes_dict, edges, block_lookup):
    """Generate a Mermaid diagram string."""
    lines = ["graph TD"]

    # Group nodes by type for classDef and class assignments
    type_groups = defaultdict(list)
    for name, btype in nodes_dict.items():
        type_groups[btype].append(name)

    # Define styles for each type present
    for btype, color in TYPE_COLORS.items():
        if btype in type_groups:
            lines.append(f"    classDef {btype.lower()} fill:{color},color:#fff,stroke:none")

    # Add nodes with labels
    for name in sorted(nodes_dict.keys()):
        nid = mermaid_node_id(name)
        # Quote names that may have special characters
        label = name.replace('"', "'")
        lines.append(f'    {nid}["{label}"]')

    # Assign classes
    for btype, names in type_groups.items():
        nids = [mermaid_node_id(n) for n in names]
        if nids:
            lines.append(f"    class {','.join(nids)} {btype.lower()}")

    # Add edges
    seen_edges = set()
    for caller, callee in edges:
        edge_key = (caller, callee)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        cid = mermaid_node_id(caller)
        tid = mermaid_node_id(callee)
        lines.append(f"    {cid} --> {tid}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text call tree
# ---------------------------------------------------------------------------

def generate_text_tree(roots, call_tree, block_lookup):
    """
    Generate a text call tree via DFS from each OB root.
    Shows: BLOCK_NAME (LANGUAGE) with indentation.
    Marks recursive calls with * suffix.
    """
    lines = []

    def dfs(block_name, depth, path):
        """DFS traversal with cycle detection."""
        indent = "  " * depth
        connector = "+-- " if depth > 0 else ""

        btype = block_lookup.get(block_name, {}).get("block_type", "?")
        blang = block_lookup.get(block_name, {}).get("programming_language", "")

        # Cycle detection
        if block_name in path:
            lines.append(f"{indent}{connector}{block_name} ({blang}) *")
            return

        # Show all blocks including DB/IDB in text tree
        lang_str = f" ({blang})" if blang and blang != "?" else ""
        lines.append(f"{indent}{connector}{block_name}{lang_str}")

        callees = call_tree.get(block_name, [])
        for callee in sorted(callees):
            dfs(callee, depth + 1, path | {block_name})

    for root in roots:
        lines.append("")  # blank line between roots
        dfs(root, 0, set())

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_statistics(call_tree, called_by, block_lookup, blocks, roots):
    """Compute dependency graph statistics."""
    # All blocks in call relationships
    all_in_tree = set(call_tree.keys()) | set(called_by.keys())

    # Count edges
    total_edges = 0
    for caller, callees in call_tree.items():
        total_edges += len(callees)

    # Classify blocks
    root_set = set(roots)
    leaf_blocks = set()
    intermediate_blocks = set()

    for name in all_in_tree:
        if name in root_set:
            continue
        callees = call_tree.get(name, [])
        if not callees:
            leaf_blocks.add(name)
        else:
            intermediate_blocks.add(name)

    # Max depth
    max_depth = compute_max_depth(roots, call_tree)

    # Block type breakdown (from blocks in call tree)
    type_counts = defaultdict(int)
    for name in all_in_tree:
        btype = block_lookup.get(name, {}).get("block_type", "?")
        type_counts[btype] += 1

    return {
        "total_blocks_in_project": len(blocks),
        "blocks_in_call_tree": len(all_in_tree),
        "roots": len(roots),
        "intermediate": len(intermediate_blocks),
        "leaves": len(leaf_blocks),
        "total_edges": total_edges,
        "max_depth": max_depth,
        "type_breakdown": dict(type_counts),
        "root_names": roots,
        "intermediate_names": sorted(intermediate_blocks),
        "leaf_names": sorted(leaf_blocks),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(stats, mermaid_str, text_tree_str):
    """Generate the full markdown report."""
    lines = []

    # Banner
    lines.append("# Block Dependency Graph")
    lines.append("")
    lines.append(f"Analyzed **{stats['blocks_in_call_tree']}** blocks in call relationships "
                 f"(out of {stats['total_blocks_in_project']} total).")
    lines.append("")

    # Mermaid diagram
    lines.append("## Call Graph")
    lines.append("")
    if stats["blocks_in_call_tree"] > MAX_MERMAID_NODES:
        lines.append(f"> *Graph limited to top-level relationships from OB roots "
                     f"(full tree has {stats['blocks_in_call_tree']} nodes).*")
        lines.append("")
    lines.append("```mermaid")
    lines.append(mermaid_str)
    lines.append("```")
    lines.append("")

    # Text call tree
    lines.append("## Call Tree")
    lines.append("")
    lines.append("```")
    lines.append(text_tree_str.strip())
    lines.append("```")
    lines.append("")

    # Statistics table
    lines.append("## Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total blocks in project | {stats['total_blocks_in_project']} |")
    lines.append(f"| Blocks in call tree | {stats['blocks_in_call_tree']} |")
    lines.append(f"| Roots (entry points) | {stats['roots']} |")
    lines.append(f"| Intermediate blocks | {stats['intermediate']} |")
    lines.append(f"| Leaf blocks | {stats['leaves']} |")
    lines.append(f"| Total call edges | {stats['total_edges']} |")
    lines.append(f"| Max call depth | {stats['max_depth']} |")
    lines.append("")

    # Type breakdown
    type_breakdown = stats.get("type_breakdown", {})
    if type_breakdown:
        lines.append("### Blocks by Type (in call tree)")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for btype in sorted(type_breakdown.keys()):
            lines.append(f"| {btype} | {type_breakdown[btype]} |")
        lines.append("")

    # Root blocks detail
    if stats["root_names"]:
        lines.append("### Root Blocks (Entry Points)")
        lines.append("")
        for name in stats["root_names"]:
            lines.append(f"- `{name}`")
        lines.append("")

    # Leaf blocks
    if stats["leaf_names"]:
        lines.append("### Leaf Blocks (No outgoing calls)")
        lines.append("")
        leaves_display = stats["leaf_names"]
        if len(leaves_display) > 30:
            for name in leaves_display[:30]:
                lines.append(f"- `{name}`")
            lines.append(f"- ... and {len(leaves_display) - 30} more")
        else:
            for name in leaves_display:
                lines.append(f"- `{name}`")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate block dependency graph from .plc_cache.json"
    )
    parser.add_argument(
        "--include-data", action="store_true",
        help="Include DB/IDB nodes in the Mermaid diagram"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: Doc_OUTPUT/analysis/dependency_graph.md)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed progress"
    )
    args = parser.parse_args()

    output_path = args.output or os.path.join(DOC_OUTPUT, "analysis", "dependency_graph.md")

    # Banner
    print("=" * 60)
    print("  Block Dependency Graph Generator")
    print("=" * 60)
    print()

    # Find and load data
    cache_path = find_cache()
    if not cache_path:
        print("ERROR: No .plc_cache.json found in Doc_OUTPUT/.")
        print("       Run extract_plc_full.py first.")
        sys.exit(1)

    if args.verbose:
        print(f"  Loading: {cache_path}")
    else:
        print("  Loading data...")

    data = load_json(cache_path)

    call_tree = data.get("call_tree", {})
    called_by = data.get("called_by", {})
    blocks = data.get("blocks", [])

    if not call_tree:
        print("ERROR: No call_tree data found in cache.")
        sys.exit(1)

    print(f"  Call tree: {len(call_tree)} callers, ", end="")
    all_in_tree = set(call_tree.keys()) | set(called_by.keys())
    print(f"{len(all_in_tree)} blocks in relationships")

    # Build block type lookup
    block_lookup = build_block_lookup(blocks)
    if args.verbose:
        print(f"  Block lookup: {len(block_lookup)} blocks indexed")

    # Find roots
    roots = find_roots(call_tree, called_by)
    print(f"  Roots (OB entry points): {len(roots)}")
    for r in roots:
        print(f"    - {r}")

    # Compute statistics
    print("  Computing statistics...")
    stats = compute_statistics(call_tree, called_by, block_lookup, blocks, roots)
    print(f"    Edges: {stats['total_edges']}, Max depth: {stats['max_depth']}")

    # Generate Mermaid diagram
    print("  Generating Mermaid diagram...")
    nodes_dict, edges = collect_mermaid_nodes(
        roots, call_tree, called_by, block_lookup, args.include_data
    )
    mermaid_str = generate_mermaid(nodes_dict, edges, block_lookup)
    if args.verbose:
        print(f"    Mermaid nodes: {len(nodes_dict)}, edges: {len(edges)}")

    # Generate text call tree
    print("  Generating text call tree...")
    text_tree_str = generate_text_tree(roots, call_tree, block_lookup)

    # Generate report
    report = generate_report(stats, mermaid_str, text_tree_str)

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print()
    print(f"  Output: {output_path}")
    print()
    print("=" * 60)
    print(f"  Done: {stats['blocks_in_call_tree']} blocks, "
          f"{stats['total_edges']} edges, max depth {stats['max_depth']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
