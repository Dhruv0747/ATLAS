# Parked CPU repair and manual-only verification — 15 October 2026

## Verified changes

Live manual-only override drifted to `ATLAS_MANUAL_ONLY=0` although the repository
specifies 1. Restored 1 and restarted only the command mux (PID 36065). General
Nav2/web/Foxglove driving is rejected; existing bounded commissioning/recovery
interfaces still exist, but commissioning is disarmed and E-STOP remains latched.
No remote conditioning or steering calibration changed.

The AI annotator rendered and JPEG-encoded previews with no subscribers.
It now skips only that unused rendering; inference and structured detections
continue. A viewer reconnect resumes previews on the next normal callback.
Only the annotator was restarted (PID 36631). Installed source SHA256:
`8c3a06c9ff6361f1d96c34d41e781fc194c69924679d68c3f0d2de1fd7e08714`.

## Measurements and limits

Whole-system CPU uses /proc/stat deltas, excluding idle/iowait without double
counting guest. Per-process percentages below use one CPU core as 100%.

| Window | System mean / peak | AI process | RAM | Maximum temperature |
| --- | --- | --- | --- | --- |
| Before, 20 seconds | 70.00 / 73.52% | 14.08% | 65.16% | 61.125 C |
| After AI patch, 60 seconds | 70.86 / 79.87% | 9.49% | 65.57% | 59.906 C |
| Diagnostic quota trial, 60 seconds | 69.27 / 77.78% | 9.21% | 68.99% | 60.531 C |

AI process cost fell approximately 33%; whole-system sustained headroom is NOT
resolved. Windows differ and do not prove a total CPU improvement. Startup also
showed a dashboard CPU sample of 87%. Suggest-only localization searches account
for some, not all, peaks. A runtime 25% CPUQuota trial did not remove peaks;
restored original 60% quota without restart (monitor PID 2015 unchanged).
No diagnostic quota is made permanent. No essential service was stopped.

Final five-second check at 04:29:59 UTC: CPU 68.43–71.45%, RAM 69.93%, maximum
temperature 60.5 C; resource/safety probe passed its scoped check, with sensor
admission still pending. This does NOT override longer-window CPU excursions.
75% CPU / 80% RAM / 70 C safeguards remain unchanged. Recording remains OFF.

## Verification and remaining work

19 offline tests passed: five preview-demand tests, six stop-hold tests, five
mapping/manual-source tests, three startup-observation tests. Syntax compilation
passed. Initial mux postflight caught transient stale DDS telemetry; preserved
that failure ledger and verified fresh stopped telemetry separately, without a
second restart. Installer now waits boundedly for stale startup telemetry only;
unsafe values fail immediately. SSH briefly timed out; no networking change.

Final evidence: latched E-STOP, zero commands, manual-only true, commissioning
false; recorder inactive/PID 0. Base, EKF, AMCL, LiDAR, IMU and camera service
identities and protected driver/calibration hashes were preserved. No movement,
recording, map change, localization reseed or steering command was issued.
Suggest-only localization remains DEGRADED/ambiguous: not navigation validation.
Further CPU profiling must isolate remaining peaks before recording admission;
do not lower thresholds or cap control services to force a pass.

## Evidence and rollback

Local raw evidence (not committed): `artifacts/cpu_manual_only_20261015/`.
Jetson backups under `/home/jetson/project_atlas/data/backups/`:

- `20261015_cpu_manual_be2989ab`: original override and transaction ledger.
- `20261015_cpu_annotator_464cb89d`: original annotator and transaction ledger.
- `20261015_cpu_search_c4afbbd4`: original unit, quota trial ledger/resource data.

Annotator rollback: restore its backed-up original to
`scripts/ai_annotator_node.py`, then restart only `atlas-ai-annotator.service`.
Manual override rollback requires restoring its original, user daemon-reload and
mux restart; do NOT restore manual-only=0 without a separate safety decision.
Quota rollback already completed: `systemctl --user set-property --runtime
atlas-localization-monitor.service CPUQuota=60%`. No autostart recording added.
