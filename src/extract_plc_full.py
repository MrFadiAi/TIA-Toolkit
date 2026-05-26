#!/usr/bin/env python3
"""
PLC Program Block Extractor (Offline)
======================================
Parses TIA Portal exported Openness XML block and tag table files.

Extracts:
  - Block metadata (name, number, type, language)
  - Interface definitions (inputs, outputs, inouts, statics, temps, constants)
  - SCL/STL code (reconstructed from tokenized XML)
  - Tag cross-references (which PLC tags are used where)
  - Call structure (which blocks call which)

Usage:
    python extract_plc_full.py "<DATA_Program blocks path>" [options]
    python extract_plc_full.py "<path>" --list-blocks

Options:
    --output PATH     Output JSON (default: Doc_OUTPUT/plc_full.json)
    --tags PATH       PLC tags directory (default: <base>/PLC tags)
    --list-blocks     List found blocks and exit
    --verbose         Print detailed progress
"""

import os
import re
import sys
import json
import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# XML namespaces used in TIA Portal exports
NS_INTERFACE = "http://www.siemens.com/automation/Openness/SW/Interface/v5"
NS_ST = "http://www.siemens.com/automation/Openness/SW/NetworkSource/StructuredText/v3"
NS_STL = "http://www.siemens.com/automation/Openness/SW/NetworkSource/StatementList/v4"

# Block type mapping from XML element names
BLOCK_TYPES = {
    "SW.Blocks.FB": "FB",
    "SW.Blocks.FC": "FC",
    "SW.Blocks.OB": "OB",
    "SW.Blocks.GlobalDB": "DB",
    "SW.Blocks.InstanceDB": "IDB",
    "SW.Types.PlcDataType": "UDT",
    "SW.Types.PlcStruct": "STRUCT",
}

# Interface section names that contain variables
INTERFACE_SECTIONS = ["Input", "Output", "InOut", "Static", "Temp", "Constant", "Return"]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def strip_ns(tag):
    """Remove XML namespace from tag name."""
    return tag.split("}")[-1] if "}" in tag else tag


def get_text(element, path, default=""):
    """Get text from an element, handling namespace."""
    text = element.findtext(path, default)
    return text.strip() if text else default


def findall_ns(element, tag_local):
    """Find all children matching local tag name (ignoring namespace)."""
    return [c for c in element if strip_ns(c.tag) == tag_local]


def find_ns(element, tag_local):
    """Find first child matching local tag name (ignoring namespace)."""
    for c in element:
        if strip_ns(c.tag) == tag_local:
            return c
    return None


# ---------------------------------------------------------------------------
# Block XML discovery
# ---------------------------------------------------------------------------
def find_block_files(base_path):
    """Walk directory recursively for .xml block files."""
    blocks = []
    # Normalize for reliable comparison
    tags_dir_normalized = os.path.normpath(os.path.join(base_path, "PLC tags")).lower()

    for root, dirs, files in os.walk(base_path):
        # Skip PLC tags directory (exact match, not substring)
        if os.path.normpath(root).lower() == tags_dir_normalized:
            continue
        # Also skip any subdirectory of PLC tags
        if os.path.normpath(root).lower().startswith(tags_dir_normalized + os.sep):
            continue
        for f in files:
            if f.lower().endswith(".xml"):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, base_path)
                blocks.append((full_path, rel_path))

    return sorted(blocks)


def detect_block_type(root):
    """Detect block type from root element. Returns (type_str, block_elem)."""
    last_child = None
    for child in root:
        last_child = child
        tag = strip_ns(child.tag)
        if tag in BLOCK_TYPES:
            return BLOCK_TYPES[tag], child
    return None, last_child


# ---------------------------------------------------------------------------
# Interface parsing
# ---------------------------------------------------------------------------
def parse_interface(block_elem):
    """Parse block interface sections from XML."""
    interface = {"inputs": [], "outputs": [], "inouts": [],
                 "statics": [], "temps": [], "constants": [], "members": [], "returns": []}
    section_map = {
        "Input": "inputs", "Output": "outputs", "InOut": "inouts",
        "Static": "statics", "Temp": "temps", "Constant": "constants",
        "None": "members", "Return": "returns",
    }

    # Find Interface element
    iface_elem = None
    for attr_list in block_elem.iter():
        if strip_ns(attr_list.tag) == "Interface":
            iface_elem = attr_list
            break
    if iface_elem is None:
        return interface

    # Find Sections
    sections_elem = find_ns(iface_elem, "Sections")
    if sections_elem is None:
        # Try direct children (interface may contain sections directly)
        for child in iface_elem:
            if strip_ns(child.tag) == "Sections":
                sections_elem = child
                break

    if sections_elem is None:
        return interface

    for section in sections_elem:
        if strip_ns(section.tag) != "Section":
            continue
        section_name = section.get("Name", "")
        target_key = section_map.get(section_name)
        if not target_key:
            # Check for nested Sections inside unmapped sections (e.g., "Base")
            for sub in section:
                if strip_ns(sub.tag) == "Sections":
                    for nested_sec in sub:
                        if strip_ns(nested_sec.tag) == "Section":
                            nested_name = nested_sec.get("Name", "")
                            nested_key = section_map.get(nested_name)
                            if nested_key:
                                for member in nested_sec:
                                    if strip_ns(member.tag) == "Member":
                                        interface[nested_key].append(parse_member(member))
            continue

        for member in section:
            if strip_ns(member.tag) == "Member":
                parsed = parse_member(member)
                interface[target_key].append(parsed)

    return interface


def _collect_members(sections_elem, result_list, depth):
    """Recursively collect Members from a Sections > Section > [Sections...] hierarchy."""
    for section in sections_elem:
        if strip_ns(section.tag) != "Section":
            continue
        for item in section:
            tag = strip_ns(item.tag)
            if tag == "Member":
                result_list.append(parse_member(item, depth + 1))
            elif tag == "Sections":
                # Nested Sections inside a Section (e.g., Section "Base" containing Sections)
                _collect_members(item, result_list, depth)


