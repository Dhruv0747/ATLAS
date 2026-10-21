"""Execute the production IR canvas conversion and banner functions in Node with a tiny DOM fixture."""
import shutil,subprocess
from pathlib import Path
import pytest

def test_ir_banner_and_canvas_native_bytes(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    js=(Path(__file__).resolve().parents[1]/'web/v2/vision3d.js').read_text()
    draw=js[js.index('  function drawIr('):js.index("  $('irCanvas').onclick")]
    state=str(Path(__file__).resolve().parents[1]/'web/v2/vision3d_state.js')
    harness=r'''
const assert=require('assert'); const els={};let image=null,ir=null,frozen=false;
const $=id=>els[id]||(els[id]={style:{},dataset:{},classList:{remove(){}},setAttribute(){},getContext(){return {createImageData(w,h){return {data:new Uint8Array(w*h*4)}},putImageData(a){image=a}}}});
const isNum=v=>typeof v==='number'&&Number.isFinite(v), mode=()=> 'ir',MODE_NAMES={ir:'infrared only'};
let status={streams:{ir:{state:'UNAVAILABLE',received:0}}};
'''+draw+r'''
// Stage32 UI fix: banner states now come from vision3d_state.js (real frame counts/freshness), not the driver PID
const S=require('''+repr(state)+r''');const m=S.newMemo();const rt={state:'ACTIVE',mode:'ir',worker_pid:5,driver_pid:2};
S.sessionView(rt,status.streams,m,0);assert.equal(S.sessionView(rt,status.streams,m,11).title,'No frames received');
assert.equal(S.sessionView(rt,{ir:{state:'ACTIVE',received:3}},m,12).title,'Live');
assert.equal(S.sessionView(rt,{ir:{state:'STALE',received:3}},m,13).title,'Frames stopped');
assert.equal(S.sessionView({state:'RESOURCE BLOCKED',mode:'ir',worker_pid:5,failed_resources:{cpu:76}},{},m,14).title,'Resource blocked');
const m2=S.newMemo();S.sessionView({state:'ACTIVE',mode:'ir',worker_pid:6},{},m2,0);
assert.equal(S.sessionView({state:'OFF',mode:'ir',worker_pid:6,driver_pid:2,driver_stopped:true,reason:'60-second session complete'},{},m2,70).title,'No frames received');
function frame(enc,bytes,big,step){const headers=new Map([['X-Width','2'],['X-Height','1'],['X-Encoding',enc],['X-Step',String(step)],['X-Bigendian',big?'1':'0'],['X-Source-Stamp','123.5']]);drawIr(Uint8Array.from(bytes).buffer,headers);}
frame('mono8',[0,255],false,2);assert.deepEqual(Array.from(ir.values),[0,255]);assert.equal(image.data[4],255);
frame('mono16',[0,1,255,255],true,4);assert.deepEqual(Array.from(ir.values),[1,65535]);
frame('16UC1',[1,0,0,1,99,99],false,6);assert.deepEqual(Array.from(ir.values),[1,256]);
assert.equal($('irCanvas').dataset.sourceStamp,'123.5');assert.equal($('irCanvas').dataset.rendered,'true');
assert.throws(()=>frame('rgb8',[0,0],false,2));assert.throws(()=>frame('mono16',[0,0],false,2));
console.log('banner and native canvas checks PASS');
'''
    p=tmp_path/'ir.js';p.write_text(harness)
    result=subprocess.run([node,str(p)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
