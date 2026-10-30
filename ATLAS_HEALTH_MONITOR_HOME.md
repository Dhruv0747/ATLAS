# ATLAS Health Monitor homepage navigation — 2026-10-30

Repository preparation only. Added one expandable hm-lab navigation card to the existing V2 homepage and one navigation-only script. Existing controls, CSS, telemetry and safety scripts are unchanged.

The card uses the existing pulse icon and panel/button styling. It initially has no localhost href. Windows platform is only a compatibility hint: explicit per-page confirmation that this PC hosts Grafana is also required. Phone/non-Windows clients remain disabled. Back/forward page restoration clears confirmation. No stored preferences, periodic probes, CORS assumptions or network-security changes.

Destination: http://127.0.0.1:3000/d/atlas-health-monitor/atlas-health-monitor, target=_blank with noopener noreferrer. Only valid from the Windows monitoring host. No remote-phone URL is invented. Availability stays UNVERIFIED because the Jetson page cannot reliably check a different origin on the user's device. Grafana's own authentication, timestamps and unavailable-data indicators remain authoritative. The card explains the Windows/WSL server may be offline.

Validation: `node --test project_atlas/tests/test_health_monitor_navigation.cjs` — 4 passed, 0 failed. Tests cover confirmation/revocation, phone/unknown-client rejection, no background/control calls, truthful status, new-tab attributes and existing navigation/safety elements. Windows localhost Grafana /api/health returned database=ok during preparation. That does not establish healthy rover metrics or access from other clients.

Deployment pending: live homepage contains additional styling (including material.css) absent from this source branch. Do NOT replace the live index.html wholesale. Apply only the reviewed insertion against a fresh hashed live baseline, add health-monitor.js, preserve all unrelated bytes, back up both destinations and validate the rendered homepage. The inspected static route reads files per request, so no rover service restart is expected. If the actual deployment requires one, request owner approval first. Rollback restores only the saved homepage and removes the new script if it was newly created. No PR merge, restart or production edit performed.

Persistent monitoring activation remains a separate approved workflow; this card does not start the exporter, open firewall ports or activate Windows tasks.
