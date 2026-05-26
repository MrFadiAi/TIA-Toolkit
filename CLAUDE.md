# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A GUI toolkit for extracting data from Siemens TIA Portal projects. Two extraction pipelines:

1. **HMI Pipeline** — extracts screen elements (buttons, IO fields, circles) with PLC tag bindings from Unified HMI projects
2. **PLC Pipeline** — extracts program blocks (FB, FC, OB, DB) with interfaces, code, tag cross-references, and call structure

Both use a dual-extraction approach: C# online (TIA Portal API) + Python offline (parses exported files), then merge and report.

## Quick Start

Double-click **`TIA Toolkit.bat`** to launch the GUI, or run `python src/gui.py`.

### Dependency

```bat
pip install openpyxl customtkinter
```

## Project Structure

```
Extract_PLC_Data_GUI/
├── CLAUDE.md                  ← This file
├── TIA Toolkit.bat            ← Double-click launcher (calls TIA Toolkit.py)
├── TIA Toolkit.py             ← Python launcher entry point
├── .gitignore
├── src/                       ← All source files
│   ├── gui.py                 ← Desktop GUI (CTk class: TiaToolkitApp)
│   ├── generate_claudemd.py   ← Project-specific CLAUDE.md generator
│   ├── extract_plc_full.py    ← PLC offline parser (XML → .plc_cache.json)
│   ├── plc_report.py          ← PLC markdown reports (→ Doc_OUTPUT/Program_Blocks/)
│   ├── merge_plc_data.py      ← PLC online+offline merger
│   ├── extract_hmi_full.py    ← HMI offline parser (RDF → .hmi_offline_data.json)
│   ├── hmi_report.py          ← HMI markdown reports (→ Doc_OUTPUT/hmi_screens/)
│   ├── merge_hmi_data.py      ← HMI online+offline merger
│   ├── tia_export_blocks.cs   ← PLC C# source (V21)
│   ├── tia_export_blocks.exe / .exe.config
│   ├── tia_export_blocks_v18.exe / .exe.config
│   ├── tia_extract.cs         ← HMI C# source (V21)
│   ├── tia_extract.exe / .exe.config
│   ├── tia_extract_v18.exe / .exe.config
│   └── tia_extract_plc.cs     ← Alt PLC C# source
└── Doc_OUTPUT/                ← Generated output (gitignored)
    ├── Program_Blocks/        ← PLC block .md reports (mirrors TIA folder structure)
    │   ├── PLC_Data_Types/    ← UDT/STRUCT reports
    │   └── PLC tags/          ← plc_tags.md
    ├── hmi_screens/           ← HMI screen .md reports + hmi_tags.md
    ├── .plc_cache.json        ← PLC extraction cache
    ├── .hmi_online_data.json  ← C# HMI extraction output
    ├── .hmi_offline_data.json ← Python HMI extraction output
    ├── .hmi_merged.json       ← Merged HMI data
    └── CLAUDE.md              ← Generated project-specific CLAUDE.md
```

All Python scripts use `SCRIPT_DIR` (points to `src/`) for exe/script references and `PROJECT_ROOT` (one level up) for `Doc_OUTPUT/`.

## Build & Run Commands

### Executables

| File | V18–V19 | V21+ |
|------|---------|------|
| PLC block exporter | `tia_export_blocks_v18.exe` | `tia_export_blocks.exe` |
| HMI online extractor | `tia_extract_v18.exe` | `tia_extract.exe` |

### Compile for V18–V19

```bat
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll" ^
  /out:tia_export_blocks_v18.exe tia_export_blocks.cs

C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll" ^
  /out:tia_extract_v18.exe tia_extract.cs
```

### Compile for V21+

```bat
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Step7.dll" ^
  /out:tia_export_blocks.exe tia_export_blocks.cs

C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.WinCCUnified.dll" ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Step7.dll" ^
  /out:tia_extract.exe tia_extract.cs
```

### CLI Usage (without GUI)

