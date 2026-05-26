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

function saveState() {
    vscode.setState({
        tiaVersion: tiaVersion,
        activeTab: activeTab,
        plc: savedPlc,
        hmi: savedHmi,
        plcOutput: savedPlcOutput,
        plcConsole: savedPlcConsole,
        hmiConsole: savedHmiConsole
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
    else { savedHmiConsole.push(text); if (savedHmiConsole.length > 1000) savedHmiConsole.shift(); }
    saveState();
}

function clearConsole() {
    var el = consoleEl();
    if (el) el.innerHTML = '';
    if (activeTab === 'plc') savedPlcConsole = []; else savedHmiConsole = [];
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
    action('loadReport', { name: e.target.value });
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

window.addEventListener('message', function(event) {
    var msg = event.data;
    switch (msg.type) {
        case 'console': appendConsole(msg.text); break;
        case 'clearConsole': clearConsole(); break;
        case 'progress': setProgress(msg.active); break;
        case 'devices': populateDevices(msg.plc, msg.hmi); break;
        case 'compileStatus': setStatus(msg.id, msg.text, msg.cls); break;
        case 'reports':
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
    }
});

// ── Restore state on load ──────────────────────────────────────────────
if (savedState.tiaVersion) setVersion(savedState.tiaVersion);
if (savedState.activeTab) switchTab(savedState.activeTab);
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
                <button class="btn" id="btn-refresh-reports">Refresh</button>
                <button class="btn" id="btn-open-editor">Open</button>
                <button class="btn" id="btn-gen-claudemd">CLAUDE.md</button>
                <button class="btn" id="btn-export-bundle">Export</button>
            </div>
            <div class="report-content" id="report-content"></div>
        </div>
    </div>
    <script>${JS}</script>
</body>
</html>`;

export function getWebviewHtml(): string {
    return HTML;
}
