import * as vscode from 'vscode';
import { spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';
import { randomUUID, randomBytes } from 'node:crypto';

interface Renderer { id: string; name: string; extensions: string[]; source: string }
interface Artifact { kind: 'image' | 'html'; entry: string; mimeType: string; files: string[] }
interface Response {
    protocolVersion: number; requestId: string; status: 'ok' | 'error';
    error?: { code: string; message: string; traceback?: string };
    renderers?: Renderer[]; diagnostics?: { source: string; message: string; traceback?: string }[];
    artifact?: Artifact;
}
interface View {
    panel: vscode.WebviewPanel; uri: vscode.Uri; abort?: AbortController; generation: number;
    disposed: boolean; currentDirectory?: string; hasResult: boolean;
}
let output: vscode.OutputChannel;
const views = new Map<string, View>();
const running = new Set<AbortController>();
const escapeHtml = (value: string) => value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const config = (uri: vscode.Uri) => vscode.workspace.getConfiguration('datapeek', uri);
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const remove = async (directory?: string) => { if (directory) { await fs.rm(directory, { recursive: true, force: true, maxRetries: 3 }).catch(e => output.appendLine(`Cleanup: ${e}`)); } };

function checkTrust() {
    if (!vscode.workspace.isTrusted) { throw new Error('Trust this workspace before executing Python renderers.'); }
}
function checkFileUri(uri: vscode.Uri) {
    if (uri.scheme !== 'file' && !(uri.scheme === 'vscode-remote' && vscode.env.remoteName)) {
        throw new Error(`Unsupported filesystem: ${uri.scheme}. Open a local or Remote SSH file.`);
    }
}
function seconds(uri: vscode.Uri, key: string, fallback: number, max: number): number {
    const value = config(uri).get<number>(key, fallback);
    return Number.isFinite(value) ? Math.max(1, Math.min(max, value)) : fallback;
}

async function execute(executable: string, args: string[], cwd: string, timeout: number, signal: AbortSignal): Promise<string> {
    if (signal.aborted) { throw new Error('CANCELLED'); }
    return new Promise((resolve, reject) => {
        const child = spawn(executable, args, {
            cwd, shell: false, detached: process.platform !== 'win32',
            env: { ...process.env, MPLBACKEND: 'Agg', PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' },
            stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
        });
        let stdout = '', stderr = '', failure: string | undefined;
        let force: NodeJS.Timeout | undefined;
        const kill = (hard: boolean) => {
            if (!child.pid) { return; }
            try {
                if (process.platform === 'win32') {
                    const killer = spawn('taskkill', ['/pid', String(child.pid), '/t', ...(hard ? ['/f'] : [])], { windowsHide: true });
                    killer.on('error', () => child.kill());
                } else { process.kill(-child.pid, hard ? 'SIGKILL' : 'SIGTERM'); }
            } catch { /* already exited */ }
        };
        const stop = (reason: string) => {
            if (failure) { return; }
            failure = reason;
            kill(false);
            force = setTimeout(() => kill(true), 2000);
        };
        const cancel = () => stop('CANCELLED');
        const timer = setTimeout(() => stop(`TIMEOUT after ${timeout / 1000}s`), timeout);
        signal.addEventListener('abort', cancel, { once: true });
        if (signal.aborted) { cancel(); }
        child.stdout.on('data', chunk => { stdout = (stdout + chunk.toString()).slice(-1048576); });
        child.stderr.on('data', chunk => { stderr = (stderr + chunk.toString()).slice(-1048576); });
        const cleanup = () => { clearTimeout(timer); if (force) { clearTimeout(force); } signal.removeEventListener('abort', cancel); };
        child.on('error', error => { cleanup(); reject(error); });
        child.on('close', code => {
            if (failure) { kill(true); }
            cleanup();
            if (stdout.trim()) { output.appendLine(stdout); }
            if (stderr.trim()) { output.appendLine(stderr); }
            if (failure) { reject(new Error(failure)); }
            else if (code !== 0) { reject(new Error(`Python exited with code ${code}. ${stderr.slice(-2000)}`)); }
            else { resolve(stdout); }
        });
    });
}

async function resolvePython(uri: vscode.Uri, signal: AbortSignal): Promise<string> {
    const folder = vscode.workspace.getWorkspaceFolder(uri);
    const cwd = folder?.uri.fsPath ?? path.dirname(uri.fsPath);
    const configured = config(uri).get<string>('pythonPath', '').trim();
    const validate = async (candidate: string) => {
        const result = await execute(candidate, ['-c', 'import sys,json; print(json.dumps({"path":sys.executable,"version":list(sys.version_info[:2])}))'], cwd, 10000, signal);
        const info = JSON.parse(result.trim());
        if (!Array.isArray(info.version) || info.version[0] !== 3 || info.version[1] < 10) { throw new Error('Python 3.10 or newer is required.'); }
        output.appendLine(`Python: ${info.path} (${info.version.join('.')}) | host: ${vscode.env.remoteName ?? 'local'}`);
        return info.path as string;
    };
    if (configured) {
        if (configured.includes('${workspaceFolder}') && !folder) { throw new Error('pythonPath uses ${workspaceFolder}, but the file is outside a workspace.'); }
        const expanded = configured.replaceAll('${workspaceFolder}', folder?.uri.fsPath ?? '');
        if (!path.isAbsolute(expanded)) { throw new Error('datapeek.pythonPath must be an absolute executable path (not a shell command).'); }
        return validate(expanded);
    }
    const pythonExtension = vscode.extensions.getExtension('ms-python.python');
    if (pythonExtension) {
        const api = await pythonExtension.activate();
        if (api?.environments?.getActiveEnvironmentPath) {
            const active = api.environments.getActiveEnvironmentPath(uri);
            if (active?.path) {
                const env = await api.environments.resolveEnvironment(active);
                const executable = env?.executable?.uri?.fsPath;
                if (!executable) { throw new Error('The selected Python environment cannot be resolved. Run DataPeek: Select Python Interpreter.'); }
                return validate(executable);
            }
        }
    }
    if (folder) {
        const candidate = path.join(folder.uri.fsPath, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
        if (await fs.stat(candidate).then(s => s.isFile(), () => false)) { return validate(candidate); }
    }
    for (const candidate of ['python3', 'python']) {
        try { return await validate(candidate); } catch (error) { if (signal.aborted) { throw error; } }
    }
    throw new Error('Python 3.10+ not found. Run DataPeek: Select Python Interpreter.');
}

async function operation(context: vscode.ExtensionContext, executable: string, uri: vscode.Uri, signal: AbortSignal, operationName: 'discover' | 'render', extra = {}): Promise<{ response: Response; directory: string }> {
    checkTrust();
    const folder = vscode.workspace.getWorkspaceFolder(uri);
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'datapeek-'));
    try {
        const requestId = randomUUID();
        const maxBytes = seconds(uri, 'maxArtifactMiB', 32, 256) * 1048576;
        const request = { protocolVersion: 1, requestId, operation: operationName, workspaceRoot: folder?.uri.fsPath ?? null, targetPath: uri.fsPath, limits: { maxArtifactBytes: maxBytes }, ...extra };
        const requestFile = path.join(directory, 'request.json');
        await fs.writeFile(requestFile, JSON.stringify(request), { mode: 0o600 });
        const timeout = operationName === 'discover' ? seconds(uri, 'discoveryTimeoutSeconds', 15, 300) : seconds(uri, 'renderTimeoutSeconds', 60, 3600);
        await execute(executable, [context.asAbsolutePath('python/runner.py'), '--request', requestFile], folder?.uri.fsPath ?? path.dirname(uri.fsPath), timeout * 1000, signal);
        if (signal.aborted) { throw new Error('CANCELLED'); }
        const responseFile = path.join(directory, 'response.json');
        if ((await fs.stat(responseFile)).size > 1048576) { throw new Error('PROTOCOL_ERROR: response too large'); }
        const response: Response = JSON.parse(await fs.readFile(responseFile, 'utf8'));
        if (!object(response) || response.protocolVersion !== 1 || response.requestId !== requestId || !['ok', 'error'].includes(response.status)) { throw new Error('PROTOCOL_ERROR: invalid Python response'); }
        if (response.status === 'error') {
            if (response.error?.traceback) { output.appendLine(response.error.traceback); }
            throw new Error(`${response.error?.code ?? 'RENDER_FAILED'}: ${response.error?.message ?? 'Unknown Python error'}\nPython: ${executable}`);
        }
        if (operationName === 'discover') {
            if (!Array.isArray(response.renderers) || !response.renderers.every(r => object(r) && typeof r.id === 'string' && typeof r.name === 'string' && typeof r.source === 'string' && Array.isArray(r.extensions) && r.extensions.every(e => typeof e === 'string'))) { throw new Error('PROTOCOL_ERROR: invalid renderer list'); }
        } else {
            const artifact = response.artifact;
            if (!artifact || !['image', 'html'].includes(artifact.kind) || typeof artifact.entry !== 'string' || !Array.isArray(artifact.files) || !artifact.files.includes(artifact.entry) || artifact.files.length > 100) { throw new Error('PROTOCOL_ERROR: invalid artifact'); }
            const root = await fs.realpath(directory);
            let total = 0;
            for (const file of artifact.files) {
                if (typeof file !== 'string' || !/^artifacts\/[a-zA-Z0-9_.-]+$/.test(file)) { throw new Error('PROTOCOL_ERROR: unsafe artifact path'); }
                const full = await fs.realpath(path.join(directory, file));
                if (!full.startsWith(root + path.sep) || !(await fs.stat(full)).isFile()) { throw new Error('PROTOCOL_ERROR: artifact escapes output directory'); }
                total += (await fs.stat(full)).size;
            }
            if (total > maxBytes) { throw new Error('OUTPUT_TOO_LARGE'); }
        }
        return { response, directory };
    } catch (error) { await remove(directory); throw error; }
}

function hostUri(file: string, resource: vscode.Uri): vscode.Uri {
    const local = vscode.Uri.file(file);
    return resource.scheme === 'vscode-remote' ? local.with({ scheme: resource.scheme, authority: resource.authority }) : local;
}
function messagePage(message: string): string {
    return `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><style>body{font-family:system-ui;padding:28px;line-height:1.6}pre{white-space:pre-wrap}</style></head><body><h2>DataPeek</h2><pre>${escapeHtml(message)}</pre></body></html>`;
}
async function showArtifact(view: View, artifact: Artifact, directory: string, uri: vscode.Uri, subtitle: string, signal: AbortSignal) {
    const webview = view.panel.webview;
    const nonce = randomBytes(18).toString('hex');
    let html: string;
    if (artifact.kind === 'image') {
        const imageUri = webview.asWebviewUri(hostUri(path.join(directory, artifact.entry), uri));
        html = `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource}; style-src 'unsafe-inline'"><style>body{font-family:system-ui;padding:16px}p{opacity:.7;font-size:12px;overflow-wrap:anywhere}img{max-width:100%;height:auto;background:white}</style></head><body><p>${escapeHtml(subtitle)}</p><img alt="Scientific data preview" src="${imageUri}"></body></html>`;
    } else {
        html = await fs.readFile(path.join(directory, artifact.entry), 'utf8');
        for (const file of artifact.files) {
            html = html.replaceAll(`__DATA_ASSET_${path.basename(file)}__`, webview.asWebviewUri(hostUri(path.join(directory, file), uri)).toString());
        }
        const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; img-src ${webview.cspSource} data: blob:; font-src ${webview.cspSource} data:; worker-src blob:; connect-src 'none';">`;
        if (!html.includes('__DATA_CSP__')) { throw new Error('PROTOCOL_ERROR: missing HTML security template'); }
        html = html.replace('__DATA_CSP__', csp).replaceAll('__DATA_NONCE__', nonce);
    }
    if (signal.aborted || view.disposed) { throw new Error('CANCELLED'); }
    webview.options = { enableScripts: artifact.kind === 'html', localResourceRoots: [hostUri(path.join(directory, 'artifacts'), uri)] };
    webview.html = html;
    view.hasResult = true;
}

async function preview(context: vscode.ExtensionContext, resource?: vscode.Uri) {
    checkTrust();
    let uri = resource ?? [...views.values()].find(view => view.panel.active)?.uri ?? vscode.window.activeTextEditor?.document.uri;
    if (!uri) { uri = (await vscode.window.showOpenDialog({ canSelectMany: false, canSelectFolders: false, title: 'Preview with DataPeek' }))?.[0]; }
    if (!uri) { return; }
    checkFileUri(uri);
    if (!(await fs.stat(uri.fsPath)).isFile()) { throw new Error('Select a file to preview.'); }
    const key = uri.toString();
    let view = views.get(key);
    if (!view) {
        const panel = vscode.window.createWebviewPanel('datapeek', `DataPeek: ${path.basename(uri.fsPath)}`, vscode.ViewColumn.Beside, { enableScripts: false, localResourceRoots: [] });
        view = { panel, uri, disposed: false, generation: 0, hasResult: false };
        views.set(key, view);
        const created = view;
        panel.onDidDispose(() => { created.disposed = true; created.abort?.abort(); views.delete(key); void remove(created.currentDirectory); });
    } else { view.panel.reveal(); view.abort?.abort(); }
    const state = view;
    const generation = ++state.generation;
    const controller = new AbortController();
    state.abort = controller;
    running.add(controller);
    if (!state.hasResult) { state.panel.webview.html = messagePage('Selecting Python and discovering renderers…'); }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'DataPeek', cancellable: true }, async (progress, token) => {
        const cancellation = token.onCancellationRequested(() => controller.abort());
        let renderedDirectory: string | undefined;
        try {
            const executable = await resolvePython(uri!, controller.signal);
            progress.report({ message: 'Discovering Python renderers…' });
            const discovery = await operation(context, executable, uri!, controller.signal, 'discover');
            const all = discovery.response.renderers!;
            for (const diagnostic of discovery.response.diagnostics ?? []) {
                output.appendLine(`${diagnostic.source}: ${diagnostic.traceback ?? diagnostic.message}`);
            }
            if (discovery.response.diagnostics?.length) { void vscode.window.showWarningMessage('Some DataPeek renderers could not be loaded. See the DataPeek output channel.'); }
            await remove(discovery.directory);
            const name = path.basename(uri!.fsPath).toLowerCase();
            const candidates = all.filter(r => r.extensions.some(ext => name.endsWith(ext.toLowerCase())));
            let renderer: Renderer | undefined;
            if (candidates.length === 1) { renderer = candidates[0]; }
            else {
                const choices = candidates.length ? candidates : all;
                const choice = await vscode.window.showQuickPick(choices.map(r => ({ label: r.name, description: r.id, renderer: r })), { title: candidates.length ? 'Select a DataPeek renderer' : 'No matching suffix — select a renderer', placeHolder: 'Custom renderers belong in .datapeek/*.py' }, token);
                renderer = choice?.renderer;
            }
            if (!renderer || controller.signal.aborted || state.disposed) { throw new Error('CANCELLED'); }
            progress.report({ message: `Rendering with ${renderer.name}…` });
            const rendererOptions = config(uri!).get<Record<string, unknown>>('rendererOptions', {})[renderer.id] ?? {};
            if (!object(rendererOptions)) { throw new Error('rendererOptions entry must be a JSON object'); }
            const options = { ...(renderer.id === 'builtin:npy' ? { backend: config(uri!).get('backend', 'matplotlib') } : {}), ...rendererOptions };
            const rendered = await operation(context, executable, uri!, controller.signal, 'render', { rendererId: renderer.id, options });
            renderedDirectory = rendered.directory;
            if (controller.signal.aborted || state.disposed) { throw new Error('CANCELLED'); }
            await showArtifact(state, rendered.response.artifact!, rendered.directory, uri!, `${renderer.name} · ${executable} · ${vscode.env.remoteName ?? 'local'}`, controller.signal);
            const previous = state.currentDirectory;
            state.currentDirectory = rendered.directory;
            renderedDirectory = undefined;
            await remove(previous);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            output.appendLine(message);
            if (!state.disposed && generation === state.generation) {
                if (!state.hasResult) { state.panel.webview.html = messagePage(message === 'CANCELLED' ? 'Preview cancelled. Run Preview with DataPeek to retry.' : message); }
                if (message !== 'CANCELLED') { void vscode.window.showErrorMessage(`DataPeek: ${message}`, 'Show logs').then(action => { if (action) { output.show(); } }); }
            }
        } finally { cancellation.dispose(); running.delete(controller); await remove(renderedDirectory); }
    });
}

