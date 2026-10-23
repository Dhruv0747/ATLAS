# Dashboard-only executor package — prepared, NOT installed

## New validation

66 tests passed with no skips in the explicit PC run:5 new native QoS/concurrency
tests (each on cancellation-only and combined variants),7 package tests,9 native
cancellation,6 count equivalence,6 loaded-summary,11 profile-analysis and22
profiling-safety tests. WSL Ubuntu22.04/Humble, localhost-only domain213.

Actual ROS tests verified incompatible reliability produces a QoS notification
and no incompatible delivery; requested deadline events are delivered after
publication stops; shutdown during a blocked timer callback reports incomplete
until the callback is released; context shutdown wakes the waiting executor;
30 subscriptions can be created/destroyed while spinning followed by successful
healthy delivery. Threads were joined and none remained alive in these tests.
Exceptions other than normal shutdown are captured and fail tests.

This covers bounded tested interleavings, not every possible race, all QoS
policies or physical safety deadlines. Does not prove ARM64 compatibility or
whole-Jetson CPU savings. Previous loaded-workload result remains6.25% median
PC process CPU saving,9/10 positive pairs, worst latency9.19ms vs8.11ms; no new
live resource measurement or camera test.

## Exact live baseline and private package

Read-only fresh copy of `/home/jetson/project_atlas/scripts/atlas_status_web.py`
still matches98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79.
No changes were made on Jetson. The package builder rejects any other baseline.

Local package directory:
`artifacts/executor_benchmark_20261023/deployment-candidate/`.
Manifest SHA256:
`463e0850fc79a22231560cb86ba292a737d7a4938f969dc6e40709d4dd5417c3`.

| Install-relative path under project_atlas | Candidate SHA256 |
|---|---|
| scripts/atlas_status_web.py | acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439 |
| scripts/atlas_dashboard_executor.py | 2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab |
| scripts/atlas_dashboard_executor_impl.py | 543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1 |

The exact live web file changes at three sites only: add a private adapter import,
replace the status executor constructor, and replace main `rclpy.spin(self.node)`
with the private spin helper. The helper supplies an explicit executor and shuts
it down in finally. Tests reverse all substitutions to the exact original bytes.
No replacement with the full repository Dashboard file.

The new adapter verifies its adjacent private implementation's hash and loads it
under a private module object. It never overwrites rclpy's module/global executor
class. Main/status each get a distinct executor instance. All other ROS processes
keep the installed library. The implementation retains the captured ROS license
header and contains only the reviewed cancelled/done-task guard and count sums.
Missing/corrupt private source raises an error; no silent fallback hides failure.

Packaged native-loader test verified corrected cancellation and unchanged global
rclpy executor class. Copy-install/rollback rehearsal verified all three hashes,
restored the original Dashboard bytes and removed only the two newly added files
in an isolated temporary directory. No live service restart was rehearsed.

Reproducible offline builder (requires captured original sources):

```bash
python3 project_atlas/tools/diagnostics/prepare_dashboard_executor_package.py artifacts/executor_benchmark_20261023/atlas_status_web.live.py artifacts/executor_benchmark_20261023/executors.py NEW_LOCAL_PACKAGE_DIRECTORY
```

Generated package/evidence is local, not committed. Builder, adapter, regression
tests and hashes are versioned. The builder cannot install or restart services.

## Proposed controlled deployment — approval required

1. Confirm parked, E-STOP latched, manual-only, zero motor commands, Astra OFF,
   recorder OFF, no navigation/commissioning goal and healthy/fresh protected
   sensors. Fresh CPU75%, RAM80%,70C limits must pass; do not inherit any prior
   diagnostic CPU exception. No physical movement test.
2. Reverify exact baseline, package manifest and every candidate hash; verify
   owner/mode, writable space and rollback. Abort if either new target file
   already exists until its provenance is reviewed; never overwrite it blindly.
3. Save original Dashboard and metadata in a new timestamped backup outside the
   active scripts directory. Verify backup hash. Snapshot protected service PIDs,
   restart counts, safety state, UI/CSS hashes and relevant ROS source identity.
4. Start low-overhead persistent CPU/resource monitoring and a matched parked
   baseline with Astra OFF. Stage the three files, verify them and preserve
   permissions. Install only these three paths. Do not touch `/opt/ros`.
5. Restart ONLY `rover-status-web` using the previously approved service procedure.
   No other service restart, reboot, camera or navigation operation. Account for
   the known restart transient separately; keep camera admission blocked. Abort
   comparison/roll back if safety, service or resource acceptance fails.
6. After settling under limits, verify private module identity, both Dashboard
   executor paths, HTTP/routes, stopped-state controls, E-STOP, sensors, Pi Camera
   health, unchanged white-glass assets and protected service identities. Confirm
   Astra/recorder remain OFF. Do not actively move steering/camera to test controls.
7. Run matched parked measurement windows and report average/peak whole-Jetson and
   Dashboard CPU, RAM, temperature and sensor freshness. Reject safety/functional
   regression; do not claim CPU benefit from a different workload or restart spike.

## Rollback plan

If package integrity, startup or health fails, restore the verified original web
file and metadata, remove ONLY the two newly installed private files after
verifying their candidate hashes, then restart only rover-status-web. Recheck
original hash and stopped-state/protected service health. Preserve all diagnostic
evidence. If rollback cannot be completed safely, leave E-STOP engaged and report;
no automatic retries or safety-threshold changes.

No live backup exists yet because nothing was installed. Live backup path must
be recorded at the separately authorized deployment; the local original copy is
not a substitute for a fresh production backup.

## Exact next approval

Approve this THREE-file Dashboard-only package plus ONE rover-status-web restart,
fresh safeguards, verified backup/rollback and matched stationary measurements,
with Astra OFF throughout. This would not authorize a camera test, recording,
driving, calibration change or systemwide ROS update. Until that approval, retain
current production unchanged. White glass and existing useful features preserved
by scope/byte-diff; full live functional verification remains pending deployment.
