/* Navigation only: no network probes, polling, storage or rover-control calls. */
(() => {
  'use strict';
  const confirm = document.getElementById('healthMonitorConfirm');
  const link = document.getElementById('healthMonitorLink');
  const help = document.getElementById('healthMonitorHelp');
  if (!confirm || !link || !help) return;
  const platform = navigator.userAgentData?.platform || navigator.platform || '';
  // Platform is only a compatibility hint, never proof this PC hosts Grafana.
  // Explicit per-page owner confirmation is also required. No persisted consent.
  const windows = /^(Windows|Win32|Win64)$/i.test(platform);
  confirm.checked = false;
  confirm.disabled = !windows;
  if (!windows) help.textContent = 'Localhost link disabled on this device. Open this homepage on the Windows PC running Grafana. Remote access requires a separately reviewed private connection; do not expose Grafana publicly.';
  const update = () => {
    const allowed = windows && confirm.checked;
    link.setAttribute('aria-disabled', String(!allowed));
    link.tabIndex = allowed ? 0 : -1;
    if (allowed) link.href = 'http://127.0.0.1:3000/d/atlas-health-monitor/atlas-health-monitor';
    else link.removeAttribute('href');
  };
  confirm.addEventListener('change', update);
  link.addEventListener('click', event => {
    if (!windows || !confirm.checked) event.preventDefault();
  });
  window.addEventListener('pageshow', () => { confirm.checked = false; update(); });
  update();
})();