```bat
:: PLC Pipeline
tia_export_blocks.exe --list
tia_export_blocks.exe "Doc_OUTPUT/DATA_Program blocks" "DEVICE_NAME"
python src\extract_plc_full.py "Doc_OUTPUT/DATA_Program blocks" --verbose
python src\plc_report.py

:: HMI Pipeline
python src\extract_hmi_full.py "D:/path/to/TIA project" --list-hmis
python src\extract_hmi_full.py "D:/path/to/TIA project" --instance 17
tia_extract.exe Doc_OUTPUT\.hmi_online_data.json "HMI_DEVICE_NAME"
python src\merge_hmi_data.py
python src\hmi_report.py

:: Generate CLAUDE.md for extracted project
python src\generate_claudemd.py
```

## Architecture

### GUI Layout

```
TIA Toolkit (gui.py — CTk class: TiaToolkitApp)
├── Sidebar: navigation (PLC / HMI / Report) + TIA version selector (V18-V19 / V21+)
├── PLC Pipeline page
│   ├── Step 1: Discover Devices (via --list) — populates both PLC & HMI dropdowns
│   ├── Step 1b: Compile C# Exporter (after code changes)
│   ├── Step 2: Export PLC Blocks (requires TIA Portal running)
│   ├── Step 3: Parse Blocks / Generate Report / View Report
│   └── Console output + progress bar
├── HMI Pipeline page
│   ├── Step 1: List HMI Devices (uses PLC exporter --list to discover HMIs)
│   ├── Step 2: Compile HMI Extractor (after code changes)
│   ├── Step 3: Extract HMI Data (online extraction → auto-generates report)
│   ├── Step 4: Generate Report / View Report
│   └── Console output + progress bar
└── Report Viewer page
    ├── Dropdown: .md files from Doc_OUTPUT/ (hmi_screens/*.md, Program_Blocks/**/*.md, CLAUDE.md)
    ├── Refresh / Open in Editor / Generate CLAUDE.md / Export Bundle
    └── Markdown text viewer (Consolas font)
└── Status bar: shows running command or "Ready"

Export Bundle copies all .md reports + JSON data files into a clean folder for use with Claude Code.
Report .md files contain full XML data: per-network code with titles/comments/language, all interface fields (start_value, accessibility, version, informative), tag table names, source file paths, and a Program_Blocks/index.md summary.
```

### Data Pipeline

```
PLC Pipeline:
  TIA Portal ──► tia_export_blocks.cs ──► Doc_OUTPUT/DATA_Program blocks/ (XML)
                                                       │
                                                       └──► extract_plc_full.py ──► .plc_cache.json ──► plc_report.py ──► Doc_OUTPUT/Program_Blocks/**/*.md
                                                              + PLC tags/*.xml

  (optional) tia_extract_plc.cs ──► plc_elements.json ─┐
  extract_plc_full.py ──► .plc_cache.json ──────────────┴─► merge_plc_data.py ─► plc_merged.json

HMI Pipeline:
  TIA Portal ──► tia_extract.cs ──► Doc_OUTPUT/.hmi_online_data.json ─┐
  extract_hmi_full.py ──► Doc_OUTPUT/hmi_offline_data.json ───────────┴─► merge_hmi_data.py ─► .hmi_merged.json ─► hmi_report.py ──► Doc_OUTPUT/hmi_screens/*.md

Report Generation:
  .plc_cache.json + .hmi_*.json ──► generate_claudemd.py ──► Doc_OUTPUT/CLAUDE.md
```

### Data source strengths

| Data | C# (online) | Python (offline) |
|------|-------------|------------------|
| HMI: PLC tag bindings (Dynamizations) | Yes | No |
| HMI: JS event code / navigation | Basic | Full extraction |
| PLC: Exact offsets from compiled project | Yes (via tia_extract_plc.cs) | No |
| PLC: SCL/STL code reconstruction | Via Export() | From tokenized XML |
| PLC: Tag cross-reference | From compiled refs | From XML Access elements |
| PLC: Call structure | From compiled refs | From CallInfo elements |
| Works without TIA Portal | No | Yes |

## TIA Portal Version Differences

| | V18–V19 | V21+ |
|---|---------|------|
| DLL structure | Single `Siemens.Engineering.dll` | Split: `net48/Siemens.Engineering.Base.dll` + `Siemens.Engineering.Step7.dll` + `WinCCUnified.dll` (HMI) |
| DLL copy local | Allowed | **Not allowed** — use `.exe.config` with `codeBase` redirects |
| Export paths | Relative OK | **Absolute paths required** |
| File overwrite | Allowed | **Not allowed** — script deletes existing files first |
| Config file | Not needed | Required: `*.exe.config` with assembly bindings |
| HMI DLL name | N/A (single DLL) | `Siemens.Engineering.WinCCUnified.dll` (NOT `HmiUnified`) |