def parse_member(member_elem, depth=0):
    """Parse a single interface member, including nested struct members."""
    name = member_elem.get("Name", "")
    datatype = member_elem.get("Datatype", "")
    remanence = member_elem.get("Remanence", "")
    accessibility = member_elem.get("Accessibility", "")
    version = member_elem.get("Version", "")
    informative = member_elem.get("Informative", "")

    # Start value
    start_value = ""
    sv_elem = find_ns(member_elem, "StartValue")
    if sv_elem is not None and sv_elem.text:
        start_value = sv_elem.text.strip()

    # Comment
    comment = ""
    comment_elem = find_ns(member_elem, "Comment")
    if comment_elem is not None:
        for mlt in comment_elem:
            if strip_ns(mlt.tag) == "MultiLanguageText":
                if mlt.get("Lang", "") == "en-US" and mlt.text:
                    comment = mlt.text.strip()
                    break
        if not comment:
            for mlt in comment_elem:
                if strip_ns(mlt.tag) == "MultiLanguageText" and mlt.text:
                    comment = mlt.text.strip()
                    break

    # Nested members (structs/UDTs)
    children = []
    for child in member_elem:
        if strip_ns(child.tag) == "Member":
            children.append(parse_member(child, depth + 1))
        elif strip_ns(child.tag) == "Sections":
            # UDT-typed members have nested Sections > Section > Member
            _collect_members(child, children, depth)

    # Subelement start values (array/struct element defaults like alarm texts, parameters)
    subelement_values = []
    for sub in member_elem.iter():
        if strip_ns(sub.tag) == "Subelement":
            sv_elem = None
            for sub_child in sub:
                if strip_ns(sub_child.tag) == "StartValue" and sub_child.text:
                    sv_elem = sub_child
                    break
            if sv_elem is not None:
                path = sub.get("Path", "")
                subelement_values.append({"path": path, "start_value": sv_elem.text.strip()})

    # Read BooleanAttribute children from AttributeList (used by PLC type structs)
    bool_attrs = {}
    attr_list = find_ns(member_elem, "AttributeList")
    if attr_list is not None:
        for attr in attr_list:
            if strip_ns(attr.tag) == "BooleanAttribute":
                attr_name = attr.get("Name", "")
                if attr.text:
                    bool_attrs[attr_name] = attr.text.strip().lower() == "true"

    # Determine accessibility: prefer direct attribute, fall back to BooleanAttributes
    if not accessibility:
        parts = []
        if bool_attrs.get("ExternalAccessible"):
            parts.append("Read")
        if bool_attrs.get("ExternalWritable"):
            parts.append("Write")
        if bool_attrs.get("ExternalVisible"):
            parts.append("Visible")
        if parts:
            accessibility = "/".join(parts)

    result = {
        "name": name,
        "data_type": datatype,
        "comment": comment,
    }
    if start_value:
        result["start_value"] = start_value
    if remanence:
        result["remanence"] = remanence
    if accessibility:
        result["accessibility"] = accessibility
    if version:
        result["version"] = version
    if informative:
        result["informative"] = True
    if bool_attrs.get("SetPoint") is not None:
        result["setpoint"] = bool_attrs["SetPoint"]
    if children:
        result["members"] = children
    if subelement_values:
        result["subelement_values"] = subelement_values

    return result


def count_interface_vars(interface):
    """Count total variables across all interface sections."""
    total = 0
    for section in ("inputs", "outputs", "inouts", "statics", "temps", "constants", "members", "returns"):
        for m in interface.get(section, []):
            total += 1
            total += count_nested(m)
    return total


def count_nested(member):
    """Recursively count nested members."""
    count = 0
    for child in member.get("members", []):
        count += 1
        count += count_nested(child)
    return count


# ---------------------------------------------------------------------------
# SCL code reconstruction (StructuredText v3 tokenized XML)
# ---------------------------------------------------------------------------
def reconstruct_scl(st_elem):
    """Reconstruct readable SCL code from tokenized StructuredText XML."""
    children = list(st_elem)
    if not children:
        # Plain text content (V14 format)
        text = st_elem.text or ""
        return text.strip()

    parts = []
    for child in children:
        tag = strip_ns(child.tag)
        _append_scl_part(child, tag, parts)

    return "".join(parts).strip()


def _append_scl_part(elem, tag, parts):
    """Append one XML token's text contribution."""
    if tag == "Token":
        text = elem.get("Text", "")
        parts.append(text)
    elif tag == "Blank":
        num = elem.get("Num")
        parts.append(" " * int(num) if num else " ")
    elif tag == "Text":
        parts.append(elem.text or "")
    elif tag == "NewLine":
        num = elem.get("Num")
        parts.append("\n" * int(num) if num else "\n")
    elif tag == "LineComment":
        text_elem = find_ns(elem, "Text")
        if text_elem is not None and text_elem.text:
            parts.append("//" + text_elem.text)
        elif elem.text:
            parts.append("//" + elem.text)
    elif tag == "BlockComment":
        parts.append("(*")
        for sub in elem:
            sub_tag = strip_ns(sub.tag)
            if sub_tag == "Text":
                parts.append(sub.text or "")
            elif sub_tag == "NewLine":
                parts.append("\n")
        parts.append("*)")
    elif tag == "Access":
        _reconstruct_access(elem, parts)
    elif tag == "NamePart":
        parts.append(elem.get("Text", ""))
    elif tag == "Date":
        parts.append(elem.get("Value", ""))
    elif tag == "Time":
        parts.append(elem.get("Value", ""))


