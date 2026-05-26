# TIA Toolkit

A GUI toolkit for extracting data from Siemens TIA Portal projects. Supports both PLC and HMI data extraction with dual online/offline pipelines, markdown report generation, and a VS Code extension.

## Features

- **PLC Pipeline** — Extract program blocks (FB, FC, OB, DB) with interfaces, SCL/STL code, tag cross-references, and call structure
- **HMI Pipeline** — Extract screen elements (buttons, IO fields, circles) with PLC tag bindings, JS events, and navigation from Unified HMI projects
- **Dual Extraction** — C# online (TIA Portal API) + Python offline (parses exported files), merged into unified reports
- **Markdown Reports** — Full block documentation with per-network code, interface fields, tag tables, and folder structure
- **CLAUDE.md Generator** — Project-specific documentation for AI-assisted development
- **Export Bundle** — Copy all reports + JSON data for use with Claude Code or other tools
- **VS Code Extension** — Sidebar panel with the same pipeline logic, output syncs to workspace

## Quick Start

### Desktop GUI

```bat
pip install openpyxl customtkinter
```

Double-click **`TIA Toolkit.bat`** or run:

```bat
python "TIA Toolkit.py"
```

### VS Code Extension

1. Install the `.vsix` from `tia-toolkit-vscode/`:
   - Extensions panel → `...` → `Install from VSIX...`
   - Select `tia-toolkit-vscode-0.2.0.vsix`
2. Open Settings and set **`tiaToolkit.toolkitPath`** to the toolkit root folder
3. Click the TIA Toolkit icon in the sidebar

### CLI Usage

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

## Project Structure

```
├── CLAUDE.md                    ← AI assistant instructions
├── TIA Toolkit.bat              ← Double-click launcher
├── TIA Toolkit.py               ← Python entry point
├── README.md
├── src/
│   ├── gui.py                   ← Desktop GUI (CustomTkinter)
│   ├── extract_plc_full.py      ← PLC offline parser (XML)
│   ├── plc_report.py            ← PLC markdown reports
│   ├── merge_plc_data.py        ← PLC online+offline merger
│   ├── extract_hmi_full.py      ← HMI offline parser (RDF)
│   ├── hmi_report.py            ← HMI markdown reports
│   ├── merge_hmi_data.py        ← HMI online+offline merger
│   ├── generate_claudemd.py     ← Project CLAUDE.md generator
│   ├── tia_export_blocks.cs     ← PLC C# source (V21)
│   ├── tia_export_blocks.exe    ← PLC block exporter (V21+)
│   ├── tia_export_blocks_v18.exe← PLC block exporter (V18-V19)
│   ├── tia_extract.cs           ← HMI C# source (V21)
│   ├── tia_extract.exe          ← HMI online extractor (V21+)
│   ├── tia_extract_v18.exe      ← HMI online extractor (V18-V19)
│   └── tia_extract_plc.cs       ← Alt PLC C# source
├── tia-toolkit-vscode/          ← VS Code extension
│   ├── package.json
│   ├── tsconfig.json
│   ├── resources/icon.svg
│   ├── src/
│   │   ├── extension.ts
│   │   ├── toolkitPanel.ts
│   │   ├── commandRunner.ts
│   │   ├── config.ts
│   │   ├── parseOutput.ts
│   │   ├── outputSync.ts
│   │   └── webviewContent.ts
│   └── webview/
│       ├── panel.html
│       ├── panel.css
│       └── panel.js
└── Doc_OUTPUT/                  ← Generated output (gitignored)
    ├── Program_Blocks/          ← PLC block .md reports
    ├── hmi_screens/             ← HMI screen .md reports
    └── CLAUDE.md                ← Generated project documentation
```

## TIA Portal Version Support

| | V18–V19 | V21+ |
|---|---------|------|
| PLC Exporter | `tia_export_blocks_v18.exe` | `tia_export_blocks.exe` |
| HMI Extractor | `tia_extract_v18.exe` | `tia_extract.exe` |
| DLL Structure | Single `Siemens.Engineering.dll` | Split: `Base.dll` + `Step7.dll` + `WinCCUnified.dll` |

## Data Pipeline

```
PLC Pipeline:
  TIA Portal → tia_export_blocks.exe → XML files
                                        ↓
            extract_plc_full.py → .plc_cache.json → plc_report.py → .md reports

HMI Pipeline:
  TIA Portal → tia_extract.exe → .hmi_online_data.json ─┐
  extract_hmi_full.py → .hmi_offline_data.json ──────────┴─→ merge → hmi_report.py → .md reports
```

## VS Code Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `tiaToolkit.toolkitPath` | `""` | Absolute path to toolkit root |
| `tiaToolkit.pythonPath` | `"py"` | Python executable |
| `tiaToolkit.autoSync` | `true` | Auto-copy Doc_OUTPUT to workspace |

## Building the VS Code Extension

```bat
cd tia-toolkit-vscode
npm install
npm run compile
npx @vscode/vsce package --allow-missing-repository
```

## Compiling C# Extractors

### V18–V19
```bat
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll" ^
  /out:tia_export_blocks_v18.exe tia_export_blocks.cs
```

### V21+
```bat
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" ^
  /reference:"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Step7.dll" ^
  /out:tia_export_blocks.exe tia_export_blocks.cs
```

## Requirements

- Python 3.8+ with `openpyxl` and `customtkinter`
- Siemens TIA Portal (V18+ for online extraction)
- .NET Framework 4.0+ (for C# compilation)
- VS Code 1.85+ or compatible IDE (for extension)

## License

MIT
