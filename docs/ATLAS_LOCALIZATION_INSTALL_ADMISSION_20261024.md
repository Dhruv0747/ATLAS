# Localization monitor installation admission — 2026-10-24

## Result: blocked before installation

Owner approved one-file installation after safety checks, restarting only
`atlas-localization-monitor.service`, with unchanged safety limits and rollback
on failure. The earlier CPU-report-only exception applied only to the completed
isolated benchmark, not this deployment.

The fresh read-only preflight measured:

- CPU: 75.29215358931553% — FAIL against 75%.
- RAM: 67.12042061945719% — below 80%.
- Maximum temperature: 60.031 C — below 70 C.
- E-STOP latched; manual-only; commissioning disabled; commands zero.
- Required sensors fresh; wheel output commands zero; mission READY.
- Astra OFF and recorder OFF.

The helper checks non-CPU safety separately; those checks passing do not override
its failed CPU result. No automatic resampling to obtain admission was performed.

## Read-only integrity confirmation after abort

Production monitor remains active, PID 1948, restart count 0. Exact live SHA256:

| File under `/home/jetson/project_atlas/scripts/` | SHA256 |
| --- | --- |
| atlas_localization_monitor.py | cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b |
| atlas_dashboard_executor.py | 2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab |
| atlas_dashboard_executor_impl.py | 543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1 |

The approved candidate hash remains
`58e5d86b21e59546cd44e5fcc87d99df910e4e9e9220d1701e24080de393a4da`.
It was NOT installed. No backup creation or installation transaction was begun;
rollback was unnecessary because production was untouched.

Protected service identities observed: camera 1858/0, telemetry 3351/1,
command mux 1852/0, EKF 2982/0, AMCL 8060/7, LiDAR 7887/12,
Dashboard 94624/0, voice 108742/0 and safety reporter 119178/0
(PID/restart count). All were active. Existing historical restart counts are
not restarts performed by this attempt. Voice and white-glass files were unchanged;
no functional voice, steering or camera exercise was performed.

## Evidence and next action

Measurements came from the read-only `safety_scan_recovery_check_20261024.py`
helper over SSH; integrity and monitor identity were then checked using
`sha256sum` and `systemctl --user show`. Tool output is retained in the task
transcript; this report is a transcription, not a new raw telemetry archive.

No code changes or repeated benchmark tests were needed. Prior isolated results
remain in `ATLAS_LOCALIZATION_ARM64_CPU_REPORT_TEST_20261024.md`: median 3.55%
process CPU saving, not a demonstrated whole-Jetson improvement.

There is no post-install CPU comparison because no installation occurred.
Installation remains pending fresh admission and rollback readiness; no service
restart, camera start, recording, motion or production guard change is authorized
by this failure report. Do not automatically retry the failed admission.
