/* Read-only diagnostics. Never call motion, reset, or restart endpoints here. */
// Explicit user-confirmed power control; never invoked by diagnostics refresh.
async function shutdownAtlas(){
  if(!confirm('Shut down ATLAS Jetson? Driving and all services will stop. You must power it on physically to reconnect.'))return;
  const button=document.getElementById('shutdownButton');button.disabled=true;
  try{const response=await fetch('/',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','X-Atlas-Wifi':'1'},body:new URLSearchParams({action:'shutdown',confirm:'POWER_OFF_ATLAS'})});const result=await response.json();if(!response.ok||!result.ok)throw Error(result.message||'Shutdown failed');button.textContent='⏻ SHUTDOWN REQUESTED';alert(result.message);}
  catch(error){button.disabled=false;alert(error.message+' — check whether ATLAS is still online.');}
}
function mainBattery(r) {
  let b; try { b=JSON.parse(r.bms_status?.value||'{}'); } catch(_) { b={}; }
  const age=Number(r.bms_status?.age)+Number(b.age_s||0);
  const valid=b.ok===true && Number.isFinite(age) && age<20 && typeof b.soc_percent==='number' && b.soc_percent>=0 && b.soc_percent<=100;
  if(!valid) return {percent:null,state:'DATA STALE / OFFLINE',color:'#a3b1bd'};
  const current=b.current_a;
  const state=typeof current!=='number'||!Number.isFinite(current)?'CURRENT UNKNOWN':current>0.15?'CHARGING':current< -0.15?'DISCHARGING':b.soc_percent>=99?'FULL · IDLE':'IDLE';
  return {percent:b.soc_percent,state,color:b.soc_percent<=20?'#ff5966':b.soc_percent<=40?'#ffcc3d':'#34e58b'};
}
function updateBatteryBadge(r) {
  let el=document.getElementById('mainBatteryBadge');
  if(!el){el=document.createElement('button');el.id='mainBatteryBadge';el.className='batteryBadge';el.onclick=()=>openDetail('telemetry:bms_status');document.querySelector('header').append(el);}
  const b=mainBattery(r),text=b.percent===null?'--%':Math.round(b.percent)+'%';
  el.innerHTML=`<span class="batteryShell"><span class="batteryFill" style="width:${b.percent??0}%;background:${b.color}"></span><span class="batteryBolt">${b.state==='CHARGING'?'ϟ':''}</span></span><span><strong>${text}</strong><small>${b.state}</small></span>`;
  el.title='Main DALY battery · '+text+' · '+b.state+' · tap for details';
  el.setAttribute('aria-label',el.title);
  el.dataset.updated=Date.now();
}
setInterval(()=>{const el=document.getElementById('mainBatteryBadge');if(el && Date.now()-Number(el.dataset.updated)>20000)updateBatteryBadge({});},5000);
const diagEscape = value => String(value ?? '--').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let latestDiagnostics = null, diagnosticBusy = false, diagnosticFetched = 0;
function networkFallbackSummary(net) {
  const f=net.fallback||{}, checks=f.checks||{};
  if(!f.fresh) return '<div class="detail">Automatic network status unavailable / stale. Assigned IP alone does not prove Internet access.</div>';
  return row('Automatic network',diagEscape(f.mode))+
    row('Internet probes',`Wi-Fi ${checks.wifi?.ok?'PASS':'FAIL'} • SIM ${checks.cellular?.ok?'PASS':'FAIL'} (${diagEscape(checks.cellular?.age_s??0)}s ago)`)+
    row('Rescue hotspot',f.hotspot_active?'ATLAS-Rescue • 10.42.0.1:8088':'Standby — starts if both Internet links fail')+
    `<div class="detail">${diagEscape(f.age_s)}s old • Hotspot is local access only.</div>`;
}
function cellularDetails(r, net) {
  const fresh = recent(r,'cell_registration',20), signalFresh=recent(r,'cell_signal',20);
  return networkFallbackSummary(net)+'<div class="rawData">'+diagEscape(
    `REGISTRATION: ${fresh?val(r,'cell_registration'):'STALE / UNKNOWN'}\nDATA SESSION: ${recent(r,'cell_connected',20)?(val(r,'cell_connected',false)?'CONNECTED (reported)':'NOT CONNECTED'):'UNKNOWN'}\nRADIO TECHNOLOGY: ${fresh?val(r,'cell_tech'):'--'}\nOPERATOR: ${fresh?val(r,'cell_operator'):'--'}\nSIGNAL REPORT: ${signalFresh?val(r,'cell_signal')+'%':'STALE / UNKNOWN'}\nREPORT AGE: ${signalFresh?age(r,'cell_signal')+'s':'--'}\n\nMODEM IP: ${net.cell_ip}\nWI-FI IP: ${net.wifi_ip}\nTAILSCALE IP: ${net.tailscale_ip}\nKERNEL SELECTED ROUTE: ${net.route}\n\nSignal quality comes from the existing modem telemetry service and may itself be a modem-cached estimate. It is not proof of SIM registration, antenna performance, or Internet access. This page does not run chargeable speed tests or switch networks.\nInspect Cellular telemetry logs in the Diagnostic Workbench if registration is searching or unknown.`)+'</div>';
}
function gnssInfo(r) {
  let g = {};
  try { g = JSON.parse(val(r, 'gps_diagnostics', '{}')); } catch (_) {}
  const heartbeat = recent(r, 'gps_diagnostics', 3);
  const live = heartbeat && g.nmea_age_s !== null && Number(g.nmea_age_s) < 3;
  const fixed = live && g.fix_valid === true && recent(r, 'gps_fix', 3);
  return {g, heartbeat, live, fixed};
}
function gnssSummary(r) {
  const {g, heartbeat, live, fixed} = gnssInfo(r), fix = val(r, 'gps_fix', {});
  const coordinates = fixed && Number.isFinite(fix.lat) && Number.isFinite(fix.lon) ? `${fix.lat.toFixed(6)}, ${fix.lon.toFixed(6)}` : 'NO CURRENT FIX';
  const safeRow = (a,b) => row(diagEscape(a), diagEscape(b));
  return safeRow('Current receiver', heartbeat ? g.source : 'NO FRESH RECEIVER DIAGNOSTICS') +
    safeRow('1 · NMEA communication', live ? 'LIVE — valid messages' : heartbeat ? g.state : 'STALE / OFFLINE') +
    safeRow('2 · Position fix', fixed ? 'FIXED' : 'NOT FIXED') +
    safeRow('Satellites used in fix', live && g.satellites_used !== null ? g.satellites_used : '--') +
    safeRow('Position', coordinates) + safeRow('NMEA age', heartbeat && g.nmea_age_s !== null ? `${g.nmea_age_s}s` : '--') +
    safeRow('HDOP', live ? g.hdop : '--') +
    `<button class="btn" onclick="openDetail('gps')">GPS / GLONASS DIAGNOSTICS</button>`;
}
function gnssDetails(r) {
  const {g, heartbeat, live, fixed} = gnssInfo(r);
  return gnssSummary(r) + `<div class="rawData">${diagEscape(
    `SOURCE: ${g.source || 'unknown'}\nPORT: ${g.port || '--'}\nCURRENT DEVICE: ${g.resolved_port || '--'}\nSTATE: ${heartbeat ? g.state : 'STALE / OFFLINE'}\nVALID NMEA: ${g.valid_nmea ?? '--'}  INVALID: ${g.invalid_nmea ?? '--'}\nBYTES TOTAL: ${g.bytes_total ?? '--'}  RECONNECTS: ${g.reconnects ?? '--'}\nLAST TRANSPORT ERROR (historical): ${g.last_transport_error || 'none recorded'}\nRECOMMENDED CHECK: ${heartbeat ? g.action : 'CHECK GNSS SERVICE / USB'}\n\nLATEST NMEA: ${live ? g.last_sentence : 'No fresh sentence'}\n\nCommunication ${live ? 'passes' : 'does not pass'}; position fix ${fixed ? 'passes' : 'does not pass'}.\nNMEA message labels do NOT prove that the antenna is working or that any satellite was received. A valid position fix is separate from USB communication. GSV bars show reported satellite counts, not signal strength.\n\n${g.note || ''}`)}</div>`;
}
function diagnosticConstellations(r) {
  const {g, heartbeat, live} = gnssInfo(r);
  return [['GPS','USA'],['GLONASS','RUSSIA'],['BEIDOU','CHINA'],['GALILEO','EUROPE'],['QZSS','JAPAN'],['NAVIC','INDIA']].map(([name,country]) => {
    const v = (g.constellations || {})[name] || {};
    const fresh = live && v.in_view !== null && Number.isFinite(v.in_view) && v.age_s !== null && v.age_s < 6;
    const count = fresh ? v.in_view : 0, label = fresh ? `${count} SAT` : heartbeat ? 'NO FRESH GSV' : 'STALE';
    return `<div class="constellation"><div class="constellation-top"><span>${name} / ${country}</span><span style="color:${count ? '#34e58b' : '#9bb4c8'}">${label}</span></div><div class="satbar"><div class="satfill" style="width:${Math.min(100,count/20*100)}%;background:#34e58b"></div></div><small>${fresh ? `GSV age ${v.age_s}s` : 'No satellite count available'}</small></div>`;
  }).join('');
}
function renderDiagnostics() {
  const panel = $('diagnosticsPanel');
  if (!panel || !panel.open || !latestStatus) return;
  const d = latestDiagnostics, r = latestStatus.ros;
  $('diagState').textContent = d ? `${d.state.toUpperCase()} • OS snapshot ${d.time || '--'} • ${d.cache_age_s ?? '--'}s old` : 'Collecting OS diagnostics…';
  $('diagServices').innerHTML = d ? (d.services || []).map(s => `<tr><td>${diagEscape(s.label)}<small style="display:block">${diagEscape(s.unit)}</small></td><td>${diagEscape(s.active)} / ${diagEscape(s.sub)}<small style="display:block">${diagEscape(s.mode)}</small></td><td>${diagEscape(s.restarts)}</td><td>${diagEscape(s.result)} / ${diagEscape(s.exit_code)}</td><td><button class="btn" onclick="loadDiagnosticLog('${s.unit}')">LOGS</button></td></tr>`).join('') : '';
  const filter = ($('diagFilter').value || '').toLowerCase();
  $('diagTelemetry').innerHTML = Object.entries(r).filter(([k]) => k.toLowerCase().includes(filter)).sort(([a],[b])=>a.localeCompare(b)).map(([key,item]) => {
    const text = typeof item.value === 'string' ? item.value : JSON.stringify(item.value);
    const knownAge = item.age !== null && Number.isFinite(item.age);
    const label = !knownAge ? 'UNKNOWN' : item.age < 10 ? 'RECENT' : 'OLDER';
    return `<tr><td><button class="btn" onclick="openDetail('telemetry:${key}')">${diagEscape(key)}</button></td><td>${label}<br>${knownAge ? item.age+'s' : '--'}</td><td>${item.observed_hz ?? '--'}</td><td>${diagEscape(item.source || 'derived status')}</td><td style="max-width:330px;overflow-wrap:anywhere">${diagEscape(text?.slice(0,180))}<small style="display:block;color:#ffce65">${diagEscape(item.note || '')}</small></td></tr>`;
  }).join('');
  $('diagPorts').textContent = d ? (d.serial_devices || []).map(p => `${p.present?'PRESENT':'MISSING'}  ${p.path}\n → ${p.device}`).join('\n') || 'No by-id devices reported' : 'Collecting…';
  $('diagVersions').textContent = d ? JSON.stringify(d.deployed_sha256 || {},null,2) : '--';
}
async function refreshDiagnostics(force=false) {
  if (!$('diagnosticsPanel')?.open || diagnosticBusy || (!force && Date.now()-diagnosticFetched<10000)) return;
  diagnosticBusy = true;
  try { const response = await fetch('/api/diagnostics',{cache:'no-store'}); if(!response.ok)throw Error(response.status);latestDiagnostics=await response.json();diagnosticFetched=Date.now();renderDiagnostics(); }
  catch(e) { $('diagState').textContent='DIAGNOSTICS UNREACHABLE: '+e.message; }
  finally { diagnosticBusy = false; }
}
async function loadDiagnosticLog(unit) {
  $('diagLog').textContent='Loading '+unit+'…';
  try { const response=await fetch('/api/diagnostics/logs?unit='+encodeURIComponent(unit),{cache:'no-store'});const d=await response.json();$('diagLog').textContent=`${unit}\n${d.note || ''}\n${d.error || ''}\n${d.log || '(no entries)'}`; }
  catch(e) { $('diagLog').textContent='Log request failed: '+e.message; }
}
function downloadDiagnostics() {
  const a=document.createElement('a'), url=URL.createObjectURL(new Blob([JSON.stringify({dashboard:latestStatus,diagnostics:latestDiagnostics},null,2)],{type:'application/json'}));
  a.href=url;a.download='atlas-diagnostics-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
