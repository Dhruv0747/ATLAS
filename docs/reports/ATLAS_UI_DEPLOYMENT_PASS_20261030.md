# Corrected six-panel UI deployment — PASS

One owner-approved attempt using verifier commit 01fa3c6. Fresh package checksums,
live baseline, safety/resources and rollback checks passed. Changed only:
`/home/jetson/project_atlas/web/v2/vision3d.html`.

Installed SHA256:
`6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57`.
Retained rollback SHA256:
`1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48`.

Live Edge/Chromium checks PASS at widths 1440, 768, 390, 320: six cards, all 24
buttons disabled, material.css preserved, original preview/distance/Home elements
present, no horizontal overflow, no JavaScript errors or non-GET browser requests.
Each viewport verified authoritative camera state OFF and driver_stopped=true
before and after checking the existing `Stopped safely` presentation. No real
camera stream test was performed. Safari/Firefox remain untested.

19 safety observations: CPU peak65.2318%, RAM peak62.3856%, temperature peak63.281 C.
E-STOP latched, manual-only, zero commands, all four encoder deltas zero, LIVE
telemetry, XBOX selected and FlySky driving disabled. Controller policy unchanged.
All captured atlas-/rover- user service PIDs, restart counts and states unchanged;
protected JS/CSS/backend hashes unchanged. No service restart, inference, camera
activation, new subscriber, firmware change, movement or PR merge.

Jetson evidence and exact-byte `rollback.html`:
`/home/jetson/project-atlas-migration/vision-ui-corrected-01fa3c6/`.
Includes result, before/after service identities, protected hashes, resource/safety
samples, browser verification and the used single-attempt marker. PC copies are
in sibling directory `vision-ui-corrected-verifier-review`. Do not rerun wrapper.

Rollback remains a separately controlled exact-file restore: require current
installed hash above, verify rollback hash, atomically restore only HTML; no
restart needed. No rollback was needed for this successful attempt.

Verified URL: http://192.168.1.16:8088/v2/vision3d . New panels are UI-only;
feature inference and physical verification remain unavailable pending approval.
