# ATLAS Stage32 — final developer handover

Documentation-only handover, 21 October 2026. No new Jetson checks, deployment,
restart, camera activation or hardware test performed for this handover.

## Repository and checkpoint

- Repository: https://github.com/Dhruv0747/ATLAS
- Dedicated branch: `agent/sync-developer-20261011`; do not merge main.
- Verified remote/source HEAD entering handover:
  `2376ede16eefa5579bba69ff229da80974ee4811` (installation rollback report).
- Instrumentation candidate source:
  `baa1f26e96b8976aed0785f62c0891558c5930f0`.
- Previous receiver diagnostic candidate:
  `3e914657857143a682f9f82fdc85334d61d92e94`.
- Original instrumented zero-frame test report:
  `d9e23bf8d2ba60e5287a16fe7493a89fd77beafa`.
- This handover commit supersedes the entering HEAD for documentation only. Resolve
  its exact SHA with `git log -1 --format=%H -- ATLAS_STAGE32_DEVELOPER_HANDOVER.md`;
  the owner's final response also supplies the pushed SHA. Do not infer installed
  versions from repository HEAD: the new diagnostics were rolled back.

Local repository:
`C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/ATLAS-github`.
Tracked code/documentation was clean before this handover. Historical untracked
`artifacts/` and `deploy/` remain in place; do not delete, blanket-add, reset or
blindly pull over developer work. Generated logs, images, binaries and backups are
intentionally not in Git. Useful current scripts/evidence are indexed below and
the deployment evidence also has a Jetson copy.

## Working versus pending

| Feature | Evidence-backed status |
|---|---|
| Stage31 Dashboard / clean cards | Deployed; preserve existing layout |
| Stage31B Depth viewer | Previously verified60s,607 real frames; not retested this session |
| Depth click-to-measure | Existing uncalibrated axial Z; not a metric-accuracy qualification |
| Private ROS Domain77 | Existing isolated configuration preserved; no owner after rollback |
| Stage32 IR interface | Installed original version; real IR viewing NOT verified |
| Pi Camera3, LiDAR, ROS systems | Healthy in last rollback verification; no new check during handover |
| IR driver diagnostic counters | Built and tested offline; attempted deployment rolled back |
| IR acquisition / zero-frame root cause | Unresolved; real driver counters not collected yet |
| Calibration / live XYZ PointCloud2 | Software preserved; unvalidated calibration blocks live geometry |
| RGB-depth registration | Unvalidated, not approved for activation |
| IR+Depth / other combinations | Not hardware-verified; no automatic next test |

Main reports: `ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md` sections16–19,
`ATLAS_STAGE31B_LIVE_DEPLOYMENT.md`, `docs/audits/ATLAS_CURRENT_BLOCKERS.md`,
`docs/audits/ATLAS_ROOT_CAUSE_REGISTRY.json`, and the focused deployment ledger
`docs/audits/ATLAS_STAGE32_DEPLOYMENT_REGISTRY.json`.

## Last verified live state — not a new admission

From preserved `postrollback.json`, 21 October:
E-STOP latched (REMOTE STOP: joystick unavailable), manual-only true,
commissioning false, source STOPPED, commands/output targets zero, mission READY,
motor speed0, recorder OFF, runtime OFF. No Astra driver/worker/cloud process and
Domain77 unoccupied. Required telemetry fresh. Pi JPEG HTTP200,26,179 bytes;
image not saved. CPU63.2689% in a later1s read-only sample, RAM67.5051%, peak60.25C.
These are historical measurements; **do not use them as fresh permission/admission**.

Only rover-status-web changed identity during install/rollback:
PID164593 →189500 →189640, automatic NRestarts0 throughout. Explicit restarts do
not increment NRestarts. Every other previously active user-service identity
matched. Protected final identities (PID/NRestarts): camera1982/0,
base-telemetry3534/1, mux1975/0, EKF3260/0, localization5713/1, LiDAR5523/5.
These nonzero historical restart counts did not increase during this attempt.

### Exact restored hashes

Paths below relative to `/home/jetson/project_atlas/`, unless indicated.