## PLC Project Structure (API)

A TIA Portal project can have **multiple PLCs and HMIs**. Each PLC is a device with `PlcSoftware`:

```
Project
  Device: PLF_01A_PLC_HOOGTE_SNIJDER
    PlcSoftware Name=PLUKROBOT
      BlockGroup (PlcBlockSystemGroup)
        Blocks: [...]          <- root-level blocks
        Groups: [...]          <- user-created folders (PlcBlockUserGroupComposition)
        SystemBlockGroups:     <- system groups (PlcSystemBlockGroupComposition)
          "System blocks"
            Blocks: [...]      <- library/system blocks
            Groups:            <- system sub-groups
              "Program resources"
              "Web server"
      TagTableGroup
        TagTables: [...]       <- PLC tag tables
```

Key API property names:
- `PlcSoftware.BlockGroup` -> root block container
- `BlockGroup.Groups` -> user folders (PlcBlockUserGroupComposition)
- `BlockGroup.SystemBlockGroups` -> system groups (PlcSystemBlockGroupComposition)
- `PlcSoftware.TagTableGroup` -> tag table container
- Use `GetProp(obj, "PropertyName")` via reflection for version independence

## Conventions

- All outputs go to `Doc_OUTPUT/`
- `SCRIPT_DIR` for relative path resolution
- `normalize_name()` for case-insensitive matching (uppercase, spaces to underscores)
- `load_json()` with UTF-8 BOM handling
- Manual JSON in C# via `StringBuilder` + `J()` helper (no Newtonsoft.Json)
- Console banners with `=` separators and per-item detail tables
- `argparse` for Python CLI with `--Verbose`, `--list-*`, `--output` options

## Data Formats

### .plc_cache.json structure

```json
{
  "extraction_info": { "plc_name": "...", "source_path": "...", "timestamp": "..." },
  "summary": { "total_blocks": N, "fb_count": N, "fc_count": N, "ob_count": N, "db_count": N, "scl_count": N, "stl_count": N, "plc_tags_loaded": N, ... },
  "call_tree": { "BLOCK_NAME": ["called_block1", ...] },
  "called_by": { "BLOCK_NAME": ["caller1", ...] },
  "tag_xref": { "TAG_NAME": { "plc_tag_address": "%Ix.y", "data_type": "Bool", "used_in": ["BLOCK1", ...] } },
  "plc_tags": { "TAG_NAME": { "name": "...", "table": "DI", "data_type": "Bool", "address": "%I0.5", "comment": "" } },
  "blocks": [{ "block_name": "...", "block_type": "FC", "block_number": 10, "programming_language": "STL", "folder": "/Control", "interface": {...}, "code": "...", "calls": [...], "tag_references": [...] }]
}
```

### .hmi_online_data.json structure

```json
{
  "extraction_info": { "project": "...", "device_filter": "...", "timestamp": "..." },
  "screens": [{ "screen_name": "...", "elements": [{ "name": "...", "type": "button", "tag_bindings": [...], "events": [...] }] }]
}
```

## XML Parsing Notes (PLC)

- Block type elements: `SW.Blocks.FB`, `SW.Blocks.FC`, `SW.Blocks.OB`, `SW.Blocks.GlobalDB`, `SW.Blocks.InstanceDB`
- Code compile units: `SW.Blocks.CompileUnit` (not just `CompileUnit`)
- SCL code in tokenized XML: `Token`, `Blank`, `Text`, `NewLine`, `Access` elements under `StructuredText`
- STL code: `StlStatement` with `StlToken` and `Access` elements under `StatementList`
- PLC calls in STL: `<CallInfo Name="BLOCK_NAME" BlockType="FC/FB">` inside `Access Scope="Call"`
- Interface namespace: `http://www.siemens.com/automation/Openness/SW/Interface/v5`
- Tag tables: `SW.Tags.PlcTagTable` -> `SW.Tags.PlcTag` with `Name`, `DataTypeName`, `LogicalAddress`
