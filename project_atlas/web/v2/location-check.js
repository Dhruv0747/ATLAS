(function () {
  'use strict';
  const number = (v, digits = 3) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';
  const pose = p => p ? `X ${number(p.x)} m · Y ${number(p.y)} m · heading ${number(p.yaw_deg, 1)}°` : 'Not independently established';
  const ago = v => typeof v === 'number' && Number.isFinite(v) ? (v < 120 ? `${v.toFixed(0)} s ago` : `${(v/60).toFixed(1)} min ago`) : '';
  const STAGES = ['scan','map','odom','imu','policy','cmd','stop','motion','coverage','scan_tf','amcl'];
  function stageLines(stages) {
    if (!stages) return [];
    return STAGES.filter(k => stages[k]).map(k => {
      const st = stages[k], extra = [];
      if (typeof st.age_s === 'number') extra.push(`age ${number(st.age_s,2)} s`);
      if (typeof st.receipt_age_s === 'number') extra.push(`receipt ${number(st.receipt_age_s,2)} s`);
      if (st.frame) extra.push(`frame ${st.frame}`);
      if (st.amcl_status) extra.push(st.amcl_status);
      if (st.reason) extra.push(st.reason);
      if (st.error) extra.push(st.error);
      return `  ${k.padEnd(9)} ${String(st.status).toUpperCase().padEnd(13)} ${st.source || ''}${extra.length ? ' · ' + extra.join(' · ') : ''}`;
    });
  }
  function amclText(e, r) {
    if (r.amcl_pose) return pose(r.amcl_pose);
    if (e.amcl_pose) return pose({x:e.amcl_pose[0],y:e.amcl_pose[1],yaw_deg:e.amcl_pose[2]*180/Math.PI});
    if (e.amcl_status && e.amcl_status !== 'OK') return `${e.amcl_status.replace(/_/g,' ')} — ${e.amcl_reason || 'no usable AMCL pose'}`;
    return 'Not independently established';
  }
  function lines(s) {
    const e = s.evidence || {}, r = s.result || {}, cs = r.candidates || [];
    const block = s.last_block, last = s.last_success;
    const blockIsCurrent = block && (!s.ended_unix || block.at_unix > s.ended_unix) && s.state !== 'CHECKING';
    const out = [
      `State: ${s.state || 'UNAVAILABLE'}${s.code ? ' · ' + s.code : ''}${s.historical_result ? ' — timestamped result, not live navigation permission' : ''}`,
      s.reason || r.reason || '',
      `Request: ${s.request_id || '—'}`,
    ];
    if (blockIsCurrent) {
      out.push(`Last request REJECTED (${ago(block.age_s)}): ${block.code} — ${block.reason}`);
      out.push('Check stages at rejection:', ...stageLines(block.stages));
    }
    out.push(
      `AMCL reference: ${amclText(e, r)}`,
      `Independent LiDAR: ${pose(r.lidar_pose)}${r.lidar_verdict ? ' · ' + r.lidar_verdict.reason : ''}`,
      `XY disagreement: ${number(r.xy_disagreement_m)} m · heading: ${number(r.heading_disagreement_deg,1)}°${r.amcl_pose ? '' : ' (no AMCL pose to compare)'}`,
      `Best held-out fit: ${number(r.best_fit)} · ambiguity margin: ${number(r.margin)} · LiDAR endpoints: ${r.endpoints_used ?? '—'}`,
      ...cs.slice(0,2).map((p,i)=>`Candidate ${i+1}: ${pose(p)} · fit ${number(p.fit_heldout)}`),
      `Candidate separation: ${number(r.candidate_separation?.xy_m)} m / ${number(r.candidate_separation?.heading_deg,1)}°`,
      `Scan timestamp: ${number(e.scan_stamp,6)} · age at capture: ${number(e.scan_age_s)} s`,
      `AMCL timestamp: ${number(e.amcl_stamp,6)} · age at capture: ${number(e.amcl_age_s)} s`,
      `AMCL covariance [x,y,yaw]: ${e.amcl_covariance ? [0,7,35].map(i=>number(e.amcl_covariance[i],5)).join(', ') : '—'}`,
      `Accepted map SHA256: ${e.map_id || '—'}`,
      `Stationary evidence: ${e.stationary === true ? 'confirmed at capture' : 'not confirmed'}`,
      `Calculation: ${number(s.calculation_s)} s · result age: ${number(s.result_age_s,1)} s`,
      `Started: ${s.started_unix ? new Date(s.started_unix*1000).toISOString() : '—'} · completed: ${s.ended_unix ? new Date(s.ended_unix*1000).toISOString() : '—'}`);
    if (s.stages && !blockIsCurrent) out.push('Check stages at rejection:', ...stageLines(s.stages));
    else if (e.stages && !blockIsCurrent) out.push('Check stages at capture:', ...stageLines(e.stages));
    out.push(last ? `Last successful independent check (historical, not a live confirmation): ${last.state} · ${pose(last.lidar_pose)} · fit ${number(last.best_fit)} · margin ${number(last.margin)} · ${ago(last.age_s)}`
                  : 'Last successful independent check: none since the location monitor started');
    out.push(r.score_definition || 'Fit compares held-out LiDAR endpoints with accepted-map walls. High fit alone is not proof of the correct location.',
      'Correction is disabled. This check does not authorize driving. Map distortion or ambiguity can still limit accuracy.');
    return out.filter(Boolean).join('\n');
  }
  if (typeof module !== 'undefined') module.exports = {lines, pose, stageLines};
  if (typeof document === 'undefined') return;
  const style=document.createElement('style');style.textContent=`.atlas-location{margin:10px;padding:12px;border:1px solid #386079;border-radius:12px;background:rgba(8,25,40,.85);color:#eef6ff;font:14px system-ui}.atlas-location .actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.atlas-location button{padding:10px 14px;border:1px solid #48caef;border-radius:8px;background:#103d55;color:white;font:inherit;cursor:pointer}.atlas-location button:disabled{opacity:.5;cursor:wait}.atlas-location pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 system-ui}.atlas-location summary{cursor:pointer;margin-top:8px}.atlas-location small{display:block;margin-top:8px;color:#aac1d2}`;
  document.head.appendChild(style);
  style.textContent+=' .atlas-location .comparison{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:10px}.atlas-location .comparison[hidden]{display:none}.atlas-location .comparison>div{padding:8px;border:1px solid #386079;border-radius:8px;overflow-wrap:anywhere}.atlas-location .comparison span{display:block;margin-top:5px;font-size:12px}';
  const box=document.createElement('section');box.className='atlas-location';box.setAttribute('aria-label','Independent location check');
  box.innerHTML='<div class="actions"><button type="button" data-start>CHECK MY LOCATION</button><button type="button" data-cancel hidden>Cancel current check</button><span data-state role="status" aria-live="polite">Read-only • parked rover only</span></div><small>Keep ATLAS stopped with remote B latched. No driving or pose correction is performed.</small><details><summary>AMCL versus independent LiDAR evidence</summary><pre data-result>No check requested.</pre></details>';
  (document.querySelector('header') || document.body.firstElementChild).insertAdjacentElement('afterend',box);
  const comparison=document.createElement('div');comparison.className='comparison';comparison.hidden=true;
  comparison.innerHTML='<div>AMCL reference<span data-amcl></span></div><div>Independent LiDAR<span data-lidar></span></div>';
  box.querySelector('details').before(comparison);
  const start=box.querySelector('[data-start]'),cancel=box.querySelector('[data-cancel]'),label=box.querySelector('[data-state]'),result=box.querySelector('[data-result]'),details=box.querySelector('details');
  let busy=false,active=false,generation=0,lastWritten=0,expectedId=null,rejected=false;
  function render(s){
    active=s.state==='CHECKING';start.disabled=active||busy;cancel.hidden=!active;
    const blk=s.last_block,blkNow=blk&&(!s.ended_unix||blk.at_unix>s.ended_unix)&&s.state!=='CHECKING';
    label.textContent=blkNow?('REJECTED: '+blk.code.replace(/_/g,' ')):((s.code?s.code.replace(/_/g,' '):(s.state||'UNAVAILABLE'))+(s.historical_result?' (recorded result)':''));
    result.textContent=lines(s);
    const e=s.evidence||{},r=s.result||{};
    comparison.hidden=!e.amcl_pose&&!r.amcl_pose&&!r.lidar_pose&&!e.amcl_status;
    comparison.querySelector('[data-amcl]').textContent=amclText(e,r);
    comparison.querySelector('[data-lidar]').textContent=pose(r.lidar_pose);
  }
  async function request(action){
    if(busy)return;busy=true;rejected=false;start.disabled=true;details.open=true;const g=++generation;
    try{
      const response=await fetch('/api/location-check',{method:'POST',headers:{'Content-Type':'application/json','X-Atlas-Location':'1'},body:JSON.stringify({action}),signal:AbortSignal.timeout(4000)});
      const data=await response.json();if(g!==generation)return;
      rejected=data.accepted===false||!response.ok;
      if(data.accepted && data.request_id)expectedId=data.request_id;
      render(data.error?{state:'UNAVAILABLE',reason:data.error}:data);
    }catch(e){label.textContent='REQUEST UNCONFIRMED';result.textContent='Request acknowledgement unavailable. Check status before retrying. '+e.message;}
    finally{busy=false;start.disabled=active;}
  }
  async function refresh(){
    if(busy||rejected||document.hidden||(!details.open&&!active))return;
    const g=generation;
    try{
      const response=await fetch('/api/location-check',{cache:'no-store',signal:AbortSignal.timeout(2000)});
      if(!response.ok)throw Error(response.status);
      const s=await response.json();if(g!==generation)return;
      if(s.written_unix && s.written_unix<lastWritten)return;
      if(active && expectedId && s.request_id && s.request_id!==expectedId)return;
      lastWritten=s.written_unix||lastWritten;render(s);
    }catch(e){label.textContent='STATUS CONNECTION UNAVAILABLE';}
  }
  start.addEventListener('click',()=>request('start'));cancel.addEventListener('click',()=>request('cancel'));
  details.addEventListener('toggle',refresh);setInterval(refresh,1000);
})();
