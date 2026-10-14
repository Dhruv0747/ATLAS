/* Explicit steering-only commissioning. Never commands traction or resets stop. */
const steeringSession = Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
let steeringSequence=0, steeringHeartBusy=false;
function steeringState(){return obj('steering_calibration')}
async function steeringSend(op,extra={}){
  return request({action:'steering',command:{op,session:steeringSession,seq:++steeringSequence,...extra}});
}
function steeringTools(){
  const box=document.createElement('div');box.id='steeringControls';
  box.innerHTML='<p>Wheels must be securely lifted; hands and cables clear. Servo degrees are commands, not wheel-angle measurements. Remote B freezes calibration. Browser loss freezes adjustment after 1.5 seconds. Traction remains inhibited until explicit exit.</p><button id="steeringEnter">ENTER STEERING CALIBRATION</button><p id="steeringResult"></p>'+['front','rear'].map(side=>`<fieldset><legend>${side.toUpperCase()} STEERING</legend><button data-jog="-5" data-side="${side}">Right −5°</button><button data-jog="-1" data-side="${side}">Right −1°</button><button data-jog="1" data-side="${side}">Left +1°</button><button data-jog="5" data-side="${side}">Left +5°</button><p>${['center','left','right'].map(point=>`<button data-mark="${point}" data-side="${side}">Mark ${point}</button>`).join('')}</p></fieldset>`).join('')+'<button id="steeringSave">SAVE MARKED CENTRES & LIMITS</button><button id="steeringExit">EXIT & RETURN TO SAVED CENTRES</button><pre id="steeringDraft"></pre>';
  $('tools').appendChild(box);
  for(const side of ['front','rear']){const witness=document.createElement('button');witness.textContent=`RECORD VERIFIED ${side.toUpperCase()} SAVED RANGE`;witness.onclick=()=>witnessSteering(side);box.appendChild(witness);}
  const reset=document.createElement('button');reset.id='steeringReset';reset.textContent='MASTER RESET — DISCARD UNSAVED MARKS';box.appendChild(reset);
  const note=document.createElement('p');note.textContent='Reset preserves saved calibration and does not move steering. Hand movement cannot be detected. PWM torque release is not verified: do not force powered steering.';box.appendChild(note);
  const invoke=async(op,args)=>{try{await steeringSend(op,args)}catch(e){$('steeringResult').textContent=e.message}};
  reset.onclick=()=>{if(confirm('Discard unsaved centre/limit marks and restore saved calibration values? No steering movement and no saved data deletion.'))invoke('reset_draft')};
  $('steeringEnter').onclick=async()=>{
    if(!live('steering_calibration',1))return alert('Updated steering owner is not online yet. No movement requested.');
    if(!obj('control_policy').stop_latched)return alert('Press LATCH DRIVE STOP first, then enter calibration.');
    if(confirm('All wheels securely lifted, hands/cables clear, rover stopped? Entering inhibits traction; it does not reset emergency stop.'))await invoke('enter',{lifted:true});
  };
  box.querySelectorAll('[data-jog]').forEach(b=>b.onclick=()=>invoke('jog',{side:b.dataset.side,step:Number(b.dataset.jog)}));
  box.querySelectorAll('[data-mark]').forEach(b=>b.onclick=()=>invoke('mark',{side:b.dataset.side,point:b.dataset.mark}));
  $('steeringSave').onclick=()=>{if(confirm('Save marked servo centres/limits permanently? Confirm you visually checked the wheels. This does not validate autonomous driving.'))invoke('save',{confirmed:true})};
  $('steeringExit').onclick=()=>{if(confirm('Exit calibration and move steering to saved centres? Traction stop remains latched.'))invoke('exit')};
  singlePersonSteeringTools(box);
  steeringRender();
}
function steeringRender(){
  if(!$('steeringControls'))return;
  const s=steeringState(), mine=live('steering_calibration',1)&&s.session===steeringSession&&s.lease_active;
  $('steeringResult').textContent=live('steering_calibration',1)?`${s.result} · ${s.error||''} · ${s.saving?'SAVING':'owner online'}`:'Steering owner not online — controls unavailable';
  $('steeringDraft').textContent=JSON.stringify({commanded:s.targets,marked:s.draft,saved:s.saved},null,2);
  $('steeringControls').querySelectorAll('[data-jog],[data-mark],#steeringSave,#steeringExit,#steeringReset').forEach(b=>b.disabled=!mine||s.saving);
  singlePersonSteeringRender();
}
setInterval(async()=>{
  steeringRender();
  if(page!=='steering'||document.hidden||steeringHeartBusy||!live('steering_calibration',1)||steeringState().session!==steeringSession)return;
  steeringHeartBusy=true;try{await steeringSend('heartbeat')}catch{}finally{steeringHeartBusy=false}
},350);

