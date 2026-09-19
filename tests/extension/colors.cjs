const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('media/detail.js','utf8');
const code=source.slice(source.indexOf('function autoLimits('),source.indexOf('\nfunction limits('));
const limits=vm.runInNewContext(code+'; autoLimits');
test('automatic limits retain shifted fields and symmetrize zero-centered display bounds',()=>{
 for(const [data,expected] of [
  [[-10,-3,-2,-1,1,2,3,100],[-9.755,9.755]],
  [[0,.25,.5,.75,1],[.005,.995]],
  [[-1,-.75,-.5,-.25,0],[-.995,-.005]],
  [[-1,2,3,4,5],[-.94,4.98]],
 ]){
  const actual=limits(data,99);
  actual.forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-12));
 }
 for(const data of [[0,0],[5,5],[NaN,Infinity]]){
  const [low,high]=limits(data,99);assert.ok(Number.isFinite(low)&&low<high);
 }
});
