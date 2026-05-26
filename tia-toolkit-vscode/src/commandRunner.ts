import { spawn, ChildProcess } from 'child_process';

export interface CommandStep {
    cmd: string[];
    cwd?: string;
    label?: string;
}

export type OutputCallback = (text: string) => void;

export class CommandRunner {
    private running = false;
    private proc: ChildProcess | null = null;

    isRunning(): boolean {
        return this.running;
    }

    cancel(): void {
        if (this.proc) {
            this.proc.kill();
            this.proc = null;
        }
    }

    async runSingle(
        cmd: string[],
        cwd: string,
        onOutput: OutputCallback
    ): Promise<{ rc: number; output: string }> {
        return new Promise((resolve) => {
            const proc = spawn(cmd[0], cmd.slice(1), {
                cwd,
                env: process.env,
                stdio: ['ignore', 'pipe', 'pipe'],
                windowsHide: true,
            });
            this.proc = proc;

            let output = '';
            proc.stdout.on('data', (data: Buffer) => {
                const text = data.toString();
                output += text;
                for (const line of text.split('\n')) {
                    const trimmed = line.trimEnd();
                    if (trimmed) {
                        onOutput(trimmed);
                    }
                }
            });

            proc.stderr.on('data', (data: Buffer) => {
                const text = data.toString();
                output += text;
                for (const line of text.split('\n')) {
                    const trimmed = line.trimEnd();
                    if (trimmed) {
                        onOutput(trimmed);
                    }
                }
            });

            proc.on('close', (code) => {
                this.proc = null;
                resolve({ rc: code ?? -1, output });
            });

            proc.on('error', (err) => {
                this.proc = null;
                onOutput(`Error: ${err.message}`);
                resolve({ rc: -1, output: err.message });
            });
        });
    }

    async runChain(
        steps: CommandStep[],
        cwd: string,
        onOutput: OutputCallback,
        onStepStart?: (index: number, label: string) => void
    ): Promise<{ rc: number; output: string }> {
        if (this.running) {
            onOutput('Another command is still running. Please wait.');
            return { rc: -1, output: '' };
        }

        this.running = true;
        let combinedOutput = '';

        try {
            for (let i = 0; i < steps.length; i++) {
                const step = steps[i];
                const label = step.label || step.cmd[0];

                if (onStepStart) {
                    onStepStart(i, label);
                }

                const result = await this.runSingle(
                    step.cmd,
                    step.cwd || cwd,
                    onOutput
                );
                combinedOutput += result.output;

                if (result.rc !== 0) {
                    onOutput(`Step failed (exit code ${result.rc}): ${label}`);
                    this.running = false;
                    return { rc: result.rc, output: combinedOutput };
                }
            }

            this.running = false;
            return { rc: 0, output: combinedOutput };
        } catch (err: any) {
            onOutput(`Chain error: ${err.message}`);
            this.running = false;
            return { rc: -1, output: combinedOutput };
        }
    }
}
