const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const crypto=require('node:crypto').webcrypto;
const elements={}, requests=[], storage=new Map();
let status={enabled:false,state:'IDLE'};
function element(){return {innerHTML:'',textContent:'',disabled:false,checked:false,value:'',dataset:{},
 appendChild(child){if(child.id)elements[child.id]=child;for(const m of child.innerHTML.matchAll(/id="([^"]+)"/g))elements[m[1]]=element();},
 querySelectorAll(){return [];}};}
const root=element();
const context={crypto,sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 document:{createElement:element,getElementById:id=>elements[id]},
 $:id=>elements[id], obj:()=>status,live:()=>true,
 request:async payload=>{requests.push(payload);return {state:'PREPARING'};},
 setInterval:()=>0,alert:()=>{},confirm:()=>true};
vm.createContext(context);
vm.runInContext(fs.readFileSync('project_atlas/scripts/atlas_steering_ui.js','utf8'),context);
context.singlePersonSteeringTools(root);
assert.equal(requests.length,0,'opening the dashboard must not start/prepare a sequence');
context.singlePersonSteeringRender();
assert.equal(elements.singlePersonPrepare.disabled,true);
assert.equal(elements.singlePersonStart.disabled,true);
status={enabled:true,state:'READY',step:1,current_command_deg:90,history:[]};
context.singlePersonSteeringRender();
assert.equal(elements.singlePersonStart.disabled,false);
elements.singlePersonStart.onclick();
assert.equal(requests.length,0,'Start requires both explicit approval checkboxes');
elements.singlePersonDelegate.checked=elements.singlePersonCentre.checked=true;
elements.singlePersonStart.onclick();
assert.equal(requests[0].action,'single_person_steering');
assert.equal(requests[0].command.op,'start');
assert.equal(requests[0].command.return_center,true);
(async()=>{
 await elements.singlePersonEmergency.onclick();
 assert.equal(requests[1].action,'stop','existing emergency input remains independent of the sequencer');
 assert.equal(requests[2].command.op,'emergency');
 assert(!requests.some(r=>r.command?.op==='heartbeat'),'browser must not own the delegated lease');
 console.log('Stage 17B UI: no auto-start, deployment gate, explicit permissions and independent stop-only emergency passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
