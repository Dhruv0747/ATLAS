'use strict';
const canvas=document.getElementById('cloud'),ctx=canvas.getContext('2d'),statusText=document.getElementById('status');
let points=[],yaw=0,pitch=.5,scale=35,panX=0,panY=0,last=null;
function draw(){canvas.width=canvas.clientWidth;canvas.height=canvas.clientHeight;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#167994';const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);for(const p of points){const x=cy*p[0]-sy*p[1],y=sy*p[0]+cy*p[1];ctx.fillRect(canvas.width/2+panX+x*scale,canvas.height/2+panY+(sp*y-cp*p[2])*scale,2,2);}}
async function get(url){const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!r.ok)throw Error('Stored map unavailable');return r.json();}
async function list(){try{const data=await get('/api/map3d/sessions'),s=document.getElementById('sessions');s.replaceChildren();for(const item of data.sessions){const o=document.createElement('option');o.value=item.id;o.textContent=item.id+' — '+item.status.state;s.append(o);}statusText.textContent=data.sessions.length?`${data.sessions.length} local sessions`:'No local maps saved yet. Camera remains unchanged.';}catch(e){statusText.textContent=e.message;}}
document.getElementById('refresh').onclick=list;
document.getElementById('load').onclick=async()=>{try{const id=document.getElementById('sessions').value;if(!id)throw Error('No session selected');const d=await get('/api/map3d/cloud?id='+encodeURIComponent(id));if(!Array.isArray(d.points)||d.points.length>20000||d.points.some(p=>!Array.isArray(p)||p.length!==3||p.some(v=>!Number.isFinite(v))))throw Error('Invalid map points');points=d.points;document.getElementById('label').textContent=d.label||'UNCALIBRATED — DIAGNOSTIC ONLY';statusText.textContent=`${points.length} points · frame ${d.frame} · stored snapshot`;draw();}catch(e){points=[];draw();statusText.textContent=e.message;}};
canvas.onpointerdown=e=>{last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};
canvas.onpointermove=e=>{if(!last)return;const dx=e.clientX-last[0],dy=e.clientY-last[1];if(e.shiftKey){panX+=dx;panY+=dy;}else{yaw+=dx*.01;pitch+=dy*.01;}last=[e.clientX,e.clientY];draw();};
canvas.onpointerup=canvas.onpointercancel=()=>{last=null;};
canvas.onwheel=e=>{e.preventDefault();scale=Math.max(2,Math.min(500,scale*Math.exp(-e.deltaY*.001)));draw();};
window.addEventListener('resize',draw);list();draw();
