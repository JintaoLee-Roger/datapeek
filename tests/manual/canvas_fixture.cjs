// Render actual extension HTML/CSP for runner artifacts; prints the browser fixture directory.
const fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const vscode={Uri:{file:p=>({toString:()=>pathToFileURL(p).toString()})}};
const sandbox={exports:{},require:name=>name==='vscode'?vscode:name.startsWith('./')?{}:require(name),process,setTimeout,clearTimeout};
vm.runInNewContext(require('node:fs').readFileSync('dist/extension.js','utf8')+'\nexports.showArtifact=showArtifact;',sandbox);
(async()=>{
 const root=process.argv[2],output=await fs.mkdtemp('/tmp/datapeek-canvas-ui-');
 for(const name of await fs.readdir(root)){
  const directory=path.join(root,name),response=JSON.parse(await fs.readFile(path.join(directory,'response.json'),'utf8'));
  const panel={webview:{cspSource:'file:',asWebviewUri:u=>u}};
  await sandbox.exports.showArtifact({panel,renderer:{kind:'array'},disposed:false},response.artifact,directory,{scheme:'file'},'Custom · Test',new AbortController().signal);
  await fs.writeFile(path.join(output,name+'.html'),panel.webview.html);
 }
 console.log(output);
})().catch(e=>{console.error(e);process.exitCode=1;});
