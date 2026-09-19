const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(customPatterns){
 let associations={'*.csv':'other.csv'},workspace={};
 let failGlobal=false;
 const writes=[],notices=[],data=new Map();
 const config={get:(_,fallback)=>customPatterns??fallback,inspect:()=>({globalValue:associations,workspaceValue:workspace}),update:async(_,value,target)=>{
  writes.push(target);
  if(target===2)throw Error('EACCES: read-only data directory');
  if(failGlobal)throw Error('user settings unavailable');
  associations=value??{};
 }};
 const vscode={env:{remoteName:undefined},ConfigurationTarget:{Global:1,Workspace:2},workspace:{workspaceFolders:[{uri:{scheme:'vscode-remote',path:'/data/project'}}],getConfiguration:()=>config},window:{showInformationMessage:message=>notices.push(message),createStatusBarItem:()=>{throw Error('Status bar must not be created');}}};
 const context={subscriptions:[],workspaceState:{get:k=>data.get(k),update:async(k,v)=>{if(v===undefined)data.delete(k);else data.set(k,v);}}};
 const sandbox={exports:{},require:name=>{assert.equal(name,'vscode');return vscode;}};
 vm.runInNewContext(fs.readFileSync('dist/autoPreview.js','utf8'),sandbox);
 return {Auto:sandbox.exports.AutoPreview,scope:sandbox.exports.scopedPatterns,context,data,writes,notices,get:()=>associations,set:v=>associations=v,setWorkspace:v=>workspace=v,fail:v=>failGlobal=v};
}
const npy='vscode-remote:/data/project/**/*.npy';
test('read-only workspace toggles via scoped user settings, without status bar',async()=>{
 const s=setup();s.set({[npy]:'old.npy','*.npy':'global.npy','*.csv':'csv'});
 const auto=new s.Auto(s.context);await auto.ready;await auto.toggle();
 assert.equal(s.get()[npy],'datapeek.autoPreview');assert.equal(s.get()['*.npy'],'global.npy');
 s.set({...s.get(),'*.csv':'new.csv'});await auto.toggle();
 assert.equal(s.get()[npy],'old.npy');assert.equal(s.get()['*.csv'],'new.csv');
 assert.equal(s.get()['vscode-remote:/data/project/**/*.npz'],undefined);
 assert.ok(s.writes.every(t=>t===1));assert.equal(s.notices.length,2);
});
test('reload restores user associations',async()=>{
 const s=setup();const first=new s.Auto(s.context);await first.ready;await first.toggle();
 const reloaded=new s.Auto(s.context);await reloaded.ready;
 assert.deepEqual(JSON.parse(JSON.stringify(s.get())),{'*.csv':'other.csv'});
});
test('user overriding association while enabled wins on restore',async()=>{
 const s=setup();const auto=new s.Auto(s.context);await auto.ready;await auto.toggle();
 s.set({...s.get(),[npy]:'chosen.editor'});await auto.restore();assert.equal(s.get()[npy],'chosen.editor');
});
test('custom patterns restored independently of current configuration',async()=>{
 const s=setup(['*.custom']);s.set({'vscode-remote:/data/project/**/*.custom':'old.custom','*.csv':'csv'});
 const first=new s.Auto(s.context);await first.ready;await first.toggle();
 const second=new s.Auto(s.context);await second.ready;
 assert.equal(s.get()['vscode-remote:/data/project/**/*.custom'],'old.custom');assert.equal(s.get()['*.csv'],'csv');
});
test('legacy failed write recovery never retries workspace mkdir',async()=>{
 const s=setup();s.data.set('autoPreview.associationBackup',{previous:{},missing:['*.npy','*.npz']});
 const auto=new s.Auto(s.context);await auto.ready;
 assert.equal(s.writes.length,0);assert.equal(s.data.has('autoPreview.associationBackup'),false);
 await auto.toggle();assert.equal(s.get()[npy],'datapeek.autoPreview');assert.ok(s.writes.every(t=>t===1));
});
test('unwritable legacy cleanup does not block new toggle',async()=>{
 const s=setup();s.setWorkspace({'*.npy':'datapeek.autoPreview'});
 s.data.set('autoPreview.associationBackup',{previous:{},missing:['*.npy']});
 const auto=new s.Auto(s.context);await auto.ready;await auto.toggle();
 assert.equal(s.get()[npy],'datapeek.autoPreview');assert.equal(s.data.has('autoPreview.associationBackup'),true);
});
test('failed user update can be retried without losing unrelated settings',async()=>{
 const s=setup();const auto=new s.Auto(s.context);await auto.ready;s.fail(true);
 await assert.rejects(auto.toggle(),/user settings unavailable/);
 assert.equal(s.data.has('autoPreview.userAssociationBackup'),false);
 s.fail(false);await auto.toggle();assert.equal(s.get()[npy],'datapeek.autoPreview');
});

// VS Code editorResolverService.globMatchesResource selects scheme:path for
// patterns containing '/', and basename otherwise. Exercise that target, not
// only whether a configuration update succeeded.
const {minimatch}=require('minimatch');
function editorMatches(pattern,resource){
 const target=pattern.includes('/')?`${resource.scheme}:${resource.path}`:resource.path.split('/').pop();
 return minimatch(target,pattern,{nocase:true});
}
test('Remote SSH associations match the real editor resolver target',()=>{
 const s=setup();
 const root={uri:{scheme:'vscode-remote',authority:'ssh-remote+a100j',path:'/home/jtli/data'}};
 const resource={scheme:'vscode-remote',path:'/home/jtli/data/seismic/seismic_data/baiyun/sx_cut.npy'};
 const patterns=s.scope([root],['*.npy','**/das/**/part_*.zarr/data/*.0.0']);
 assert.equal(editorMatches('/home/jtli/data/**/*.npy',resource),false,'Previous path-only rule must reproduce the bug');
 assert.ok(patterns.some(p=>editorMatches(p,resource)));
 assert.ok(patterns.some(p=>editorMatches(p,{scheme:'vscode-remote',path:'/home/jtli/data/das/earthquake/Ridgecrest/part_00.zarr/data/7.0.0'})));
 assert.equal(patterns.some(p=>editorMatches(p,{scheme:'vscode-remote',path:'/home/jtli/other/sx_cut.npy'})),false);
 assert.equal(patterns.some(p=>editorMatches(p,{scheme:'file',path:resource.path})),false);
});
test('local workspace patterns use file scheme and match direct children',()=>{
 const s=setup();const patterns=s.scope([{uri:{scheme:'file',path:'/tmp/data'}}],['*.npy']);
 assert.ok(patterns.some(p=>editorMatches(p,{scheme:'file',path:'/tmp/data/a.npy'})));
 assert.ok(patterns.some(p=>editorMatches(p,{scheme:'file',path:'/tmp/data/nested/a.npy'})));
});

test('remote extension host file URI is translated to the UI resolver scheme',()=>{
 const s=setup();const root={uri:{scheme:'file',path:'/home/jtli/data'}};
 const patterns=s.scope([root],['*.npy'],true);
 assert.ok(patterns.some(p=>editorMatches(p,{scheme:'vscode-remote',path:'/home/jtli/data/seismic/seismic_data/baiyun/sx_cut.npy'})));
 assert.equal(patterns.some(p=>editorMatches(p,{scheme:'file',path:'/home/jtli/data/a.npy'})),false);
});
