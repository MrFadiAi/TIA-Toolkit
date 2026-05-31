import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execSync } from 'child_process';

export interface ToolkitConfig {
    toolkitPath: string;
    pythonPath: string;
    autoSync: boolean;
    srcDir: string;
    docOutput: string;
    plcDataBlocks: string;
    workspaceDocOutput: string;
}

/** Cached Python resolution across getConfig() calls */
let cachedPythonPath: string | undefined;

/**
 * Find a working Python executable.
 * Tries in order: user config → python → py → python3.
 * Probes each by running `python --version` to verify it actually works.
 */
function resolvePython(userSetting: string): string {
    const candidates = [userSetting, 'python', 'py', 'python3']
        .filter((v, i, a) => a.indexOf(v) === i);  // deduplicate

    for (const candidate of candidates) {
        try {
            execSync(`${candidate} --version`, {
                stdio: 'pipe',
                timeout: 5000,
                windowsHide: true,
            });
            return candidate;
        } catch {
            // not found or broken, try next
        }
    }

    // Nothing worked — return the user setting and let the command fail
    // with a clear error message the user can act on
    return userSetting;
}

export function getConfig(): ToolkitConfig | undefined {
    const cfg = vscode.workspace.getConfiguration('tiaToolkit');
    const toolkitPath = cfg.get<string>('toolkitPath', '').trim();
    const userPython = cfg.get<string>('pythonPath', 'python');
    const autoSync = cfg.get<boolean>('autoSync', true);

    if (!toolkitPath) {
        vscode.window.showErrorMessage(
            'TIA Toolkit path not configured. Set tiaToolkit.toolkitPath in Settings.'
        );
        return undefined;
    }

    if (!fs.existsSync(toolkitPath)) {
        vscode.window.showErrorMessage(
            `TIA Toolkit path does not exist: ${toolkitPath}`
        );
        return undefined;
    }

    // Resolve Python once per session (or until config changes)
    if (!cachedPythonPath) {
        cachedPythonPath = resolvePython(userPython);
    }
    const pythonPath = cachedPythonPath;

    const srcDir = path.join(toolkitPath, 'src');
    const docOutput = path.join(toolkitPath, 'Doc_OUTPUT');
    const plcDataBlocks = path.join(docOutput, 'DATA_Program blocks');

    const wsFolders = vscode.workspace.workspaceFolders;
    const workspaceDocOutput = wsFolders?.length
        ? path.join(wsFolders[0].uri.fsPath, 'Doc_OUTPUT')
        : docOutput;

    return {
        toolkitPath,
        pythonPath,
        autoSync,
        srcDir,
        docOutput,
        plcDataBlocks,
        workspaceDocOutput,
    };
}

export function getExportExe(srcDir: string, version: string): string {
    const name = version === 'V18-V19'
        ? 'tia_export_blocks_v18.exe'
        : 'tia_export_blocks.exe';
    return path.join(srcDir, name);
}

export function getExtractExe(srcDir: string, version: string): string {
    const name = version === 'V18-V19'
        ? 'tia_extract_v18.exe'
        : 'tia_extract.exe';
    return path.join(srcDir, name);
}

export function getHardwareExe(srcDir: string): string {
    return path.join(srcDir, 'tia_extract_hardware.exe');
}

export function getHardwareCompileCommand(srcDir: string, version: string): string[] {
    const csc = 'C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe';
    const out = path.join(srcDir, 'tia_extract_hardware.exe');
    const cs = path.join(srcDir, 'tia_extract_hardware.cs');

    if (version === 'V18-V19') {
        const dll = 'C:\\Program Files\\Siemens\\Automation\\Portal V18\\PublicAPI\\V18\\Siemens.Engineering.dll';
        return [csc, `/reference:${dll}`, `/out:${out}`, cs];
    } else {
        const base = 'C:\\Program Files\\Siemens\\Automation\\Portal V21\\PublicAPI\\V21\\net48';
        return [csc,
            `/reference:${base}\\Siemens.Engineering.Base.dll`,
            `/reference:${base}\\Siemens.Engineering.Step7.dll`,
            `/out:${out}`, cs];
    }
}

export function getCompileCommand(
    srcDir: string, version: string, target: 'plc' | 'hmi'
): string[] {
    const csc = 'C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe';

    if (version === 'V18-V19') {
        const dll = 'C:\\Program Files\\Siemens\\Automation\\Portal V18\\PublicAPI\\V18\\Siemens.Engineering.dll';
        if (target === 'plc') {
            return [csc, `/reference:${dll}`, `/out:${path.join(srcDir, 'tia_export_blocks_v18.exe')}`,
                path.join(srcDir, 'tia_export_blocks.cs')];
        } else {
            return [csc, `/reference:${dll}`, `/out:${path.join(srcDir, 'tia_extract_v18.exe')}`,
                path.join(srcDir, 'tia_extract.cs')];
        }
    } else {
        const base = 'C:\\Program Files\\Siemens\\Automation\\Portal V21\\PublicAPI\\V21\\net48';
        if (target === 'plc') {
            return [csc,
                `/reference:${base}\\Siemens.Engineering.Base.dll`,
                `/reference:${base}\\Siemens.Engineering.Step7.dll`,
                `/out:${path.join(srcDir, 'tia_export_blocks.exe')}`,
                path.join(srcDir, 'tia_export_blocks.cs')];
        } else {
            return [csc,
                `/reference:${base}\\Siemens.Engineering.Base.dll`,
                `/reference:${base}\\Siemens.Engineering.WinCCUnified.dll`,
                `/reference:${base}\\Siemens.Engineering.Step7.dll`,
                `/out:${path.join(srcDir, 'tia_extract.exe')}`,
                path.join(srcDir, 'tia_extract.cs')];
        }
    }
}
