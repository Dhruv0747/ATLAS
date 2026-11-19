# ATLAS read-only 3D Vision Lab deployment — 21 October 2026

Owner scope: Dashboard V2 page + Home shortcut, rover-status-web restart only,
bounded stationary Astra viewing under normal75% CPU/80% RAM/70°C guards.
No movement, recording, autostart, steering, localization or Nav2 changes.

## Candidate prepared

Existing interface reused. Explicit Start selects depth-only160x120 or optional
concurrent RGB320x240; maximum60s and four-second viewer lease. Pausing/hiding/
closing revokes the lease; guardian kills only its own Astra child. Process-death
signal also prevents an orphan camera. No automatic restart after a failed test.
Receive-only existing Foxglove bridge avoids a second DDS discovery participant.

Separate depth/RGB CameraInfo topics are observed as fallback diagnostics only.
All live metric XYZ/range/cloud/registration are hard-blocked, including direct
cloud API requests. Click displays source pixel axial Z, validity and timestamp
with UNCALIBRATED / ACCURACY NOT VERIFIED. No ±3mm claim. No frames saved.
Actual USB-error counters are not available from this adapter; identity/access
checks are not a full USB error monitor. No assertion of complete USB stability.

Scoped installer preserves unrelated live changes: patches only Vision Lab
import/GET/POST hooks, V2 route and Home link against exact live SHA256 baseline.
It does not deploy repository-only single-person steering hooks. Backups cover
every overwritten file and absent-file markers; private rollback rehearsal runs
before touching production. Only rover-status-web may restart. Protected owner
PID/restart counts must remain identical. Unexpected baselines abort.

108 targeted offline tests pass, including synthetic resource failure before
camera launch, lease-EOF owned-child cleanup, calibration-disabled geometry,
request-origin checks and exact rollback restoration. These are not live results.

## Deployment result: PAGE DEPLOYED / LIVE CAMERA RESOURCE BLOCKED

Code checkpoint: `87477d482cc4f52291e316039b84790ecb57199d`. Package:
`vision3d-live-approved-v1.tar.gz`, SHA256
`7b1ac50d5923b3e457291ebf25e7d02c66e1f9f9128b4574a5c3559d6d7f94c2`.
Twelve allowlisted files installed and rehashed with zero mismatches.
The live status-web candidate is a patch of the verified deployed baseline,
not a byte-for-byte copy of repository status-web (unrelated steering additions
intentionally excluded). Backup and fixture rollback rehearsal passed.

Backup: `/home/jetson/project-atlas-migration/vision3d-deploy-20261021-124126/backup`.
Rollback ledger and result: sibling `rollback-ledger.json` and `result.json`.
Manifest of installed hashes: sibling `manifest.json`. Directory timestamp uses
Jetson's clock; no timezone inference from its name.

Only `rover-status-web.service` restarted: PID2149 →67677, NRestarts0 →0,
active afterward. Protected identities unchanged:
Pi camera1982/0, base3534/1, mux1975/0, EKF3260/0, localization5713/1,
LiDAR5523/5 (PID/restart count). Stage20 remains inactive/PID0.

Deployment admission CPU62.65/67.61/63.49%, RAM69%, hottest63.25°C;
E-STOP latched, manual-only, commissioning disarmed, commands zero, mission READY,
measured motor speed0, required Pi/LiDAR/IMU/encoder/drive telemetry fresh.
Existing458 Astra runtime hashes also checked before install.

One explicit Depth-only Start was exercised through the actual browser button.
Three initial guardian samples passed; last CPU69.688%, RAM68.309%, hottest63.312°C.
First post-launch sample reached CPU77.9097% (RAM68.2015%, hottest63.5°C).
Guardian stopped only its Astra child and displayed RESOURCE BLOCKED; no override,
automatic retry or concurrent-mode attempt. No depth/RGB frame reached this viewer.
Actual pixel values, FPS, Astra per-process CPU/RSS and click-to-measure end-to-end
therefore remain UNVERIFIED for this deployment. Existing earlier bounded streams
are separate evidence, not this new guard-constrained pass.