def _reconstruct_access(access_elem, parts):
    """Reconstruct an Access element (variable/constant reference)."""
    scope = access_elem.get("Scope", "")

    if scope == "Call":
        # Block call: extract block name and parameters
        _reconstruct_call(access_elem, parts)
        return

    if scope == "GlobalVariable":
        # PLC tag: "DB_NAME".Member
        _reconstruct_symbol(access_elem, parts, global_var=True)
        return

    if scope == "LocalVariable":
        # Local var: #VarName
        parts.append("#")
        _reconstruct_symbol(access_elem, parts, global_var=False)
        return

    if scope == "LocalConstant":
        _reconstruct_symbol(access_elem, parts, global_var=False)
        return

    if scope == "Label":
        for child in access_elem:
            if strip_ns(child.tag) == "Label":
                parts.append(child.get("Name", ""))
        return

    if scope in ("LiteralConstant", "TypedConstant"):
        const_elem = find_ns(access_elem, "Constant")
        if const_elem is not None:
            val_elem = find_ns(const_elem, "ConstantValue")
            if val_elem is not None and val_elem.text:
                parts.append(val_elem.text)
            else:
                type_elem = find_ns(const_elem, "ConstantType")
                val = const_elem.text or ""
                if type_elem is not None and type_elem.text == "String":
                    parts.append(f"'{val}'")
                else:
                    parts.append(val)
        return

    if scope in ("Input", "Output", "InOut", "Static", "Temp"):
        parts.append("#")
        _reconstruct_symbol(access_elem, parts, global_var=False)
        return

    # Fallback: process children normally
    for child in access_elem:
        child_tag = strip_ns(child.tag)
        if child_tag not in ("Symbol", "Constant", "CallInfo", "Instance", "Instruction"):
            _append_scl_part(child, child_tag, parts)


def _reconstruct_symbol(parent_elem, parts, global_var=False):
    """Reconstruct a Symbol path from Component elements."""
    symbols = []
    for child in parent_elem:
        tag = strip_ns(child.tag)
        if tag == "Symbol":
            _collect_symbol_path(child, symbols, global_var)
        elif tag == "Component":
            name = child.get("Name", "")
            has_quotes = False
            for attr in child:
                if strip_ns(attr.tag) == "BooleanAttribute" and attr.get("Name") == "HasQuotes":
                    has_quotes = attr.text == "true"
            if global_var and has_quotes:
                symbols.append(f'"{name}"')
            else:
                symbols.append(name)
        elif tag in ("Token", "Blank", "Text", "NewLine"):
            _append_scl_part(child, tag, parts)

    if symbols:
        parts.append(".".join(symbols))


def _collect_symbol_path(symbol_elem, parts, global_var):
    """Collect dot-separated symbol path from a Symbol element."""
    segments = []
    for child in symbol_elem:
        tag = strip_ns(child.tag)
        if tag == "Component":
            name = child.get("Name", "")
            has_quotes = False
            for attr in child:
                if strip_ns(attr.tag) == "BooleanAttribute" and attr.get("Name") == "HasQuotes":
                    has_quotes = attr.text == "true"
            if global_var and has_quotes:
                segments.append(f'"{name}"')
            else:
                segments.append(name)
        elif tag == "Token":
            tok = child.get("Text", "")
            if tok == ".":
                pass  # dot separator handled by join
            else:
                segments.append(tok)
        elif tag == "Access" and child.get("AccessModifier") == "Array":
            # Array access: [index]
            inner_parts = []
            for sub in child:
                sub_tag = strip_ns(sub.tag)
                if sub_tag == "Symbol":
                    _collect_symbol_path(sub, inner_parts, False)
                elif sub_tag == "Access":
                    _reconstruct_access(sub, inner_parts)
            if segments:
                segments[-1] += "[" + "".join(inner_parts) + "]"
    parts.append(".".join(segments))


def _reconstruct_call(call_elem, parts):
    """Reconstruct a block call from Access Scope=Call."""
    for child in call_elem:
        tag = strip_ns(child.tag)
        if tag in ("CallInfo", "Instruction"):
            # CallInfo: standard block calls
            # Instruction: library/system block calls (e.g., Program_Alarm)
            block_name = child.get("Name", "")
            if block_name:
                parts.append(f'"{block_name}"')
            # Instance DB / local instance
            for sub in child:
                sub_tag = strip_ns(sub.tag)
                if sub_tag == "Instance":
                    inst_parts = []
                    for inst_child in sub:
                        if strip_ns(inst_child.tag) == "Component":
                            inst_parts.append(inst_child.get("Name", ""))
                    if inst_parts:
                        inst_name = ".".join(inst_parts)
                        inst_scope = sub.get("Scope", "")
                        if inst_scope == "LocalVariable":
                            inst_name = "#" + inst_name
                        parts.append(f', {inst_name}')
                elif sub_tag == "Token":
                    parts.append(sub.get("Text", ""))
                elif sub_tag == "Parameter":
                    pname = sub.get("Name", "")
                    parts.append(pname)
                    has_children = False
                    for param_child in sub:
                        has_children = True
                        ptag = strip_ns(param_child.tag)
                        if ptag == "Access":
                            _reconstruct_access(param_child, parts)
                        elif ptag == "Token":
                            parts.append(param_child.get("Text", ""))
                        elif ptag == "Blank":
                            num = param_child.get("Num")
                            parts.append(" " * int(num) if num else " ")
                        elif ptag == "NewLine":
                            num = param_child.get("Num")
                            parts.append("\n" * int(num) if num else "\n")
                    if not has_children:
                        parts.append(" := ")
                elif sub_tag == "NamelessParameter":
                    # Nested function call arguments (no name prefix)
                    for param_child in sub:
                        ptag = strip_ns(param_child.tag)
                        if ptag == "Access":
                            _reconstruct_access(param_child, parts)
                        elif ptag == "Token":
                            parts.append(param_child.get("Text", ""))
                        elif ptag == "Blank":
                            num = param_child.get("Num")
                            parts.append(" " * int(num) if num else " ")
                        elif ptag == "NewLine":
                            num = param_child.get("Num")
                            parts.append("\n" * int(num) if num else "\n")
                elif sub_tag == "NewLine":
                    num = sub.get("Num")
                    parts.append("\n" * int(num) if num else "\n")
                elif sub_tag == "Blank":
                    num = sub.get("Num")
                    parts.append(" " * int(num) if num else " ")
        elif tag == "Token":
            parts.append(child.get("Text", ""))


