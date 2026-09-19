import * as vscode from 'vscode';

export const editorId = 'datapeek.autoPreview';
export const patterns = ['*.npy','*.npz','*.h5','*.hdf5'];
const backupKey='autoPreview.associationBackup';
const userBackupKey='autoPreview.userAssociationBackup';
type Associations = Record<string,string>;
type Backup = {previous: Associations; missing: string[]};

// VS Code globMatchesResource matches patterns containing '/' against
// `${resource.scheme}:${resource.path}`, NOT fsPath and NOT the full URI
// (the remote authority is intentionally absent). Scope to each workspace.
// https://github.com/microsoft/vscode/blob/main/src/vs/workbench/services/editor/common/editorResolverService.ts
export function scopedPatterns(roots: readonly vscode.WorkspaceFolder[], configured: string[], remoteHost = false): string[] {
    return [...new Set(roots.flatMap(folder=>{
        const scheme=remoteHost && folder.uri.scheme==='file' ? 'vscode-remote' : folder.uri.scheme;
        const root=folder.uri.path.replace(/\/$/,'');
        // Escape glob metacharacters that belong to a literal directory name.
        const literal=root.replace(/[\[\]*?{}]/g, c=>`[${c}]`);
        return configured.map(pattern=>`${scheme}:${literal}/**/${pattern.replace(/^\*\*\//,'')}`);
    }))];
}

export class AutoPreview {
    private enabled=false;
    private changing=false;
    readonly ready: Promise<void>;
    constructor(private context: vscode.ExtensionContext) {
        // No status bar item. Recover session associations on window reload.
        this.ready=this.recover();
    }
    private current(): Associations {
        return vscode.workspace.getConfiguration('workbench').inspect<Associations>('editorAssociations')?.globalValue??{};
    }
    private recovered(current: Associations, backup: Backup): Associations {
        const result={...current};
        for(const pattern of new Set([...Object.keys(backup.previous),...backup.missing])){
            if(result[pattern]!==editorId)continue;
            if(pattern in backup.previous)result[pattern]=backup.previous[pattern];
            else delete result[pattern];
        }
        return result;
    }
    private async recover() {
        await this.restore();
        // The previous implementation saved a workspace backup before attempting
        // to write settings. A failed EACCES write leaves nothing to restore.
        const legacy=this.context.workspaceState.get<Backup>(backupKey);
        if(!legacy)return;
        const current=vscode.workspace.getConfiguration('workbench').inspect<Associations>('editorAssociations')?.workspaceValue??{};
        const restored=this.recovered(current,legacy);
        if(JSON.stringify(current)!==JSON.stringify(restored)){
            try{
                await vscode.workspace.getConfiguration('workbench').update('editorAssociations',Object.keys(restored).length?restored:undefined,vscode.ConfigurationTarget.Workspace);
            }catch{
                // Leave the old backup available for a later writable session;
                // its cleanup must not block the new user-scoped toggle.
                return;
            }
        }
        await this.context.workspaceState.update(backupKey,undefined);
    }
    async toggle(){
        await this.ready;
        if(this.changing)return;
        const roots=vscode.workspace.workspaceFolders;
        if(!roots?.length)throw new Error('Open a data folder before enabling automatic preview.');
        this.changing=true;
        try{
            if(this.enabled){
                await this.restore();
                void vscode.window.showInformationMessage('DataPeek automatic preview disabled.');
            }else{
                await this.restore(); // Retry any unfinished rollback before creating a new backup.
                const current=this.current();const previous:Associations={};const missing:string[]=[];
                const configured=vscode.workspace.getConfiguration('datapeek').get<string[]>('autoPreviewPatterns',patterns);
                const scoped=scopedPatterns(roots,configured,!!vscode.env.remoteName);
                for(const pattern of scoped){if(pattern in current)previous[pattern]=current[pattern];else missing.push(pattern);}
                await this.context.workspaceState.update(userBackupKey,{previous,missing});
                try{
                    await vscode.workspace.getConfiguration('workbench').update('editorAssociations',{...current,...Object.fromEntries(scoped.map(p=>[p,editorId]))},vscode.ConfigurationTarget.Global);
                }catch(error){
                    // Roll back only our entries if a provider partially applied
                    // the update. A failed update must not poison future toggles.
                    await this.restore().catch(()=>{});
                    throw error;
                }
                this.enabled=true;
                void vscode.window.showInformationMessage('Automatic preview enabled for this workspace. Reopen existing text tabs to preview them.');
            }
        }finally{this.changing=false;}
    }
    async restore(){
        const backup=this.context.workspaceState.get<Backup>(userBackupKey);
        if(backup){
            const current=this.current();
            const restored=this.recovered(current,backup);
            if(JSON.stringify(current)!==JSON.stringify(restored)){
                await vscode.workspace.getConfiguration('workbench').update('editorAssociations',Object.keys(restored).length?restored:undefined,vscode.ConfigurationTarget.Global);
            }
            await this.context.workspaceState.update(userBackupKey,undefined);
        }
        this.enabled=false;
    }
}
