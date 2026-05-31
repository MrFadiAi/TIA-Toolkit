// Inlined webview content — no external file dependencies

const CSS = `
:root {
    --bg: var(--vscode-editor-background);
    --fg: var(--vscode-editor-foreground);
    --border: var(--vscode-panel-border, #3c3c3c);
    --btn-bg: var(--vscode-button-background, #0e639c);
    --btn-fg: var(--vscode-button-foreground, #fff);
    --btn-hover: var(--vscode-button-hoverBackground, #1177bb);
    --btn-secondary-bg: var(--vscode-button-secondaryBackground, #3a3d41);
    --btn-secondary-fg: var(--vscode-button-secondaryForeground, #fff);
    --btn-secondary-hover: var(--vscode-button-secondaryHoverBackground, #45494e);
    --input-bg: var(--vscode-input-background, #3c3c3c);
    --input-fg: var(--vscode-input-foreground, #ccc);
    --input-border: var(--vscode-input-border, #3c3c3c);
    --active-tab: var(--vscode-tab-activeBackground, #1e1e1e);
    --inactive-tab: var(--vscode-tab-inactiveBackground, #2d2d2d);
    --accent: var(--vscode-focusBorder, #007fd4);
    --warning: #F59E0B;
    --success: #10B981;
    --error: #EF4444;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif);
    font-size: var(--vscode-font-size, 13px);
    color: var(--fg);
    background: var(--bg);
    padding: 8px;
}
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.title { font-size: 15px; font-weight: 600; }
.version-selector { display: flex; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; }
.seg-btn {
    padding: 3px 10px; border: none; background: var(--inactive-tab);
    color: var(--fg); cursor: pointer; font-size: 11px; transition: background 0.15s;
}
.seg-btn.active { background: var(--btn-bg); color: var(--btn-fg); }
.seg-btn:hover:not(.active) { background: var(--btn-secondary-hover); }
.tab-bar { display: flex; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.tab-btn {
    flex: 1; padding: 6px 4px; border: none; border-bottom: 2px solid transparent;
    background: var(--inactive-tab); color: var(--fg); cursor: pointer;
    font-size: 12px; transition: all 0.15s; text-align: center;
}
.tab-btn.active { background: var(--active-tab); border-bottom-color: var(--accent); }
.tab-btn:hover:not(.active) { background: var(--btn-secondary-hover); }
.tab-content { display: none; }
.tab-content.active { display: block; }
.step-group {
    background: var(--inactive-tab); border: 1px solid var(--border);
    border-radius: 4px; padding: 8px 10px; margin-bottom: 6px;
}
.step-header { font-weight: 600; margin-bottom: 6px; font-size: 12px; }
.step-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.warning { color: var(--warning); font-size: 10px; margin-top: 4px; }
.btn {
    padding: 4px 10px; border: 1px solid var(--border); border-radius: 3px;
    background: var(--btn-secondary-bg); color: var(--btn-secondary-fg);
    cursor: pointer; font-size: 11px; white-space: nowrap; transition: background 0.15s;
}
.btn:hover { background: var(--btn-secondary-hover); }
.btn-primary { background: var(--btn-bg); color: var(--btn-fg); border-color: var(--btn-bg); }
.btn-primary:hover { background: var(--btn-hover); }
.btn-sm { padding: 4px 8px; }
.input {
    flex: 1; padding: 4px 6px; border: 1px solid var(--input-border); border-radius: 3px;
    background: var(--input-bg); color: var(--input-fg); font-size: 11px; min-width: 100px;
}
.select {
    flex: 1; padding: 4px 6px; border: 1px solid var(--input-border); border-radius: 3px;
    background: var(--input-bg); color: var(--input-fg); font-size: 11px; min-width: 100px;
}
.select-wide { flex: 2; min-width: 120px; }
.status-label { font-size: 11px; font-weight: 600; }
.status-label.ok { color: var(--success); }
.status-label.fail { color: var(--error); }
.status-label.busy { color: var(--warning); }
.console-area {
    background: var(--vscode-terminal-background, #1e1e1e); color: var(--fg);
    font-family: 'Consolas', 'Courier New', monospace; font-size: 11px;
    padding: 6px; border: 1px solid var(--border); border-radius: 3px;
    height: 150px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; margin-top: 6px;
}
.console-line { line-height: 1.3; }
.progress-bar {
    height: 2px; background: var(--border); border-radius: 2px;
    margin-top: 4px; overflow: hidden; position: relative;
}
.progress-bar.active::after {
    content: ''; position: absolute; top: 0; left: -40%; width: 40%; height: 100%;
    background: var(--accent); animation: slide 1.2s ease-in-out infinite;
}
@keyframes slide { 0% { left: -40%; } 100% { left: 100%; } }
.report-toolbar { margin-bottom: 6px; }
.report-content {
    background: var(--vscode-textCodeBlock-background, #1e1e1e); color: var(--fg);
    font-family: 'Consolas', 'Courier New', monospace; font-size: 11px;
    padding: 8px; border: 1px solid var(--border); border-radius: 3px;
    height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; line-height: 1.4;
}
`;