| File | Last verified installed SHA256 |
|---|---|
| scripts/atlas_vision3d_runtime.py |454dd25fd0e5bafbb25b63983af865cca78a01354547e4129c2e2016b8023151|
| scripts/atlas_vision3d_web.py |889881c062717d076430414f57825b14f7f0de36ba4cf8c20b0c74fbff9ec1bf|
| web/v2/vision3d.html |a930af8392b0fbaab3380eaf8dbc547780df487f27e44fb4d349ad1447e48c09|
| web/v2/vision3d.js |76f9a20267e7d90a9d4b0a3be7f75a6c0e0ca594ddc1254e337e618215cf3fba|
| web/v2/vision3d.css |04f98c8c0338b960add11346e84c149ae82dac48954d81ffdd726839b0a6971f|
| config/vision3d_live.json |e27bc0c0551d22babb7a477c551d49c5ab20937e56b6aa4fe8a8ce6aff9f9c9a|
| scripts/atlas_vision3d_geometry.py |75d020120d22fe31d8cc6b741f1ae8b19192047aafb03396a47669ee9d4b4354|
| scripts/atlas_vision3d_cloud_node.py |d2bfad1cfd970593d0f4871ab3652e41cfaa2283e470d68463df1fb4299544c0|
| tools/vision3d/calibration_validation.py |9ca7f52cdf8fe323a4327e0adfa526afe5ea41b39138a8e6ee7bc49419613398|
| tools/vision3d/checkerboard_calibration.py |132522ba2a2b780b959a81c1ad47c113844bdb4b33ad41e7b326cbf189292fbc|

Isolated driver root:
`/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2/`.
`lib/libastra_camera.so` restored hash:
`6ae876010c824be97d2545996f897e40e07e0c97fa7a45694f96f342cf6e22a6`.
Unchanged `lib/astra_camera/astra_camera_node` checked before installation:
`2f7a58f9b409ee98aa38dde8966fbd661f0c532c589eead32207a58964635aa9`.

## Latest failure: verified, not speculation

Approved three-file installation passed exact hashes, fresh safety/resources,
disk space (394,550,407,168 bytes free), and RTLD_NOW ARM64 dependency loading
without constructing a node/opening camera. Backups verified. Candidate files
installed; only rover-status-web restarted. Post-restart whole-machine1s CPU
sample **95.63758389261746%** exceeded unchanged75% guard. Installation aborted.
All three originals restored with exact hashes; web restarted for rollback.
**No IR Start request or live IR session occurred. No retry occurred.**

Preflight CPU63.34–65.71%, immediately prewrite62.03–65.66%. Later lower CPU is
not permission to disregard the failed sample. RAM/temperature were not sampled
in the failed window because CPU rejection was immediate. The spike mechanism
is unproven: a temporal association with restart is not proof of a Python,
FastDDS, kernel, AI or network-fallback cause. No camera acquisition counters
exist from this aborted installation; do not confuse it with the prior live test.

## Evidence, packages and build environment

Latest full evidence on Jetson:
`/home/jetson/project-atlas-migration/stage32-instrumented-approved-20261021/`.
PC copy relative to repo:
`artifacts/astra_stationary_20261021/stage32-instrumented-approved-20261021/`.
Contains `result.json`, `postrollback.json`, `terminal.txt`, `rollback-ledger.json`,
`attempt.lock`, reviewed package, installer, final read-only checker, and
`backup/` originals. Do not rerun installer: single-use attempt is consumed.
Checksums are in report section19 and focused deployment registry. Preserve all.

Earlier live zero-frame evidence:
`/home/jetson/project-atlas-migration/stage32-ir-revalidation-20261021/` and matching
PC `artifacts/astra_stationary_20261021/stage32-ir-revalidation-20261021/`.
Zero callbacks in11 ACTIVE samples; actual IR mode metadata unavailable despite
driver320x240@30 startup. CPU69.78%,RAM70.09%,59.47C: **not CPU-blocked**. Preserve
`telemetry.jsonl`, `driver.log`, `pre.json`, `post.json`, `final-runtime.json`.

Earlier deployment/calibration metadata: matching Jetson/PC
`stage32-deploy-20261021/`. Keep original backups there and elsewhere untouched.
PC helper scripts in `artifacts/astra_stationary_20261021/` include
`ir_revalidation_monitor.py`, `install_ir_instrumented_once.py`, and
`ir_install_postrollback.py`. These are retained artifacts, not autostart services.