# ---------------------------------------------------------------------------
# STL code reconstruction (StatementList v4)
# ---------------------------------------------------------------------------
def reconstruct_stl(stl_elem):
    """Reconstruct readable STL code from tokenized StatementList XML."""
    parts = []
    for stmt in stl_elem:
        tag = strip_ns(stmt.tag)
        if tag != "StlStatement":
            continue

        # STL token
        token_elem = find_ns(stmt, "StlToken")
        if token_elem is not None:
            token_text = token_elem.get("Text", "")
            if token_text == "EMPTY_LINE":
                parts.append("\n")
                continue
            if token_text == "COMMENT":
                # Line comment: text is in LineComment > Text grandchild
                for child in stmt:
                    child_tag = strip_ns(child.tag)
                    if child_tag == "LineComment":
                        for txt in child:
                            if strip_ns(txt.tag) == "Text" and txt.text:
                                parts.append(f"      //{txt.text}\n")
                        break
                continue
            # Map XML token names to real STL mnemonics
            token_map = {
                "Assign": "=",
                "A_BRACK": "A(",
                "AN_BRACK": "AN(",
                "O_BRACK": "O(",
                "ON_BRACK": "ON(",
                "BRACKET": ")",
                "NOP_0": "NOP 0",
                "ADD_R": "+R",
                "SUB_R": "-R",
                "MUL_R": "*R",
                "DIV_R": "/R",
                "Rise": "FP",
                "Fall": "FN",
                "OnDelay": "SD",
                "OffDelay": "SF",
            }
            token_text = token_map.get(token_text, token_text)
            # Closing bracket has no operand after it
            if token_text == ")":
                parts.append(f"      )\n")
                continue
            parts.append(f"      {token_text}     ")

        # Operand (Access elements)
        for child in stmt:
            child_tag = strip_ns(child.tag)
            if child_tag == "StlToken":
                continue
            if child_tag == "Access":
                scope = child.get("Scope", "")
                access_comment = ""
                if scope == "GlobalVariable":
                    sym_parts = []
                    for sym in child:
                        if strip_ns(sym.tag) == "Symbol":
                            _collect_stl_symbol(sym, sym_parts)
                        elif strip_ns(sym.tag) == "LineComment":
                            for txt in sym:
                                if strip_ns(txt.tag) == "Text" and txt.text:
                                    access_comment = txt.text.strip()
                    parts.append("".join(sym_parts))
                elif scope == "LocalVariable":
                    sym_parts = ["#"]
                    for sym in child:
                        if strip_ns(sym.tag) == "Symbol":
                            _collect_stl_symbol(sym, sym_parts)
                        elif strip_ns(sym.tag) == "LineComment":
                            for txt in sym:
                                if strip_ns(txt.tag) == "Text" and txt.text:
                                    access_comment = txt.text.strip()
                    parts.append("".join(sym_parts))
                elif scope == "LiteralConstant":
                    for const in child:
                        if strip_ns(const.tag) == "Constant":
                            val = find_ns(const, "ConstantValue")
                            if val is not None and val.text:
                                parts.append(val.text)
                        elif strip_ns(const.tag) == "LineComment":
                            for txt in const:
                                if strip_ns(txt.tag) == "Text" and txt.text:
                                    access_comment = txt.text.strip()
                elif scope == "TypedConstant":
                    for const in child:
                        if strip_ns(const.tag) == "Constant":
                            val = find_ns(const, "ConstantValue")
                            if val is not None and val.text:
                                parts.append(val.text)
                        elif strip_ns(const.tag) == "LineComment":
                            for txt in const:
                                if strip_ns(txt.tag) == "Text" and txt.text:
                                    access_comment = txt.text.strip()
                elif scope == "Call":
                    # CALL instruction - find CallInfo with block name
                    for sub in child:
                        sub_tag = strip_ns(sub.tag)
                        if sub_tag == "CallInfo":
                            call_name = sub.get("Name", "")
                            if call_name:
                                parts.append(f'"{call_name}"')
                            # Instance DB (for FB calls)
                            for inst in sub:
                                if strip_ns(inst.tag) == "Instance":
                                    inst_scope = inst.get("Scope", "")
                                    if inst_scope == "GlobalVariable":
                                        # Instance has Component children directly
                                        inst_name = ""
                                        for ic in inst:
                                            if strip_ns(ic.tag) == "Component":
                                                inst_name = ic.get("Name", "")
                                            elif strip_ns(ic.tag) == "Symbol":
                                                isegs = []
                                                _collect_stl_symbol(ic, isegs)
                                                inst_name = "".join(isegs)
                                        if inst_name:
                                            parts.append(f', "{inst_name}"')
                            # Parameters
                            for param in sub:
                                ptag = strip_ns(param.tag)
                                if ptag == "Parameter":
                                    pname = param.get("Name", "")
                                    parts.append(f"\n        {pname} := ")
                                    for pc in param:
                                        pc_tag = strip_ns(pc.tag)
                                        if pc_tag == "Access":
                                            pc_scope = pc.get("Scope", "")
                                            if pc_scope == "GlobalVariable":
                                                sp = []
                                                for sym in pc:
                                                    if strip_ns(sym.tag) == "Symbol":
                                                        _collect_stl_symbol(sym, sp)
                                                parts.append("".join(sp))
                                            elif pc_scope == "LocalVariable":
                                                parts.append("#")
                                                for sym in pc:
                                                    if strip_ns(sym.tag) == "Symbol":
                                                        _collect_stl_symbol(sym, parts)
                                            elif pc_scope in ("LiteralConstant", "TypedConstant"):
                                                for const in pc:
                                                    if strip_ns(const.tag) == "Constant":
                                                        val = find_ns(const, "ConstantValue")
                                                        if val is not None and val.text:
                                                            parts.append(val.text)
                        elif sub_tag == "Instruction":
                            instr_name = sub.get("Name", "")
                            if instr_name:
                                parts.append(instr_name)
                            # Instance (local variable like #S_1)
                            for inst in sub:
                                if strip_ns(inst.tag) == "Instance":
                                    inst_scope = inst.get("Scope", "")
                                    inst_name = ""
                                    for ic in inst:
                                        if strip_ns(ic.tag) == "Component":
                                            inst_name = ic.get("Name", "")
                                    if inst_name:
                                        if inst_scope == "LocalVariable":
                                            parts.append(f", #{inst_name}")
                                        else:
                                            parts.append(f', "{inst_name}"')
                            # Parameters
                            for param in sub:
                                ptag = strip_ns(param.tag)
                                if ptag == "Parameter":
                                    pname = param.get("Name", "")
                                    parts.append(f"\n        {pname} := ")
                                    for pc in param:
                                        pc_tag = strip_ns(pc.tag)
                                        if pc_tag == "Access":
                                            pc_scope = pc.get("Scope", "")
                                            if pc_scope == "GlobalVariable":
                                                sp = []
                                                for sym in pc:
                                                    if strip_ns(sym.tag) == "Symbol":
                                                        _collect_stl_symbol(sym, sp)
                                                parts.append("".join(sp))
                                            elif pc_scope == "LocalVariable":
                                                sp = ["#"]
                                                for sym in pc:
                                                    if strip_ns(sym.tag) == "Symbol":
                                                        _collect_stl_symbol(sym, sp)
                                                parts.append("".join(sp))
                                            elif pc_scope in ("LiteralConstant", "TypedConstant"):
                                                for const in pc:
                                                    if strip_ns(const.tag) == "Constant":
                                                        val = find_ns(const, "ConstantValue")
                                                        if val is not None and val.text:
                                                            parts.append(val.text)
                if access_comment:
                    parts.append(f"  //{access_comment}")
            if child_tag == "Comment":
                for txt in child:
                    if strip_ns(txt.tag) == "Text" and txt.text:
                        parts.append(f"  //{txt.text}")
            if child_tag == "LineComment":
                for txt in child:
                    if strip_ns(txt.tag) == "Text" and txt.text:
                        parts.append(f"  //{txt.text.strip()}")

        parts.append("\n")

    return "".join(parts).rstrip()


