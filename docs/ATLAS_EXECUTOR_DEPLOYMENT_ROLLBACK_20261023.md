# Approved Dashboard executor attempt — ROLLED BACK

Owner approved three-file installation, web-only restart, matched parked CPU
comparison and rollback on failed checks. One attempt performed; no retry.

## Preflight and installation

Fresh initial CPU samples72.158%,69.552%,70.216%; RAM below70%, maximum59.968C.
E-STOP latched, manual-only, zero commands, recorder OFF, fresh required sensors,
zero wheel output, mission READY. Essential service identities active. Live web
hash98f3c269 matched the reviewed baseline; new target paths absent;394173509632
bytes free. Local and staged manifest/candidate hashes verified. Astra OFF
verified by existing summary/process checks before modification and during checks.

Persistent low-overhead1s proc CPU monitor started before baseline and restart.
Verified backup retained. Installed only the three approved files, each checked
against the reviewed hash before replacement. Only rover-status-web restarted.
Known restart CPU transients were recorded separately during bounded settling,
not used as camera admission or CPU-saving evidence. Camera was never started.

The new service settled sufficiently for three successive fresh gate passes.
The subsequent measurement failed at77.23440134907251% CPU. The75% threshold was
not raised; the attempt immediately entered the reviewed rollback path.

## Before/after evidence — incomplete comparison

| Metric | Original baseline | Candidate, interrupted |
|---|---:|---:|
| Continuous1s proc samples | 23 | 13 |
| Whole-Jetson CPU mean | 70.8163% | 71.1385% |
| Whole-Jetson CPU peak | 72.6962% | 77.2344% |
| Maximum RAM among completed health samples | 70.6185% | 70.9854% |
| Maximum temperature among completed health samples | 60.187C | 60.5C |

Baseline measured Dashboard process CPU44.2658% of one core over23.404s. The
candidate window aborted before its ending process-CPU measurement, so a valid
candidate Dashboard CPU figure is unavailable. Do not infer it from aggregate
CPU. Baseline health-loop mean70.9508% differs from continuous proc mean because
health queries do not consume every monitor sample. Continuous numbers above
use all phase-tagged samples, including the failing candidate sample.

The failing CPU sample intentionally did not continue RAM/temperature checks;
values above cover completed health samples only. Restart/rollback settling
trace peaked100% and is excluded from the comparison. Windows are unequal due
to abort; this is NOT a successful matched measurement or proof the candidate
caused the spike. Existing aggregate-load variance remains a possible contributor.
No whole-Jetson CPU saving is demonstrated.

## Rollback and final health

Original Dashboard restored byte-for-byte:
`98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79`.
Both newly installed private executor source files removed after candidate-hash
verification. White-glass material.css unchanged:
`ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5`.
Only rover-status-web restarted a second time for rollback. Final PID93159,
ActiveState=active,NRestarts=0 (explicit restarts counted separately, two total).
HTTP `/v2/`, `/v2/vision3d`, `/api/commissioning` each returned200 afterward.

| Protected unit | PID before/after | NRestarts before/after |
|---|---:|---:|
| atlas-camera | 1858 | 0 |
| rover-base-telemetry | 3351 | 1 |
| atlas-cmd-vel-mux | 1852 | 0 |
| atlas-ekf | 2982 | 0 |
| atlas-localization | 8060 | 7 |
| atlas-lidar | 7887 | 12 |

All six remained active and identities unchanged. Rollback health CPU68.2676%,
RAM71.9932%, max60.531C; E-STOP latched, manual-only, commands zero, recorder OFF.
Existing extra-safety/freshness and Astra-OFF checks passed during rollback
settling and final health. No steering, camera movement or drive commands issued.
No calibration, maps, safety thresholds or system ROS libraries changed.

## Evidence and rollback location

Jetson evidence directory:
`/home/jetson/project-atlas-migration/executor-deploy-20261023/executor-deploy-c6a7b2s6/`

- Original backup: `atlas_status_web.original` (verified baseline SHA, mode0664).
- Durable resource/health trace: `trace.jsonl`.
- Outcome: `result.json`, status ROLLED_BACK.
- Staged one-shot deployment script retained in parent directory; do not rerun.

Result SHA256: `3596029899f998b38a48aa2023988f94e415e50965b9003abf762bf8250ae179`.
Trace SHA256: `bdf9b5b60ea0cb40745408a3949686ff1d08e5bcae3baf757fb1fea54e1c253a`.
Private copies retained under local artifacts/executor_benchmark_20261023.
Raw generated logs/backups are not committed. Rollback has already completed;
no further installation is authorized by this report.

## Next action

Keep original production runtime. Do not retry camera or installation. Analyze
retained aggregate CPU evidence and measurement timing offline before proposing
another attempt; this failed gate does not justify relaxing safeguards. Offline
candidate remains available, but its PC improvement did not establish production
resource readiness. White-glass and existing useful functionality preserved.
