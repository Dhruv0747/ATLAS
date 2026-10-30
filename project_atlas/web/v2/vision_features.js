/* Optional feature metadata only. Existing camera preview/lease stays authoritative. */
(() => {
 'use strict';
 const root=document.getElementById('featureCards'),notice=document.getElementById('featureNotice'),cards=new Map();
 const names={face:'Face Recognition',gesture:'Gesture Recognition',body:'Human Body Tracking',target:'Target Tracking',object:'Object Detection',mapping:'RGB-D 3D Mapping'};
 const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
 let busy=false,timer;
 async function action(body){
  if(busy)return;busy=true;
  try{const response=await fetch('/api/vision3d/features',{method:'POST',headers:{'Content-Type':'application/json','X-Atlas-Vision3D':'1'},body:JSON.stringify(body),signal:AbortSignal.timeout(3000)});
   const value=await response.json();if(!response.ok)throw Error(value.error||'Feature request failed');render(value);
  }catch(e){notice.textContent=e.message;}finally{busy=false;}
 }
 for(const [id,name] of Object.entries(names)){
  const card=el('article');card.className='feature-card';card.append(el('h3',name));
  const state=el('strong','UNAVAILABLE'),reason=el('p','Awaiting backend'),metrics=el('pre','Measurements unavailable');card.append(state,reason,metrics);
  const buttons={};for(const [key,label] of Object.entries({start:'Start Test',stop:'Stop Test',pass:'Manual PASS',fail:'Manual FAIL'})){
   const b=el('button',label);b.className='btn';b.disabled=true;b.type='button';
   b.onclick=()=>action(key==='start'?{action:'start',feature:id}:key==='stop'?{action:'stop'}:{action:'verdict',feature:id,verdict:key.toUpperCase()});
   buttons[key]=b;card.append(b);
  }
  const download=el('a','Download local test report');download.className='btn';download.hidden=true;download.href='/api/vision3d/feature-report?feature='+id;card.append(download);
  if(id==='body')card.append(el('p','Person box tracking only; skeletal pose is not installed.'));
  root.append(card);cards.set(id,{state,reason,metrics,buttons,download});
 }
 const number=(n,suffix='')=>typeof n==='number'&&Number.isFinite(n)?n.toFixed(2)+suffix:'UNAVAILABLE';
 function render(data){
  notice.textContent=data.active?'Running: '+names[data.active]+' — local guard active':'No feature test running. No automatic starts.';
  for(const row of data.features){const c=cards.get(row.id);if(!c)continue;const r=row.report,m=row.metrics||{};
   c.state.textContent=row.state;c.reason.textContent=row.reason;c.buttons.start.disabled=!row.start_available||busy;
   c.buttons.stop.disabled=data.active!==row.id;c.buttons.pass.disabled=!!data.active||!r||r.state!=='READY'||r.frames<2||r.detections_seen<1;
   c.buttons.fail.disabled=!!data.active||!r;c.download.hidden=!r;
   c.metrics.textContent='FPS: '+number(r?.fps)+'\nWhole Jetson CPU: '+number(m.cpu,'%')+'\nWhole Jetson RAM: '+number(m.ram,'%')+'\nTemperature: '+number(m.temperature,' °C')+
    '\nWorker peak RSS: '+number(r?.last_result?.peak_rss_kib/1024,' MiB')+'\nInference CPU time: '+number(r?.last_result?.cpu_s,' s')+
    '\nFrames: '+(r?.frames??'UNAVAILABLE')+'\nSource timestamp ns: '+(r?.last_result?.stamp_ns_exact??'UNAVAILABLE')+
    '\nResults: '+(r?.last_result?JSON.stringify(r.last_result.detections):'UNAVAILABLE');
  }
  const result=data.latest,img=document.getElementById('rgbImage'),canvas=document.getElementById('featureOverlay'),label=document.getElementById('featureOverlayStatus');
  canvas.hidden=true;label.textContent='Overlay unavailable: no matching fresh RGB result';
  if(result&&data.active&&Date.now()/1000-result.received_at<1&&img.complete&&img.naturalWidth===result.width&&img.naturalHeight===result.height&&Math.abs(Number(img.dataset.sourceStamp)-result.stamp_ns/1e9)<.000001){
   canvas.width=result.width;canvas.height=result.height;const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);ctx.strokeStyle='#00f080';ctx.fillStyle='#00f080';ctx.font='16px sans-serif';
   for(const d of result.detections){const [x,y,x2,y2]=d.box;ctx.strokeRect(x,y,x2-x,y2-y);ctx.fillText(d.label+' '+number(d.confidence*100,'%')+(d.track_id?' #'+d.track_id:''),x,Math.max(18,y));}
   canvas.hidden=false;label.textContent='Matched RGB source frame; 2D detection only, distance UNAVAILABLE';
  }
 }
 async function poll(){
  let active=false;
  try{if(!document.hidden&&!busy){const r=await fetch('/api/vision3d/features',{signal:AbortSignal.timeout(2500)});if(!r.ok)throw Error('Feature backend unavailable');const d=await r.json();render(d);active=!!d.active;}}
  catch(e){notice.textContent=e.message;for(const c of cards.values()){c.state.textContent='UNAVAILABLE';c.buttons.start.disabled=true;}}
  timer=setTimeout(poll,active?1000:3000);
 }
 window.addEventListener('pagehide',()=>clearTimeout(timer));poll();
})();
