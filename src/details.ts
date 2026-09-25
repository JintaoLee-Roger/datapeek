import * as vscode from 'vscode';
import { spawn, ChildProcessWithoutNullStreams } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as os from 'node:os';
import { randomBytes, createHash } from 'node:crypto';

const esc = (s: string) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const hostUri = (p: string, uri: vscode.Uri) => uri.scheme === 'vscode-remote' ? vscode.Uri.file(p).with({scheme: uri.scheme, authority: uri.authority}) : vscode.Uri.file(p);

class Reader {
    private child: ChildProcessWithoutNullStreams;
    private pending = new Map<number, { resolve: (x: any) => void; reject: (e: Error) => void; timer: NodeJS.Timeout }>();
    private next = 1;
    private stopped = false;
    readonly ready: Promise<any>;
    constructor(executable: string, script: string, request: string, cwd: string, private log: vscode.OutputChannel) {
        this.ready = this.waitFor(0);
        this.child = spawn(executable, [script, '--request', request], {cwd, shell: false, detached: process.platform !== 'win32', env: {...process.env, MPLBACKEND: 'Agg', PYTHONUNBUFFERED: '1'}});
        let buffer = '';
        this.child.stdout.setEncoding('utf8');
        this.child.stdout.on('data', (part: string) => {
            buffer += part;
            if (buffer.length > 40 * 1024 * 1024) { this.stop(new Error('Detailed response exceeded 40 MiB')); return; }
            let end;
            while ((end = buffer.indexOf('\n')) >= 0) {
                const line = buffer.slice(0,end); buffer = buffer.slice(end+1);
                try {
                    const message = JSON.parse(line);
                    const item = this.pending.get(message.id);
                    if (!item) { continue; }
                    clearTimeout(item.timer); this.pending.delete(message.id);
                    if (message.error) { item.reject(new Error(message.error)); } else { item.resolve(message.result); }
                } catch { this.stop(new Error('Invalid detailed reader response')); }
            }
        });
        this.child.stdin.on('error', error => this.stop(error));
        this.child.stderr.on('data', part => this.log.append(part.toString().slice(-16384)));
        this.child.on('error', e => this.stop(e));
        this.child.on('exit', code => this.stop(new Error(`Detailed reader exited (${code})`)));
    }
    private waitFor(id: number): Promise<any> {
        return new Promise((resolve,reject) => {
            const timer = setTimeout(() => this.stop(new Error('Detailed reader timed out after 120 seconds')),120000);
            this.pending.set(id,{resolve,reject,timer});
        });
    }
    call(action: string, options: unknown = {}): Promise<any> {
        if (this.stopped) { return Promise.reject(new Error('Reader closed. Reopen detailed view.')); }
        const id = this.next++;
        const promise = this.waitFor(id);
        this.child.stdin.write(JSON.stringify({id,action,options})+'\n');
        return promise;
    }
    stop(error = new Error('CANCELLED')) {
        if (this.stopped) { return; }
        this.stopped = true;
        for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.reject(error); }
        this.pending.clear();
        if (this.child?.pid) {
            try {
                if (process.platform !== 'win32') { process.kill(-this.child.pid,'SIGTERM'); }
                else { this.child.kill(); }
            } catch { /* already exited */ }
            const pid = this.child.pid;
            const timer = setTimeout(() => { try { if (process.platform !== 'win32') { process.kill(-pid,'SIGKILL'); } } catch { /* exited */ } },2000);
            timer.unref();
        }
    }
}