const JS = `
const vscode = acquireVsCodeApi();
var savedState = vscode.getState() || {};
var tiaVersion = savedState.tiaVersion || 'V21+';
var activeTab = savedState.activeTab || 'plc';
var savedPlc = savedState.plc || [];
var savedHmi = savedState.hmi || [];
var savedPlcOutput = savedState.plcOutput || '';
var savedPlcConsole = savedState.plcConsole || [];
var savedHmiConsole = savedState.hmiConsole || [];
var savedAnalysisConsole = savedState.analysisConsole || [];
var currentReport = savedState.currentReport || '';
var reportViewMode = savedState.reportViewMode || 'md';
window.__reportFiles = [];

function saveState() {
    vscode.setState({
        tiaVersion: tiaVersion,
        activeTab: activeTab,
        plc: savedPlc,
        hmi: savedHmi,
        plcOutput: savedPlcOutput,
        currentReport: currentReport,
        reportViewMode: reportViewMode,
        plcConsole: savedPlcConsole,
        hmiConsole: savedHmiConsole,
        analysisConsole: savedAnalysisConsole
    });
}

function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.toggle('active', b.dataset.tab === tab); });
    document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.toggle('active', c.id === 'tab-' + tab); });
    saveState();
}

function setVersion(v) {
    tiaVersion = v;
    document.querySelectorAll('.seg-btn').forEach(function(b) { b.classList.toggle('active', b.dataset.version === v); });
    saveState();
}

document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() { switchTab(btn.dataset.tab); vscode.postMessage({ type: 'switchTab', tab: btn.dataset.tab }); });
});
document.querySelectorAll('.seg-btn').forEach(function(btn) {
    btn.addEventListener('click', function() { setVersion(btn.dataset.version); vscode.postMessage({ type: 'setVersion', version: tiaVersion }); });
});

function setReportViewMode(mode) {
    reportViewMode = mode;
    document.querySelectorAll('#report-view-mode .seg-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.view === mode);
    });
    saveState();
    vscode.postMessage({ type: 'setReportViewMode', mode: mode });
}
document.querySelectorAll('#report-view-mode .seg-btn').forEach(function(btn) {
    btn.addEventListener('click', function() { setReportViewMode(btn.dataset.view); });
});

function action(type, payload) {
    payload = payload || {};
    vscode.postMessage(Object.assign({ type: type, version: tiaVersion }, payload));
}

function consoleEl() { return document.getElementById(activeTab + '-console'); }

function appendConsole(text) {
    var el = consoleEl();
    if (!el) return;
    var line = document.createElement('div');
    line.className = 'console-line';
    line.textContent = text;
    el.appendChild(line);
    while (el.childElementCount > 10000) { el.removeChild(el.firstChild); }
    el.scrollTop = el.scrollHeight;
    if (activeTab === 'plc') { savedPlcConsole.push(text); if (savedPlcConsole.length > 1000) savedPlcConsole.shift(); }
    else if (activeTab === 'hmi') { savedHmiConsole.push(text); if (savedHmiConsole.length > 1000) savedHmiConsole.shift(); }
    else { savedAnalysisConsole.push(text); if (savedAnalysisConsole.length > 1000) savedAnalysisConsole.shift(); }
    saveState();
}

function clearConsole() {
    var el = consoleEl();
    if (el) el.innerHTML = '';
    if (activeTab === 'plc') savedPlcConsole = []; else if (activeTab === 'hmi') savedHmiConsole = []; else savedAnalysisConsole = [];
    saveState();
}

function setProgress(active) {
    var el = document.getElementById(activeTab + '-progress');
    if (el) el.classList.toggle('active', active);
}

function setStatus(id, text, cls) {
    var el = document.getElementById(id);
    if (el) { el.textContent = text; el.className = 'status-label ' + cls; }
}

function populateDevices(plc, hmi) {
    savedPlc = plc; savedHmi = hmi;
    var plcSel = document.getElementById('plc-device-select');
    plcSel.innerHTML = '';
    if (plc.length === 0) {
        plcSel.innerHTML = '<option value="">-- no PLC found --</option>';
    } else {
        plc.forEach(function(d) {
            var opt = document.createElement('option');
            opt.value = d.device;
            opt.textContent = '[PLC] ' + d.name + '  (' + d.device + ')';
            plcSel.appendChild(opt);
        });
    }
    var hmiSel = document.getElementById('hmi-device-select');
    hmiSel.innerHTML = '';
    if (hmi.length === 0) {
        hmiSel.innerHTML = '<option value="">-- no HMI found --</option>';
    } else {
        hmi.forEach(function(d) {
            var opt = document.createElement('option');
            opt.value = d.device;
            opt.textContent = '[HMI] ' + d.name + '  (' + d.device + ')';
            hmiSel.appendChild(opt);
        });
    }
    saveState();
    // Sync pipeline dropdowns
    var pPlc = document.getElementById('pipeline-plc');
    pPlc.innerHTML = '<option value="">-- PLC --</option>';
    plc.forEach(function(d) { var o = document.createElement('option'); o.value = d.device; o.textContent = d.name; pPlc.appendChild(o); });
    var pHmi = document.getElementById('pipeline-hmi');
    pHmi.innerHTML = '<option value="">-- HMI --</option>';
    hmi.forEach(function(d) { var o = document.createElement('option'); o.value = d.device; o.textContent = d.name; pHmi.appendChild(o); });
}

document.getElementById('btn-list-devices').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('listDevices');
});
document.getElementById('btn-compile-plc').addEventListener('click', function() {
    clearConsole(); setProgress(true); setStatus('plc-compile-status', 'Compiling...', 'busy'); action('compilePlc');
});
document.getElementById('btn-browse-plc').addEventListener('click', function() {
    action('browsePlcOutput');
});
document.getElementById('btn-export-blocks').addEventListener('click', function() {
    var device = document.getElementById('plc-device-select').value;
    var outputPath = document.getElementById('plc-output-path').value;
    if (!device) { appendConsole('Select a PLC device first.'); return; }
    clearConsole(); setProgress(true); action('exportBlocks', { device: device, outputPath: outputPath });
});
document.getElementById('btn-parse-blocks').addEventListener('click', function() {
    var outputPath = document.getElementById('plc-output-path').value;
    clearConsole(); setProgress(true); action('parseBlocks', { outputPath: outputPath });
});
document.getElementById('btn-gen-plc-report').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('genPlcReport');
});
document.getElementById('btn-view-plc-report').addEventListener('click', function() {
    switchTab('report'); vscode.postMessage({ type: 'switchTab', tab: 'report' });
});
document.getElementById('btn-list-hmi').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('listHmiDevices');
});
document.getElementById('btn-compile-hmi').addEventListener('click', function() {
    clearConsole(); setProgress(true); setStatus('hmi-compile-status', 'Compiling...', 'busy'); action('compileHmi');
});
document.getElementById('btn-extract-hmi').addEventListener('click', function() {
    var device = document.getElementById('hmi-device-select').value;
    if (!device) { appendConsole('Select an HMI device first.'); return; }
    clearConsole(); setProgress(true); action('extractHmi', { device: device });
});
document.getElementById('btn-gen-hmi-report').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('genHmiReport');
});
document.getElementById('btn-view-hmi-report').addEventListener('click', function() {
    switchTab('report'); vscode.postMessage({ type: 'switchTab', tab: 'report' });
});
document.getElementById('btn-refresh-reports').addEventListener('click', function() {
    action('refreshReports');
});
document.getElementById('report-select').addEventListener('change', function(e) {
    currentReport = e.target.value; saveState();
    var fullPath = '';
    if (window.__reportFiles) {
        var found = window.__reportFiles.find(function(f) { return f.name === e.target.value; });
        if (found) fullPath = found.fullPath;
    }
    action('loadReport', { name: e.target.value, fullPath: fullPath });
});
document.getElementById('btn-open-editor').addEventListener('click', function() {
    var name = document.getElementById('report-select').value;
    if (name) action('openInEditor', { name: name });
});
document.getElementById('btn-gen-claudemd').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('genClaudeMd');
});
document.getElementById('btn-export-bundle').addEventListener('click', function() {
    action('exportBundle');
});

// ── Analysis tab buttons ─────────────────────────────────────────────────
document.getElementById('btn-run-pipeline').addEventListener('click', function() {
    var plc = document.getElementById('pipeline-plc').value;
    var hmi = document.getElementById('pipeline-hmi').value;
    if (!plc && !hmi) { appendConsole('Select at least a PLC or HMI device.'); return; }
    clearConsole(); setProgress(true);
    action('runFullPipeline', { plcDevice: plc, hmiDevice: hmi });
});
document.getElementById('btn-xref-search').addEventListener('click', function() {
    var q = document.getElementById('xref-query').value;
    var t = document.getElementById('xref-type').value;
    if (!q) { appendConsole('Enter a search query.'); return; }
    clearConsole(); setProgress(true); action('crossReference', { query: q, queryType: t });
});
document.getElementById('btn-dead-code').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('deadCode');
});
document.getElementById('btn-traceability').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('traceabilityMatrix');
});
document.getElementById('btn-dep-graph').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('dependencyGraph');
});
document.getElementById('btn-compile-hw').addEventListener('click', function() {
    clearConsole(); setProgress(true); setStatus('hw-compile-status', 'Compiling...', 'busy'); action('compileHardware');
});
document.getElementById('btn-extract-hw').addEventListener('click', function() {
    clearConsole(); setProgress(true); action('extractHardware');
});

window.addEventListener('message', function(event) {
    var msg = event.data;
    switch (msg.type) {
        case 'console': appendConsole(msg.text); break;
        case 'clearConsole': clearConsole(); break;
        case 'progress': setProgress(msg.active); break;
        case 'devices': populateDevices(msg.plc, msg.hmi); break;
        case 'compileStatus': setStatus(msg.id, msg.text, msg.cls); break;
        case 'reports':
            window.__reportFiles = msg.files;
            var sel = document.getElementById('report-select');
            sel.innerHTML = '';
            if (msg.files.length === 0) {
                sel.innerHTML = '<option value="">-- no reports --</option>';
            } else {
                msg.files.forEach(function(f) {
                    var opt = document.createElement('option');
                    opt.value = f.name;
                    opt.textContent = f.name;
                    sel.appendChild(opt);
                });
                // Auto-load first report only if none was previously selected
                if (!currentReport) {
                    sel.selectedIndex = 0;
                    vscode.postMessage({ type: 'loadReport', name: msg.files[0].name, fullPath: msg.files[0].fullPath });
                }
            }
            break;
        case 'reportContent':
            document.getElementById('report-content').textContent = msg.content;
            break;
        case 'plcOutputPath':
            document.getElementById('plc-output-path').value = msg.path;
            savedPlcOutput = msg.path; saveState();
            break;
        case 'switchTab':
            switchTab(msg.tab);
            break;
        case 'selectReport':
            var reportSel = document.getElementById('report-select');
            if (reportSel) { reportSel.value = msg.name; }
            currentReport = msg.name; saveState();
            break;
    }
});

// ── Restore state on load ──────────────────────────────────────────────
if (savedState.tiaVersion) setVersion(savedState.tiaVersion);
if (savedState.activeTab) switchTab(savedState.activeTab);
if (savedState.reportViewMode) setReportViewMode(savedState.reportViewMode);
if (savedPlc.length > 0 || savedHmi.length > 0) populateDevices(savedPlc, savedHmi);
if (savedPlcOutput) document.getElementById('plc-output-path').value = savedPlcOutput;
savedPlcConsole.forEach(function(l) {
    var el = document.getElementById('plc-console');
    if (el) { var d = document.createElement('div'); d.className = 'console-line'; d.textContent = l; el.appendChild(d); }
});
savedHmiConsole.forEach(function(l) {
    var el = document.getElementById('hmi-console');
    if (el) { var d = document.createElement('div'); d.className = 'console-line'; d.textContent = l; el.appendChild(d); }
});
savedAnalysisConsole.forEach(function(l) {
    var el = document.getElementById('analysis-console');
    if (el) { var d = document.createElement('div'); d.className = 'console-line'; d.textContent = l; el.appendChild(d); }
});
`;

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <style>${CSS}</style>
</head>
<body>
    <div class="app">
        <div class="header">
            <h1 class="title">TIA Toolkit</h1>
            <div class="version-selector">
                <button class="seg-btn active" data-version="V21+">V21+</button>
                <button class="seg-btn" data-version="V18-V19">V18-V19</button>
            </div>
        </div>
        <div class="tab-bar">
            <button class="tab-btn active" data-tab="plc">PLC</button>
            <button class="tab-btn" data-tab="hmi">HMI</button>
            <button class="tab-btn" data-tab="report">Reports</button>
            <button class="tab-btn" data-tab="analysis">Analysis</button>
        </div>
        <div class="tab-content active" id="tab-plc">
            <div class="step-group">
                <div class="step-header">Step 1: Discover Devices</div>
                <div class="step-row">
                    <button class="btn" id="btn-list-devices">List Devices</button>
                    <select class="select" id="plc-device-select"><option value="">-- select PLC --</option></select>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Step 1b: Compile Exporter</div>
                <div class="step-row">
                    <button class="btn" id="btn-compile-plc">Compile C#</button>
                    <span class="status-label" id="plc-compile-status"></span>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Step 2: Export PLC Blocks</div>
                <div class="step-row">
                    <input type="text" class="input" id="plc-output-path" placeholder="Output path...">
                    <button class="btn btn-sm" id="btn-browse-plc">...</button>
                    <button class="btn btn-primary" id="btn-export-blocks">Export</button>
                </div>
                <div class="warning">Requires TIA Portal running with project open</div>
            </div>
            <div class="step-group">
                <div class="step-header">Step 3: Parse &amp; Report</div>
                <div class="step-row">
                    <button class="btn" id="btn-parse-blocks">Parse</button>
                    <button class="btn" id="btn-gen-plc-report">Report</button>
                    <button class="btn" id="btn-view-plc-report">View</button>
                </div>
            </div>
            <div class="console-area" id="plc-console"></div>
            <div class="progress-bar" id="plc-progress"></div>
        </div>
        <div class="tab-content" id="tab-hmi">
            <div class="step-group">
                <div class="step-header">Step 1: Select HMI Device</div>
                <div class="step-row">
                    <button class="btn" id="btn-list-hmi">List HMI</button>
                    <select class="select" id="hmi-device-select"><option value="">-- select --</option></select>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Step 2: Compile HMI Extractor</div>
                <div class="step-row">
                    <button class="btn" id="btn-compile-hmi">Compile C#</button>
                    <span class="status-label" id="hmi-compile-status"></span>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Step 3: Extract HMI Data</div>
                <div class="step-row">
                    <button class="btn btn-primary" id="btn-extract-hmi">Extract HMI Data</button>
                </div>
                <div class="warning">Requires TIA Portal running</div>
            </div>
            <div class="step-group">
                <div class="step-header">Step 4: Generate Report</div>
                <div class="step-row">
                    <button class="btn" id="btn-gen-hmi-report">Report</button>
                    <button class="btn" id="btn-view-hmi-report">View</button>
                </div>
            </div>
            <div class="console-area" id="hmi-console"></div>
            <div class="progress-bar" id="hmi-progress"></div>
        </div>
        <div class="tab-content" id="tab-report">
            <div class="step-row report-toolbar">
                <select class="select select-wide" id="report-select"><option value="">-- no reports --</option></select>
            </div>
            <div class="step-row" style="margin-bottom:6px">
                <div class="version-selector" id="report-view-mode" style="margin-right:8px">
                    <button class="seg-btn" data-view="xml">XML Source</button>
                    <button class="seg-btn active" data-view="md">MD Reports</button>
                    <button class="seg-btn" data-view="both">Both</button>
                </div>
                <button class="btn" id="btn-refresh-reports">Refresh</button>
                <button class="btn" id="btn-open-editor">Open</button>
                <button class="btn" id="btn-gen-claudemd">CLAUDE.md</button>
                <button class="btn" id="btn-export-bundle">Export</button>
            </div>
            <div class="report-content" id="report-content"></div>
        </div>
        <div class="tab-content" id="tab-analysis">
            <div class="step-group" style="border-color:var(--accent)">
                <div class="step-header" style="color:var(--accent)">Full Pipeline</div>
                <div class="step-row">
                    <select class="select" id="pipeline-plc" style="flex:1;min-width:120px"><option value="">-- PLC --</option></select>
                    <select class="select" id="pipeline-hmi" style="flex:1;min-width:120px"><option value="">-- HMI --</option></select>
                    <button class="btn btn-primary" id="btn-run-pipeline" style="white-space:nowrap">Run Full Pipeline</button>
                </div>
                <div class="warning">Exports PLC + HMI, runs all analyses, generates CLAUDE.md. Requires TIA Portal open.</div>
            </div>
            <div class="step-group">
                <div class="step-header">Cross-reference Search</div>
                <div class="step-row">
                    <input type="text" class="input" id="xref-query" placeholder="Tag, block, or HMI element...">
                    <select class="select" id="xref-type" style="flex:0;min-width:80px">
                        <option value="auto">Auto</option>
                        <option value="tag">Tag</option>
                        <option value="block">Block</option>
                        <option value="hmi">HMI</option>
                    </select>
                    <button class="btn btn-primary" id="btn-xref-search">Search</button>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Dead Code Analysis</div>
                <div class="step-row">
                    <button class="btn" id="btn-dead-code">Run Analysis</button>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">HMI-PLC Traceability</div>
                <div class="step-row">
                    <button class="btn btn-primary" id="btn-traceability">Generate Matrix</button>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Dependency Graph</div>
                <div class="step-row">
                    <button class="btn" id="btn-dep-graph">Generate Graph</button>
                </div>
            </div>
            <div class="step-group">
                <div class="step-header">Hardware Catalog</div>
                <div class="step-row">
                    <button class="btn" id="btn-compile-hw">Compile</button>
                    <button class="btn btn-primary" id="btn-extract-hw">Extract Hardware</button>
                    <span class="status-label" id="hw-compile-status"></span>
                </div>
                <div class="warning">Requires TIA Portal running with project open</div>
            </div>
            <div class="console-area" id="analysis-console"></div>
            <div class="progress-bar" id="analysis-progress"></div>
        </div>
    </div>
    <script>${JS}</script>
</body>
</html>`;

export function getWebviewHtml(): string {
    return HTML;
}
