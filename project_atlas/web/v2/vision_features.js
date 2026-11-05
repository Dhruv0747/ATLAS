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
 const prep=el('button','Prepare Vision Lab (10 min)');prep.className='btn';prep.style.cssText='font-weight:700;border:2px solid #1f8f4e';prep.type='button';prep.onclick=()=>action({action:'prepare'});
 const endBtn=el('button','End test window now');endBtn.className='btn';endBtn.type='button';endBtn.hidden=true;endBtn.onclick=()=>action({action:'end'});
 const prepInfo=el('span','');prepBar.append(prep,endBtn,prepInfo);root.before(prepBar);
 const fig=document.getElementById('featureOverlay').closest('figure');root.before(fig);
 fig.style.cssText='margin:0 0 16px';
 const strip=el('div');strip.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:10px;margin-bottom:6px';
 const mkWin=(title,cv)=>{const box=el('div');const h=el('div',title);h.style.cssText='font-weight:700;font-size:13px;margin:0 0 4px';
   cv.style.cssText='width:100%;aspect-ratio:4/3;border-radius:10px;background:#05080c;display:block';
   const note=el('div','');note.style.cssText='font-size:12px;opacity:.75;margin-top:3px;min-height:16px';box.append(h,cv,note);strip.append(box);return note;};
 const cvRgb=document.getElementById('featureOverlay');cvRgb.hidden=false;
 const cvIr=document.createElement('canvas'),cvDepth=document.createElement('canvas');
 const noteRgb=mkWin('Colour + results',cvRgb),noteIr=mkWin('Infrared',cvIr),noteDepth=mkWin('Depth (uncalibrated preview)',cvDepth);
 fig.prepend(strip);
 const blank=(cv,msg,note)=>{cv.width=320;cv.height=240;const c=cv.getContext('2d');c.fillStyle='#05080c';c.fillRect(0,0,320,240);note.textContent=msg;};
 // Small previews refresh once a second while the camera is live (read-only GETs that also keep the viewer lease).
 let pv=false;
 async function previews(){
  if(pv||document.hidden)return;pv=true;
  try{
   const st=document.getElementById('runtimeState');const liveCam=st&&/Live/.test(st.textContent);
   if(!liveCam){blank(cvIr,'Camera off',noteIr);blank(cvDepth,'Camera off',noteDepth);return;}
   const ir=await fetch('/api/vision3d/raw?kind=ir',{cache:'no-store',signal:AbortSignal.timeout(1500)});
   if(ir.ok){const w=+ir.headers.get('X-Width'),h=+ir.headers.get('X-Height'),step=+ir.headers.get('X-Step'),enc=ir.headers.get('X-Encoding');
     const b=new Uint8Array(await ir.arrayBuffer());const sw=w/2|0,sh=h/2|0;cvIr.width=sw;cvIr.height=sh;const c=cvIr.getContext('2d'),im=c.createImageData(sw,sh);
     const px=(x,y)=>enc==='mono8'?b[y*step+x]:(b[y*step+2*x]|(b[y*step+2*x+1]<<8))/16;
     let lo=255,hi=0;for(let i=0;i<4000;i++){const v=px((Math.random()*w)|0,(Math.random()*h)|0);if(v<lo)lo=v;if(v>hi)hi=v;}
     for(let y=0;y<sh;y++)for(let x=0;x<sw;x++){let v=(px(2*x,2*y)-lo)*255/Math.max(1,hi-lo);v=v<0?0:v>255?255:v;const k=(y*sw+x)*4;im.data[k]=im.data[k+1]=im.data[k+2]=v;im.data[k+3]=255;}
     c.putImageData(im,0,0);noteIr.textContent=w+'×'+h+' '+enc;}
   else blank(cvIr,'Not in this camera mode (use Infrared + RGB)',noteIr);
   const dp=await fetch('/api/vision3d/frame?kind=depth',{cache:'no-store',signal:AbortSignal.timeout(1500)});
   if(dp.ok){const bm=await createImageBitmap(await dp.blob());cvDepth.width=bm.width;cvDepth.height=bm.height;cvDepth.getContext('2d').drawImage(bm,0,0);noteDepth.textContent=bm.width+'×'+bm.height+' · distances not calibrated';}
   else blank(cvDepth,'Not in this camera mode (Astra IR and depth share one sensor; use a Depth mode)',noteDepth);
  }catch(e){}finally{pv=false;}
 }
 setInterval(previews,1000);
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
   const needPrep=bridgeOff&&row.start_available&&!r;
   c.state.textContent=needPrep?'READY — press Prepare first':row.state;
   c.reason.textContent=needPrep?'Installed and working. Press “Prepare Vision Lab” above, start the camera (Infrared + RGB), then Start Test.':row.reason;c.buttons.start.disabled=!row.start_available||busy||bridgeOff;
   c.buttons.stop.disabled=data.active!==row.id;c.buttons.pass.disabled=!!data.active||!r||r.state!=='READY'||r.frames<2||r.detections_seen<1;
   c.buttons.fail.disabled=!!data.active||!r;c.download.hidden=!r;
   if(!['object','target','gesture','body','face'].includes(row.id))for(const button of Object.values(c.buttons))button.disabled=true;
   c.metrics.textContent='FPS: '+number(r?.fps)+'\nWhole Jetson CPU: '+number(m.cpu,'%')+'\nWhole Jetson RAM: '+number(m.ram,'%')+'\nTemperature: '+number(m.temperature,' °C')+
    '\nWorker peak RSS: '+number(r?.last_result?.peak_rss_kib/1024,' MiB')+'\nInference CPU time: '+number(r?.last_result?.cpu_s,' s')+
    '\nFrames: '+(r?.frames??'UNAVAILABLE')+'\nSource timestamp ns: '+(r?.last_result?.stamp_ns_exact??'UNAVAILABLE')+
    '\nResults: '+(r?.last_result?JSON.stringify(r.last_result.detections):'UNAVAILABLE');
  }
  const result=data.latest,img=document.getElementById('rgbImage'),canvas=document.getElementById('featureOverlay'),label=document.getElementById('featureOverlayStatus');
  // Live test window: latest camera picture with the newest result drawn on it. Boxes come from the frame the
  // model saw (age shown); 2D only, no distance. Nothing is stored.
  const live=img.complete&&img.naturalWidth>0&&/Live/.test((document.getElementById('runtimeState')||{}).textContent||'');
  if(!live){canvas.width=320;canvas.height=240;const c0=canvas.getContext('2d');c0.fillStyle='#05080c';c0.fillRect(0,0,320,240);label.textContent=data.active?'Waiting for camera picture (start the camera above).':'Start the camera above to see the live windows. Results are drawn here during a test.';return;}
  if(!data.active){canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;canvas.getContext('2d').drawImage(img,0,0);label.textContent='Camera live. Press Start Test on a feature to see its results drawn here.';return;}
  const W=result?result.width:img.naturalWidth,H=result?result.height:img.naturalHeight;
  canvas.width=W;canvas.height=H;const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,W,H);
  const age=result?Date.now()/1000-result.received_at:null;
  if(!result||age>3){label.textContent='Live: '+names[data.active]+' running — waiting for first result…';return;}
  ctx.lineWidth=2;ctx.font='bold 13px sans-serif';
  for(const d of result.detections){const [x,y,x2,y2]=d.box;ctx.strokeStyle=ctx.fillStyle='#00e676';ctx.strokeRect(x,y,x2-x,y2-y);
   const t=(d.label||'')+(d.hand?' ('+d.hand+')':'')+' '+Math.round((d.confidence||0)*100)+'%'+(d.track_id?' #'+d.track_id:'');
   const tw=ctx.measureText(t).width;ctx.fillStyle='rgba(0,0,0,.65)';ctx.fillRect(x,Math.max(0,y-16),tw+6,16);ctx.fillStyle='#00e676';ctx.fillText(t,x+3,Math.max(12,y-4));
   if(d.keypoints){ctx.fillStyle='#ffca28';for(const [kx,ky,v] of d.keypoints)if(v>=.5){ctx.beginPath();ctx.arc(kx,ky,2.5,0,6.3);ctx.fill();}}}
  label.textContent='Live: '+names[data.active]+' — '+(result.detections.length?result.detections.length+' found: '+result.detections.map(d=>d.label).join(', '):'nothing found in this frame')+' · result '+age.toFixed(1)+' s old · '+Math.round(result.inference_s*1000)+' ms per frame';
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
