/* ATLAS one-click Stage-3 run page (2026-11-22). Polls /api/stage3; START / Cancel via POST (dashboard only). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const ORDER = ['POSITION', 'SETTLE', 'OUT', 'HOME', 'CHECK', 'DONE'];
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let lastB = false, audio = null;

  function beep() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = 880; o.connect(g); g.connect(audio.destination); g.gain.value = 0.25;
      o.start(); o.stop(audio.currentTime + 0.35);
    } catch (e) { /* sound is optional */ }
    try { navigator.vibrate && navigator.vibrate([300, 150, 300]); } catch (e) { }
  }

  async function post(action) {
    try {
      const r = await fetch('/api/stage3', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' },
        body: JSON.stringify({ action, confirm: 'STAGE3' }) });
      const d = await r.json(); $('msg').textContent = d.message || ('HTTP ' + r.status);
    } catch (e) { $('msg').textContent = 'Could not reach ATLAS: ' + e.message; }
    poll();
  }

  function render(d) {
    const running = !['IDLE', 'DONE', 'CANCELLED', 'ERROR'].includes(d.state);
    $('go').disabled = running; $('go').textContent = running ? 'RUNNING…' : (d.state === 'IDLE' ? 'START STAGE 3 RUN' : 'START AGAIN');
    $('cancel').hidden = !running;
    $('msg').textContent = d.message || '';
    $('pressb').style.display = d.press_b_now ? 'block' : 'none';
    if (d.press_b_now && !lastB) beep();
    lastB = !!d.press_b_now;
    const cur = ORDER.indexOf(d.state);
    document.querySelectorAll('#steps li').forEach(li => {
      const i = ORDER.indexOf(li.dataset.s);
      li.className = cur < 0 ? '' : (i < cur ? 'done' : (i === cur ? 'now' : ''));
      if (li.dataset.s === 'OUT' && d.stop_done) li.textContent = 'Recording · Go hall · safe stop (B) recorded ✓';
    });
    const res = d.result;
    if (res) {
      const rows = Object.entries(res.checks || {}).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="${v.ok ? 'ok' : 'bad'}">${v.ok ? 'PASS' : 'FAIL'}</td><td>${esc(v.detail)}</td></tr>`).join('');
      $('result').innerHTML = `<div class="big ${res.verdict === 'PASS' ? 'ok' : 'bad'}" style="background:${res.verdict === 'PASS' ? '#124d2f' : '#5c1420'}">STAGE 3: ${esc(res.verdict)}</div><table>${rows}</table>` +
        (d.bag ? `<small>Recording: ${esc(d.bag)}</small>` : '');
    } else { $('result').innerHTML = d.bag ? `<small>Recording: ${esc(d.bag)}${d.recording ? ' (running)' : ''}</small>` : ''; }
    $('log').textContent = (d.log || []).map(l => l[1]).join('\n');
  }

  let busy = false;
  async function poll() {
    if (busy) return; busy = true;
    try { const r = await fetch('/api/stage3', { cache: 'no-store', signal: AbortSignal.timeout(2500) }); render(await r.json()); }
    catch (e) { $('msg').textContent = 'Lost contact with ATLAS (the run continues on ATLAS): ' + e.message; }
    finally { busy = false; }
  }
  $('go').onclick = () => {
    if (!confirm('Start the Stage-3 round trip?\n\nATLAS will drive by itself (Go dhruv room if needed, then Go hall and back). Keep the remote in hand. Press B once when PRESS B NOW appears.')) return;
    beep(); post('start');           // beep once on a user tap so the browser allows later sounds
  };
  $('cancel').onclick = () => { if (confirm('Cancel the Stage-3 run? (Use the remote / Abort to stop ATLAS if it is moving.)')) post('cancel'); };
  setInterval(poll, 700); poll();
})();