export class DetailView {
    private reader?: Reader;
    private viserPanel?: vscode.WebviewPanel;
    private directory?: string;
    private subscription?: vscode.Disposable;
    private closed = false;
    private serial = 0;
    private busy = false;
    private latest?: {seq: number; options: any};
    private assets: string;
    private stateKey: string;
    constructor(private context: vscode.ExtensionContext, private panel: vscode.WebviewPanel, private uri: vscode.Uri,
                private log: vscode.OutputChannel, private quick: () => void) {
        this.assets = context.asAbsolutePath('media');
        this.stateKey = 'detail.'+createHash('sha256').update(uri.toString()).digest('hex');
    }
    async open(executable: string, options: Record<string,unknown>, open3D = false, source?: {id:string;name:string;source:string;workspaceRoot?:string;readerPaths:string[]}) {
        this.stateKey='detail.'+createHash('sha256').update(JSON.stringify([this.uri.toString(),source?.id??'builtin',options.dataset??null,options])).digest('hex');
        this.directory = await fs.mkdtemp(path.join(os.tmpdir(),'datapeek-detail-'));
        if (this.closed) { await fs.rm(this.directory,{recursive:true,force:true}); return; }
        const file = path.join(this.directory,'request.json');
        await fs.writeFile(file,JSON.stringify({targetPath:this.uri.fsPath,options,assetDirectory:this.directory,rendererId:source?.id,workspaceRoot:source?.workspaceRoot,readerPaths:source?.readerPaths}),{mode:0o600});
        if (this.closed) { return; }
        this.reader = new Reader(executable,this.context.asAbsolutePath('python/detail_worker.py'),file,path.dirname(this.uri.fsPath),this.log);
        const info = await this.reader.ready;
        if (this.closed) { return; }
        const webview = this.panel.webview;
        const nonce = randomBytes(18).toString('hex');
        const asset = (file: string) => webview.asWebviewUri(hostUri(file,this.uri)).toString();
        webview.options={enableScripts:true,localResourceRoots:[hostUri(this.directory,this.uri),hostUri(this.assets,this.uri)]};
        const saved = this.context.workspaceState.get<Record<string,unknown>>(this.stateKey,{});
        const initial = JSON.stringify({info,saved,open3D}).replace(/</g,'\\u003c');
        this.subscription = webview.onDidReceiveMessage(message => {
            if (this.closed || !message || typeof message !== 'object') { return; }
            if (message.action === 'quick') { this.quick(); return; }
            if (message.action === 'sample') {
                const options = message.options;
                if (!options || typeof options !== 'object' || JSON.stringify(options).length>8192) { return; }
                this.latest={seq:++this.serial,options};
                void this.pump();
            } else if (message.action === 'save' && message.options && JSON.stringify(message.options).length<=8192) {
                void this.context.workspaceState.update(this.stateKey,message.options);
            } else if (message.action === 'viser') {
                void this.openViser(message.options).catch(error=>this.report(error));
            } else if (message.action === 'stopViser') {
                void this.stopViser().catch(error=>this.report(error));
            }
        });
        webview.html=`<!doctype html><html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src ${webview.cspSource} 'unsafe-inline'; img-src ${webview.cspSource} data: blob:; font-src ${webview.cspSource} data:; worker-src blob:; connect-src 'none';"><link rel="stylesheet" href="${asset(path.join(this.assets,'detail.css'))}"></head><body>
        <header><button id="quick">← Quick Preview</button><button id="choose">Choose Reader</button><strong>${esc(info.title || path.basename(this.uri.fsPath))}</strong><span id="viserAxes"><label><input type="checkbox" id="vx">iline</label><label><input type="checkbox" id="vy">xline</label><label><input type="checkbox" id="vz">time</label></span><button id="viser">3D View</button><button id="stopViser" hidden>Stop 3D</button></header>
        <section id="controls"><label id="axisLabel">Axis <select id="axis"><option>iline</option><option>xline</option><option>time</option></select></label><label id="indexLabel">Slice <input id="index" type="number" min="0" step="1"><input id="slider" type="range" min="0" step="1"></label>
        <label>vmin <input id="vmin" type="number" step="any"></label><label>vmax <input id="vmax" type="number" step="any"></label><label>Colormap <select id="cmap"><option>gray</option><option>seismic</option><option>RdBu_r</option><option>viridis</option><option value="Petrel">Petrel</option></select></label><button id="apply">Apply</button><label><input id="preserveAspect" type="checkbox">Original aspect</label><label title="Plot width / height; 2 means 2:1">W/H <input id="aspectRatio" type="number" min="0.01" step="any"></label><button id="region">Read Visible Region</button><button id="reset">Full View</button><button id="defaults" title="Restore the configured slice, color limits, colormap, and aspect">Reset Defaults</button></section>
        <p id="status" role="status">Reading…</p><div id="plotFrame"><div id="plot"></div></div>
        <script nonce="${nonce}">window.DATA_PEEK=${initial};</script><script nonce="${nonce}" src="${asset(path.join(this.directory,'plotly.min.js'))}"></script><script nonce="${nonce}" src="${asset(path.join(this.assets,'detail.js'))}"></script></body></html>`;
    }
    private async pump() {
        if (this.busy || !this.latest || this.closed) { return; }
        this.busy=true;
        while (this.latest && !this.closed) {
            const next=this.latest; this.latest=undefined;
            try {
                const result=await this.reader!.call('sample',next.options);
                result.clientRequest=next.options.clientRequest;
                result.region=!!next.options.region;
                if(result.region)result.view={xrange:next.options.xrange,yrange:next.options.yrange};
                if (!this.closed && next.seq===this.serial) { await this.panel.webview.postMessage({type:'sample',result}); }
            } catch (error) { if (next.seq===this.serial) { this.report(error,next.options.clientRequest); } }
        }
        this.busy=false;
    }
    private async openViser(options: unknown) {
        if (!options || typeof options !== 'object' || JSON.stringify(options).length>8192) { throw new Error('Invalid 3D options'); }
        const result = await this.reader!.call('viser',options);
        if (this.closed) { return; }
        if (!Number.isInteger(result.port) || result.port<1 || result.port>65535) { throw new Error('Invalid 3D server port'); }
        const forwarded = await vscode.env.asExternalUri(vscode.Uri.parse(`http://127.0.0.1:${result.port}`));
        if (this.closed) { return; }
        const previous=this.viserPanel;
        this.viserPanel=undefined;
        previous?.dispose();
        const panel=vscode.window.createWebviewPanel('datapeek.3d',`DataPeek 3D: ${path.basename(this.uri.fsPath)}`,vscode.ViewColumn.Active,{enableScripts:true,retainContextWhenHidden:true});
        this.viserPanel=panel;
        const url=forwarded.toString();
        const origin=new URL(url).origin;
        const nonce=randomBytes(18).toString('hex');
        panel.webview.html=`<!doctype html><html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${esc(origin)}; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';"><style>html,body{height:100%;margin:0;display:flex;flex-direction:column;background:var(--vscode-editor-background);color:var(--vscode-editor-foreground)}header{padding:8px}iframe{flex:1;width:100%;border:0}button{cursor:pointer}</style></head><body><header><button id="external">Open in Browser</button></header><iframe src="${esc(url)}" title="DataPeek 3D" allow="fullscreen"></iframe><script nonce="${nonce}">const vscode=acquireVsCodeApi();document.getElementById('external').onclick=()=>vscode.postMessage({action:'external'});</script></body></html>`;
        panel.webview.onDidReceiveMessage(message=>{
            if(message?.action==='external')void vscode.env.openExternal(forwarded).then(ok=>{if(!ok)this.report(new Error('Could not open the browser.'));},error=>this.report(error));
        });
        panel.onDidDispose(()=>{
            if(this.viserPanel!==panel)return;
            this.viserPanel=undefined;
            if(!this.closed)void this.stopViser().catch(error=>this.report(error));
        });
        await this.panel.webview.postMessage({type:'viserStarted'});
    }
    private async stopViser() {
        const panel=this.viserPanel;
        this.viserPanel=undefined;
        panel?.dispose();
        await this.reader?.call('stopViser');
        if(!this.closed)await this.panel.webview.postMessage({type:'viserStopped'});
    }
    private report(error: unknown, clientRequest?:number) {
        const message=error instanceof Error?error.message:String(error);
        this.log.appendLine(message);
        if (!this.closed) { void this.panel.webview.postMessage({type:'error',message,clientRequest}); }
    }
    dispose() {
        this.closed=true;this.latest=undefined;
        const panel=this.viserPanel;this.viserPanel=undefined;panel?.dispose();
        this.subscription?.dispose();this.reader?.stop();
        if (this.directory) { void fs.rm(this.directory,{recursive:true,force:true,maxRetries:3}).catch(error=>this.log.appendLine(String(error))); }
    }
}
