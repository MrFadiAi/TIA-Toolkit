// @ts-nocheck
const vscode = acquireVsCodeApi();

// ── State ──────────────────────────────────────────────────────────────────
let tiaVersion = 'V21+';
let activeTab = 'plc';

// ── Tab switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        switchTab(tab);
        vscode.postMessage({ type: 'switchTab', tab });
    });
});

function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));
}

// ── Version selector ───────────────────────────────────────────────────────
document.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        tiaVersion = btn.dataset.version;
        document.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('active', b === btn));
        vscode.postMessage({ type: 'setVersion', version: tiaVersion });
    });
});

// ── Helper: send action ────────────────────────────────────────────────────
function action(type, payload = {}) {
    vscode.postMessage({ type, ...payload, version: tiaVersion });
}

// ── Console helpers ────────────────────────────────────────────────────────
function consoleEl() {
    return document.getElementById(`${activeTab}-console`);
}

function appendConsole(text) {
    const el = consoleEl();
    if (!el) { return; }
    const line = document.createElement('div');
    line.className = 'console-line';
    line.textContent = text;
    el.appendChild(line);
    // Trim to 10000 lines
    while (el.childElementCount > 10000) {
        el.removeChild(el.firstChild);
    }
    el.scrollTop = el.scrollHeight;
}

function clearConsole() {
    const el = consoleEl();
    if (el) { el.innerHTML = ''; }
}

function setProgress(active) {
    const el = document.getElementById(`${activeTab}-progress`);
    if (el) { el.classList.toggle('active', active); }
}

function setStatus(id, text, cls) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
        el.className = `status-label ${cls}`;
    }
}

// ── PLC Pipeline buttons ───────────────────────────────────────────────────
document.getElementById('btn-list-devices').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    action('listDevices');
});

document.getElementById('btn-compile-plc').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    setStatus('plc-compile-status', 'Compiling...', 'busy');
    action('compilePlc');
});

document.getElementById('btn-browse-plc').addEventListener('click', () => {
    action('browsePlcOutput');
});

document.getElementById('btn-export-blocks').addEventListener('click', () => {
    const device = document.getElementById('plc-device-select').value;
    const outputPath = document.getElementById('plc-output-path').value;
    if (!device) { appendConsole('Select a PLC device first.'); return; }
    clearConsole();
    setProgress(true);
    action('exportBlocks', { device, outputPath });
});

document.getElementById('btn-parse-blocks').addEventListener('click', () => {
    const outputPath = document.getElementById('plc-output-path').value;
    clearConsole();
    setProgress(true);
    action('parseBlocks', { outputPath });
});

document.getElementById('btn-gen-plc-report').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    action('genPlcReport');
});

document.getElementById('btn-view-plc-report').addEventListener('click', () => {
    switchTab('report');
    vscode.postMessage({ type: 'switchTab', tab: 'report' });
});

// ── HMI Pipeline buttons ───────────────────────────────────────────────────
document.getElementById('btn-list-hmi').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    action('listHmiDevices');
});

document.getElementById('btn-compile-hmi').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    setStatus('hmi-compile-status', 'Compiling...', 'busy');
    action('compileHmi');
});

document.getElementById('btn-extract-hmi').addEventListener('click', () => {
    const device = document.getElementById('hmi-device-select').value;
    if (!device) { appendConsole('Select an HMI device first.'); return; }
    clearConsole();
    setProgress(true);
    action('extractHmi', { device });
});

document.getElementById('btn-gen-hmi-report').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    action('genHmiReport');
});

document.getElementById('btn-view-hmi-report').addEventListener('click', () => {
    switchTab('report');
    vscode.postMessage({ type: 'switchTab', tab: 'report' });
});

// ── Report Viewer buttons ──────────────────────────────────────────────────
document.getElementById('btn-refresh-reports').addEventListener('click', () => {
    action('refreshReports');
});

document.getElementById('report-select').addEventListener('change', (e) => {
    action('loadReport', { name: e.target.value });
});

document.getElementById('btn-open-editor').addEventListener('click', () => {
    const name = document.getElementById('report-select').value;
    if (name) { action('openInEditor', { name }); }
});

document.getElementById('btn-gen-claudemd').addEventListener('click', () => {
    clearConsole();
    setProgress(true);
    action('genClaudeMd');
});

document.getElementById('btn-export-bundle').addEventListener('click', () => {
    action('exportBundle');
});

// ── Message handler (from extension) ───────────────────────────────────────
window.addEventListener('message', (event) => {
    const msg = event.data;

    switch (msg.type) {
        case 'console':
            appendConsole(msg.text);
            break;

        case 'clearConsole':
            clearConsole();
            break;

        case 'progress':
            setProgress(msg.active);
            break;

        case 'devices': {
            // Populate PLC dropdown
            const plcSel = document.getElementById('plc-device-select');
            plcSel.innerHTML = '';
            if (msg.plc.length === 0) {
                plcSel.innerHTML = '<option value="">-- no PLC found --</option>';
            } else {
                msg.plc.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d.device;
                    opt.textContent = `[PLC] ${d.name}  (${d.device})`;
                    plcSel.appendChild(opt);
                });
            }
            // Populate HMI dropdown
            const hmiSel = document.getElementById('hmi-device-select');
            hmiSel.innerHTML = '';
            if (msg.hmi.length === 0) {
                hmiSel.innerHTML = '<option value="">-- no HMI found --</option>';
            } else {
                msg.hmi.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d.device;
                    opt.textContent = `[HMI] ${d.name}  (${d.device})`;
                    hmiSel.appendChild(opt);
                });
            }
            break;
        }

        case 'compileStatus':
            setStatus(msg.id, msg.text, msg.cls);
            break;

        case 'reports': {
            const sel = document.getElementById('report-select');
            sel.innerHTML = '';
            if (msg.files.length === 0) {
                sel.innerHTML = '<option value="">-- no reports --</option>';
            } else {
                msg.files.forEach(f => {
                    const opt = document.createElement('option');
                    opt.value = f.name;
                    opt.textContent = f.name;
                    sel.appendChild(opt);
                });
            }
            break;
        }

        case 'reportContent':
            document.getElementById('report-content').textContent = msg.content;
            break;

        case 'plcOutputPath':
            document.getElementById('plc-output-path').value = msg.path;
            break;

        case 'switchTab':
            switchTab(msg.tab);
            break;
    }
});
