// Generate the real TypeScript webview HTML for an opt-in headless browser test.
const fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const callbacks=[];
let created,externalCalls=0;
const vscode={Uri:{parse:s=>({toString:()=>s}),file:p=>({fsPath:p,scheme:'file',toString:()=>pathToFileURL(p).toString()})},env:{asExternalUri:async u=>u,openExternal:async()=>{externalCalls++;return true;}}};
vscode.ViewColumn={Active:-1};
vscode.window={createWebviewPanel:()=>{
 let close;
 created={webview:{onDidReceiveMessage:fn=>{created.message=fn;}},onDidDispose:fn=>{close=fn;},dispose:()=>close?.()};
 return created;
}};
const sandbox={URL,exports:{},require:name=>name==='vscode'?vscode:require(name),process,setTimeout,clearTimeout};
vm.runInNewContext(require('node:fs').readFileSync('dist/details.js','utf8'),sandbox);
(async()=>{
 const root=await fs.mkdtemp('/tmp/datapeek-ui-');
 const messages=[];
 const panel={webview:{cspSource:'file:',asWebviewUri:u=>u,onDidReceiveMessage:fn=>{callbacks.push(fn);return {dispose(){}};},postMessage:async message=>messages.push(message)}};
 const context={asAbsolutePath:p=>path.resolve(p),workspaceState:{get:()=>({}),update:async()=>{}}};
 const uri={scheme:'file',fsPath:'/home/jtli/data/seismic/seismic_data/baiyun/sx_cut.npy',toString(){return this.fsPath;}};
 const detail=new sandbox.exports.DetailView(context,panel,uri,{append(){},appendLine(){}},()=>{});
 try{
  await detail.open('/home/jtli/envs/main/bin/python3',{});
  const html=panel.webview.html;
  const src=html.match(/src="(file:[^"]*plotly.min.js)"/)[1];
  await fs.copyFile(new URL(src),path.join(root,'plotly.min.js'));
  await fs.writeFile(path.join(root,'index.html'),html.replace(src,pathToFileURL(path.join(root,'plotly.min.js')).toString()));
  callbacks[0]({action:'sample',options:{axis:'iline',index:2}});
  callbacks[0]({action:'sample',options:{axis:'iline',index:7}});
  const start=Date.now();
  while(!messages.some(x=>x.type==='sample')&&Date.now()-start<30000)await new Promise(r=>setTimeout(r,50));
  assert.equal(messages.filter(x=>x.type==='sample').length,1);
  assert.equal(messages.find(x=>x.type==='sample').result.index,7);
  await detail.openViser({axis:'iline',index:7,slices:['iline'],vmin:0,vmax:1,cmap:'Petrel'});
  assert.equal(externalCalls,0,'3D must not automatically launch browser');
  await fs.writeFile(path.join(root,'3d.html'),created.webview.html);
  created.message({action:'external'});
  assert.equal(externalCalls,1);
  created.dispose();
  const deadline=Date.now()+5000;
  while(!messages.some(x=>x.type==='viserStopped')&&Date.now()<deadline)await new Promise(r=>setTimeout(r,50));
  assert.ok(messages.some(x=>x.type==='viserStopped'),'Closing 3D must stop server');
  console.log(root);
 }finally{detail.dispose();}
})().catch(error=>{console.error(error);process.exitCode=1;});