def _collect_stl_symbol(symbol_elem, parts):
    """Collect symbol path for STL operand."""
    segments = []
    for child in symbol_elem:
        tag = strip_ns(child.tag)
        if tag == "Component":
            name = child.get("Name", "")
            is_array = child.get("AccessModifier") == "Array"
            # First component (DB/FC/FB name) is always quoted in STL
            # Subsequent components check HasQuotes attribute
            if not segments:
                seg = f'"{name}"'
            else:
                has_quotes = False
                for attr in child:
                    if strip_ns(attr.tag) == "BooleanAttribute" and attr.get("Name") == "HasQuotes":
                        has_quotes = attr.text == "true"
                seg = f'"{name}"' if has_quotes else name
            # Handle array index on Component
            if is_array:
                idx = _extract_array_index(child)
                seg += f"[{idx}]"
            segments.append(seg)
        elif tag == "Access" and child.get("AccessModifier") == "Array":
            idx = _extract_access_value(child)
            if segments:
                segments[-1] += f"[{idx}]"
    parts.append(".".join(segments))


def _extract_array_index(elem):
    """Extract array index from child Access elements (LiteralConstant/TypedConstant/Symbol)."""
    for sub in elem:
        if strip_ns(sub.tag) == "Access":
            return _extract_access_value(sub)
    return ""


def _extract_access_value(access_elem):
    """Extract value from an Access element (constant or symbol)."""
    scope = access_elem.get("Scope", "")
    if scope in ("LiteralConstant", "TypedConstant"):
        for const in access_elem:
            if strip_ns(const.tag) == "Constant":
                val = find_ns(const, "ConstantValue")
                if val is not None and val.text:
                    return val.text
    elif scope == "GlobalVariable":
        inner = []
        for sym in access_elem:
            if strip_ns(sym.tag) == "Symbol":
                _collect_stl_symbol(sym, inner)
        return "".join(inner)
    elif scope == "LocalVariable":
        inner = ["#"]
        for sym in access_elem:
            if strip_ns(sym.tag) == "Symbol":
                _collect_stl_symbol(sym, inner)
        return "".join(inner)
    return ""


# ---------------------------------------------------------------------------
# Code extraction from CompileUnit
# ---------------------------------------------------------------------------
def _extract_network_title(cu_elem):
    """Extract network title from CompileUnit's ObjectList."""
    for child in cu_elem:
        if strip_ns(child.tag) == "ObjectList":
            for obj in child:
                if strip_ns(obj.tag) == "MultilingualText" and obj.get("CompositionName") == "Title":
                    for item in obj:
                        if strip_ns(item.tag) == "ObjectList":
                            for mti in item:
                                if strip_ns(mti.tag) == "MultilingualTextItem":
                                    for al in mti:
                                        if strip_ns(al.tag) == "AttributeList":
                                            text = None
                                            for attr in al:
                                                if strip_ns(attr.tag) == "Text" and attr.text:
                                                    text = attr.text
                                            if text:
                                                return text
    return ""


def _extract_network_comment(cu_elem):
    """Extract network comment from CompileUnit's ObjectList."""
    for child in cu_elem:
        if strip_ns(child.tag) == "ObjectList":
            for obj in child:
                if strip_ns(obj.tag) == "MultilingualText" and obj.get("CompositionName") == "Comment":
                    for item in obj:
                        if strip_ns(item.tag) == "ObjectList":
                            for mti in item:
                                if strip_ns(mti.tag) == "MultilingualTextItem":
                                    for al in mti:
                                        if strip_ns(al.tag) == "AttributeList":
                                            text = None
                                            for attr in al:
                                                if strip_ns(attr.tag) == "Text" and attr.text:
                                                    text = attr.text
                                            if text:
                                                return text
    return ""


def extract_code_from_block(block_elem):
    """Extract all code networks from block's CompileUnits."""
    networks = []

    for cu in block_elem.iter():
        cu_tag = strip_ns(cu.tag)
        if cu_tag not in ("CompileUnit", "SW.Blocks.CompileUnit"):
            continue

        # Extract network metadata
        title = _extract_network_title(cu)
        net_comment = _extract_network_comment(cu)

        # Find NetworkSource and ProgrammingLanguage
        ns_elem = None
        net_lang = ""
        for child in cu:
            if strip_ns(child.tag) == "AttributeList":
                for attr in child:
                    if strip_ns(attr.tag) == "NetworkSource":
                        ns_elem = attr
                    elif strip_ns(attr.tag) == "ProgrammingLanguage":
                        net_lang = (attr.text or "").strip()

        if ns_elem is None:
            continue

        # Check for StructuredText or StatementList
        for lang_elem in ns_elem:
            lang_tag = strip_ns(lang_elem.tag)

            if lang_tag == "StructuredText":
                code = reconstruct_scl(lang_elem)
                if code:
                    networks.append({"language": "SCL", "code": code, "title": title,
                                     "comment": net_comment, "net_lang": net_lang})

            elif lang_tag == "StatementList":
                code = reconstruct_stl(lang_elem)
                if code:
                    networks.append({"language": "STL", "code": code, "title": title,
                                     "comment": net_comment, "net_lang": net_lang})

    return networks


