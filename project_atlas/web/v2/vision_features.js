/* Optional feature metadata only. Existing camera preview/lease stays authoritative. */
(() => {
 'use strict';
 const root=document.getElementById('featureCards'),notice=document.getElementById('featureNotice'),cards=new Map();
 const names={face:'Face Detection (no identity)',gesture:'Gesture Recognition',body:'Human Body Tracking (pose)',target:'Target Tracking',object:'Object Detection',mapping:'RGB-D 3D Mapping'};
 const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
 let busy=false,timer;
 // The guard reads /api/status, whose non-blocking cache is empty right after idle: warm it first
 // and keep it warm while a test runs. Read-only GETs; no safety logic lives in this page.
 const warm=()=>fetch('/api/status',{cache:'no-store',signal:AbortSignal.timeout(2000)}).catch(()=>{});
 let warmTimer=null;
 async function action(body){
  if(busy)return;busy=true;
  try{if(body.action==='start'){clearInterval(warmTimer);warmTimer=setInterval(warm,1000);await warm();await new Promise(r=>setTimeout(r,700));await warm();}
const response=await fetch('/api/vision3d/features',{method:'POST',headers:{'Content-Type':'application/json','X-Atlas-Vision3D':'1'},body:JSON.stringify(body),signal:AbortSignal.timeout(body.action==='prepare'||body.action==='end'?25000:3000)});
   const value=await response.json();if(!response.ok)throw Error(value.error||'Feature request failed');render(value);
  }catch(e){notice.textContent=e.message;}finally{busy=false;}
 }
 const prepBar=el('div');prepBar.style.cssText='margin:8px 0 14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap';
 const prep=el('button','Prepare Vision Lab (10 min)');prep.className='btn';prep.type='button';prep.onclick=()=>action({action:'prepare'});
 const endBtn=el('button','End test window now');endBtn.className='btn';endBtn.type='button';endBtn.hidden=true;endBtn.onclick=()=>action({action:'end'});
 const prepInfo=el('span','');prepBar.append(prep,endBtn,prepInfo);root.before(prepBar);
 for(const [id,name] of Object.entries(names)){
  const card=el('article');card.className='feature-card';card.append(el('h3',name));
  const state=el('strong','UNAVAILABLE'),reason=el('p','Awaiting backend'),metrics=el('pre','Measurements unavailable');card.append(state,reason,metrics);
  const buttons={};for(const [key,label] of Object.entries({start:'Start Test',stop:'Stop Test',pass:'Manual PASS',fail:'Manual FAIL'})){
   const b=el('button',label);b.className='btn';b.disabled=true;b.type='button';
   b.onclick=()=>action(key==='start'?{action:'start',feature:id}:key==='stop'?{action:'stop'}:{action:'verdict',feature:id,verdict:key.toUpperCase()});
   buttons[key]=b;card.append(b);
  }
  const download=el('a','Download local test report');download.className='btn';download.hidden=true;download.href='/api/vision3d/feature-report?feature='+id;card.append(download);
  if(id==='body')card.append(el('p','MediaPipe 33-point pose (2D). No distance.'));
  if(id==='face')card.append(el('p','Finds faces only. No identity matching, no face data stored.'));
  if(id==='gesture')card.append(el('p','Hands + gestures: thumbs up/down, victory, fist, pointing, open palm, I-love-you.'));
  root.append(card);cards.set(id,{state,reason,metrics,buttons,download});
 }
 const number=(n,suffix='')=>typeof n==='number'&&Number.isFinite(n)?n.toFixed(2)+suffix:'UNAVAILABLE';
 function render(data){
  const bridgeOff=data.prereq&&data.prereq.foxglove_bridge===false;
  const left=data.prereq?data.prereq.session_left_s:null;
  prep.hidden=!(left==null);endBtn.hidden=(left==null);
  prepInfo.textContent=left==null?'Step 1: press Prepare (turns on the camera bridge and pauses the voice companion, localization monitor, visual-cloud agent, local LLM and shadow LiDAR odometry for 10 min, then restores them automatically).':'Vision Lab ready: '+Math.floor(left/60)+' min '+(left%60)+' s left. Step 2: start the camera above in Infrared + RGB mode. Step 3: Start Test.';
  notice.textContent=(data.active?'Running: '+names[data.active]+' — local guard active':'No feature test running. No automatic starts.')+
   (bridgeOff?' Camera bridge is OFF: press Prepare first.':'')+
   ' Steps: start the camera above in Infrared + RGB mode, keep this page open, then Start Test (30 s).';
  for(const row of data.features){const c=cards.get(row.id);if(!c)continue;const r=row.report,m=row.metrics||{};
   c.state.textContent=row.state;c.reason.textContent=row.reason;c.buttons.start.disabled=!row.start_available||busy||bridgeOff;
   c.buttons.stop.disabled=data.active!==row.id;c.buttons.pass.disabled=!!data.active||!r||r.state!=='READY'||r.frames<2||r.detections_seen<1;
   c.buttons.fail.disabled=!!data.active||!r;c.download.hidden=!r;
   if(!['object','target','gesture','body','face'].includes(row.id))for(const button of Object.values(c.buttons))button.disabled=true;
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
  if(active&&!warmTimer)warmTimer=setInterval(warm,1000);
  if(!active&&warmTimer&&!busy){clearInterval(warmTimer);warmTimer=null;}
  timer=setTimeout(poll,active?1000:3000);
 }
 window.addEventListener('pagehide',()=>clearTimeout(timer));poll();
})();
