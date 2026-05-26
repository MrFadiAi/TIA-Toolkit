#!/usr/bin/env python3
"""TIA Portal Extraction Toolkit — Desktop GUI"""

import customtkinter as ctk
import threading
import subprocess
import os
import re
import shutil
import glob
from tkinter import filedialog

# ── Constants ──────────────────────────────────────────────────────────────
WINDOW_W, WINDOW_H = 1100, 720
SIDEBAR_W = 200
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DOC_OUTPUT = os.path.join(PROJECT_ROOT, "Doc_OUTPUT")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Parsing helpers ────────────────────────────────────────────────────────

def parse_device_list(text):
    plc, hmi = [], []
    cur = None
    for line in text.splitlines():
        m = re.match(r"Device:\s+(.+)", line)
        if m:
            cur = m.group(1).strip()
        m = re.match(r"\s+->\s+\[(PLC|HMI)\]\s+(.+)", line)
        if m and cur:
            entry = {"device": cur, "name": m.group(2).strip()}
            (plc if m.group(1) == "PLC" else hmi).append(entry)
    return plc, hmi


def parse_hmi_instances(text):
    instances, cur = [], {}
    for line in text.splitlines():
        m = re.match(r"\s+Instance\s+I/(\d+):", line)
        if m:
            if cur:
                instances.append(cur)
            cur = {"id": int(m.group(1))}
        elif cur:
            kv = re.match(r"\s+(\w[\w\s]*?):\s+(.+)", line)
            if kv:
                cur[kv.group(1).strip()] = kv.group(2).strip()
    if cur:
        instances.append(cur)
    return instances


def scan_reports():
    """Scan for .md report files in all output directories."""
    files = glob.glob(os.path.join(DOC_OUTPUT, "hmi_screens", "*.md"))
    files += glob.glob(os.path.join(DOC_OUTPUT, "Program_Blocks", "**", "*.md"), recursive=True)
    claudemd = os.path.join(DOC_OUTPUT, "CLAUDE.md")
    if os.path.exists(claudemd):
        files.append(claudemd)
    return sorted(files)


# ── Main application ──────────────────────────────────────────────────────

class TiaToolkitApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TIA Portal Extraction Toolkit")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(900, 600)

        # state
        self.tia_version = ctk.StringVar(value="V21+")
        self.plc_devices = []
        self.hmi_devices = []
        self._running = False
        self._active_console = None
        self._active_progress = None

        self._build_sidebar()
        self._build_main_area()
        self._build_statusbar()
        self.show_page("plc")

    # ── exe helpers ────────────────────────────────────────────────────

    @property
    def export_exe(self):
        v = self.tia_version.get()
        name = "tia_export_blocks_v18.exe" if v == "V18-V19" else "tia_export_blocks.exe"
        return os.path.join(SCRIPT_DIR, name)

    @property
    def extract_exe(self):
        v = self.tia_version.get()
        name = "tia_extract_v18.exe" if v == "V18-V19" else "tia_extract.exe"
        return os.path.join(SCRIPT_DIR, name)

    @staticmethod
    def _device_from_label(label):
        """Extract device name from '[PLC] Name  (Device)' label."""
        m = re.search(r"\((.+)\)\s*$", label)
        return m.group(1).strip() if m else label

    # ── sidebar ────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=SIDEBAR_W, corner_radius=0)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sb.grid_propagate(False)

        ctk.CTkLabel(sb, text="TIA Toolkit", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 30))

        self.nav_btns = {}
        for key, label in [("plc", "PLC Pipeline"), ("hmi", "HMI Pipeline"), ("report", "Report Viewer"), ("analysis", "Analysis")]:
            btn = ctk.CTkButton(sb, text=label, anchor="w", height=40,
                                command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", padx=15, pady=4)
            self.nav_btns[key] = btn

        ctk.CTkLabel(sb, text="TIA Portal Version", font=ctk.CTkFont(size=13)).pack(pady=(30, 5))
        seg = ctk.CTkSegmentedButton(sb, values=["V18-V19", "V21+"],
                                     variable=self.tia_version, command=self._on_version_change)
        seg.pack(padx=15, fill="x")

    def _on_version_change(self, val):
        self.log(f"TIA version set to {val}")

    # ── main area ──────────────────────────────────────────────────────

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.pages = {}
        for key in ("plc", "hmi", "report", "analysis"):
            page = ctk.CTkFrame(main, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()
            self.pages[key] = page

        self._build_plc_page()
        self._build_hmi_page()
        self._build_report_page()
        self._build_analysis_page()

    def show_page(self, key):
        for k, page in self.pages.items():
            page.grid_remove()
        self.pages[key].grid()
        for k, btn in self.nav_btns.items():
            btn.configure(fg_color=("#3B8ED0" if k == key else "transparent"),
                          text_color=("white" if k == key else ("gray10", "#D4D4D4")))
        # track active console
        if key == "plc":
            self._active_console = self.plc_console
            self._active_progress = self.plc_progress
        elif key == "hmi":
            self._active_console = self.hmi_console
            self._active_progress = self.hmi_progress
        elif key == "analysis":
            self._active_console = self.analysis_console
            self._active_progress = self.analysis_progress
        if key == "report":
            self._refresh_reports()

    # ── status bar ─────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=30, corner_radius=0,
                           fg_color=("#E0E0E0", "#1E1E1E"))
        bar.grid(row=1, column=1, sticky="ew")
        self.status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(bar, textvariable=self.status_var, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=10)

    # ═══════════════════════════════════════════════════════════════════
    # PLC PAGE
    # ═══════════════════════════════════════════════════════════════════

    def _build_plc_page(self):
        p = self.pages["plc"]
        p.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(p, text="PLC Extraction Pipeline",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 15))

        # Step 1
        f1 = ctk.CTkFrame(p)
        f1.grid(row=1, column=0, sticky="ew", pady=5)
        f1.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f1, text="Step 1: Discover Devices", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f1, text="List Devices", width=140, command=self._list_devices).grid(row=1, column=0, padx=10, pady=6)
        self.plc_device_var = ctk.StringVar(value="-- select PLC --")
        self.plc_device_dd = ctk.CTkOptionMenu(f1, variable=self.plc_device_var, values=["-- select PLC --"], width=400)
        self.plc_device_dd.grid(row=1, column=1, padx=10, pady=6, sticky="ew")

        # Step 1b: Compile
        fc = ctk.CTkFrame(p)
        fc.grid(row=2, column=0, sticky="ew", pady=5)
        fc.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fc, text="Step 1b: Compile Exporter (after code changes)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(fc, text="Compile C# Exporter", width=180, command=self._compile_exporter).grid(row=1, column=0, padx=10, pady=6)
        self.compile_status = ctk.CTkLabel(fc, text="", font=ctk.CTkFont(size=12))
        self.compile_status.grid(row=1, column=1, sticky="w", padx=5, pady=6)

        # Step 2
        f2 = ctk.CTkFrame(p)
        f2.grid(row=3, column=0, sticky="ew", pady=5)
        f2.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f2, text="Step 2: Export PLC Blocks", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 4))
        self.plc_output_var = ctk.StringVar(value=os.path.join(DOC_OUTPUT, "DATA_Program blocks"))
        ctk.CTkEntry(f2, textvariable=self.plc_output_var).grid(row=1, column=0, columnspan=2, padx=10, pady=6, sticky="ew")
        ctk.CTkButton(f2, text="Browse", width=80, command=lambda: self._browse_folder(self.plc_output_var)).grid(row=1, column=2, padx=5, pady=6)
        ctk.CTkButton(f2, text="Export Blocks", width=140, command=self._export_blocks).grid(row=1, column=3, padx=10, pady=6)
        ctk.CTkLabel(f2, text="⚠ Requires TIA Portal running with project open", text_color="#F59E0B",
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))

        # Step 3
        f3 = ctk.CTkFrame(p)
        f3.grid(row=4, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f3, text="Step 3: Parse & Generate Report", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f3, text="Parse Blocks", width=140, command=self._parse_plc).grid(row=1, column=0, padx=10, pady=6)
        ctk.CTkButton(f3, text="Generate Report", width=140, command=self._gen_plc_report).grid(row=1, column=1, padx=5, pady=6)
        ctk.CTkButton(f3, text="View Report", width=120, command=lambda: self.show_page("report")).grid(row=1, column=2, padx=5, pady=6)

        # Console
        self._build_console(p, row=5, name="plc")

    def _list_devices(self):
        self.clear_console()
        self.log("Listing devices...")
        self.run_command([self.export_exe, "--list"], on_complete=self._on_devices_listed)

    def _on_devices_listed(self, rc, output):
        if rc != 0:
            self.log("Failed to list devices.")
            return
        self.plc_devices, self.hmi_devices = parse_device_list(output)
        plc_labels = [f"[PLC] {d['name']}  ({d['device']})" for d in self.plc_devices]
        self.plc_device_dd.configure(values=plc_labels or ["-- no PLC found --"])
        if plc_labels:
            self.plc_device_var.set(plc_labels[0])
        hmi_labels = [f"[HMI] {d['name']}  ({d['device']})" for d in self.hmi_devices]
        self.hmi_device_dd.configure(values=hmi_labels or ["-- no HMI found --"])
        if hmi_labels:
            self.hmi_device_var.set(hmi_labels[0])
        self.log(f"Found {len(self.plc_devices)} PLC(s), {len(self.hmi_devices)} HMI(s)")
        # Sync pipeline dropdowns
        p_plc = [d['name'] for d in self.plc_devices]
        p_hmi = [d['name'] for d in self.hmi_devices]
        self.pipeline_plc_dd.configure(values=p_plc or ["-- no PLC --"])
        self.pipeline_hmi_dd.configure(values=p_hmi or ["-- no HMI --"])
        if p_plc:
            self.pipeline_plc_var.set(p_plc[0])
        if p_hmi:
            self.pipeline_hmi_var.set(p_hmi[0])

    def _compile_exporter(self):
        v = self.tia_version.get()
        csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
        cs_file = os.path.join(SCRIPT_DIR, "tia_export_blocks.cs")

        if v == "V18-V19":
            dll = r"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll"
            out = os.path.join(SCRIPT_DIR, "tia_export_blocks_v18.exe")
            cmd = [csc, f"/reference:{dll}", f"/out:{out}", cs_file]
        else:
            base = r"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48"
            out = os.path.join(SCRIPT_DIR, "tia_export_blocks.exe")
            cmd = [csc,
                   f"/reference:{base}\\Siemens.Engineering.Base.dll",
                   f"/reference:{base}\\Siemens.Engineering.Step7.dll",
                   f"/out:{out}", cs_file]

        self.clear_console()
        self.log(f"Compiling {os.path.basename(out)}...")
        self.compile_status.configure(text="Compiling...", text_color="#F59E0B")

        def on_done(rc, output):
            if rc == 0:
                self.compile_status.configure(text="OK", text_color="#10B981")
                self.log("Compile successful.")
            else:
                self.compile_status.configure(text="FAILED", text_color="#EF4444")
                self.log("Compile failed. Check Siemens DLL paths.")

        self.run_command(cmd, on_complete=on_done)

    def _export_blocks(self):
        dev = self._device_from_label(self.plc_device_var.get())
        if dev.startswith("--"):
            self.log("Select a PLC device first.")
            return
        path = self.plc_output_var.get()
        self.clear_console()
        self.log(f"Exporting blocks from '{dev}'...")
        self.run_command([self.export_exe, path, dev],
                         on_complete=lambda rc, _: self._on_export_blocks_done(rc))

    def _on_export_blocks_done(self, rc):
        if rc != 0:
            self.log("Export failed.")
            return
        self.log("Parsing exported blocks...")
        path = self.plc_output_var.get()
        dev = self._device_from_label(self.plc_device_var.get())
        cmd = ["python", os.path.join(SCRIPT_DIR, "extract_plc_full.py"), path, "--verbose", "--plc-name", dev]
        self.run_command(cmd, on_complete=lambda rc2, _: self._on_parse_plc_done(rc2))

    def _parse_plc(self):
        path = self.plc_output_var.get()
        self.clear_console()
        self.run_command(["python", os.path.join(SCRIPT_DIR, "extract_plc_full.py"), path, "--verbose"],
                         on_complete=lambda rc, _: self._on_parse_plc_done(rc))

    def _on_parse_plc_done(self, rc):
        if rc != 0:
            self.log("Parse failed. Cannot generate markdown reports.")
            return
        self.log("Generating PLC markdown reports...")
        self.run_command(["python", os.path.join(SCRIPT_DIR, "plc_report.py")])

    def _gen_plc_report(self):
        self.clear_console()
        self.run_command(["python", os.path.join(SCRIPT_DIR, "plc_report.py")])

    # ═══════════════════════════════════════════════════════════════════
    # HMI PAGE
    # ═══════════════════════════════════════════════════════════════════

    def _build_hmi_page(self):
        p = self.pages["hmi"]
        p.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(p, text="HMI Extraction Pipeline",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 15))

        # Step 1: Select HMI Device
        f1 = ctk.CTkFrame(p)
        f1.grid(row=1, column=0, sticky="ew", pady=5)
        f1.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f1, text="Step 1: Select HMI Device", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f1, text="List HMI Devices", width=150, command=self._list_hmi_devices).grid(row=1, column=0, padx=10, pady=6)
        self.hmi_device_var = ctk.StringVar(value="-- select --")
        self.hmi_device_dd = ctk.CTkOptionMenu(f1, variable=self.hmi_device_var, values=["-- select --"], width=400)
        self.hmi_device_dd.grid(row=1, column=1, padx=5, pady=6, sticky="ew")

        # Step 2: Compile HMI Extractor
        fc = ctk.CTkFrame(p)
        fc.grid(row=2, column=0, sticky="ew", pady=5)
        fc.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fc, text="Step 2: Compile HMI Extractor (after code changes)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(fc, text="Compile HMI Extractor", width=180, command=self._compile_hmi_extractor).grid(row=1, column=0, padx=10, pady=6)
        self.hmi_compile_status = ctk.CTkLabel(fc, text="", font=ctk.CTkFont(size=12))
        self.hmi_compile_status.grid(row=1, column=1, sticky="w", padx=5, pady=6)

        # Step 3: Extract
        f2 = ctk.CTkFrame(p)
        f2.grid(row=3, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f2, text="Step 3: Extract HMI Data", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f2, text="Extract HMI Data", width=160, command=self._online_extract).grid(row=1, column=0, padx=10, pady=6)
        ctk.CTkLabel(f2, text="Extracts elements, tags, events, navigation (requires TIA Portal running)",
                     text_color="#F59E0B", font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

        # Step 4: Generate Report
        f3 = ctk.CTkFrame(p)
        f3.grid(row=4, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f3, text="Step 4: Generate Report", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f3, text="Generate Report", width=140, command=self._gen_hmi_report).grid(row=1, column=0, padx=10, pady=6)
        ctk.CTkButton(f3, text="View Report", width=120, command=lambda: self.show_page("report")).grid(row=1, column=1, padx=5, pady=6)

        # Console
        self._build_console(p, row=5, name="hmi")

    def _list_hmi_devices(self):
        self.clear_console()
        self.log("Discovering HMI devices from TIA Portal...")
        self.run_command([self.export_exe, "--list"], on_complete=self._on_hmi_devices_listed)

    def _on_hmi_devices_listed(self, rc, output):
        if rc != 0:
            self.log("Failed to list devices. Is TIA Portal running?")
            return
        self.plc_devices, self.hmi_devices = parse_device_list(output)
        hmi_labels = [f"[HMI] {d['name']}  ({d['device']})" for d in self.hmi_devices]
        self.hmi_device_dd.configure(values=hmi_labels or ["-- no HMI found --"])
        if hmi_labels:
            self.hmi_device_var.set(hmi_labels[0])
        # Also update PLC dropdown in case user goes there later
        plc_labels = [f"[PLC] {d['name']}  ({d['device']})" for d in self.plc_devices]
        self.plc_device_dd.configure(values=plc_labels or ["-- no PLC found --"])
        if plc_labels:
            self.plc_device_var.set(plc_labels[0])
        self.log(f"Found {len(self.hmi_devices)} HMI(s), {len(self.plc_devices)} PLC(s)")

    def _compile_hmi_extractor(self):
        v = self.tia_version.get()
        csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
        cs_file = os.path.join(SCRIPT_DIR, "tia_extract.cs")

        if v == "V18-V19":
            dll = r"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll"
            out = os.path.join(SCRIPT_DIR, "tia_extract_v18.exe")
            cmd = [csc, f"/reference:{dll}", f"/out:{out}", cs_file]
        else:
            base = r"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48"
            out = os.path.join(SCRIPT_DIR, "tia_extract.exe")
            cmd = [csc,
                   f"/reference:{base}\\Siemens.Engineering.Base.dll",
                   f"/reference:{base}\\Siemens.Engineering.WinCCUnified.dll",
                   f"/reference:{base}\\Siemens.Engineering.Step7.dll",
                   f"/out:{out}", cs_file]

        self.clear_console()
        self.log(f"Compiling {os.path.basename(out)}...")
        self.hmi_compile_status.configure(text="Compiling...", text_color="#F59E0B")

        def on_done(rc, output):
            if rc == 0:
                self.hmi_compile_status.configure(text="OK", text_color="#10B981")
                self.log("Compile successful.")
            else:
                self.hmi_compile_status.configure(text="FAILED", text_color="#EF4444")
                self.log("Compile failed. Check Siemens DLL paths.")

        self.run_command(cmd, on_complete=on_done)

    def _online_extract(self):
        dev = self._device_from_label(self.hmi_device_var.get())
        if dev.startswith("--"):
            self.log("Select an HMI device first.")
            return
        out = os.path.join(DOC_OUTPUT, ".hmi_online_data.json")
        self.clear_console()
        self.log(f"Extracting HMI data for '{dev}'...")
        self.run_command([self.extract_exe, out, dev],
                         on_complete=lambda rc, _: self._on_extract_done(rc))

    def _on_extract_done(self, rc):
        if rc != 0:
            self.log("Extraction failed. Cannot generate markdown reports.")
            return
        self.log("Generating markdown reports...")
        self.run_command(["python", os.path.join(SCRIPT_DIR, "hmi_report.py")])

    def _gen_hmi_report(self):
        self.clear_console()
        self.run_command(["python", os.path.join(SCRIPT_DIR, "hmi_report.py")])

    # ═══════════════════════════════════════════════════════════════════
    # ANALYSIS PAGE
    # ═══════════════════════════════════════════════════════════════════

    def _build_analysis_page(self):
        p = self.pages["analysis"]
        p.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(p, text="Analysis Tools",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 15))

        # Full Pipeline
        fp = ctk.CTkFrame(p, border_width=2, border_color=("#3B82F6", "#3B82F6"))
        fp.grid(row=1, column=0, sticky="ew", pady=5)
        fp.grid_columnconfigure(1, weight=1)
        fp.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(fp, text="Full Pipeline", font=ctk.CTkFont(weight="bold", size=14),
                     text_color=("#3B82F6", "#3B82F6")).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 4))
        self.pipeline_plc_var = ctk.StringVar(value="-- select PLC --")
        self.pipeline_plc_dd = ctk.CTkOptionMenu(fp, variable=self.pipeline_plc_var, values=["-- select PLC --"],
                          width=200)
        self.pipeline_plc_dd.grid(row=1, column=1, padx=5, pady=6, sticky="ew")
        self.pipeline_hmi_var = ctk.StringVar(value="-- select HMI --")
        self.pipeline_hmi_dd = ctk.CTkOptionMenu(fp, variable=self.pipeline_hmi_var, values=["-- select HMI --"],
                          width=200)
        self.pipeline_hmi_dd.grid(row=1, column=2, padx=5, pady=6, sticky="ew")
        ctk.CTkButton(fp, text="Run Full Pipeline", width=160, fg_color=("#3B82F6", "#3B82F6"),
                      command=self._run_full_pipeline).grid(row=1, column=3, padx=10, pady=6)
        ctk.CTkLabel(fp, text="Exports PLC + HMI, runs all analyses, generates CLAUDE.md. Requires TIA Portal open.",
                     text_color="#F59E0B", font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))

        # Cross-reference Search
        f1 = ctk.CTkFrame(p)
        f1.grid(row=2, column=0, sticky="ew", pady=5)
        f1.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f1, text="Cross-reference Search", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 4))
        self.xref_query_var = ctk.StringVar()
        ctk.CTkEntry(f1, textvariable=self.xref_query_var, placeholder_text="Enter tag, block, or HMI element name...").grid(row=1, column=0, columnspan=2, padx=10, pady=6, sticky="ew")
        self.xref_type_var = ctk.StringVar(value="Auto")
        ctk.CTkOptionMenu(f1, variable=self.xref_type_var, values=["Auto", "Tag", "Block", "HMI"], width=100).grid(row=1, column=2, padx=5, pady=6)
        ctk.CTkButton(f1, text="Search", width=100, command=self._run_cross_reference).grid(row=1, column=3, padx=10, pady=6)

        # Dead Code Analysis
        f2 = ctk.CTkFrame(p)
        f2.grid(row=3, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f2, text="Unused Tags / Dead Code Detection", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f2, text="Run Analysis", width=140, command=self._run_dead_code).grid(row=1, column=0, padx=10, pady=6)

        # Traceability Matrix
        f3 = ctk.CTkFrame(p)
        f3.grid(row=4, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f3, text="HMI-PLC Traceability Matrix", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f3, text="Generate Matrix", width=160, command=self._run_traceability).grid(row=1, column=0, padx=10, pady=6)

        # Dependency Graph
        f4 = ctk.CTkFrame(p)
        f4.grid(row=5, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f4, text="Block Dependency Graph", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f4, text="Generate Graph", width=160, command=self._run_dependency_graph).grid(row=1, column=0, padx=10, pady=6)

        # Hardware Catalog
        f5 = ctk.CTkFrame(p)
        f5.grid(row=6, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(f5, text="Hardware Catalog", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkButton(f5, text="Extract Hardware", width=160, command=self._run_hardware_extract).grid(row=1, column=0, padx=10, pady=6)
        ctk.CTkButton(f5, text="Compile Extractor", width=150, command=self._compile_hardware).grid(row=1, column=1, padx=5, pady=6)
        self.hw_compile_status = ctk.CTkLabel(f5, text="", font=ctk.CTkFont(size=12))
        self.hw_compile_status.grid(row=1, column=2, sticky="w", padx=5, pady=6)
        ctk.CTkLabel(f5, text="Requires TIA Portal running with project open", text_color="#F59E0B",
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))

        # Console
        self._build_console(p, row=7, name="analysis")

    # ── Analysis handlers ─────────────────────────────────────────────

    def _run_cross_reference(self):
        query = self.xref_query_var.get().strip()
        if not query:
            self.log("Enter a search query first.")
            return
        type_flag = self.xref_type_var.get().lower()
        cmd = ["python", os.path.join(SCRIPT_DIR, "cross_reference.py"), query]
        if type_flag != "auto":
            cmd.append(f"--{type_flag}")
        self.clear_console()
        self.log(f"Searching: {query}")
        self.run_command(cmd)

    def _run_dead_code(self):
        self.clear_console()
        self.log("Running dead code analysis...")
        self.run_command(["python", os.path.join(SCRIPT_DIR, "dead_code_analysis.py")])

    def _run_traceability(self):
        self.clear_console()
        self.log("Generating traceability matrix...")
        self.run_command(["python", os.path.join(SCRIPT_DIR, "traceability_matrix.py")])

    def _run_dependency_graph(self):
        self.clear_console()
        self.log("Generating dependency graph...")
        self.run_command(["python", os.path.join(SCRIPT_DIR, "dependency_graph.py")])

    def _compile_hardware(self):
        v = self.tia_version.get()
        csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
        cs_file = os.path.join(SCRIPT_DIR, "tia_extract_hardware.cs")

        if v == "V18-V19":
            dll = r"C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll"
            cmd = [csc, f"/reference:{dll}", f"/out:{os.path.join(SCRIPT_DIR, 'tia_extract_hardware.exe')}", cs_file]
        else:
            base = r"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48"
            cmd = [csc,
                   f"/reference:{base}\\Siemens.Engineering.Base.dll",
                   f"/reference:{base}\\Siemens.Engineering.Step7.dll",
                   f"/out:{os.path.join(SCRIPT_DIR, 'tia_extract_hardware.exe')}", cs_file]

        self.clear_console()
        self.log("Compiling hardware extractor...")
        self.hw_compile_status.configure(text="Compiling...", text_color="#F59E0B")

        def on_done(rc, output):
            if rc == 0:
                self.hw_compile_status.configure(text="OK", text_color="#10B981")
                self.log("Compile successful.")
            else:
                self.hw_compile_status.configure(text="FAILED", text_color="#EF4444")
                self.log("Compile failed. Check Siemens DLL paths.")

        self.run_command(cmd, on_complete=on_done)

    def _run_hardware_extract(self):
        hw_exe = os.path.join(SCRIPT_DIR, "tia_extract_hardware.exe")
        if not os.path.exists(hw_exe):
            self.log("Hardware extractor not found. Compile it first.")
            return
        out = os.path.join(DOC_OUTPUT, ".hardware.json")
        self.clear_console()
        self.log("Extracting hardware config...")
        self.run_command([hw_exe, out],
                         on_complete=lambda rc, _: self._on_hw_extract_done(rc))

    def _on_hw_extract_done(self, rc):
        if rc != 0:
            self.log("Extraction failed.")
            return
        self.log("Generating hardware report...")
        self.run_command(["python", os.path.join(SCRIPT_DIR, "hardware_report.py")])

    def _pipeline_device_by_name(self, name):
        """Find device dict by display name from pipeline dropdown."""
        for d in self.plc_devices:
            if d['name'] == name:
                return d['device']
        for d in self.hmi_devices:
            if d['name'] == name:
                return d['device']
        return None

    def _run_full_pipeline(self):
        plc_name = self.pipeline_plc_var.get()
        hmi_name = self.pipeline_hmi_var.get()
        if plc_name.startswith("--") and hmi_name.startswith("--"):
            self.log("Select at least a PLC or HMI device first.")
            return
        self.clear_console()

        # Build step queue
        self._pipeline_steps = []
        plc_device = self._pipeline_device_by_name(plc_name) if not plc_name.startswith("--") else None
        hmi_device = self._pipeline_device_by_name(hmi_name) if not hmi_name.startswith("--") else None

        if plc_device:
            v = self.tia_version.get()
            exe = os.path.join(SCRIPT_DIR, "tia_export_blocks_v18.exe" if v == "V18-V19" else "tia_export_blocks.exe")
            out = os.path.join(DOC_OUTPUT, "DATA_Program blocks")
            self._pipeline_steps.append(("Export PLC blocks", [exe, out, plc_device]))
            self._pipeline_steps.append(("Parse PLC blocks", ["python", os.path.join(SCRIPT_DIR, "extract_plc_full.py"), out, "--verbose", "--plc-name", plc_device]))
            self._pipeline_steps.append(("Generate PLC reports", ["python", os.path.join(SCRIPT_DIR, "plc_report.py")]))

        if hmi_device:
            v = self.tia_version.get()
            exe = os.path.join(SCRIPT_DIR, "tia_extract_v18.exe" if v == "V18-V19" else "tia_extract.exe")
            json_path = os.path.join(DOC_OUTPUT, ".hmi_online_data.json")
            self._pipeline_steps.append(("Extract HMI data", [exe, json_path, hmi_device]))
            self._pipeline_steps.append(("Generate HMI reports", ["python", os.path.join(SCRIPT_DIR, "hmi_report.py")]))

        self._pipeline_steps.append(("Dead code analysis", ["python", os.path.join(SCRIPT_DIR, "dead_code_analysis.py")]))
        self._pipeline_steps.append(("Traceability matrix", ["python", os.path.join(SCRIPT_DIR, "traceability_matrix.py")]))
        self._pipeline_steps.append(("Dependency graph", ["python", os.path.join(SCRIPT_DIR, "dependency_graph.py")]))

        hw_exe = os.path.join(SCRIPT_DIR, "tia_extract_hardware.exe")
        if os.path.exists(hw_exe):
            self._pipeline_steps.append(("Extract hardware", [hw_exe, os.path.join(DOC_OUTPUT, ".hardware.json")]))

        self._pipeline_steps.append(("Generate CLAUDE.md", ["python", os.path.join(SCRIPT_DIR, "generate_claudemd.py")]))

        self._pipeline_idx = 0
        self._pipeline_total = len(self._pipeline_steps)
        self._run_next_pipeline_step()

    def _run_next_pipeline_step(self):
        if self._pipeline_idx >= len(self._pipeline_steps):
            self.log(f"\nPipeline complete ({self._pipeline_total} steps).")
            return
        label, cmd = self._pipeline_steps[self._pipeline_idx]
        self.log(f"\n[{self._pipeline_idx + 1}/{self._pipeline_total}] {label}...")

        # For hardware step, add report generation after
        next_idx = self._pipeline_idx + 1
        if "hardware" in label.lower():
            self.run_command(cmd, on_complete=lambda rc, _: self._on_hw_extract_then_continue(rc))
        else:
            self.run_command(cmd, on_complete=lambda rc, _: self._advance_pipeline(rc))

    def _on_hw_extract_then_continue(self, rc):
        if rc == 0:
            self.run_command(["python", os.path.join(SCRIPT_DIR, "hardware_report.py")],
                             on_complete=lambda rc2, _: self._advance_pipeline(rc2))
        else:
            self._advance_pipeline(rc)

    def _advance_pipeline(self, rc):
        if rc != 0:
            self.log(f"Step failed (exit {rc}), continuing...")
        self._pipeline_idx += 1
        self._run_next_pipeline_step()

    # ═══════════════════════════════════════════════════════════════════
    # REPORT PAGE
    # ═══════════════════════════════════════════════════════════════════

    def _build_report_page(self):
        p = self.pages["report"]
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(p, text="Report Viewer",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 15))

        cf = ctk.CTkFrame(p)
        cf.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        cf.grid_columnconfigure(0, weight=1)
        self.report_file_var = ctk.StringVar()
        self.report_dd = ctk.CTkOptionMenu(cf, variable=self.report_file_var, values=["-- no reports --"],
                                           command=self._load_report)
        self.report_dd.grid(row=0, column=0, padx=10, pady=6, sticky="ew")
        ctk.CTkButton(cf, text="Refresh", width=100, command=self._refresh_reports).grid(row=0, column=1, padx=5, pady=6)
        ctk.CTkButton(cf, text="Open in Editor", width=130, command=self._open_editor).grid(row=0, column=2, padx=5, pady=6)
        ctk.CTkButton(cf, text="Generate CLAUDE.md", width=160, command=self._gen_claudemd).grid(row=0, column=3, padx=5, pady=6)
        ctk.CTkButton(cf, text="Export Bundle", width=130, command=self._export_bundle).grid(row=0, column=4, padx=5, pady=6)

        self.report_text = ctk.CTkTextbox(p, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.report_text.grid(row=1, column=0, sticky="nsew")

    def _refresh_reports(self):
        files = scan_reports()
        if not files:
            self.report_dd.configure(values=["-- no reports --"])
            self.report_file_var.set("-- no reports --")
            self._report_files = {}
            return
        # Store basename -> full path mapping for subdirectory support
        self._report_files = {os.path.basename(f): f for f in files}
        names = list(self._report_files.keys())
        self.report_dd.configure(values=names)
        if not self.report_file_var.get() or self.report_file_var.get().startswith("--"):
            self.report_file_var.set(names[0])
            self._load_report(names[0])

    def _load_report(self, name=None):
        if name is None or name.startswith("--"):
            return
        # Look up full path from stored mapping, fall back to Doc_OUTPUT/name
        if hasattr(self, '_report_files') and name in self._report_files:
            path = self._report_files[name]
        else:
            path = os.path.join(DOC_OUTPUT, name)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.report_text.configure(state="normal")
            self.report_text.delete("1.0", "end")
            self.report_text.insert("1.0", content)
            self.report_text.configure(state="disabled")
            lines = content.count("\n")
            self.log(f"Loaded {name} ({lines} lines)")
        except Exception as e:
            self.log(f"Error reading {name}: {e}")

    def _open_editor(self):
        name = self.report_file_var.get()
        if name.startswith("--"):
            return
        if hasattr(self, '_report_files') and name in self._report_files:
            path = self._report_files[name]
        else:
            path = os.path.join(DOC_OUTPUT, name)
        if os.path.exists(path):
            os.startfile(path)

    def _gen_claudemd(self):
        self.clear_console()
        self.log("Generating CLAUDE.md...")
        self._active_console = self.plc_console
        self._active_progress = self.plc_progress
        self.run_command(
            ["python", os.path.join(SCRIPT_DIR, "generate_claudemd.py")],
            on_complete=lambda rc, _: self._on_claudemd_done(rc),
        )

    def _on_claudemd_done(self, rc):
        if rc == 0:
            self._refresh_reports()
            self.report_file_var.set("CLAUDE.md")
            self._load_report("CLAUDE.md")
            self.log("CLAUDE.md generated and loaded in Report Viewer.")

    def _export_bundle(self):
        """Export all reports + JSON data to a folder for Claude Code."""
        target = filedialog.askdirectory(title="Select Export Target Folder")
        if not target:
            return

        self._active_console = self.plc_console
        self._active_progress = self.plc_progress
        self.clear_console()
        self.log(f"Exporting bundle to: {target}")

        import shutil
        copied = 0

        # Program_Blocks/
        src_pb = os.path.join(DOC_OUTPUT, "Program_Blocks")
        dst_pb = os.path.join(target, "Program_Blocks")
        if os.path.isdir(src_pb):
            if os.path.exists(dst_pb):
                shutil.rmtree(dst_pb)
            shutil.copytree(src_pb, dst_pb)
            count = sum(1 for _ in glob.glob(os.path.join(dst_pb, "**", "*.md"), recursive=True))
            self.log(f"  Program_Blocks/ — {count} .md files")
            copied += count

        # hmi_screens/
        src_hmi = os.path.join(DOC_OUTPUT, "hmi_screens")
        dst_hmi = os.path.join(target, "hmi_screens")
        if os.path.isdir(src_hmi):
            if os.path.exists(dst_hmi):
                shutil.rmtree(dst_hmi)
            shutil.copytree(src_hmi, dst_hmi)
            count = sum(1 for _ in glob.glob(os.path.join(dst_hmi, "*.md")))
            self.log(f"  hmi_screens/ — {count} .md files")
            copied += count

        # CLAUDE.md
        src_claude = os.path.join(DOC_OUTPUT, "CLAUDE.md")
        if os.path.exists(src_claude):
            shutil.copy2(src_claude, os.path.join(target, "CLAUDE.md"))
            self.log("  CLAUDE.md")
            copied += 1

        # JSON data files (rename without dot prefix for visibility)
        json_files = {
            ".plc_cache.json": "plc_cache.json",
            ".hmi_merged.json": "hmi_merged.json",
            ".hmi_online_data.json": "hmi_online_data.json",
            "hmi_offline_data.json": "hmi_offline_data.json",
        }
        for src_name, dst_name in json_files.items():
            src = os.path.join(DOC_OUTPUT, src_name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(target, dst_name))
                self.log(f"  {dst_name}")
                copied += 1

        if copied:
            self.log(f"\nExport complete: {copied} files to {target}")
            self.status_var.set(f"Exported {copied} files")
        else:
            self.log("Nothing to export. Run extractions first.")
            self.status_var.set("Export: nothing to export")

    # ═══════════════════════════════════════════════════════════════════
    # CONSOLE WIDGET (shared by PLC & HMI pages)
    # ═══════════════════════════════════════════════════════════════════

    def _build_console(self, parent, row, name="plc"):
        console = ctk.CTkTextbox(parent, height=220, font=ctk.CTkFont(family="Consolas", size=12))
        console.grid(row=row, column=0, sticky="ew", pady=(10, 5))
        progress = ctk.CTkProgressBar(parent, mode="indeterminate", height=6)
        progress.grid(row=row + 1, column=0, sticky="ew", pady=(0, 5))
        if name == "plc":
            self.plc_console = console
            self.plc_progress = progress
            self._active_console = console
            self._active_progress = progress
        else:
            self.hmi_console = console
            self.hmi_progress = progress
        return console, progress

    def log(self, msg):
        c = self._active_console
        if c is None:
            return
        c.configure(state="normal")
        c.insert("end", msg + "\n")
        c.see("end")
        line_count = int(c.index("end-1c").split(".")[0])
        if line_count > 10000:
            c.delete("1.0", f"{line_count - 10000}.0")
        c.configure(state="disabled")

    def clear_console(self):
        c = self._active_console
        if c is None:
            return
        c.configure(state="normal")
        c.delete("1.0", "end")
        c.configure(state="disabled")

    # ═══════════════════════════════════════════════════════════════════
    # SUBPROCESS MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════

    def run_command(self, cmd_parts, on_complete=None):
        if self._running:
            self.log("Another command is still running. Please wait.")
            return
        self._running = True
        p = self._active_progress
        if p:
            p.start()
        self.status_var.set(f"Running: {os.path.basename(cmd_parts[0])}...")
        threading.Thread(target=self._worker, args=(cmd_parts, on_complete), daemon=True).start()

    def _worker(self, cmd_parts, on_complete):
        try:
            proc = subprocess.Popen(
                cmd_parts, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=SCRIPT_DIR,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            output_lines = []
            for line in proc.stdout:
                output_lines.append(line)
                stripped = line.rstrip()
                if stripped:
                    self.after(0, self.log, stripped)
            rc = proc.wait()
            full_output = "".join(output_lines)
        except Exception as e:
            rc = -1
            full_output = str(e)
            self.after(0, self.log, f"Error: {e}")

        self.after(0, self._on_command_done, rc, full_output, on_complete)

    def _on_command_done(self, rc, output, on_complete):
        self._running = False
        p = self._active_progress
        if p:
            p.stop()
        if rc == 0:
            self.status_var.set("Ready")
            self.log("Done.")
        else:
            self.status_var.set(f"Failed (exit code {rc})")
            self.log(f"Command failed with exit code {rc}.")
        if on_complete:
            on_complete(rc, output)

    # ── helpers ────────────────────────────────────────────────────────

    def _browse_folder(self, var):
        result = filedialog.askdirectory(title="Select Folder")
        if result:
            var.set(result)


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = TiaToolkitApp()
    app.mainloop()
