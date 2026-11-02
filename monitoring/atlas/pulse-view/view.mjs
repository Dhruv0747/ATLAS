import {stateFor} from './gates.mjs';
const topology=await fetch('../grafana/neural_topology.json').then(r=>{if(!r.ok)throw Error('Topology unavailable');return r.json()});
const svg=document.querySelector('svg'),ns='http://www.w3.org/2000/svg';
const colors={FRESH:'#32c48d',IDLE:'#5794f2',STALE:'#ffb357',UNAVAILABLE:'#8e8e93',UNVERIFIED:'#8e8e93'};
function el(name,attrs,parent=svg){const e=document.createElementNS(ns,name);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e;}
const positions=new Map(topology.nodes.map((n,i)=>[n.id,{x:100+(i%4)*280,y:65+Math.floor(i/4)*160}]));
let snapshot=null,received=0,lastQuery=-Infinity,paused=matchMedia('(prefers-reduced-motion: reduce)').matches;
const edges=topology.edges.map((e,i)=>{
 const a=positions.get(e.source),b=positions.get(e.target),bend=25+(i%3)*18;
 const path=el('path',{d:`M${a.x},${a.y} Q${(a.x+b.x)/2+bend},${(a.y+b.y)/2-bend} ${b.x},${b.y}`,class:'edge',tabindex:0,'data-edge':e.id,stroke:colors.UNAVAILABLE});
 const pulse=el('circle',{r:4,class:'pulse','data-pulse':e.id,visibility:'hidden'});
 const title=el('title',{},path);title.textContent=e.evidence;
 const inspect=()=>{document.querySelector('#details').textContent=`${e.source} → ${e.target}: ${path.dataset.state}. ${e.evidence}`;};
 path.addEventListener('click',inspect);path.addEventListener('keydown',event=>{if(event.key==='Enter')inspect()});
 return {e,path,pulse,length:path.getTotalLength()};
});
for(const n of topology.nodes){const p=positions.get(n.id);el('rect',{x:p.x-86,y:p.y-24,width:172,height:48,rx:14,class:'node'});const t=el('text',{x:p.x,y:p.y+5,'text-anchor':'middle'});t.textContent=n.title;}
// Test seam only. No credentials, network poller, live ingress or ROS subscriptions.
// Reject repeated/older responses rather than refreshing their expiry.
window.atlasPulseTest={accept(s){if(!s || !Number.isFinite(s.queryTime) || s.queryTime<=lastQuery){snapshot=null;return false;}lastQuery=s.queryTime;snapshot=structuredClone(s);received=performance.now();return true;},disconnect(){snapshot=null;},topology};
const button=document.querySelector('#motion');
function label(){button.textContent=paused?'Resume visual motion':'Pause visual motion'}
label();button.onclick=()=>{paused=!paused;label()};
let lastFrame=0;
function render(now){
 requestAnimationFrame(render);if(now-lastFrame<50)return;lastFrame=now;
 for(const {e,path,pulse,length}of edges){
  const state=stateFor(e,snapshot,now-received);path.dataset.state=state;path.setAttribute('stroke',colors[state]);path.setAttribute('aria-label',`${e.id}: ${state}`);
  const active=state==='FRESH'&&!paused&&!document.hidden;
  pulse.setAttribute('visibility',active?'visible':'hidden');
  if(active){const point=path.getPointAtLength((now%1600)/1600*length);pulse.setAttribute('cx',point.x);pulse.setAttribute('cy',point.y);}
 }
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)for(const {pulse}of edges)pulse.setAttribute('visibility','hidden')});
requestAnimationFrame(render);
