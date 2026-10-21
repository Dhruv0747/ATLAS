# Stage32 exact-live snapshot optimization — installed and verified

2026-10-21, owner-approved package ae63113. Only
`/home/jetson/project_atlas/scripts/atlas_status_web.py` installed; only
`rover-status-web` restarted. Astra never started. No motor/steering commands,
recording, calibration, USB permission or safety policy changes.

## Hashes and rollback

-Verified original/backup SHA256: `fa62787f94c63b0103c666855cef0175b2c86e40022bf700beebe77e44adbd12`
-Verified package SHA256: `2aa2db41878ae99d6716f4a8fbcedc9582a98381d07a6ab44eb29c5ad3c67160`
-Verified installed SHA256: `98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79`

Backup and durable evidence directory:
`/home/jetson/project-atlas-migration/astra-20261021/snapshot-live-20261021T220006/`
Original file `atlas_status_web.py`, `deployment.json`, `cpu.jsonl` retained there.
Free space394,451,750,912bytes. Backup byte hash verified before atomic replacement;
file mode preserved. No rollback needed: installation and health gates passed.
Rollback if later approved/required: restore this verified backup with metadata,
restart only web, verify original hash, safety, resources and protected services.

The first helper invocation at215945 stopped before installation with
`AssertionError('monitor failed')`: first sample check raced the monitoring thread.
It performed no restart and preserved a verified original backup. Its evidence
remains in `snapshot-live-20261021T215945/`. Helper corrected to wait at most3s
for a completed persistent CPU sample; no limit relaxed. Fresh preflight repeated
before the successful deployment. This was not a camera retry.

## Admission and recovery

Three fresh CPU samples71.9178,70.9122,67.7758%, RAM63.11-63.20%, max60.781C.
E-STOP latched/manual-only, commissioning disarmed, zero cmd_vel and four wheel
output/target commands, mission READY, measured motor speed0, recorder OFF.
LiDAR,IMU,four encoders and Pi Camera freshness passed. Astra absent and previous
RESOURCE BLOCKED state driver_stopped=true; after web restart state OFF and no
Astra driver process. The default OFF summary's driver_stopped=false is not used
as evidence of a running camera; process-absence check also passed.

Persistent1s /proc monitoring began before baseline and restart. Restart peaked
100% (known transient); five below75% samples plus fresh health checks passed
25.085s after restart. No safety configuration or admission threshold changed.
Web PID40386 ->51991, active, NRestarts0 ->0 (explicit restart is not an automatic
restart counter increment). All six protected service identities unchanged:
camera1824,telemetry3293,mux1814,EKF2868,localization4595,LiDAR1815; active,0restarts.

Runtime/core/web Vision Lab, config and both safety probe hashes unchanged.
CPU75%,RAM80%,70C,Domain77 and camera mode settings preserved.

## Parked comparison: NO demonstrated whole-Jetson CPU saving

Same20-sample windows,1s sampling and safety snapshots every5s, Astra OFF.
No added ROS subscriptions. External client traffic/background work not frozen;
short before/after comparison is not a randomized performance experiment.

|Metric|Before mean / peak|After mean / peak|
|---|---:|---:|
|Whole-Jetson CPU|69.270% /72.300%|71.215% /74.959%|
|Web process CPU, ONE core|44.845% /49.825%|45.383% /47.810%|
|RAM|63.191% /63.331%|64.295% /64.360%|
|Highest thermal zone|60.772C /60.875C|60.890C /61.000C|

Whole-machine average increased1.945 percentage points; web average increased
0.538one-core points. Therefore **no actual CPU improvement demonstrated**.
Do not claim offline82% snapshot savings apply to the entire web process or
Jetson. Restart settling/background variation may contribute; cause of this
small before/after difference is unproven. All post-window resource gates passed,
so this was not a health-triggered rollback. Sustained headroom remains unresolved.
Helper process CPU0.368s over67trace samples (includes checks, not only monitor).

## Postflight

Final CPU71.522%,RAM64.341%,max60.812C. E-STOP still latched (remote unavailable),
manual-only,commissioning off,zero commands,recorder OFF,Astra OFF/absent.
Final ages: LiDAR0.2s,IMU0.1s,all encoders0.1s,Pi Camera0.3s,policy0s,cmd_vel0.1s.
Pi Camera age at one post check1.1s, below existing2s criterion.
GET routes /, /v2/, /v2/vision3d, /api/commissioning, /api/vision3d/summary all200.
Steering/HTTP code preserved by exact two-site patch and offline regression;
no live steering or E-STOP-release POST test performed, to avoid motion/state changes.
Safety/telemetry health and protected identities verified, not autonomous qualification.

## Evidence integrity and next step

Deployment JSON SHA256: `30c96a94a3e4fa46480d899f30c5ead3833404a7ef9431b1e0fb0dd68d15e480`
CPU JSONL SHA256: `4704719f46ac93d4651a96220aa91ab83fa2081950ed78fc417448d1bd671915`
Local private copies: artifacts/astra_concurrent_20261021/snapshot-deployed.json
and snapshot-deployed-cpu.jsonl. Raw logs/backups not committed.

No further camera test authorized or performed. Next useful work is explaining
remaining web/executor/background load rather than claiming this micro-optimization
fixed admission. Any further service change or Astra Start needs separate approval.
