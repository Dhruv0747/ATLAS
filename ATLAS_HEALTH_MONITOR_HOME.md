# ATLAS Health Monitor homepage navigation — 2026-10-30

## Targeted live deployment — PASS

Owner-authorized deployment completed without a restart. Only the Health Monitor HTML fragment, script include and new health-monitor.js were installed. The original live homepage differed from the repository by material.css and the FlySky Driving card; both were preserved. Reversing the two inserted byte sequences reconstructs the original live file exactly.

- Original homepage SHA256: `80f905a4bf11d3808c05cb6157c7aeeaf4c51b2d3965348ae52e5a25ead1bff9`
- Installed homepage SHA256: `18b13e5505fedac8d365750af2b08d5be9beb6d48cc70e35276a86f1924d18f0`
- Installed script SHA256: `e7abaff3b26f56dc8bd35e801049a0ad06cd92ffc10ef49993d9713d5d0e3237`
- Backup/evidence: `/home/jetson/project-atlas-migration/health-home-20261030/` (`index.html.before`, before/after service states, result.json).
- Homepage: http://192.168.1.16:8088/v2/ — GET confirms new card, white-glass stylesheet and FlySky Driving card; script GET matches installed bytes.
- Dashboard, command mux, base telemetry, Pi Camera and voice service PID/restart/state observations remained identical. No service restarted, no camera/control command sent.

Focused native Edge browser tests used the captured live homepage and live CSS in isolated request fixtures, with rover requests blocked. Desktop (1440px) and phone (390px) PASS: all old navigation links unchanged, material.css retained, no additional horizontal overflow, confirmation gate, phone disabled. Windows click created a real new tab reaching the private Grafana login route; authentication was not bypassed. Screenshots were inspected as static layout evidence, not live sensor evidence. Earlier four navigation tests remain passing and unchanged.

Rollback: verify current hashes still match this deployment; atomically restore index.html.before to the live index path, verify its original hash, then remove only health-monitor.js if its hash still matches. No web restart is required. Do not restore an old backup over subsequent edits.

The sections below describe the earlier repository preparation; its deployment-pending status is superseded by this result. Persistent monitoring exporter activation is separate and was not performed in this homepage task.

Repository preparation only. Added one expandable hm-lab navigation card to the existing V2 homepage and one navigation-only script. Existing controls, CSS, telemetry and safety scripts are unchanged.

The card uses the existing pulse icon and panel/button styling. It initially has no localhost href. Windows platform is only a compatibility hint: explicit per-page confirmation that this PC hosts Grafana is also required. Phone/non-Windows clients remain disabled. Back/forward page restoration clears confirmation. No stored preferences, periodic probes, CORS assumptions or network-security changes.

Destination: http://127.0.0.1:3000/d/atlas-health-monitor/atlas-health-monitor, target=_blank with noopener noreferrer. Only valid from the Windows monitoring host. No remote-phone URL is invented. Availability stays UNVERIFIED because the Jetson page cannot reliably check a different origin on the user's device. Grafana's own authentication, timestamps and unavailable-data indicators remain authoritative. The card explains the Windows/WSL server may be offline.

Validation: `node --test project_atlas/tests/test_health_monitor_navigation.cjs` — 4 passed, 0 failed. Tests cover confirmation/revocation, phone/unknown-client rejection, no background/control calls, truthful status, new-tab attributes and existing navigation/safety elements. Windows localhost Grafana /api/health returned database=ok during preparation. That does not establish healthy rover metrics or access from other clients.

Deployment pending: live homepage contains additional styling (including material.css) absent from this source branch. Do NOT replace the live index.html wholesale. Apply only the reviewed insertion against a fresh hashed live baseline, add health-monitor.js, preserve all unrelated bytes, back up both destinations and validate the rendered homepage. The inspected static route reads files per request, so no rover service restart is expected. If the actual deployment requires one, request owner approval first. Rollback restores only the saved homepage and removes the new script if it was newly created. No PR merge, restart or production edit performed.

Persistent monitoring activation remains a separate approved workflow; this card does not start the exporter, open firewall ports or activate Windows tasks.