Desktop1366×900 and mobile390×844 were rendered in the actual browser. DOM checks
showed two651.5px columns and one355px column respectively, with scroll width below
viewport width. Screenshots showed no overlap. Original browser size restored.
Home →3D Vision Lab and reverse Home link exercised successfully.
HTTP200: page, JS, status API, Camera, Motor Test Lab, FlySky Test Lab, Mapping;
cloud API409 as required. No actuating controls on those pages were used.
Pause was exercised after the resource abort; it clears the UI and revokes the
viewer lease. Closing/hiding cleanup is covered by offline fixtures/lease design,
not a second live active-camera shutdown trial.

Post-deployment checks CPU62.995/64.344/64.904%, RAM68.17–68.20%, hottest63.312°C;
E-STOP/manual-only/zero/recorder-OFF and fresh required sensors passed. Pi camera
returned HTTP200/27,971-byte valid JPEG in memory; no image saved. No Astra process
remained. No protected owner PID/restart-count change. No autonomous goal issued.
These short samples are not a full load benchmark or endurance qualification.

Artifacts retained locally outside Git:
`artifacts/astra_stationary_20261021/visionlab-install-result.json`,
`visionlab-first-resource-blocked.json`, `visionlab-desktop.png`, `visionlab-mobile.png`.
Only scalar deployment/health state was written on Jetson; no RGB/depth recording.

Page installation is retained because resource blocking is the required safe
behavior, not a dashboard/control regression. Do not call the live viewer passed.
CPU headroom must improve under an approved scoped change before a measured1m
test can yield readings. No owner target arrangement is needed until then.

### Installed SHA256 (under `/home/jetson/project_atlas`)

| File | SHA256 |
|---|---|
| scripts/atlas_vision3d_core.py | `1e4c095d5d2ae76aae528e09aa152f66218d4838855e882f1cb91196a7efe63e` |
| scripts/atlas_vision3d_web.py | `b51a1870b0bb4831fbfa00f70a086a24d513ff0df4b02e99ae928ea6aa1e4e36` |
| scripts/atlas_vision3d_runtime.py | `1803eb363d3dcc95a607dd363248e58c8e3833b7be3abd7f3242d39ec0a20bcf` |
| scripts/atlas_status_web.py | `fa62787f94c63b0103c666855cef0175b2c86e40022bf700beebe77e44adbd12` |
| scripts/atlas_web_v2.py | `cd5b627db687b04cea6507c676ce898f13a0ab5ba3e9ab55312cd46f3cf58819` |
| web/v2/index.html | `f53d68120ecdb82efa0d942ec5519712e283ee511dc02e3b2cbdc88cc12a53c0` |
| web/v2/vision3d.html | `2d5b6bf89756b0d8407feacda1bc3459094e21a50b2631fc918720c2ef4eed68` |
| web/v2/vision3d.css | `f422f69e7d391bbfe66d53de0ab06356bd9e7993495fa77e6869c90cdc345cd5` |
| web/v2/vision3d.js | `d27d6907508fc06c49af1c4181fa44cd68f372fc53e33a70e01685fcf2ce9ab8` |
| config/vision3d_live.json | `d815940f95d9595ede60372a810aed95314ce44ac7ceeeea06421277dd8e6209` |
| tools/vision3d/stationary_gate.py | `880297606b92acfbbca982f5e4ea70e75cf1529f1f321ea9c97cda4b8ea4824f` |
| tools/vision3d/stationary_ros_probe.py | `6fd59f325b97e90df3b6e1902713f0a20155fb4a37581cc136357092bfea7262` |

### Rollback procedure

Keep ATLAS parked/E-stopped. Pause the viewer and confirm no Astra child. Recheck
stationary/resource admission. Use the retained installer module's tested
`restore(LIVE, backup, ledger)` on the exact ledger above; it restores all old
bytes and removes only enumerated newly installed files. Restart only
`rover-status-web.service`, verify original baseline hashes and protected service
identities. Never restore maps/calibration or restart motor/localization owners.
Fixture rollback was executed; no live rollback was needed.

## Operator test

Open `/v2/vision3d` from Home. Keep ATLAS E-stopped and stationary. Select Depth
only and Start. If RESOURCE BLOCKED, do not bypass the limit; the camera is OFF.
If depth appears, place a flat matte target at a tape-measured1.00m from the
Astra optical reference, square to it, hands out of beam. Click central valid
pixels and compare axial Z; report physical distance and sensor readings.
This is not calibration. Other measured distances follow only within sensor range.
Pause/stop afterward. Do not enable XYZ or colored cloud using fallback values.
