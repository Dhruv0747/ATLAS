# Approved single UI attempt — FAIL, rollback VERIFIED

Approved candidate from d39c867 was staged and its package/live hashes verified.
Only `/home/jetson/project_atlas/web/v2/vision3d.html` was temporarily replaced.
Served HTML matched the exact candidate (apart from existing home-nav decoration).
All new controls were static/disabled. No services were restarted.

External browser verification timed out waiting for the literal title `Camera off`.
The transaction received FAIL and automatically restored the byte-exact backup.
No retry was performed. Read-only post-rollback browser inspection found title
`Stopped safely`, reason viewer paused/closed, no JavaScript errors and no new
panels. The expectation was too specific for this existing safe OFF state. The
candidate's live desktop/mobile verification did NOT complete; do not call it PASS.

Rollback SHA256:
`1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48`.
Protected HTML-adjacent assets/backend hashes unchanged. All captured atlas-/rover-
user service MainPID, NRestarts and ActiveState values unchanged. Astra summary
OFF/driver_stopped=true. E-STOP latched, manual-only, commission false, XBOX selected,
FlySky drive disabled, commands zero, four encoder deltas zero and LIVE telemetry.

48 guarded observations: CPU peak 65.0171%, RAM peak 63.0%, temperature peak 63.281 C.
No safety limit was relaxed. These are validation-window measurements, not UI
performance savings or incremental overhead estimates.

Jetson evidence/backup:
`/home/jetson/project-atlas-migration/vision-ui-only-20261030/`
contains `rollback.html`, `result.json`, `samples.json`, `services-before.json`,
`protected-hashes.json`, `browser-validation.json`, package files and single-use marker.
PC evidence: sibling work directory `vision-ui-only-review`.

Next action: revise browser verification to accept documented OFF presentations
while separately checking authoritative Astra OFF and existing controls; validate
that change offline. A new deployment attempt requires separate approval. The
used deployment command must NOT be rerun. Original Lab remains at
http://192.168.1.16:8088/v2/vision3d .
