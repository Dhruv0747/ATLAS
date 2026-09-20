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
  steeringRender();
}
function steeringRender(){
  if(!$('steeringControls'))return;
  const s=steeringState(), mine=live('steering_calibration',1)&&s.session===steeringSession&&s.lease_active;
  $('steeringResult').textContent=live('steering_calibration',1)?`${s.result} · ${s.error||''} · ${s.saving?'SAVING':'owner online'}`:'Steering owner not online — controls unavailable';
  $('steeringDraft').textContent=JSON.stringify({commanded:s.targets,marked:s.draft,saved:s.saved},null,2);
  $('steeringControls').querySelectorAll('[data-jog],[data-mark],#steeringSave,#steeringExit,#steeringReset').forEach(b=>b.disabled=!mine||s.saving);
}
setInterval(async()=>{
  steeringRender();
  if(page!=='steering'||document.hidden||steeringHeartBusy||!live('steering_calibration',1)||steeringState().session!==steeringSession)return;
  steeringHeartBusy=true;try{await steeringSend('heartbeat')}catch{}finally{steeringHeartBusy=false}
},350);
