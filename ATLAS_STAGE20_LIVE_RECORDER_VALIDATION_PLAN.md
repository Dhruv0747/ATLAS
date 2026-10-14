# Stage 20 live recorder validation preparation — 2026-10-14

## Installation closed; activation blocked

Installation succeeded at 16:12 UTC. Nine installed payload hashes matched the prepared manifest `fd73590a71244541e1e527b5023a5a6f34d80e45ff4e46435954a0eb69732a7b`; the optional user-unit copy also matched. It remains static (no autostart), inactive, PID 0, never started. Production service identities were unchanged. No recording, movement, calibration change or resource bypass occurred.

Rollback/evidence directory:
`/home/jetson/project_atlas/data/backups/20261014T161223Z-stage20-e894fd8a74894292a9480cc0b9bb2309`.
It contains the transaction manifest and copied supervisor/installer evidence. The approved corrected installer remains `/tmp/atlas-stage20-cpu-kHPUKBLO/cpu_candidate/installer/stage20_public_install.py`; explicit rollback uses `--rollback <above directory> --owner-approved-install`, not deletion of historical recordings. No rollback is currently needed.

## Fresh preparation preflight

One bounded admission check at approximately 16:26 UTC; no repeated attempts:

- All nine installed hashes match again; no authorization grant exists.
- Boot: `260efab5-7a80-4d97-85e4-68465df67608`.
- E-STOP latched, source STOPPED, commissioning unarmed; policy age 0.0s.
- Linear/angular commands both zero; command age 0.1s.
- Nav2 and exploration inactive. EKF active PID 3234/restarts 0; localization active PID 11868/restarts 17; motor telemetry active PID 3364/restarts 1. These restart counts are historical, not new restarts.
- Five whole-machine CPU intervals: **79.496, 76.897, 69.257, 72.712, 68.313%**.
- RAM 73.091%; temperature 58.031 C; disk free 394,546,204,672 bytes.
- **Admission refused:** first two intervals exceed 75%. The dashboard's later 70% does not override this refusal.

Consequently no collector activation, comprehensive topic validation, or fresh graph load was attempted. Active services are not proof of valid topic data. LiDAR/IM10A/encoder/EKF/AMCL/TF rates and stamps remain activation-preflight requirements. Thresholds remain CPU 75%, RAM 80%, temperature 70 C, disk reserve 2 GiB. Installation-only success does not qualify recording load.

## Additional preparation finding: 30-second profile mismatch

The installed public collector requires exactly **120 seconds / 500 MiB** (stage20_capture.py lines 142–143). Its installed unit passes duration 120, RuntimeMaxSec 150 and TimeoutStopSec 25. Simply supplying `--duration 30` is rejected. Therefore the requested 30-second profile is **not deployment-ready** and must not be represented as supported by an invented grant.

A shorter duration reduces total output, not necessarily instantaneous CPU. Do not omit critical topics or downsample to claim headroom. An offline exact-30-second profile change with matching unit/grant identity and regression tests is the next preparation item; production remains unchanged. Alternatively an explicitly approved externally supervised early stop would need independent deadline/failure tests before being offered. Neither is executed here.

## Activation procedure after blockers are cleared

1. Qualify the exact bounded profile offline and obtain approval for any required diagnostic-only file/unit update. Preserve current package and rollback.
2. Complete one fresh safety/resource check, full topic availability/stamp check and runtime/map/config/boot identity check. Refuse failed admission, do not poll until a low sample.
3. Ask explicitly: “Approve one supervised 30-second stationary public-topic capture, E-STOP latched, no motion, no autostart?” This report does not request immediate activation because the profile and headroom are not ready.
4. Only after that approval use the existing gate's schema: enabled/owner_approved/deployment_ready, read_only_partial_public, source commit, exact PUBLIC_RUNTIME_FILES hashes, exact map/config identities, current expires_after_boot_session, fresh UUID grant_id. Do not create a grant now, reuse a grant, or substitute private instrumentation. The gate creates an exclusive used marker.
5. Start only the optional installed unit; never enable it. Its current protections include Restart=no, Nice=15, MemoryHigh=128M, MemoryMax=192M, TasksMax=48 and LimitCPU=75. CPUQuota=60% is configured but CPU-controller delegation was previously unavailable; do not claim an enforced 60% quota. These caps are not measured expected resource consumption.
6. Monitor before/during/after CPU mean/p95/max, recorder CPU/RSS, temperature, pressure, disk throughput, queue/drop reports, source/receipt timestamps, critical topic ages and dashboard response. Stop only the collector if thresholds or safety freshness fail. No production restart or E-STOP release.
7. Gracefully close the bag; verify SQLite integrity, topics, gaps, CDR/source/receipt timestamps and hashes; compare service identities and safety afterward. No zero-drop claim solely from application counters. Keep public-only fidelity limitations explicit: no complete private EKF state, relative reference or AMCL RNG state.

## Work remaining toward the actual goal

1. Resolve recording headroom and qualify the bounded stationary profile; then separately approve and validate one real capture.
2. Use existing evidence plus that capture to compare current wheel X/Y pose+velocity fusion against a minimal candidate reducing correlated wheel-pose authority. Preserve frames, timestamps, covariance semantics and working steering. Do not assume a faulty motor/encoder or apply blind scaling/sign changes.
3. Separately approve a small manual forward/reverse/left/right test with roughly 20s stationary before/after, once recording and safety pass. No full-house repetition requested now.
4. Validate moving/stopped localization and then supervised room-to-room navigation/recovery. Neither is passed by installation or static tests.

Known heading/translation inconsistencies and historical parked AMCL jumps remain unresolved. No reliable overall completion percentage or finish date follows from diagnostic installation. The nearest measurable milestone is one safe, integrity-checked stationary recording—not autonomous readiness.
