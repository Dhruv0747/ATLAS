/* Evidence controls never start a physical test or release an actuator gate. */
let evidence=null, evidenceBusy=false, evidenceReceived=0;
function evidenceFresh(){return evidence && Date.now()-evidenceReceived<12000;}
function renderEvidence(){
 const ready=evidence?.readiness;
 $('continueCommissioning').disabled=!evidenceFresh();
 $('invalidateEvidence').disabled=!evidenceFresh();
 if(!ready)return;
 $('readinessSummary').textContent=`${ready.state} · PRIMARY BLOCKER: ${ready.primary_blocker}`;
 $('evidenceSummary').textContent=`NEXT SINGLE ACTION: ${ready.next_action} Runtime restrictions: ${ready.blocked.join('; ')||'Separate safety review still required'}. No movement will start from Continue.`;
 $('evidenceRows').innerHTML='<table><tr><th>Property</th><th>Evidence state</th><th>What changed / why retest / what it proves</th></tr>'+evidence.records.map(r=>`<tr><td>${esc(r.title)}</td><td>${esc(r.status)}</td><td>${esc(r.retest_reason|| (r.status==='PASS'?'Retained PASS — do not repeat unless relevant evidence changes':r.status==='OBSERVED'?'Observation retained; not physical qualification':'No qualifying evidence yet'))}${r.invalidated_by?'<br>'+esc(JSON.stringify(r.invalidated_by)):''}<br>${esc(r.next_action)}</td></tr>`).join('')+'</table>';
 const selection=$('invalidateGate').value;
 $('invalidateGate').innerHTML=evidence.records.map(r=>`<option value="${esc(r.gate)}">${esc(r.title)}</option>`).join('');
 if(selection)$('invalidateGate').value=selection;
}
async function pollEvidence(){
 if(evidenceBusy||document.hidden)return;
 evidenceBusy=true;
 try{const r=await fetch('/api/commissioning/evidence',{cache:'no-store',signal:AbortSignal.timeout(5000)});const body=await r.json();if(!r.ok)throw Error(body.error||'Evidence unavailable');evidence=body;evidenceReceived=Date.now();renderEvidence();}
 catch(e){evidence=null;evidenceReceived=0;$('readinessSummary').textContent='EVIDENCE UNAVAILABLE — autonomy blocked';$('evidenceSummary').textContent=e.message;$('continueCommissioning').disabled=true;$('invalidateEvidence').disabled=true;}
 finally{evidenceBusy=false;}
}
$('continueCommissioning').onclick=()=>{
 if(!evidenceFresh())return;
 const step=evidence.readiness.next_required_step, record=evidence.records.find(r=>r.gate===step);
 if(record){location.hash=record.subsystem;$('evidenceMessage').textContent=record.next_action+' This only opens the relevant page; it does not start a test.';}
};
$('invalidateEvidence').onclick=async()=>{
 if(!evidenceFresh())return;
 const record=evidence.records.find(r=>r.gate===$('invalidateGate').value),reason=$('invalidateReason').value.trim();
 if(reason.length<8)return alert('Explain the relevant change; evidence is never invalidated silently.');
 if(!confirm('Mark this property RETEST REQUIRED? No calibration is changed and no test starts.'))return;
 try{await request({action:'invalidate_evidence',gate:record.gate,test_id:record.test_id,reason});$('evidenceMessage').textContent='Change recorded. Previous evidence remains in history.';await pollEvidence();}catch(e){$('evidenceMessage').textContent=e.message;}
};
async function witnessSteering(side){
 if(!evidenceFresh())return alert('Wait for fresh evidence.');
 const record=evidence.records.find(r=>r.gate==='steering_'+side);
 if(record.status==='PASS')return alert('This saved range already has a valid PASS. No repeat needed.');
 const confirmation=prompt(`Only after saving: confirm you physically verified the ${side} centre AND both safe endpoints without binding. Describe your observation. This records your evidence, not a measured wheel angle.`);
 if(!confirmation)return;
 try{await request({action:'verify_steering',side,configuration_hash:record.current_configuration_hash,confirmation});$('evidenceMessage').textContent='Operator verification recorded for the saved configuration. Autonomy remains locked.';await pollEvidence();}catch(e){alert(e.message);}
}
pollEvidence();setInterval(pollEvidence,5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollEvidence();});
