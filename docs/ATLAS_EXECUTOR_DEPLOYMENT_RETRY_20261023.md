# Dashboard executor deployment retry — 2026-10-23

## Result and authorization

DEPLOYED; safety/sensor health verified. Owner explicitly authorized one retry
with installation CPU reporting instead of the installation CPU abort. This did
not change the production 75% CPU, 80% RAM, 70 C or camera admission guards.
Only rover-status-web restarted. Astra and recording remained OFF, E-STOP
latched, manual-only enabled, commissioning disabled and commands zero.
No movement, steering, UI, navigation or global ROS changes were made.

This supersedes the deployment status, not the evidence, of the earlier rolled
back attempt. The earlier failure is preserved in its separate report.

## Exact package and installed SHA256

Reviewed package: 37c32940b113eb9d84b73751902b1933a547d28e.
Manifest: `463e0850fc79a22231560cb86ba292a737d7a4938f969dc6e40709d4dd5417c3`.
Paths below are relative to `/home/jetson/project_atlas/scripts/`.

| File | Installed SHA256 |
|---|---|
| atlas_status_web.py | acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439 |
| atlas_dashboard_executor.py | 2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab |
| atlas_dashboard_executor_impl.py | 543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1 |

Fresh baseline matched `98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79`.
Backup verified before replacement. Installed hashes independently checked again.
White-glass CSS unchanged: `ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5`.
Stationary gate and ROS probe hashes unchanged:
`0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9`,
`f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd`.

## Measured parked comparison

Same 20-sample health-check workload before and after; monitoring began before
restart. Post window followed at least 30 seconds settling and successful checks.

| Metric | Before | After |
|---|---:|---:|
| Window duration, seconds | 23.53 | 23.34 |
| Whole-Jetson CPU average, % | 71.218 | 71.100 |
| Whole-Jetson CPU peak, % | 73.289 | 73.993 |
| Dashboard process CPU, % of one core | 46.869 | 44.652 |
| Maximum RAM, % | 71.100 | 71.662 |
| Maximum sampled temperature, C | 60.343 | 60.562 |

Observed Dashboard reduction is 2.218 one-core percentage points (4.73% relative).
Whole-system average fell only 0.118 percentage points; peak increased. These
short sequential windows do NOT establish significant whole-Jetson savings or
sufficient Astra startup headroom. Restart/settling trace reached 100% CPU;
that transient is retained, not included in parked means or hidden as a pass.
CPU exception applied only to this deployment observer. No Astra test authorized.

## Verification

Reused completed 66 offline regression tests, including QoS, concurrent shutdown,
cancellation, package integrity and byte-for-byte rollback rehearsal; no redundant
rerun. Live hash checks, HTTP routes `/v2/`, `/v2/vision3d`,
`/api/vision3d/summary`, `/api/commissioning`, sensor freshness and safety checks
passed. No physical steering or motor test was performed.

Protected PIDs/restart counts unchanged and active before/after:
Pi Camera 1858/0; telemetry 3351/1; command mux 1852/0; EKF 2982/0;
localization 8060/7; LiDAR 7887/12. Web changed 93159 to 94624, restart count 0.
Existing restart counts are historical, not introduced by this deployment.
Recent web journal showed normal stop/start, no reported startup exception.

## Evidence and rollback

Jetson evidence directory:
`/home/jetson/project-atlas-migration/executor-deploy-20261023/executor-deploy-mzwduyu2/`.
Retained original: `atlas_status_web.original` (baseline hash above, mode 0664).
`result.json` SHA256: `30c5e5ad598bf4ae4606bca62f2d79fdf85372246332e647d3708dcad52df47d`.
`trace.jsonl` SHA256: `e0469a40e8a8970f4b56b302c051c3ebdabedbb9d8afac01182db3079154726f`.
Local evidence copies are under `artifacts/executor_benchmark_20261023/` as
`deployment-retry-result.json` and `deployment-retry-trace.jsonl`; raw logs are not committed.
Installer retained remotely as `deploy_retry_cpu_report_only.py` in the parent
directory, with durable failure logging and a single-attempt lifecycle.

Rollback: while stopped, verify current three candidate hashes and backup hash;
restore that exact backup to scripts/atlas_status_web.py preserving mode 0664;
remove only the two new private executor files after verifying their hashes;
restart only rover-status-web; repeat safety, freshness, HTTP and hash checks.
No rollback was required on this attempt. Preserve backup for later recovery.

Remaining: establish sustained CPU headroom and separately approve any guarded
Depth-only test. This deployment does not verify live 3D Preview or autonomy.