# ---------------------------------------------------------------------------
# Tag and call reference extraction from code
# ---------------------------------------------------------------------------
def extract_global_vars_from_xml(block_elem):
    """Extract all GlobalVariable references directly from XML for reliable tag xref."""
    refs = set()
    for access in block_elem.iter():
        if strip_ns(access.tag) != "Access":
            continue
        if access.get("Scope") == "GlobalVariable":
            path_parts = []
            for child in access:
                if strip_ns(child.tag) == "Symbol":
                    _collect_var_path(child, path_parts)
            if path_parts:
                refs.add(".".join(path_parts))
        elif access.get("Scope") == "Call":
            # Extract called block name
            for child in access:
                ctag = strip_ns(child.tag)
                if ctag == "CallInfo":
                    # STL format: <CallInfo Name="FC_LIJN" BlockType="FC" />
                    call_name = child.get("Name", "")
                    if call_name:
                        refs.add("CALL:" + call_name)
                    # SCL format: <Instance Scope="GlobalVariable"><Symbol>...
                    for sub in child:
                        if strip_ns(sub.tag) == "Instance":
                            for inst in sub:
                                if strip_ns(inst.tag) == "Symbol":
                                    name_parts = []
                                    _collect_var_path(inst, name_parts)
                                    if name_parts:
                                        refs.add("CALL:" + ".".join(name_parts))
    return refs


def _collect_var_path(symbol_elem, parts):
    """Collect variable path from Symbol element."""
    segments = []
    for child in symbol_elem:
        tag = strip_ns(child.tag)
        if tag == "Component":
            segments.append(child.get("Name", ""))
        elif tag == "Access" and child.get("AccessModifier") == "Array":
            # Skip array index, just note it's array access
            pass
    if segments:
        parts.append(".".join(segments))


def classify_references(global_refs):
    """Split global refs into tag references and block calls."""
    tag_refs = []
    calls = []

    for ref in global_refs:
        if ref.startswith("CALL:"):
            calls.append(ref[5:])
        else:
            tag_refs.append(ref)

    return sorted(set(tag_refs)), sorted(set(calls))


# ---------------------------------------------------------------------------
# PLC tag table parsing
# ---------------------------------------------------------------------------
def parse_tag_tables(tags_dir):
    """Parse all PLC tag table XML files in directory."""
    all_tags = {}

    if not os.path.isdir(tags_dir):
        return all_tags

    for f in sorted(os.listdir(tags_dir)):
        if not f.lower().endswith(".xml"):
            continue

        filepath = os.path.join(tags_dir, f)
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except ET.ParseError:
            continue

        # Find table name
        table_name = ""
        for child in root:
            ctag = strip_ns(child.tag)
            if ctag == "SW.Tags.PlcTagTable":
                for attr_list in child:
                    if strip_ns(attr_list.tag) == "AttributeList":
                        name_elem = find_ns(attr_list, "Name")
                        if name_elem is not None and name_elem.text:
                            table_name = name_elem.text.strip()
                break

        if not table_name:
            table_name = os.path.splitext(f)[0]

        # Parse tags — elements are named SW.Tags.PlcTag (not namespaced)
        for tag_elem in root.iter():
            tag_local = strip_ns(tag_elem.tag)
            if tag_local != "SW.Tags.PlcTag":
                continue

            attrs = None
            for child in tag_elem:
                if strip_ns(child.tag) == "AttributeList":
                    attrs = child
                    break

            if attrs is None:
                continue

            name = ""
            data_type = ""
            address = ""
            comment = ""

            for field in attrs:
                field_tag = strip_ns(field.tag)
                if field_tag == "Name":
                    name = (field.text or "").strip()
                elif field_tag == "DataTypeName":
                    data_type = (field.text or "").strip()
                elif field_tag == "LogicalAddress":
                    address = (field.text or "").strip()

            # Comment
            for child in tag_elem:
                if strip_ns(child.tag) == "ObjectList":
                    for obj in child:
                        if strip_ns(obj.tag) == "MultilingualText":
                            is_comment = False
                            for sub in obj:
                                if strip_ns(sub.tag) == "AttributeList":
                                    pass
                                elif strip_ns(sub.tag) == "ObjectList":
                                    for item in sub:
                                        if strip_ns(item.tag) == "MultilingualTextItem":
                                            culture = ""
                                            text = ""
                                            for ia in item:
                                                ia_tag = strip_ns(ia.tag)
                                                if ia_tag == "AttributeList":
                                                    for ia_field in ia:
                                                        if strip_ns(ia_field.tag) == "Culture":
                                                            culture = (ia_field.text or "").strip()
                                                elif ia_tag == "Text":
                                                    text = (ia.text or "").strip()
                                            if culture == "en-US" and text:
                                                comment = text
                                                break
                                    break

            if name:
                all_tags[name] = {
                    "name": name,
                    "table": table_name,
                    "data_type": data_type,
                    "address": address,
                    "comment": comment,
                }

    return all_tags


