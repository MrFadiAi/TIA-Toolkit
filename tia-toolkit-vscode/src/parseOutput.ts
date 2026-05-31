export interface DeviceEntry {
    device: string;
    name: string;
}

export interface ParsedDevices {
    plc: DeviceEntry[];
    hmi: DeviceEntry[];
}

export function parseDeviceList(text: string): ParsedDevices {
    const plc: DeviceEntry[] = [];
    const hmi: DeviceEntry[] = [];
    let cur: string | null = null;

    for (const raw of text.split(/\r?\n/)) {
        const line = raw.trim();
        const devMatch = line.match(/^Device:\s+(.+)$/);
        if (devMatch) {
            cur = devMatch[1].trim();
        }
        const typeMatch = line.match(/^->\s*\[(PLC|HMI)\]\s+(.+)$/);
        if (typeMatch && cur) {
            const entry: DeviceEntry = { device: cur, name: typeMatch[2].trim() };
            if (typeMatch[1] === 'PLC') {
                plc.push(entry);
            } else {
                hmi.push(entry);
            }
        }
    }

    return { plc, hmi };
}

export function deviceFromLabel(label: string): string {
    const m = label.match(/\((.+)\)\s*$/);
    return m ? m[1].trim() : label;
}

export function deviceLabel(entry: DeviceEntry, type: 'PLC' | 'HMI'): string {
    return `[${type}] ${entry.name}  (${entry.device})`;
}

export interface ReportEntry {
    name: string;
    fullPath: string;
}

export function scanReports(docOutput: string, mode: string = 'md'): ReportEntry[] {
    const fs = require('fs');
    const path = require('path');
    const results: ReportEntry[] = [];

    function walk(dir: string, base: string, extension: string) {
        if (!fs.existsSync(dir)) { return; }
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                walk(full, path.join(base, entry.name), extension);
            } else if (entry.name.endsWith(extension)) {
                results.push({ name: path.join(base, entry.name), fullPath: full });
            }
        }
    }

    // MD sources (Program_Blocks, hmi_screens, analysis, CLAUDE.md)
    if (mode === 'md' || mode === 'both') {
        walk(path.join(docOutput, 'hmi_screens'), 'hmi_screens', '.md');
        walk(path.join(docOutput, 'Program_Blocks'), 'Program_Blocks', '.md');
        walk(path.join(docOutput, 'analysis'), 'analysis', '.md');

        const claudeMd = path.join(docOutput, 'CLAUDE.md');
        if (fs.existsSync(claudeMd)) {
            results.push({ name: 'CLAUDE.md', fullPath: claudeMd });
        }
    }

    // XML sources (raw TIA Portal exports)
    if (mode === 'xml' || mode === 'both') {
        walk(path.join(docOutput, 'DATA_Program blocks'), 'DATA_Program blocks', '.xml');
    }

    results.sort((a, b) => a.name.localeCompare(b.name));
    return results;
}
