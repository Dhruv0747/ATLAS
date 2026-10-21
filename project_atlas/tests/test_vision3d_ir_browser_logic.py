"""Execute the production IR canvas conversion and banner functions in Node with a tiny DOM fixture."""
import shutil,subprocess
from pathlib import Path
import pytest

def test_ir_banner_and_canvas_native_bytes(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    js=(Path(__file__).resolve().parents[1]/'web/v2/vision3d.js').read_text()
    draw=js[js.index('  function drawIr('):js.index("  $('irCanvas').onclick")]
    banner=js[js.index('  function bar('):js.index('  function streamView(')]
    harness=r'''
const assert=require('assert'); const els={};let image=null,ir=null,frozen=false;
const $=id=>els[id]||(els[id]={style:{},dataset:{},classList:{remove(){}},setAttribute(){},getContext(){return {createImageData(w,h){return {data:new Uint8Array(w*h*4)}},putImageData(a){image=a}}}});
const isNum=v=>typeof v==='number'&&Number.isFinite(v), mode=()=> 'ir',MODE_NAMES={ir:'infrared only'};
let status={streams:{ir:{state:'UNAVAILABLE',received:0}}};
'''+draw+banner+r'''
const rt={state:'ACTIVE',mode:'ir',driver_pid:2};explain(rt);assert.equal($('vlTitle').textContent,'IR NO FRAMES RECEIVED');
status.streams.ir.state='STALE';explain(rt);assert.equal($('vlTitle').textContent,'IR STREAM STALE');
status.streams.ir.state='ACTIVE';explain(rt);assert.equal($('vlTitle').textContent,'IR frames received');
explain({state:'RESOURCE BLOCKED',mode:'ir',failed_resources:{cpu:76}});assert.equal($('vlTitle').textContent,'Stopped to protect ATLAS');
status.last_session={streams:{ir:{received:0}}};explain({state:'OFF',mode:'ir',driver_pid:2});assert.equal($('vlTitle').textContent,'IR NO FRAMES RECEIVED');
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