# ---------------------------------------------------------------------------
# Single block file parser
# ---------------------------------------------------------------------------
def parse_block_file(filepath, rel_path):
    """Parse a single exported block XML file."""
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}", "file": rel_path}

    root = tree.getroot()

    # Detect block type
    block_type, block_elem = detect_block_type(root)
    if block_type is None:
        return None  # Not a block file

    # Metadata from AttributeList
    block_name = ""
    block_number = ""
    prog_language = ""
    memory_layout = ""
    header_author = ""
    header_family = ""
    header_name = ""
    header_version = ""
    db_opc_ua = ""
    db_webserver = ""
    instance_of_name = ""
    instance_of_type = ""
    comment = ""

    for child in block_elem:
        if strip_ns(child.tag) == "AttributeList":
            for attr in child:
                attr_tag = strip_ns(attr.tag)
                if attr_tag == "Name":
                    block_name = (attr.text or "").strip()
                elif attr_tag == "Number":
                    block_number = (attr.text or "").strip()
                elif attr_tag == "ProgrammingLanguage":
                    prog_language = (attr.text or "").strip()
                elif attr_tag == "MemoryLayout":
                    memory_layout = (attr.text or "").strip()
                elif attr_tag == "HeaderAuthor":
                    header_author = (attr.text or "").strip()
                elif attr_tag == "HeaderFamily":
                    header_family = (attr.text or "").strip()
                elif attr_tag == "HeaderName":
                    header_name = (attr.text or "").strip()
                elif attr_tag == "HeaderVersion":
                    header_version = (attr.text or "").strip()
                elif attr_tag == "DBAccessibleFromOPCUA":
                    db_opc_ua = (attr.text or "").strip()
                elif attr_tag == "DBAccessibleFromWebserver":
                    db_webserver = (attr.text or "").strip()
                elif attr_tag == "InstanceOfName":
                    instance_of_name = (attr.text or "").strip()
                elif attr_tag == "InstanceOfType":
                    instance_of_type = (attr.text or "").strip()

    # Comment and Title from MultilingualText
    block_title = ""
    for child in block_elem:
        if strip_ns(child.tag) == "ObjectList":
            for obj in child:
                if strip_ns(obj.tag) == "MultilingualText":
                    comp_name = obj.get("CompositionName", "")
                    for sub in obj:
                        if strip_ns(sub.tag) == "ObjectList":
                            for item in sub:
                                if strip_ns(item.tag) == "MultilingualTextItem":
                                    culture = ""
                                    text = ""
                                    for field in item:
                                        ftag = strip_ns(field.tag)
                                        if ftag == "AttributeList":
                                            for af in field:
                                                if strip_ns(af.tag) == "Culture":
                                                    culture = (af.text or "").strip()
                                        elif ftag == "Text":
                                            text = (field.text or "").strip()
                                    if culture == "en-US" and text:
                                        if comp_name == "Title":
                                            block_title = text
                                        else:
                                            comment = text

    # Fallback: use filename as block name (for STRUCT/UDT types)
    if not block_name:
        block_name = os.path.splitext(os.path.basename(rel_path))[0]

    # Fallback language for types without code
    if not prog_language and block_type in ("STRUCT", "UDT"):
        prog_language = block_type

    # Folder path (parent directory of the file)
    folder = os.path.dirname(rel_path).replace("\\", "/")
    if folder == ".":
        folder = ""

    # Interface
    interface = parse_interface(block_elem)

    # Code
    networks = extract_code_from_block(block_elem)
    code_parts = []
    for i, n in enumerate(networks, 1):
        title = n.get("title", "")
        net_comment = n.get("comment", "")
        header = f"Network {i}"
        if title:
            header += f": {title}"
        code_parts.append(f"// {header}")
        if net_comment:
            code_parts.append(f"// Comment: {net_comment}")
        code_parts.append(n["code"])
    full_code = "\n".join(code_parts)

    # Global variable references from XML (most reliable)
    global_refs = extract_global_vars_from_xml(block_elem)
    tag_refs, calls = classify_references(global_refs)

    return {
        "block_name": block_name,
        "block_number": int(block_number) if block_number.isdigit() else block_number,
        "block_type": block_type,
        "programming_language": prog_language,
        "memory_layout": memory_layout,
        "header_author": header_author,
        "header_family": header_family,
        "header_name": header_name,
        "header_version": header_version,
        "db_opc_ua": db_opc_ua,
        "db_webserver": db_webserver,
        "instance_of_name": instance_of_name,
        "instance_of_type": instance_of_type,
        "comment": comment,
        "block_title": block_title,
        "folder": folder,
        "source_file": rel_path.replace("\\", "/"),
        "interface": interface,
        "interface_count": count_interface_vars(interface),
        "networks": networks,
        "code": full_code,
        "tag_references": tag_refs,
        "calls": calls,
    }


# ---------------------------------------------------------------------------
# Analysis: tag xref and call tree
# ---------------------------------------------------------------------------
def build_tag_xref(blocks):
    """Build tag cross-reference: tag_name -> list of blocks using it."""
    xref = defaultdict(list)
    for block in blocks:
        for tag in block.get("tag_references", []):
            xref[tag].append({
                "block": block["block_name"],
                "block_type": block["block_type"],
            })
    return dict(sorted(xref.items()))


