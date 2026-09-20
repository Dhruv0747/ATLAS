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
 renderCapabilities();
}
function capabilitiesUnavailable(message){
 $('capabilitySummary').textContent=message+' — no movement authority.';
 for(const id of ['capabilityGoal','capabilityRequirements','capabilityRows','capabilityProfiles'])$(id).textContent='';
}
function renderCapabilities(){
 const c=evidence?.capabilities;
 if(!c||!evidenceFresh())return capabilitiesUnavailable('Capability evidence stale or unavailable');
 if(c.error)return capabilitiesUnavailable(c.error);
 $('capabilitySummary').textContent=`READ-ONLY · ${c.decision} · snapshot ${new Date(evidenceReceived).toLocaleTimeString()}. ${c.runtime_restrictions.join('; ')}`;
 $('capabilityGoal').textContent=`Goal reported by agent: ${c.current_goal_report}. Assessment scenario: ${c.assessment_goal_type} (not a dispatched mission). ${c.goal_retention}.`;
 $('capabilityRequirements').innerHTML='<h3>Required capabilities — room navigation</h3><table><tr><th>Capability</th><th>Observed source components</th><th>Qualification</th></tr>'+c.capabilities.map(r=>`<tr><td>${esc(r.capability)}</td><td>${esc(r.observed_sources.join(', ')||'None verified in this snapshot')}</td><td>${esc(r.state)}<br>${esc(r.reason)}</td></tr>`).join('')+'</table>';
 $('capabilityRows').innerHTML='<h3>Configured sensor usage — telemetry is not authority</h3><table><tr><th>Source / role</th><th>Data / age at snapshot</th><th>Validation</th><th>Consumer / authority</th></tr>'+c.sensors.map(r=>`<tr><td>${esc(r.name)}<br><span class="muted">${esc(r.role)}</span></td><td>${esc(r.health)} · ${r.age_s===null?'unknown':esc(r.age_s.toFixed(2))+' s'}<br>${esc(r.reason)}</td><td>${esc(r.validation)}<br>${esc(r.missing_evidence.join(', '))}</td><td>${esc(r.topic)}<br>${esc(r.consumer)}<br>${esc(r.authority)}</td></tr>`).join('')+'</table>';
 $('capabilityProfiles').textContent=`Approved fallback profiles: NONE. Candidates only: ${c.candidate_profiles.map(p=>p.id+' — '+p.approval).join('; ')}. Authorized speed from this view: 0 m/s. ${c.reason}`;
}
async function pollEvidence(){
 if(evidenceBusy||document.hidden)return;
 evidenceBusy=true;
 try{const r=await fetch('/api/commissioning/evidence',{cache:'no-store',signal:AbortSignal.timeout(5000)});const body=await r.json();if(!r.ok)throw Error(body.error||'Evidence unavailable');evidence=body;evidenceReceived=Date.now();renderEvidence();}
 catch(e){evidence=null;evidenceReceived=0;$('readinessSummary').textContent='EVIDENCE UNAVAILABLE — autonomy blocked';$('evidenceSummary').textContent=e.message;$('continueCommissioning').disabled=true;$('invalidateEvidence').disabled=true;capabilitiesUnavailable('Capability evidence unavailable');}
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
setInterval(()=>{if(!evidenceFresh()){capabilitiesUnavailable('Capability evidence stale');$('continueCommissioning').disabled=true;$('invalidateEvidence').disabled=true;}},1000);