export function activate(context: vscode.ExtensionContext) {
    output = vscode.window.createOutputChannel('DataPeek');
    context.subscriptions.push(output);
    const guarded = (fn: (...args: any[]) => Promise<unknown>) => (...args: any[]) => fn(...args).catch(error => { output.appendLine(String(error)); void vscode.window.showErrorMessage(`DataPeek: ${error.message ?? error}`); });
    context.subscriptions.push(vscode.commands.registerCommand('datapeek.preview', guarded((uri?: vscode.Uri) => preview(context, uri))));
    context.subscriptions.push(vscode.commands.registerCommand('datapeek.selectPython', guarded(async () => {
        checkTrust();
        const folders = vscode.workspace.workspaceFolders ?? [];
        let folder = vscode.window.activeTextEditor ? vscode.workspace.getWorkspaceFolder(vscode.window.activeTextEditor.document.uri) : undefined;
        if (!folder && folders.length === 1) { folder = folders[0]; }
        if (!folder && folders.length > 1) { folder = await vscode.window.showWorkspaceFolderPick(); if (!folder) { return; } }
        const selected = await vscode.window.showOpenDialog({ title: 'Select Python executable on the extension host', canSelectMany: false, canSelectFolders: false, defaultUri: folder?.uri });
        if (!selected?.[0]) { return; }
        checkFileUri(selected[0]);
        await vscode.workspace.getConfiguration('datapeek', folder?.uri).update('pythonPath', selected[0].fsPath, folder ? vscode.ConfigurationTarget.WorkspaceFolder : vscode.ConfigurationTarget.Global);
        void vscode.window.showInformationMessage(`DataPeek Python: ${selected[0].fsPath}`);
    })));
    context.subscriptions.push(vscode.commands.registerCommand('datapeek.refreshRenderers', guarded(() => preview(context))));
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
        if (event.affectsConfiguration('datapeek.pythonPath') || event.affectsConfiguration('python')) { for (const controller of running) { controller.abort(); } }
    }));
}

export async function deactivate() {
    for (const controller of running) { controller.abort(); }
    await Promise.all([...views.values()].map(view => { view.disposed = true; view.panel.dispose(); return remove(view.currentDirectory); }));
    views.clear();
}
