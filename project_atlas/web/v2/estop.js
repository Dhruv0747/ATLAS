/* ATLAS Glass UI V2 dock E-STOP for pages without a command-center post() helper.
 * Sends exactly the command-center E-STOP request: form POST "/" with action=e_stop.
 * It never sends drive, navigation or release commands. */
(() => {
  'use strict';
  const b = document.getElementById('v2Estop'), msg = document.getElementById('v2EstopMsg');
  if (!b) return;
  // pointerdown, not click: a second-finger tap produces no click while another finger is down.
  const fire = async () => {
    if (msg) msg.textContent = 'Sending stop…';
    try {
      const r = await fetch('/', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                                   body: new URLSearchParams({ action: 'e_stop' }) });
      let j = {}; try { j = await r.json(); } catch (e) { /* non-JSON reply */ }
      if (msg) msg.textContent = r.ok ? (j.message || 'Stop sent.') : `Stop refused (${r.status}): ${j.message || 'use the physical remote stop.'}`;
    } catch (e) {
      if (msg) msg.textContent = 'Control link lost. Use the physical remote stop.';
    }
  };
  let ptrAt = 0;   // a touch tap can also emit a detail-0 click; do not send E-STOP twice
  b.addEventListener('pointerdown', e => { e.preventDefault(); ptrAt = Date.now(); fire(); });
  b.addEventListener('click', e => { if (e.detail === 0 && Date.now() - ptrAt > 1000) fire(); });   // keyboard
})();
