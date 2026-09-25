/* global Plotly */
(() => {
'use strict';
const vscode=acquireVsCodeApi();
const {info,saved,open3D}=window.DATA_PEEK;
const $=id=>document.getElementById(id);
const plot=$('plot'),plotFrame=$('plotFrame');
let displayAspect=2, resizeFrame, observedWidth=-1, observedHeight=-1;
const margins={l:65,r:80,t:20,b:55,autoexpand:false};
function plotSize(){
 const availableWidth=Math.max(1,plotFrame.clientWidth-margins.l-margins.r);
 const availableHeight=Math.max(1,plotFrame.clientHeight-margins.t-margins.b);
 const imageWidth=Math.min(availableWidth,availableHeight*(preserveAspect?displayAspect:customAspect));
 return {width:imageWidth+margins.l+margins.r,height:imageWidth/(preserveAspect?displayAspect:customAspect)+margins.t+margins.b};
}
const observer=new ResizeObserver(entries=>{
 const {width,height}=entries[0].contentRect;
 if(width===observedWidth&&height===observedHeight)return;
 observedWidth=width;observedHeight=height;
 cancelAnimationFrame(resizeFrame);
 resizeFrame=requestAnimationFrame(()=>{if(plot.data)void Plotly.relayout(plot,plotSize());});
});
observer.observe(plotFrame);
let payload, overview=null, fixedLimits=null, first=true, requestNumber=0, loading=false;
const axes=['iline','xline','time'];
const initial={...info.defaults,...saved};
let preserveAspect=initial.preserve_aspect!==false;
let customAspect=Number.isFinite(initial.aspect_ratio)&&initial.aspect_ratio>0?initial.aspect_ratio:2;
function aspectControls(){
 $('preserveAspect').checked=preserveAspect;
 $('aspectRatio').value=customAspect;
 $('aspectRatio').disabled=preserveAspect;
}
aspectControls();
async function changeAspect(){
 const ratio=Number($('aspectRatio').value);
 if(!Number.isFinite(ratio)||ratio<=0){aspectControls();return;}
 preserveAspect=$('preserveAspect').checked;customAspect=ratio;aspectControls();
 if(plot.data)await Plotly.relayout(plot,plotSize());
 save();
}
$('preserveAspect').onchange=changeAspect;
$('aspectRatio').onchange=changeAspect;
$('axis').value=axes.includes(initial.axis)?initial.axis:(initial.slices||['iline'])[0];
let positions={};
axes.forEach((axis,i)=>positions[axis]=Math.max(0,Math.min((info.shape[i]||1)-1,initial.positions?.[axis]??initial[axis]??Math.floor((info.shape[i]||1)/2))));
if(!info.colorscales?.Petrel)$('cmap').querySelector('option[value="Petrel"]').remove();
$('cmap').value=Array.from($('cmap').options).some(o=>o.value===initial.cmap)?initial.cmap:'gray';
if (Number.isFinite(initial.vmin)&&Number.isFinite(initial.vmax)&&initial.vmin<initial.vmax) {
 fixedLimits=[initial.vmin,initial.vmax];
}
let activeCmap=$('cmap').value;
const large=info.nbytes>(initial.large_volume_gb??1.5)*1e9;
['vx','vy','vz'].forEach((id,i)=>$(id).checked=initial.slices?initial.slices.includes(axes[i]):(!large||i===0));
if (!info.volume) { $('viserAxes').hidden=true; $('axisLabel').hidden=true;$('indexLabel').hidden=true;$('viser').hidden=true; }
if(info.shape.length===1){for(const id of ['vmin','vmax','cmap'])$(id).closest('label').hidden=true;$('apply').hidden=true;}
function status(text){const node=$('status');node.textContent=text;node.title=text;}
function indexControls(){const axis=$('axis').value;const max=info.shape[axes.indexOf(axis)]-1;for(const id of ['index','slider']){$(id).max=max;$(id).value=positions[axis];}}
indexControls();
function colors(){return {vmin:fixedLimits?.[0]??null,vmax:fixedLimits?.[1]??null,clip_percentile:initial.clip_percentile??99};}
function inputLimits(){
 const low=$('vmin').value.trim(),high=$('vmax').value.trim();const vmin=Number(low),vmax=Number(high);
 if(!low||!high||!Number.isFinite(vmin)||!Number.isFinite(vmax)||vmin>=vmax)throw Error('Enter finite values with vmin < vmax.');
 return [vmin,vmax];
}
function state(){return {preserve_aspect:preserveAspect,aspect_ratio:customAspect,axis:$('axis').value,positions:{...positions},cmap:activeCmap,...colors()};}
function save(){vscode.postMessage({action:'save',options:state()});}
function busy(value){loading=value;for(const id of ['region','reset','apply','defaults','viser'])$(id).disabled=value;}
function restoreDisplayed(){
 if(!payload||!info.volume)return;
 $('axis').value=payload.axis;positions[payload.axis]=payload.index;indexControls();
}
function request(region=false){
 try{
  const color=colors();
  const index=Number($('index').value);
  if(info.volume&&(!Number.isInteger(index)||index<0||index>Number($('index').max)))throw Error('Slice index is out of range.');
  busy(true);
  status(region?'Reading region…':'Reading slice…');
  const bounds=region?{xrange:[...plot.layout.xaxis.range],...(payload.kind==='line'?{}:{yrange:[...plot.layout.yaxis.range]})}:{};
  vscode.postMessage({action:'sample',options:{axis:$('axis').value,index,resolution:768,...bounds,...color,region,clientRequest:++requestNumber}});
 }catch(e){busy(false);restoreDisplayed();status(e.message);}
}
function scale(cmap=activeCmap){switch(cmap){case 'Petrel':return info.colorscales.Petrel;case 'gray':return [[0,'black'],[1,'white']];case 'seismic':return [[0,'#00004c'],[.25,'blue'],[.5,'white'],[.75,'red'],[1,'#800000']];case 'RdBu_r':return [[0,'#053061'],[.5,'#f7f7f7'],[1,'#67001f']];default:return 'Viridis';}}
function autoLimits(data,percentile){
 const finite=Array.from(data).filter(Number.isFinite).sort((a,b)=>a-b);
 if(!finite.length)return [-1,1];
 const q=p=>{const x=(finite.length-1)*p/100;const a=Math.floor(x),b=Math.ceil(x);return finite[a]+(finite[b]-finite[a])*(x-a);};
 const tail=(100-percentile)/2;
 const low=q(tail),high=q(100-tail);
 // Match Python: a median within 10% of the IQR of zero, with both signs.
 if(low<0&&high>0&&Math.abs(q(50))<=.1*(q(75)-q(25))){
  const a=Math.min(Math.abs(low),Math.abs(high));
  return [-a,a];
 }
 if(low===high){const pad=Math.max(Math.abs(low)*1e-6,Number.EPSILON);return [low-pad,high+pad];}
 return [low,high];
}
function limits(){
 if(!fixedLimits)fixedLimits=autoLimits(payload.values,initial.clip_percentile??99);
 return fixedLimits;
}
async function recolor(){
 try{if(!payload)return;const [low,high]=inputLimits();await Plotly.restyle(plot,{zmin:low,zmax:high,zauto:false,colorscale:[scale($('cmap').value)]});fixedLimits=[low,high];activeCmap=$('cmap').value;save();}catch(e){status(e.message);}
}
async function render(result){
 if(result.clientRequest!==undefined && result.clientRequest!==requestNumber)return;
 if(!result.region){overview=result;displayAspect=result.displayAspect??(result.kind==='line'?2:result.shape[1]/result.shape[0]);}
 const bytes=Uint8Array.from(atob(result.data),c=>c.charCodeAt(0));
 const values=new Float32Array(bytes.buffer);payload={...result,values};
 const clean=n=>Number.isFinite(n)?n:null;
 const line=result.kind==='line';
 const n=line?result.shape[0]:result.shape[1];
 const x=Array.from({length:n},(_,i)=>result.x0+i*result.dx);
 const y=line?Array.from(values,clean):Array.from({length:result.shape[0]},(_,i)=>result.y0+i*result.dy);
 const z=line?undefined:Array.from({length:result.shape[0]},(_,row)=>Array.from(values.subarray(row*n,(row+1)*n),clean));
 const [low,high]=limits();
 const trace=line?{type:'scatter',mode:'lines',x,y,line:{width:1}}:{type:'heatmap',x,y,z,zmin:low,zmax:high,zauto:false,colorscale:scale(),zsmooth:false,hoverongaps:false,hovertemplate:'x=%{x}<br>y=%{y}<br>value=%{z}<extra></extra>'};
 await Plotly.react(plot,[trace],{...plotSize(),autosize:false,margin:margins,dragmode:'zoom',xaxis:{title:{text:result.xlabel},range:result.view?.xrange||result.xbounds},yaxis:{title:{text:result.ylabel},...(line?{}:{range:result.view?.yrange||[result.ybounds[1],result.ybounds[0]]})}},{responsive:false,scrollZoom:true,displaylogo:false});
 $('vmin').value=low;$('vmax').value=high;
 restoreDisplayed();busy(false);
 save();
 if(first){first=false;if(open3D&&info.volume)$('viser').click();}
 status('');
}
window.addEventListener('message',event=>{
 const message=event.data;
 if(message.type==='sample')void render(message.result).catch(e=>{busy(false);restoreDisplayed();status(e.message);});
 if(message.type==='error'&&(message.clientRequest===undefined||message.clientRequest===requestNumber)){busy(false);restoreDisplayed();status(message.message+(payload?' (previous image retained)':''));}
 if(message.type==='viserStarted'){$('viser').disabled=false;$('stopViser').hidden=false;status('');}
 if(message.type==='viserStopped'){$('stopViser').hidden=true;status('');}
});
$('axis').onchange=()=>{indexControls();request();};
$('slider').oninput=()=>{$('index').value=$('slider').value;};
$('slider').onchange=()=>{positions[$('axis').value]=Number($('slider').value);request();};
$('index').onchange=()=>{positions[$('axis').value]=Number($('index').value);$('slider').value=$('index').value;request();};
$('apply').onclick=()=>void recolor();
$('region').onclick=()=>{if(payload&&!loading)request(true);};
$('reset').onclick=()=>{if(overview&&!loading)void render({...overview,clientRequest:requestNumber});};
$('defaults').onclick=()=>{
 const defaults=info.defaults;
 preserveAspect=defaults.preserve_aspect!==false;customAspect=defaults.aspect_ratio??2;aspectControls();
 fixedLimits=Number.isFinite(defaults.vmin)&&Number.isFinite(defaults.vmax)?[defaults.vmin,defaults.vmax]:null;
 activeCmap=Array.from($('cmap').options).some(o=>o.value===defaults.cmap)?defaults.cmap:'gray';$('cmap').value=activeCmap;
 axes.forEach((axis,i)=>positions[axis]=defaults[axis]??Math.floor((info.shape[i]||1)/2));
 $('axis').value=(defaults.slices||['iline'])[0];indexControls();request();
};
$('choose').onclick=()=>vscode.postMessage({action:'chooseReader'});
$('quick').onclick=()=>vscode.postMessage({action:'quick'});
$('viser').onclick=()=>{if(!payload||loading)return;try{$('viser').disabled=true;status('Starting 3D…');const slices=axes.filter((_,i)=>$(['vx','vy','vz'][i]).checked);if(!slices.length)throw Error('Select at least one 3D axis.');vscode.postMessage({action:'viser',options:{slices,axis:payload.axis,index:payload.index,positions:{...positions},cmap:activeCmap,...colors()}});}catch(e){$('viser').disabled=false;status(e.message);}};
$('stopViser').onclick=()=>vscode.postMessage({action:'stopViser'});
request();
})();
