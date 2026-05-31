import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { getConfig, getExportExe, getExtractExe, getCompileCommand, getHardwareExe, getHardwareCompileCommand, ToolkitConfig } from './config';
import { CommandRunner } from './commandRunner';
import { parseDeviceList, scanReports } from './parseOutput';
import { syncToWorkspace } from './outputSync';
import { getWebviewHtml } from './webviewContent';

export class ToolkitViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'tiaToolkit.sidebar';

    private view?: vscode.WebviewView;
    private readonly runner = new CommandRunner();
    private config: ToolkitConfig;
    private tiaVersion = 'V21+';
    private resolved = false;
    private disposables: vscode.Disposable[] = [];

    constructor(private readonly extensionUri: vscode.Uri) {
        const cfg = getConfig();
        if (!cfg) {
            throw new Error('Toolkit not configured. Set tiaToolkit.toolkitPath in Settings.');
        }
        this.config = cfg;
    }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ): void {
        this.view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
        };

        webviewView.webview.html = getWebviewHtml();

        // Send default PLC output path to webview (matches gui.py behavior)
        this.postMessage({ type: 'plcOutputPath', path: this.config.plcDataBlocks });

        webviewView.webview.onDidReceiveMessage(
            (msg) => this.handleMessage(msg),
            null,
            this.disposables
        );
    }

    private refreshConfig(): void {
        const cfg = getConfig();
        if (cfg) {
            this.config = cfg;
        }
    }

    private postMessage(msg: any): void {
        this.view?.webview.postMessage(msg);
    }

    private consoleLog(text: string): void {
        this.postMessage({ type: 'console', text });
    }

    private setProgress(active: boolean): void {
        this.postMessage({ type: 'progress', active });
    }

    // ── Message dispatch ────────────────────────────────────────────────

    private async handleMessage(msg: any): Promise<void> {
        this.refreshConfig();

        if (msg.version) {
            this.tiaVersion = msg.version;
        }

        switch (msg.type) {
            case 'switchTab':
                break;
            case 'setVersion':
                this.tiaVersion = msg.version;
                this.consoleLog(`TIA version set to ${msg.version}`);
                break;
            case 'listDevices':
                await this.listDevices();
                break;
            case 'compilePlc':
                await this.compilePlc();
                break;
            case 'browsePlcOutput':
                await this.browsePlcOutput();
                break;
            case 'exportBlocks':
                await this.exportBlocks(msg.device, msg.outputPath);
                break;
            case 'parseBlocks':
                await this.parseBlocks(msg.outputPath);
                break;
            case 'genPlcReport':
                await this.runSingle(['plc_report.py']);
                break;
            case 'listHmiDevices':
                await this.listDevices(true);
                break;
            case 'compileHmi':
                await this.compileHmi();
                break;
            case 'extractHmi':
                await this.extractHmi(msg.device);
                break;
            case 'genHmiReport':
                await this.runSingle(['hmi_report.py']);
                break;
            case 'refreshReports':
                this.refreshReports();
                break;
            case 'loadReport':
                this.loadReport(msg.name);
                break;
            case 'openInEditor':
                this.openInEditor(msg.name);
                break;
            case 'genClaudeMd':
                await this.runSingle(['generate_claudemd.py'], async () => {
                    this.refreshReports();
                    // Auto-load CLAUDE.md in report viewer (matches gui.py behavior)
                    this.postMessage({ type: 'switchTab', tab: 'report' });
                    this.postMessage({ type: 'selectReport', name: 'CLAUDE.md' });
                    this.loadReport('CLAUDE.md');
                });
                break;
            case 'exportBundle':
                await this.doExportBundle();
                break;
            case 'crossReference':
                await this.runCrossReference(msg.query, msg.queryType);
                break;
            case 'deadCode':
                await this.runSingle(['dead_code_analysis.py']);
                break;
            case 'traceabilityMatrix':
                await this.runSingle(['traceability_matrix.py']);
                break;
            case 'dependencyGraph':
                await this.runSingle(['dependency_graph.py']);
                break;
            case 'compileHardware':
                await this.compileHardware();
                break;
            case 'extractHardware':
                await this.extractHardware();
                break;
            case 'runFullPipeline':
                await this.runFullPipeline(msg.plcDevice, msg.hmiDevice);
                break;
        }
    }

    // ── Command implementations ─────────────────────────────────────────

    private async listDevices(hmiOnly = false): Promise<void> {
        const exe = getExportExe(this.config.srcDir, this.tiaVersion);
        const result = await this.runner.runSingle(
            [exe, '--list'],
            this.config.srcDir,
            (text) => this.consoleLog(text)
        );

        this.setProgress(false);

        if (result.rc === 0) {
            const { plc, hmi } = parseDeviceList(result.output);
            this.postMessage({ type: 'devices', plc, hmi });
            this.consoleLog(`Found ${plc.length} PLC(s), ${hmi.length} HMI(s)`);
        } else {
            this.consoleLog('Failed to list devices.');
        }
    }

    private async compilePlc(): Promise<void> {
        const cmd = getCompileCommand(this.config.srcDir, this.tiaVersion, 'plc');
        const result = await this.runner.runSingle(
            cmd, this.config.srcDir,
            (text) => this.consoleLog(text)
        );

        this.setProgress(false);
        if (result.rc === 0) {
            this.postMessage({ type: 'compileStatus', id: 'plc-compile-status', text: 'OK', cls: 'ok' });
            this.consoleLog('Compile successful.');
        } else {
            this.postMessage({ type: 'compileStatus', id: 'plc-compile-status', text: 'FAILED', cls: 'fail' });
            this.consoleLog('Compile failed. Check Siemens DLL paths.');
        }
    }

    private async compileHmi(): Promise<void> {
        const cmd = getCompileCommand(this.config.srcDir, this.tiaVersion, 'hmi');
        const result = await this.runner.runSingle(
            cmd, this.config.srcDir,
            (text) => this.consoleLog(text)
        );

        this.setProgress(false);
        if (result.rc === 0) {
            this.postMessage({ type: 'compileStatus', id: 'hmi-compile-status', text: 'OK', cls: 'ok' });
            this.consoleLog('Compile successful.');
        } else {
            this.postMessage({ type: 'compileStatus', id: 'hmi-compile-status', text: 'FAILED', cls: 'fail' });
            this.consoleLog('Compile failed. Check Siemens DLL paths.');
        }
    }

    private async browsePlcOutput(): Promise<void> {
        const result = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            title: 'Select Output Folder',
            defaultUri: vscode.Uri.file(this.config.plcDataBlocks),
        });
        if (result && result.length > 0) {
            this.postMessage({ type: 'plcOutputPath', path: result[0].fsPath });
        }
    }

    private async exportBlocks(device: string, outputPath: string): Promise<void> {
        this.cleanPlcOutput();
        const exe = getExportExe(this.config.srcDir, this.tiaVersion);
        const outPath = outputPath || this.config.plcDataBlocks;

        await this.runner.runChain([
            { cmd: [exe, outPath, device], label: 'Export blocks from TIA Portal' },
            { cmd: [this.config.pythonPath, path.join(this.config.srcDir, 'extract_plc_full.py'), outPath, '--verbose', '--plc-name', device], label: 'Parse exported blocks' },
            { cmd: [this.config.pythonPath, path.join(this.config.srcDir, 'plc_report.py')], label: 'Generate PLC reports' },
        ], this.config.srcDir, (text) => this.consoleLog(text),
        (_i, label) => this.consoleLog(`\n── ${label} ──`));

        this.setProgress(false);
        await this.maybeSync();
    }

    private async parseBlocks(outputPath: string): Promise<void> {
        this.cleanPlcOutput();
        const outPath = outputPath || this.config.plcDataBlocks;

        await this.runner.runChain([
            { cmd: [this.config.pythonPath, path.join(this.config.srcDir, 'extract_plc_full.py'), outPath, '--verbose'], label: 'Parse blocks' },
            { cmd: [this.config.pythonPath, path.join(this.config.srcDir, 'plc_report.py')], label: 'Generate reports' },
        ], this.config.srcDir, (text) => this.consoleLog(text),
        (_i, label) => this.consoleLog(`\n── ${label} ──`));

        this.setProgress(false);
        await this.maybeSync();
    }

    private async extractHmi(device: string): Promise<void> {
        this.cleanHmiOutput();
        const exe = getExtractExe(this.config.srcDir, this.tiaVersion);
        const jsonPath = path.join(this.config.docOutput, '.hmi_online_data.json');

        // Full HMI pipeline: online extract → offline extract → merge → report
        await this.runner.runChain([
            { cmd: [exe, jsonPath, device], label: 'Extract HMI online data from TIA Portal' },
            { cmd: [this.config.pythonPath, path.join(this.config.srcDir, 'hmi_report.py')], label: 'Generate HMI reports' },
        ], this.config.srcDir, (text) => this.consoleLog(text),
        (_i, label) => this.consoleLog(`\n── ${label} ──`));

        this.setProgress(false);
        await this.maybeSync();
    }

    private async runSingle(
        scriptParts: string[],
        onComplete?: () => Promise<void>
    ): Promise<void> {
        const cmd = [this.config.pythonPath, ...scriptParts.map(p => path.join(this.config.srcDir, p))];
        const result = await this.runner.runSingle(
            cmd, this.config.srcDir,
            (text) => this.consoleLog(text)
        );

        this.setProgress(false);
        if (result.rc === 0) {
            this.consoleLog('Done.');
        } else {
            this.consoleLog(`Failed (exit code ${result.rc}).`);
        }

        await this.maybeSync();
        if (onComplete) { await onComplete(); }
    }

    // ── Report viewer ───────────────────────────────────────────────────

    private refreshReports(): void {
        const reports = scanReports(this.config.docOutput);
        const wsReports = this.config.autoSync
            ? scanReports(this.config.workspaceDocOutput)
            : [];

        const files = wsReports.length > 0 ? wsReports : reports;
        this.postMessage({
            type: 'reports',
            files: files.map(r => ({ name: r.name, fullPath: r.fullPath })),
        });
    }

    private loadReport(name: string): void {
        if (!name) { return; }

        const locations = [
            this.config.workspaceDocOutput,
            this.config.docOutput,
        ];

        for (const base of locations) {
            const fullPath = path.join(base, name);
            if (fs.existsSync(fullPath)) {
                try {
                    const content = fs.readFileSync(fullPath, 'utf-8');
                    this.postMessage({ type: 'reportContent', content });
                    const lines = content.split('\n').length;
                    this.consoleLog(`Loaded ${name} (${lines} lines)`);
                    return;
                } catch (err: any) {
                    this.consoleLog(`Error reading ${name}: ${err.message}`);
                    return;
                }
            }
        }

        this.consoleLog(`Report not found: ${name}`);
    }

    private openInEditor(name: string): void {
        if (!name) { return; }

        const locations = [
            this.config.workspaceDocOutput,
            this.config.docOutput,
        ];

        for (const base of locations) {
            const fullPath = path.join(base, name);
            if (fs.existsSync(fullPath)) {
                vscode.workspace.openTextDocument(vscode.Uri.file(fullPath)).then(doc => {
                    vscode.window.showTextDocument(doc);
                });
                return;
            }
        }
    }

    // ── Output sync ─────────────────────────────────────────────────────

    private async maybeSync(): Promise<void> {
        if (!this.config.autoSync) { return; }

        const result = syncToWorkspace(this.config.docOutput, this.config.workspaceDocOutput);
        // Always log sync result (including diagnostics and skip messages)
        if (result.details.length > 0) {
            this.consoleLog(`Sync: ${result.copied} files`);
            for (const detail of result.details) {
                this.consoleLog(`  ${detail}`);
            }
        }
    }

    private async doExportBundle(): Promise<void> {
        const result = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            title: 'Select Export Target Folder',
        });

        if (!result || result.length === 0) { return; }

        const target = result[0].fsPath;
        const syncResult = syncToWorkspace(this.config.docOutput, target);

        if (syncResult.copied > 0) {
            vscode.window.showInformationMessage(
                `Exported ${syncResult.copied} files to ${path.basename(target)}`
            );
            for (const detail of syncResult.details) {
                this.consoleLog(`  ${detail}`);
            }
            this.consoleLog(`Export complete: ${syncResult.copied} files to ${target}`);
        } else {
            this.consoleLog('Nothing to export. Run extractions first.');
        }
    }

    // ── Analysis handlers ─────────────────────────────────────────────

    private async runCrossReference(query: string, queryType: string): Promise<void> {
        const cmd = [this.config.pythonPath, path.join(this.config.srcDir, 'cross_reference.py'), query];
        if (queryType && queryType !== 'auto') {
            cmd.push(`--${queryType}`);
        }
        const result = await this.runner.runSingle(
            cmd, this.config.srcDir,
            (text) => this.consoleLog(text)
        );
        this.setProgress(false);
        if (result.rc === 0) { this.consoleLog('Done.'); }
        else { this.consoleLog(`Search failed (exit code ${result.rc}).`); }
        await this.maybeSync();
    }

    private async compileHardware(): Promise<void> {
        const cmd = getHardwareCompileCommand(this.config.srcDir, this.tiaVersion);
        const result = await this.runner.runSingle(
            cmd, this.config.srcDir,
            (text) => this.consoleLog(text)
        );
        this.setProgress(false);
        if (result.rc === 0) {
            this.postMessage({ type: 'compileStatus', id: 'hw-compile-status', text: 'OK', cls: 'ok' });
            this.consoleLog('Compile successful.');
        } else {
            this.postMessage({ type: 'compileStatus', id: 'hw-compile-status', text: 'FAILED', cls: 'fail' });
            this.consoleLog('Compile failed.');
        }
    }

    private async extractHardware(): Promise<void> {
        const hwExe = getHardwareExe(this.config.srcDir);
        if (!fs.existsSync(hwExe)) {
            this.consoleLog('Hardware extractor not found. Compile it first (Step: Compile).');
            this.setProgress(false);
            return;
        }
        const jsonPath = path.join(this.config.docOutput, '.hardware.json');

        await this.runner.runChain([
            { cmd: [hwExe, jsonPath], label: 'Extract hardware' },
            { cmd: [this.config.pythonPath, path.join(this.config.srcDir, 'hardware_report.py')], label: 'Generate report' },
        ], this.config.srcDir, (text) => this.consoleLog(text),
        (_i, label) => this.consoleLog(`\n── ${label} ──`));

        this.setProgress(false);
        await this.maybeSync();
    }

    // ── Full Pipeline ──────────────────────────────────────────────────

    private async runFullPipeline(plcDevice: string, hmiDevice: string): Promise<void> {
        this.cleanAllOutput();
        const steps: { label: string; fn: () => Promise<void> }[] = [];

        // 1. Export PLC blocks
        if (plcDevice) {
            steps.push({ label: 'Export PLC blocks', fn: async () => {
                await this.exportBlocks(plcDevice, '');
            }});
        }

        // 2. Extract HMI data
        if (hmiDevice) {
            steps.push({ label: 'Extract HMI data', fn: async () => {
                await this.extractHmi(hmiDevice);
            }});
        }

        // 3-7. Analysis scripts
        const analysisScripts = [
            { label: 'Dead code analysis', script: 'dead_code_analysis.py' },
            { label: 'Traceability matrix', script: 'traceability_matrix.py' },
            { label: 'Dependency graph', script: 'dependency_graph.py' },
        ];

        for (const a of analysisScripts) {
            steps.push({ label: a.label, fn: async () => {
                const cmd = [this.config.pythonPath, path.join(this.config.srcDir, a.script)];
                const result = await this.runner.runSingle(cmd, this.config.srcDir, (t) => this.consoleLog(t));
                if (result.rc !== 0) { this.consoleLog(`${a.label} failed (exit ${result.rc}).`); }
                await this.maybeSync();
            }});
        }

        // Hardware extraction (only if exe exists — matches gui.py behavior)
        const hwExe = getHardwareExe(this.config.srcDir);
        if (fs.existsSync(hwExe)) {
            steps.push({ label: 'Hardware extraction', fn: async () => {
                await this.extractHardware();
            }});
        } else {
            this.consoleLog('Hardware extractor not found — skipping hardware step.');
        }

        // Generate CLAUDE.md
        steps.push({ label: 'Generate CLAUDE.md', fn: async () => {
            await this.runSingle(['generate_claudemd.py'], async () => {
                this.refreshReports();
            });
        }});

        // Run all steps sequentially
        const total = steps.length;
        for (let i = 0; i < steps.length; i++) {
            this.consoleLog(`\n[${ i + 1}/${total}] ${steps[i].label}...`);
            try {
                await steps[i].fn();
            } catch (err: any) {
                this.consoleLog(`Error in ${steps[i].label}: ${err.message}`);
            }
        }

        this.setProgress(false);
        this.consoleLog(`\nPipeline complete (${total} steps).`);
        await this.maybeSync();
    }

    // ── Cleanup ──────────────────────────────────────────────────────────

    private cleanPlcOutput(): void {
        const doc = this.config.docOutput;
        const dirs = ['DATA_Program blocks', 'Program_Blocks'];
        const files = ['.plc_cache.json'];
        for (const d of dirs) {
            const p = path.join(doc, d);
            if (fs.existsSync(p)) { fs.rmSync(p, { recursive: true, force: true }); }
        }
        for (const f of files) {
            const p = path.join(doc, f);
            if (fs.existsSync(p)) { fs.unlinkSync(p); }
        }
        this.consoleLog('Cleaned old PLC output.');
    }

    private cleanHmiOutput(): void {
        const doc = this.config.docOutput;
        const dirs = ['hmi_screens'];
        const files = ['.hmi_online_data.json', '.hmi_offline_data.json', '.hmi_merged.json'];
        for (const d of dirs) {
            const p = path.join(doc, d);
            if (fs.existsSync(p)) { fs.rmSync(p, { recursive: true, force: true }); }
        }
        for (const f of files) {
            const p = path.join(doc, f);
            if (fs.existsSync(p)) { fs.unlinkSync(p); }
        }
        this.consoleLog('Cleaned old HMI output.');
    }

    private cleanAllOutput(): void {
        this.cleanPlcOutput();
        this.cleanHmiOutput();
        // Also clean analysis and hardware
        const doc = this.config.docOutput;
        const dirs = ['analysis'];
        const files = ['.hardware.json'];
        for (const d of dirs) {
            const p = path.join(doc, d);
            if (fs.existsSync(p)) { fs.rmSync(p, { recursive: true, force: true }); }
        }
        for (const f of files) {
            const p = path.join(doc, f);
            if (fs.existsSync(p)) { fs.unlinkSync(p); }
        }
        this.consoleLog('Cleaned all old output.');
    }

    public dispose(): void {
        this.runner.cancel();
        for (const d of this.disposables) { d.dispose(); }
    }
}