Pending package: PC
`artifacts/astra_stationary_20261021/ir-driver-instrumented-candidate/candidate.tar.gz`;
also copied into latest Jetson evidence directory.
Archive SHA256:
`1e6704adb163747328b1a9f37dfd0053e713fb8d16aa09afbb1ae7744e5a3473`.
Three candidate payloads (not installed):

| Payload | SHA256 |
|---|---|
| lib/libastra_camera.so |8609f2641d181fb6fccda60e84f83d4c5d399b673dc65b27b723490a8b24cab9|
| project_atlas/scripts/atlas_vision3d_web.py |a7b9f1f92ac4a9acd08954103df981d41dfea7ed613b01146669248ef9cd584c|
| project_atlas/web/v2/vision3d.js |91460fcf775cd3517f19d050c86f1c55d9627e710d398b6e79dd456a696d99a5|

Exact vendor delta in candidate directory; hash
`973eb10f839856406d03ce0c95d884b86f0f71cf7a9d41159a4613c5f11064f5`.
Older `ir-diagnostics-candidate/` is superseded; do not install both packages.
Tracked tools under `project_atlas/tools/vision3d/`: `instrument_ir_driver.py`,
`ir_counters.hpp`, `test_ir_counters.cpp`, `package_ir_instrumentation.py`,
`ir_receiver_smoke.py`, build/toolchain files. Receiver/browser tests under
`project_atlas/tests/test_vision3d_ir*.py`.

WSL Ubuntu-22.04 build environment `/root/atlas-stage29/`: pinned vendor source
`source/ros2_astra_camera` at f7e71d9ce806e788cb48d8580aac2c778fba4214, existing
ARM64 CMake patch plus instrumentation; do not blindly reapply instrumentation.
`cross-build/astra_camera/libastra_camera.so` is candidate;
`cross-install/lib/libastra_camera.so` remains baseline. Sysroot `target/`.
97 offline tests passed (94+3), one Playwright skip, separate Node canvas pass.
Latest PC synthetic ROS test179/180 received,0 rejects; not loss-free/hardware proof.

## Immediate next task and unresolved hypotheses

1. **First analyze retained installation output and available startup logs for the
   web restart CPU spike.** Use passive read-only process/resource observation if
   needed, never a restart to reproduce it without approval. Correlate startup
   ROS participant/FastDDS graph discovery, Python/type-support initialization,
   web startup work, kernel reclaim/compaction, background AI and network-fallback
   load. Existing evidence lacks per-process attribution in the failed second.
   Avoid ROS CLI discovery commands which add load. If existing evidence cannot
   distinguish causes, specify exactly what passive capture is missing.
2. Prepare a minimal evidence-based deployment plan using existing candidate and
   rollback; no unchanged installation retry, guard relaxation or unrelated tuning.
3. After fresh explicit approval, ONE instrumented IR-only session can localize
   the missing-frame boundary. Poll readiness/readFrame → callback/conversion →
   ROS publish attempts/returns/subscriber presence → receiver → API → canvas.
   Summaries are bounded, no pixels retained. One early timeout, no auto-retry.
4. Only afterward revisit calibration/cloud under separate physical approval.

IR evidence gaps: vendor poll timeouts were silent; no actual read/publish counts
exist yet. Domain/QoS topics appear compatible; synthetic receiver tests pass,
but do not prove Jetson discovery. Registration property5 failure is nonfatal in
control flow, hardware effect unknown. OpenNI USB-priority warning source is not
available in pinned checkout. Teardown undeclare errors occur after stop. Do not
infer camera failure, change firmware or blame CPU for the prior IR zero-frame run.

## Authorization boundary

This handover grants **no new operational authorization**. Read reports/source,
analyze retained logs, passive read-only Jetson checks, offline builds/tests and
package/rollback preparation only. Fresh owner approval required before production
file changes, service restarts, any camera session, resource-policy changes,
physical calibration capture/install, live PointCloud2, navigation or movement.
Maintain CPU75%,RAM80%,70C, minimum1s CPU sampling and all E-STOP/freshness guards.
Keep normal runtime independent of Windows. No recordings, autostart, emitter or
firmware changes. Never reuse historical safety readings as current admission.

Current developer stops after pushing this documentation. No next investigation
or hardware execution is initiated by this handover.