def build_call_tree(blocks):
    """Build call tree: forward (block -> calls) and reverse (block -> called_by)."""
    forward = {}
    reverse = defaultdict(list)

    for block in blocks:
        name = block["block_name"]
        calls = block.get("calls", [])
        forward[name] = calls
        for called in calls:
            reverse[called].append(name)

    return forward, {k: sorted(set(v)) for k, v in reverse.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="PLC Program Block Extractor (Offline) - Parse exported Openness XML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("blocks_path",
                        help="Path to DATA_Program blocks directory")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON path (default: <blocks_path>/.plc_cache.json)")
    parser.add_argument("--tags", default=None,
                        help="PLC tags directory (default: <blocks_path>/PLC tags)")
    parser.add_argument("--list-blocks", action="store_true",
                        help="List found blocks and exit")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed progress")
    parser.add_argument("--plc-name", default=None,
                        help="PLC device name (stored in cache for report generation)")
    args = parser.parse_args()

    blocks_path = args.blocks_path.replace("\\", "/")
    if not os.path.exists(blocks_path):
        print(f"ERROR: Path does not exist: {blocks_path}")
        sys.exit(1)

    output_path = args.output or os.path.join(blocks_path, ".plc_cache.json")
    tags_dir = args.tags or os.path.join(blocks_path, "PLC tags")

    # --- Discover block files ---
    print(f"{'=' * 70}")
    print(f" PLC Program Block Extractor (Offline)")
    print(f"{'=' * 70}")
    print(f" Source: {blocks_path}")

    block_files = find_block_files(blocks_path)
    print(f" Found {len(block_files)} XML files")

    if args.list_blocks:
        for full_path, rel_path in block_files:
            result = parse_block_file(full_path, rel_path)
            if result and "error" not in result:
                lang = result.get("programming_language", "?")
                btype = result.get("block_type", "?")
                bnum = result.get("block_number", "?")
                name = result.get("block_name", "?")
                iface = result.get("interface_count", 0)
                calls = len(result.get("calls", []))
                tags = len(result.get("tag_references", []))
                print(f"  {btype:>3s} {str(bnum):>5s} {lang:>3s}  {name:<40s}  iface={iface:>3d}  calls={calls:>2d}  tags={tags:>2d}  {rel_path}")
        return

    # --- Parse tag tables ---
    print(f"\n--- Loading PLC tag tables ---")
    plc_tags = parse_tag_tables(tags_dir)
    print(f" Loaded {len(plc_tags)} PLC tags")

    # Also parse tag tables found in the blocks directory (AI, DI, etc.)
    inline_tags = parse_tag_tables(blocks_path)
    merged = 0
    for name, detail in inline_tags.items():
        if name not in plc_tags:
            plc_tags[name] = detail
            merged += 1
    if merged:
        print(f" Added {merged} additional tags from block directory")

    # --- Parse blocks ---
    print(f"\n--- Parsing blocks ---")
    blocks = []
    errors = []

    for i, (full_path, rel_path) in enumerate(block_files):
        result = parse_block_file(full_path, rel_path)
        if result is None:
            continue  # Not a block file
        if "error" in result:
            errors.append(result)
            if args.verbose:
                print(f"  [{i + 1:3d}] ERROR: {rel_path} - {result['error']}")
            continue

        blocks.append(result)
        if args.verbose:
            b = result
            print(f"  [{i + 1:3d}/{len(block_files)}] {b['block_type']:>3s} {str(b['block_number']):>5s} "
                  f"{b['programming_language']:>3s}  {b['block_name']:<40s}  "
                  f"iface={b['interface_count']:>3d}  calls={len(b['calls']):>2d}  "
                  f"tags={len(b['tag_references']):>2d}")

    print(f" Parsed {len(blocks)} blocks ({len(errors)} errors)")

    # --- Build indexes ---
    tag_xref = build_tag_xref(blocks)
    call_forward, call_reverse = build_call_tree(blocks)

    # Resolve tag references against tag tables
    resolved_tags = {}
    for tag_ref, usage in tag_xref.items():
        # Try exact match first, then base name (before first dot)
        base_name = tag_ref.split(".")[0] if "." in tag_ref else tag_ref
        tag_detail = plc_tags.get(tag_ref) or plc_tags.get(base_name)
        resolved_tags[tag_ref] = {
            "plc_tag_address": tag_detail["address"] if tag_detail else "(not in tag table)",
            "data_type": tag_detail["data_type"] if tag_detail else "?",
            "used_in": [u["block"] for u in usage],
        }

    # --- Summary ---
    type_counts = defaultdict(int)
    lang_counts = defaultdict(int)
    total_iface = 0
    total_calls = 0
    total_tag_refs = 0

    for b in blocks:
        type_counts[b["block_type"]] += 1
        lang_counts[b["programming_language"]] += 1
        total_iface += b["interface_count"]
        total_calls += len(b["calls"])
        total_tag_refs += len(b["tag_references"])

    summary = {
        "total_blocks": len(blocks),
        "fb_count": type_counts.get("FB", 0),
        "fc_count": type_counts.get("FC", 0),
        "ob_count": type_counts.get("OB", 0),
        "db_count": type_counts.get("DB", 0),
        "idb_count": type_counts.get("IDB", 0),
        "scl_count": lang_counts.get("SCL", 0),
        "stl_count": lang_counts.get("STL", 0),
        "db_lang_count": lang_counts.get("DB", 0),
        "total_interfaces": total_iface,
        "total_calls": total_calls,
        "total_tag_refs": total_tag_refs,
        "unique_tag_refs": len(tag_xref),
        "unique_calls": len(call_forward),
        "plc_tags_loaded": len(plc_tags),
    }

    # --- Output ---
    output = {
        "extraction_info": {
            "tool": "extract_plc_full.py",
            "source_path": blocks_path,
            "timestamp": datetime.now().isoformat(),
            "plc_name": args.plc_name or "",
            "data_sources": {
                "block_xml_files": len(block_files),
                "blocks_parsed": len(blocks),
                "errors": len(errors),
                "plc_tags_loaded": len(plc_tags),
            },
        },
        "summary": summary,
        "call_tree": call_forward,
        "called_by": call_reverse,
        "tag_xref": resolved_tags,
        "plc_tags": {k: v for k, v in sorted(plc_tags.items())},
        "blocks": blocks,
    }

    if errors:
        output["errors"] = errors

    # --- Write ---
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # --- Console report ---
    print(f"\n{'=' * 70}")
    print(f" EXTRACTION COMPLETE")
    print(f"{'=' * 70}")
    for k, v in summary.items():
        print(f"  {k:<25s} {v}")
    print(f"\n  Output: {output_path}")
    print(f"{'=' * 70}")

    # Per-block table
    print(f"\n{'Block':<36s} {'Type':>4s} {'#':>5s} {'Lang':>4s} {'Iface':>5s} {'Calls':>5s} {'Tags':>5s} {'Folder'}")
    print("-" * 110)
    for b in blocks:
        folder = b["folder"]
        if len(folder) > 40:
            folder = "..." + folder[-37:]
        print(f"  {b['block_name']:<34s} {b['block_type']:>4s} {str(b['block_number']):>5s} "
              f"{b['programming_language']:>4s} {b['interface_count']:>5d} "
              f"{len(b['calls']):>5d} {len(b['tag_references']):>5d}  {folder}")

    return output


if __name__ == "__main__":
    main()
