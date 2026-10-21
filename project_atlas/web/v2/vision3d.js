/* Receive-only, same-origin GETs. No ROS control, driver mode changes or recording. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id), api='/api/vision3d/';
  let paused=false,busy=false,timer=null,controller=null,status=null,urls={},imageStamps={},cloud=null,projected=[];
  let yaw=0,pitch=0,zoom=110,pan=[0,0],panning=false,drag=null;
  const canvas=$('cloudCanvas'),ctx=canvas.getContext('2d');
  const fmt=n=>Number.isFinite(n)?n.toFixed(3):'unknown';
  function clearImage(k){$(k+'Image').removeAttribute('src');if(urls[k])URL.revokeObjectURL(urls[k]);delete urls[k];}
  async function get(route){const r=await fetch(api+route,{cache:'no-store',signal:controller.signal});if(!r.ok){let e=await r.json();throw Error(e.error||r.status);}return r;}
  function project(p){const a=p[0]*Math.cos(yaw)+p[2]*Math.sin(yaw),b=-p[0]*Math.sin(yaw)+p[2]*Math.cos(yaw),c=p[1]*Math.cos(pitch)-b*Math.sin(pitch),d=p[1]*Math.sin(pitch)+b*Math.cos(pitch);return [canvas.width/2+a*zoom+pan[0],canvas.height/2+c*zoom+pan[1],d];}
  function draw(){
    canvas.width=Math.max(1,Math.floor(canvas.clientWidth));canvas.height=Math.max(1,Math.floor(canvas.clientHeight));ctx.clearRect(0,0,canvas.width,canvas.height);projected=[];
    ctx.fillStyle='#abc4d6';ctx.font='12px system-ui';
    if(!cloud){ctx.fillText('No fresh 3D data',18,28);return;}
    for(const p of cloud.points){const q=project(p);if(q[0]<0||q[1]<0||q[0]>canvas.width||q[1]>canvas.height)continue;ctx.fillStyle=`hsl(${Math.min(240,p[2]*48)},85%,65%)`;ctx.fillRect(q[0],q[1],2,2);projected.push({q,p});}
    const origin=project([0,0,0]);for(const [label,p,color]of [['X',[.4,0,0],'#ff8f94'],['Y',[0,.4,0],'#87f8b3'],['Z',[0,0,.4],'#85beff']]){const q=project(p);ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(origin[0],origin[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();ctx.fillStyle=color;ctx.fillText(label,q[0]+4,q[1]);}
  }
  function xyzText(p){return `X ${fmt(p[0])} m · Y ${fmt(p[1])} m · Z ${fmt(p[2])} m\nRange ${fmt(Math.hypot(...p))} m`;}
  async function refresh(){
    if(busy||paused||document.hidden)return;busy=true;controller=new AbortController();
    try{
      status=await(await get('status')).json();
      $('sourceNotice').textContent=(status.simulated?'SIMULATED UI TEST — NOT JETSON DATA · ':'')+status.configuration+(status.error?' · '+status.error:'');
      $('mode').replaceChildren(...(status.modes.length?status.modes:['MODE UNSUPPORTED / not verified']).map(m=>{const o=document.createElement('option');o.textContent=typeof m==='string'?m:JSON.stringify(m);return o;}));
      for(const k of ['rgb','depth','ir','cloud']){
        const s=status.streams[k];$(k+'State').textContent=s.state==='ACTIVE'?(k==='cloud'?'3D CLOUD ACTIVE':k.toUpperCase()+' ACTIVE'):(s.state==='STALE'?'STREAM STALE':k.toUpperCase()+' UNAVAILABLE');$(k+'State').classList.toggle('active',s.state==='ACTIVE');
        $(k+'Meta').textContent=`${s.topic||'No approved topic'} · ${s.width||'—'} × ${s.height||'—'} · ${s.encoding||'—'} · ${fmt(s.fps_observed)} Hz · source age ${fmt(s.source_age_s)} s · ${s.frame||'no frame'}`;
        if(k==='cloud')continue;
        if(s.state!=='ACTIVE'){clearImage(k);continue;}
        try{const response=await get('frame?kind='+k),blob=await response.blob();clearImage(k);imageStamps[k]=response.headers.get('X-Source-Stamp');urls[k]=URL.createObjectURL(blob);$(k+'Image').src=urls[k];}catch(e){clearImage(k);$(k+'State').textContent=e.message;}
      }
      if($('showCloud').checked&&status.streams.cloud.state==='ACTIVE'){
        try{cloud=await(await get('cloud')).json();$('obstacles').textContent=JSON.stringify(cloud.shadow_obstacles,null,2);}catch(e){cloud=null;$('cloudMeta').textContent=e.message;}
      }else cloud=null;
      draw();$('diagnostics').textContent=JSON.stringify({usb_inventory:status.usb_verified,usb_note:status.usb_note,depth_validity_sample:status.depth_stats,streams:status.streams,drops:status.dropped_messages,tf:status.tf,detections:status.detections},null,2);
    }catch(e){if(e.name!=='AbortError')$('sourceNotice').textContent='SENSOR ERROR · '+e.message;cloud=null;for(const k of ['rgb','depth','ir'])clearImage(k);draw();}
    finally{busy=false;if(!paused&&!document.hidden)timer=setTimeout(refresh,500);}
  }
  function suspend(){clearTimeout(timer);if(controller)controller.abort();cloud=null;for(const k of ['rgb','depth','ir'])clearImage(k);draw();}
  $('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'Resume viewer':'Pause viewer';if(paused)suspend();else refresh();};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)suspend();else refresh();});window.addEventListener('pagehide',suspend);
  $('depthImage').onclick=async e=>{if(!status||paused)return;const r=e.target.getBoundingClientRect(),s=status.streams.depth,u=Math.floor((e.clientX-r.left)/r.width*s.width),v=Math.floor((e.clientY-r.top)/r.height*s.height);try{const m=await(await get(`pixel?u=${u}&v=${v}&stamp=${encodeURIComponent(imageStamps.depth)}`)).json();$('measurement').textContent=!m.valid?'INVALID DEPTH — no measurement':`Pixel ${u}, ${v} · axial depth ${fmt(m.depth_z_m)} m\n`+(m.xyz_m?xyzText(m.xyz_m):m.xyz_unavailable_reason)+`\nFrame ${m.frame} · source ${m.source_stamp} (selection, not continuous ranging)`;}catch(err){$('measurement').textContent=err.message;}};
  canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,pan:e.shiftKey||panning};canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(drag.pan){pan[0]+=dx;pan[1]+=dy;}else{yaw+=dx*.008;pitch=Math.max(-1.5,Math.min(1.5,pitch+dy*.008));}drag.x=e.clientX;drag.y=e.clientY;draw();};
  canvas.onpointerup=e=>{if(drag&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<5){const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;let best=null,d=12;for(const v of projected){const n=Math.hypot(v.q[0]-x,v.q[1]-y);if(n<d){best=v;d=n;}}if(best)$('measurement').textContent=xyzText(best.p)+`\nFrame ${cloud.frame} · source ${cloud.source_stamp}`;}drag=null;};canvas.onpointercancel=()=>drag=null;
  function scale(f){zoom=Math.max(10,Math.min(1000,zoom*f));draw();}canvas.addEventListener('wheel',e=>{e.preventDefault();scale(e.deltaY<0?1.1:.9);},{passive:false});
  $('zoomIn').onclick=()=>scale(1.2);$('zoomOut').onclick=()=>scale(1/1.2);$('resetView').onclick=()=>{yaw=0;pitch=0;zoom=110;pan=[0,0];draw();};$('panMode').onclick=()=>{panning=!panning;$('panMode').setAttribute('aria-pressed',String(panning));};$('showCloud').onchange=()=>{if(!$('showCloud').checked){cloud=null;draw();}};
  new ResizeObserver(draw).observe(canvas);refresh();
})();
