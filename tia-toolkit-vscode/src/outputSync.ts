import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

/**
 * Recursively copy a directory, replacing existing content.
 */
function copyDirRecursive(src: string, dst: string): number {
    if (!fs.existsSync(src)) { return 0; }
    if (fs.existsSync(dst)) {
        fs.rmSync(dst, { recursive: true, force: true });
    }
    fs.mkdirSync(dst, { recursive: true });
    let count = 0;

    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
        const srcPath = path.join(src, entry.name);
        const dstPath = path.join(dst, entry.name);
        if (entry.isDirectory()) {
            count += copyDirRecursive(srcPath, dstPath);
        } else {
            fs.copyFileSync(srcPath, dstPath);
            count++;
        }
    }
    return count;
}

export interface SyncResult {
    copied: number;
    details: string[];
}

/**
 * Copy Doc_OUTPUT from toolkit to workspace, mirroring the Export Bundle logic.
 */
export function syncToWorkspace(toolkitDocOutput: string, workspaceDocOutput: string): SyncResult {
    const details: string[] = [];
    let copied = 0;

    fs.mkdirSync(workspaceDocOutput, { recursive: true });

    // Program_Blocks/
    const srcPb = path.join(toolkitDocOutput, 'Program_Blocks');
    const dstPb = path.join(workspaceDocOutput, 'Program_Blocks');
    if (fs.existsSync(srcPb)) {
        const n = copyDirRecursive(srcPb, dstPb);
        details.push(`Program_Blocks/ — ${n} files`);
        copied += n;
    }

    // hmi_screens/
    const srcHmi = path.join(toolkitDocOutput, 'hmi_screens');
    const dstHmi = path.join(workspaceDocOutput, 'hmi_screens');
    if (fs.existsSync(srcHmi)) {
        const n = copyDirRecursive(srcHmi, dstHmi);
        details.push(`hmi_screens/ — ${n} files`);
        copied += n;
    }

    // CLAUDE.md
    const srcClaude = path.join(toolkitDocOutput, 'CLAUDE.md');
    if (fs.existsSync(srcClaude)) {
        fs.copyFileSync(srcClaude, path.join(workspaceDocOutput, 'CLAUDE.md'));
        details.push('CLAUDE.md');
        copied++;
    }

    // JSON data files (rename dot-prefix for visibility)
    const jsonFiles: Record<string, string> = {
        '.plc_cache.json': 'plc_cache.json',
        '.hmi_merged.json': 'hmi_merged.json',
        '.hmi_online_data.json': 'hmi_online_data.json',
        'hmi_offline_data.json': 'hmi_offline_data.json',
    };
    for (const [srcName, dstName] of Object.entries(jsonFiles)) {
        const src = path.join(toolkitDocOutput, srcName);
        if (fs.existsSync(src)) {
            fs.copyFileSync(src, path.join(workspaceDocOutput, dstName));
            details.push(dstName);
            copied++;
        }
    }

    return { copied, details };
}
