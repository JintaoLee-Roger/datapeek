// Exercise the real quick-preview HTML, including array vs Figure capability buttons.
const fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const vscode={Uri:{file:p=>({toString:()=>pathToFileURL(p).toString()})}};
const sandbox={exports:{},require:name=>name==='vscode'?vscode:name.startsWith('./')?{}:require(name),process,setTimeout,clearTimeout};
vm.runInNewContext(require('node:fs').readFileSync('dist/extension.js','utf8')+'\nexports.showArtifact=showArtifact;',sandbox);
(async()=>{
 const directory=await fs.mkdtemp('/tmp/datapeek-quick-');
 await fs.mkdir(path.join(directory,'artifacts'));
 await fs.copyFile('/tmp/datapeek-final-preview/baiyun/artifacts/figure.png',path.join(directory,'artifacts/figure.png'));
 const panel={webview:{cspSource:'file:',asWebviewUri:u=>u}};
 for(const kind of ['array','figure']){
  const view={panel,renderer:{kind},disposed:false};
  await sandbox.exports.showArtifact(view,{kind:'image',entry:'artifacts/figure.png'},directory,{scheme:'file'},'Custom · test reader',new AbortController().signal);
  await fs.writeFile(path.join(directory,kind+'.html'),panel.webview.html);
 }
 console.log(directory);
})().catch(e=>{console.error(e);process.exitCode=1;});
