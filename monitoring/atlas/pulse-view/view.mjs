import {stateFor} from './gates.mjs';
import {pollOnce} from './source.mjs';
const offline=new URLSearchParams(location.search).get('offline')==='1';
const topology=await fetch('../grafana/neural_topology.json').then(r=>{if(!r.ok)throw Error('Topology unavailable');return r.json()});
const svg=document.querySelector('svg'),ns='http://www.w3.org/2000/svg';
const colors={FRESH:'#32c48d',IDLE:'#5794f2',STALE:'#ffb357',UNAVAILABLE:'#8e8e93',UNVERIFIED:'#8e8e93'};
function el(name,attrs,parent=svg){const e=document.createElementNS(ns,name);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e;}
const positions=new Map(topology.nodes.map((n,i)=>[n.id,{x:100+(i%4)*280,y:65+Math.floor(i/4)*160}]));
let selected=null,snapshot=null,received=0,lastQuery=-Infinity,paused=matchMedia('(prefers-reduced-motion: reduce)').matches;
const edges=topology.edges.map((e,i)=>{
 const a=positions.get(e.source),b=positions.get(e.target),bend=25+(i%3)*18;
 const path=el('path',{d:`M${a.x},${a.y} Q${(a.x+b.x)/2+bend},${(a.y+b.y)/2-bend} ${b.x},${b.y}`,class:'edge',tabindex:0,'data-edge':e.id,stroke:colors.UNAVAILABLE});
 const pulse=el('circle',{r:4,class:'pulse','data-pulse':e.id,visibility:'hidden'});
 const title=el('title',{},path);title.textContent=e.evidence;
 const inspect=()=>{
  const state=stateFor(e,snapshot,performance.now()-received),t=snapshot?.topics?.[e.topic];
  const measured=state==='FRESH'||state==='IDLE'||state==='STALE';
  const age=measured?t.age+snapshot.queryTime-snapshot.observedTime+(performance.now()-received+snapshot.requestMs)/1000:null;
  document.querySelector('#details').textContent=`${e.source} → ${e.target}: ${state}. Rate: ${measured?t.rate+' Hz':'UNAVAILABLE'}. Age: ${age===null?'UNAVAILABLE':age.toFixed(2)+' s'}. Last observation: ${measured?new Date(snapshot.observedTime*1000).toISOString():'UNAVAILABLE'}. ${e.evidence}`;
 };
 const select=()=>{selected=inspect;inspect()};
 path.addEventListener('click',select);path.addEventListener('keydown',event=>{if(event.key==='Enter')select()});
 return {e,path,pulse,length:path.getTotalLength()};
});
for(const n of topology.nodes){const p=positions.get(n.id);el('rect',{x:p.x-86,y:p.y-24,width:172,height:48,rx:14,class:'node'});const t=el('text',{x:p.x,y:p.y+5,'text-anchor':'middle'});t.textContent=n.title;}
// No credentials in client code. Test injection only in explicitly labelled offline mode.
// Reject repeated/older responses rather than refreshing their expiry.
const input={accept(s){if(!s || !Number.isFinite(s.queryTime) || s.queryTime<=lastQuery){snapshot=null;return false;}lastQuery=s.queryTime;snapshot=structuredClone(s);received=performance.now();return true;},disconnect(){snapshot=null;},topology};
const button=document.querySelector('#motion');
function label(){button.textContent=paused?'Resume visual motion':'Pause visual motion'}
label();button.onclick=()=>{paused=!paused;label()};
let lastFrame=0;
function render(now){
 requestAnimationFrame(render);if(now-lastFrame<50)return;lastFrame=now;
 for(const {e,path,pulse,length}of edges){
  const state=stateFor(e,snapshot,performance.now()-received);path.dataset.state=state;path.setAttribute('stroke',colors[state]);path.setAttribute('aria-label',`${e.id}: ${state}`);
  const active=state==='FRESH'&&!paused&&!document.hidden;
  pulse.setAttribute('visibility',active?'visible':'hidden');
  if(active){const point=path.getPointAtLength((now%1600)/1600*length);pulse.setAttribute('cx',point.x);pulse.setAttribute('cy',point.y);}
 }
 if(selected)selected();
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)for(const {pulse}of edges)pulse.setAttribute('visibility','hidden')});
requestAnimationFrame(render);

const status=document.querySelector('#connection');
if(offline){window.atlasPulseTest=input;status.textContent='OFFLINE TEST DATA — NOT LIVE';}
else{
 let epoch=0,inFlight=false,timer=null,pending=false,online=navigator.onLine;
 status.textContent='Checking authenticated Grafana data…';
 function invalidate(message){
  epoch++;clearTimeout(timer);timer=null;pending=false;selected=null;input.disconnect();
  for(const {e,path,pulse}of edges){
   const state=stateFor(e,null,0);path.dataset.state=state;path.setAttribute('stroke',colors[state]);
   pulse.setAttribute('visibility','hidden');
  }
  document.querySelector('#details').textContent=message;
  status.textContent=message;
 }
 async function poll(){
  clearTimeout(timer);timer=null;
  if(document.hidden||!online)return;
  if(inFlight){pending=true;return;}
  inFlight=true;const generation=epoch;
  try{
   const s=await pollOnce();
   if(generation!==epoch||document.hidden||!online)return; // discard late response
   if(!input.accept(s))throw Error('Repeated/older response');
   status.textContent=s.up===1?`Authenticated observations received; Last observation: ${new Date(s.observedTime*1000).toISOString()}; per-path expiry enforced`:'Exporter unavailable';
  }catch(error){
   if(generation===epoch){input.disconnect();status.textContent='UNAVAILABLE: '+error.message;}
  }finally{
   inFlight=false;
   if(online&&!document.hidden){
    const delay=pending?0:30000;pending=false;timer=setTimeout(poll,delay);
   }
  }
 }
 poll();
 window.addEventListener('offline',()=>{online=false;invalidate('UNAVAILABLE: network offline');});
 window.addEventListener('online',()=>{online=true;invalidate('Checking authenticated Grafana data…');poll();});
 document.addEventListener('visibilitychange',()=>{
  invalidate(document.hidden?'Paused while hidden':'Checking authenticated Grafana data…');
  if(!document.hidden)poll();
 });
}
