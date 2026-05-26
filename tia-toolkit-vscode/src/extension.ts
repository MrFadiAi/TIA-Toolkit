import * as vscode from 'vscode';
import { ToolkitViewProvider } from './toolkitPanel';

export function activate(context: vscode.ExtensionContext): void {
    const provider = new ToolkitViewProvider(context.extensionUri);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            ToolkitViewProvider.viewType,
            provider
        )
    );

    // Keep the command for keyboard shortcut access
    context.subscriptions.push(
        vscode.commands.registerCommand('tiaToolkit.open', () => {
            vscode.commands.executeCommand('workbench.view.extension.tia-toolkit-sidebar');
        })
    );
}

export function deactivate(): void {
    // Provider disposes via subscriptions
}