// Stage 17B server owns the bounded sequence; this browser never renews its lease.
const stage17BrowserSession=sessionStorage.getItem('atlas-stage17b-client')||Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
sessionStorage.setItem('atlas-stage17b-client',stage17BrowserSession);
function singlePersonSteeringTools(parent){
 const panel=document.createElement('fieldset');panel.id='singlePersonSteering';
 panel.innerHTML=`<legend>Single-Person Front Steering Test</legend>
 <p>Your current Protractor app measures phone tilt. Its 90° value is not a wheel angle. Use the caliper method below, or observe the wheels without contact.</p>
 <p>The existing stop stays latched. Press B to latch, then release the physical B button; do not release the software stop. New B/STOP cancels the sequence. Rear steering stays at its existing centre.</p>
 <label>Mode <select id="singlePersonMode"><option value="caliper">Caliper — pauses after each hold</option><option value="observe">Automatic visual observation — no contact</option></select></label>
 <p>Front PWM commands: 90 → 95 → 100 → 95 → 90 → 85 → 80 → 85 → 90. Each hold is 15 seconds. Maximum: 300 seconds with caliper pauses, 210 seconds in observation mode.</p>
 ${[['lifted','All four wheels securely lifted'],['charger_disconnected','Charger disconnected'],['hands_clear','Hands and cables clear'],['cutoff_ready','Emergency stop and physical power cut-off within reach']].map(([k,l])=>`<label style="display:block"><input type="checkbox" data-single-safe="${k}"> ${l}</label>`).join('')}
 <button id="singlePersonPrepare">PREPARE</button>
 <label style="display:block"><input type="checkbox" id="singlePersonDelegate"> I authorize this bounded local sequence while my phone app is backgrounded or its connection drops. Local owner/safety failures cancel; the maximum duration cannot be extended.</label>
 <label style="display:block"><input type="checkbox" id="singlePersonCentre"> I permit the listed returns to the existing front centre while safety remains valid.</label>
 <button id="singlePersonStart">START APPROVED TEST</button><button id="singlePersonPause">PAUSE FUTURE STEPS</button><button id="singlePersonResume">HANDS CLEAR — RESUME</button><button id="singlePersonCancel">CANCEL — HOLD CURRENT</button><button id="singlePersonEmergency">EMERGENCY STOP</button>
 <p id="singlePersonStatus">Waiting for server capability.</p><p id="singlePersonResult"></p>
 <details><summary>Caliper method and results</summary><p>Do not touch a wheel during automatic steps. In caliper mode, wait for PAUSED and visible stillness, then measure. Remove the caliper and your hands before Resume. Choose two rigid wheel-axis reference points a measured 40–150 mm apart. Measure their signed lateral offsets against one chassis-fixed forward reference. Enter Δy = front point offset minus rear point offset, positive toward rover-left. If there is no repeatable coplanar reference, record the limitation instead of an angle. θ = asin(Δy / measured point-to-point baseline); deflection is relative to the first measured centre. Rubber, chassis-reference and placement errors remain.</p>
 <label>Measured baseline FL <input id="singlePersonLfl" type="number" min="40" max="150" step="0.1"> mm</label> <label>FR <input id="singlePersonLfr" type="number" min="40" max="150" step="0.1"> mm</label>
 <label>Estimated error per offset/baseline <input id="singlePersonError" type="number" min="0.1" max="5" step="0.1" value="1"> mm (not the caliper display resolution)</label>
 <div style="overflow-x:auto"><table><tr><th>Step / PWM</th><th>FL Δy mm</th><th>FR Δy mm</th></tr>${[90,95,100,95,90,85,80,85,90].map((v,i)=>`<tr><td>${i+1} / ${v}</td><td><input style="width:5em" data-single-reading="${i}" data-wheel="front_left" type="number" step="0.1"></td><td><input style="width:5em" data-single-reading="${i}" data-wheel="front_right" type="number" step="0.1"></td></tr>`).join('')}</table></div>
 <button id="singlePersonMeasurements">SAVE OBSERVATIONS — NO CALIBRATION CHANGE</button><pre id="singlePersonMeasurementsResult"></pre></details>
 <details><summary>Timestamped command history</summary><pre id="singlePersonHistory"></pre></details>
 <p>Body-mounted IM10A measures chassis motion, not individual wheel angles. Cancel, safety loss or restart never performs an automatic centering sweep. The steering lock remains until you explicitly re-enter/exit existing manual calibration with hands clear.</p>`;
 parent.appendChild(panel);
 const draftKey='atlas-stage17b-readings';
 const draftFields=()=>[...panel.querySelectorAll('[data-single-reading]'),$('singlePersonLfl'),$('singlePersonLfr'),$('singlePersonError')];
 const storeDraft=()=>sessionStorage.setItem(draftKey,JSON.stringify({test_id:obj('single_person_steering').test_id,values:draftFields().map(b=>b.value)}));
 try{const draft=JSON.parse(sessionStorage.getItem(draftKey)||'null');if(draft&&draft.test_id===obj('single_person_steering').test_id)draftFields().forEach((b,i)=>b.value=draft.values[i]??'');}catch{}
 draftFields().forEach(b=>b.oninput=storeDraft);
 const invoke=async(op,extra={})=>{try{const response=await request({action:'single_person_steering',command:{op,session:stage17BrowserSession,...extra}});$('singlePersonResult').textContent=response.reason||response.state;return response;}catch(e){$('singlePersonResult').textContent=e.message;}};
 $('singlePersonPrepare').onclick=async()=>{const confirmations={};panel.querySelectorAll('[data-single-safe]').forEach(b=>confirmations[b.dataset.singleSafe]=b.checked);const response=await invoke('prepare',{confirmations,mode:$('singlePersonMode').value});if(response){panel.querySelectorAll('[data-single-reading]').forEach(b=>b.value='');sessionStorage.setItem(draftKey,JSON.stringify({test_id:response.test_id,values:draftFields().map(b=>b.value)}));}};
 $('singlePersonStart').onclick=()=>{if(!$('singlePersonDelegate').checked||!$('singlePersonCentre').checked)return alert('Approve the bounded delegation and listed centre returns first.');if(confirm('Start this front-only test? The Jetson continues while you switch phone apps. Keep hands clear; use the physical emergency stop if needed.'))invoke('start',{approved:true,return_center:true});};
 $('singlePersonPause').onclick=()=>invoke('pause');
 $('singlePersonResume').onclick=()=>{if(confirm('Caliper removed and hands/cables clear of steering?'))invoke('resume',{hands_clear:true});};
 $('singlePersonCancel').onclick=()=>invoke('cancel');
 $('singlePersonEmergency').onclick=async()=>{try{await request({action:'stop'});}catch(e){$('singlePersonResult').textContent='Stop request failed; use physical emergency stop. '+e.message;}await invoke('emergency');};
 $('singlePersonMeasurements').onclick=()=>{const readings=Array.from({length:9},()=>({}));panel.querySelectorAll('[data-single-reading]').forEach(b=>readings[Number(b.dataset.singleReading)][b.dataset.wheel]=b.value===''?null:Number(b.value));invoke('measurements',{method:'caliper',readings,baselines:{front_left:Number($('singlePersonLfl').value),front_right:Number($('singlePersonLfr').value)},error_mm:Number($('singlePersonError').value)});};
}
function singlePersonSteeringRender(){
 if(!$('singlePersonSteering'))return;
 const s=obj('single_person_steering'),fresh=live('single_person_steering',2),enabled=fresh&&s.enabled;
 $('singlePersonStatus').textContent=!fresh?'Stage 17B server not deployed/available':!enabled?'DISABLED — deployment approval required':`${s.state} · step ${s.step}/9 · command ${s.current_command_deg} PWM° · countdown/hold ${s.remaining_seconds}s · bounded time remaining ${s.maximum_remaining_seconds}s`;
 $('singlePersonPrepare').disabled=!enabled||!['IDLE','COMPLETE','CANCELLED'].includes(s.state);
 $('singlePersonStart').disabled=!enabled||s.state!=='READY';
 $('singlePersonPause').disabled=!enabled||!['COUNTDOWN','SETTLING','HOLD'].includes(s.state);
 $('singlePersonResume').disabled=!enabled||s.state!=='PAUSED';
 $('singlePersonCancel').disabled=!fresh||['IDLE','COMPLETE','CANCELLED'].includes(s.state);
 $('singlePersonMeasurements').disabled=!fresh||!['COMPLETE','CANCELLED'].includes(s.state);
 $('singlePersonHistory').textContent=JSON.stringify(s.history||[],null,2);
 $('singlePersonMeasurementsResult').textContent=JSON.stringify(s.measurements||{},null,2);
}
