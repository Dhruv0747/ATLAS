'use strict';

// 2026-11-22 "What ATLAS sees": the Nav2 LiDAR gate, direction by direction (display only).
const GATE_COL={lidar:'#2fd47a',astra:'#3d8bff',ultrasonic:'#b06cff',map:'#ffd23f',none:'#ff3b4e'};
const GATE_TXT={lidar:'LiDAR sees it',astra:'Astra camera sees it',ultrasonic:'Ultrasonic sees it',map:'No echo; map or virtual obstacle explains it',none:'NOTHING sees it; Nav2 is stopped if it needs this way'};
function drawGate(g,dpr){
 const gv=data&&data.gate,el=document.getElementById('gate');if(!el)return;
 window.__atlasGate=gv||{};
 if(!gv||gv.state!=='LIVE'){el.innerHTML=`<b>What ATLAS sees:</b> ${gv?(gv.reason||gv.state):'not available'}`;return;}
 const r0=g.r*g.s*1.02,r1=r0+16*dpr;
 for(const it of gv.bins){const a1=it.from_deg*Math.PI/180,a2=(it.from_deg+5)*Math.PI/180;
  ctx.beginPath();ctx.arc(g.cx,g.cy,r1,-Math.PI/2-a1,-Math.PI/2-a2,true);ctx.arc(g.cx,g.cy,r0,-Math.PI/2-a2,-Math.PI/2-a1,false);ctx.closePath();
  ctx.fillStyle=GATE_COL[it.source]||'#888';ctx.globalAlpha=it.source==='lidar'?.55:.95;ctx.fill();ctx.globalAlpha=1;
  if(it.source==='none'){ctx.strokeStyle='rgba(255,59,78,.35)';ctx.lineWidth=1*dpr;const am=-Math.PI/2-(a1+a2)/2;ctx.beginPath();ctx.moveTo(g.cx,g.cy);ctx.lineTo(g.cx+Math.cos(am)*r0,g.cy+Math.sin(am)*r0);ctx.stroke();}}
 for(const o of gv.astra_obstacles||[]){const a=(o.bin*5+2.5)*Math.PI/180,x=-0.05+o.distance_m*Math.cos(a),y=o.distance_m*Math.sin(a);if(Math.hypot(x,y)>g.r)continue;ctx.fillStyle='#3d8bff';ctx.beginPath();ctx.arc(g.cx-y*g.s,g.cy-x*g.s,5*dpr,0,2*Math.PI);ctx.fill();}
 const p=gv.probes||{},chip=(n,k)=>{const x=p[k]||{};return `<span class="gchip ${x.ok?'ok':'bad'}">${n}: ${x.ok?'OK':'STOP'}</span>`;};
 const legend=Object.keys(GATE_COL).map(k=>`<span class="glegend"><i style="background:${GATE_COL[k]}"></i>${GATE_TXT[k]} (${(gv.counts||{})[k]||0})</span>`).join('');
 const deg=b=>{let d=b.from_deg+2.5;if(d>180)d-=360;return d;};
 const side=d=>Math.abs(d)<=20?'ahead':Math.abs(d)>=160?'behind':(d>0?'left':'right')+(Math.abs(d)<70?' front':Math.abs(d)>110?' rear':'');
 const groups=[];for(const it of gv.bins){if(it.source!=='none')continue;const last=groups[groups.length-1];if(last&&last.to===it.bin-1){last.to=it.bin;last.items.push(it);}else groups.push({from:it.bin,to:it.bin,items:[it]});}
 if(groups.length>1&&groups[0].from===0&&groups[groups.length-1].to===71){const f=groups.shift(),l=groups[groups.length-1];l.items=l.items.concat(f.items);l.to=f.to;}
 const rows=groups.map(gr=>{const a=deg(gr.items[0]),b=deg(gr.items[gr.items.length-1]),mid=gr.items[Math.floor(gr.items.length/2)],m=mid.map;
  const where=m?`map ray: ${m.hit==='wall'?'mapped wall/virtual obstacle':m.hit==='unknown'?'UNKNOWN (never mapped)':m.hit} at ${m.distance_m} m → map point (${m.point[0]}, ${m.point[1]})`:'no map position';
  return `<li><b>${gr.items.length>1?a.toFixed(0)+'° to '+b.toFixed(0)+'°':a.toFixed(0)+'°'} (${side((a+b)/2)})</b>, ${gr.items.length*5}° wide. ${where}</li>`;}).join('');
 el.innerHTML=`<b>What ATLAS sees</b> <span class="gsub">(the Nav2 LiDAR safety gate, live)</span><div>${chip('Drive forward','forward')}${chip('Reverse','reverse')}${chip('Turn on the spot','spin')}</div>`+
  `<div class="gsub">Map fallback: ${gv.map_fallback} · location ±${gv.xy_std_m??'--'} m (limit ${gv.limits.pose_max_xy_std_m}) · at most ${gv.limits.map_gap_max_bins} directions may be explained by the map at once · ultrasonic ${Object.entries(gv.ultrasonic_m||{}).map(([k,v])=>k+' '+v+' m').join(', ')||'none fresh'}</div>`+
  `<div>${legend}</div>`+(((gv.counts||{}).map||0)+((gv.counts||{}).none||0)>gv.limits.map_gap_max_bins?`<div class="gwarn">⚠ ${((gv.counts||{}).map||0)+((gv.counts||{}).none||0)} directions have no echo. The gate uses the map for at most ${gv.limits.map_gap_max_bins} of the directions a move needs, so moves that need more of them stop even where the map knows the wall.</div>`:'')+(rows?`<b>Directions nothing sees:</b><ul>${rows}</ul>`:'<p>Every direction is covered right now.</p>')+
  (p.forward&&!p.forward.ok?`<div class="gsub">Gate (forward): ${p.forward.reason}</div>`:'');
}
const canvas=document.getElementById('scan'),ctx=canvas.getContext('2d'),statusEl=document.getElementById('status');
let data=null,received=0,busy=false,selection=null;
function geometry(){const r=Number(document.getElementById('radius').value);return {r,cx:canvas.width/2,cy:canvas.height/2,s:Math.min(canvas.width,canvas.height)*.43/r};}
function draw(){const dpr=Math.min(devicePixelRatio||1,2),rect=canvas.getBoundingClientRect();canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;const g=geometry();ctx.fillStyle='#0b1c29';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.font=`${14*dpr}px system-ui`;ctx.textAlign='center';ctx.strokeStyle='#254654';ctx.fillStyle='#adc9d4';for(let r=g.r/4;r<=g.r;r+=g.r/4){ctx.beginPath();ctx.arc(g.cx,g.cy,r*g.s,0,Math.PI*2);ctx.stroke();ctx.fillText(r+' m',g.cx+8*dpr,g.cy-r*g.s+15*dpr);}ctx.fillText('FRONT +X',g.cx,20*dpr);ctx.fillText('REAR −X',g.cx,canvas.height-10*dpr);ctx.fillText('LEFT +Y',65*dpr,g.cy);ctx.fillText('RIGHT −Y',canvas.width-65*dpr,g.cy);ctx.fillStyle='#4ec8ef';ctx.beginPath();ctx.moveTo(g.cx,g.cy-15*dpr);ctx.lineTo(g.cx-9*dpr,g.cy+12*dpr);ctx.lineTo(g.cx+9*dpr,g.cy+12*dpr);ctx.closePath();ctx.fill();
const live=data&&data.state==='LIVE'&&performance.now()-received<2000;if(!live){statusEl.textContent=data&&performance.now()-received<2000?`${data.state}: ${data.reason||'no current returns'}`:'STALE / DISCONNECTED — no clearance assumed';document.getElementById('directions').textContent='Directional ranges unavailable';drawGate(g,dpr);return;}
drawGate(g,dpr);ctx.fillStyle='#7cf3b8';for(const [x,y] of data.points){if(Math.hypot(x,y)>g.r)continue;ctx.fillRect(g.cx-y*g.s,g.cy-x*g.s,2*dpr,2*dpr);}statusEl.textContent=`LIVE · /scan ${Number(data.hz||0).toFixed(1)} Hz · age ${(data.age_s+(performance.now()-received)/1000).toFixed(2)} s · ${data.valid} valid / ${data.invalid} invalid · base_link`;
const lines=[];
for(const [k,v] of Object.entries(data.closest)){
 const p=data.minima&&data.minima[k],surface=data.surfaces&&data.surfaces[k];
 if(p){const x=g.cx-p.y_m*g.s,y=g.cy-p.x_m*g.s;ctx.strokeStyle='#ffbf69';ctx.lineWidth=2*dpr;ctx.beginPath();ctx.arc(x,y,7*dpr,0,2*Math.PI);ctx.stroke();ctx.fillStyle='#ffbf69';ctx.fillText(k.toUpperCase(),x,y-11*dpr);}
 lines.push(`${k.toUpperCase()} closest: ${v==null?'NO VALID RETURN':v.toFixed(3)+' m'}${p?` · bearing ${(p.bearing_rad*180/Math.PI).toFixed(1)}° · ray #${p.index}\n  Sensor range ${p.raw_range_m.toFixed(3)} m at ${(p.raw_angle_rad*180/Math.PI).toFixed(1)}° in ${data.frame} · ray time ${(data.stamp_s+p.ray_offset_s).toFixed(6)}`:''}\n  Dominant cluster estimate: ${surface?surface.distance_m.toFixed(3)+' m ('+surface.count+' rays; '+surface.angular_span_deg.toFixed(1)+'° span)':'INSUFFICIENT SUPPORT'}`);
}
document.getElementById('directions').textContent=lines.join('\n\n')+`\n\nScan stamp: ${Number(data.stamp_s).toFixed(6)} · source age: ${Number(data.stamp_age_s).toFixed(3)} s`;
}
canvas.addEventListener('click',e=>{if(!data||data.state!=='LIVE'||performance.now()-received>2000)return;const g=geometry(),r=canvas.getBoundingClientRect(),px=(e.clientX-r.left)*canvas.width/r.width,py=(e.clientY-r.top)*canvas.height/r.height;let best=null,dist=20*canvas.width/r.width;for(const p of data.points){const d=Math.hypot(g.cx-p[1]*g.s-px,g.cy-p[0]*g.s-py);if(d<dist){dist=d;best=p;}}document.getElementById('selected').textContent=best?`Selected observation: ${Math.hypot(...best).toFixed(2)} m · ${(Math.atan2(best[1],best[0])*180/Math.PI).toFixed(1)}° (positive left), at ${new Date().toLocaleTimeString()}`:'No observed point near selection';});
async function poll(){if(document.hidden||busy)return;busy=true;try{const r=await fetch('/api/lidar-view',{cache:'no-store',signal:AbortSignal.timeout(1800)});if(!r.ok)throw Error(r.status);data=await r.json();received=performance.now();}catch(e){data=null;}finally{busy=false;draw();}}
setInterval(poll,500);setInterval(()=>{if(!document.hidden)draw();},500);document.getElementById('radius').onchange=draw;window.addEventListener('resize',draw);poll();
