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

## Deployment evidence

Pending installation and browser/live verification. This section will be updated
with installed hashes, rollback path, measured resources and exact limitations.
An installed page is not a passed live camera test.

## Operator test

Open `/v2/vision3d` from Home. Keep ATLAS E-stopped and stationary. Select Depth
only and Start. If RESOURCE BLOCKED, do not bypass the limit; the camera is OFF.
If depth appears, place a flat matte target at a tape-measured1.00m from the
Astra optical reference, square to it, hands out of beam. Click central valid
pixels and compare axial Z; report physical distance and sensor readings.
This is not calibration. Other measured distances follow only within sensor range.
Pause/stop afterward. Do not enable XYZ or colored cloud using fallback values.
