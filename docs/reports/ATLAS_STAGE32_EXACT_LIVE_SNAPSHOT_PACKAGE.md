# Stage32 exact-live dashboard patch — prepared, NOT deployed

2026-10-21. Continues afee764; replaces the previously blocked full-repository
deployment package. Only read-only SSH hash verification was used on Jetson.
No service restart, installation, camera Start, recording or movement.

## Baseline and differences preserved

Fresh Jetson SHA256 of `/home/jetson/project_atlas/scripts/atlas_status_web.py`
matches the retained byte-for-byte source:
`fa62787f94c63b0103c666855cef0175b2c86e40022bf700beebe77e44adbd12`.
Its copy remains private at `artifacts/astra_concurrent_20261021/dashboard-predeploy-live.py`.

All live-vs-Git baseline differences found in afee764 remain unchanged:

|Area|Live behavior preserved (Git differs)|
|---|---|
|Vision Lab import|Existing comment retained; no functional import change|
|Single-person steering|No added import, state fields, publishers, timer, startup, cleanup or action handler|
|JSON response|Existing indent=2 retained; no compact serialization change|
|POST dispatch|Existing location/testlab/FlySky/VisionLab ordering retained|
|Commissioning body limit|Existing1024-byte validation retained; no8192-byte special case|

No repository features were merged into live source. The repository's main
atlas_status_web.py is deliberately NOT substituted into this package.

## Exact edits to live source

Only two replacement sites, eight inserted lines and two removed lines:

1. Original line431: replace unconditional `setdefault(key, deque(maxlen=128))`
   with `get(key)` and allocate only when missing (candidate431-433).
2. Original line1519 (candidate1521-1525): replace the per-request timestamp-list
   scan with removal of expired prefix entries and reuse of the bounded deque.

No value/age cache. Monotonic stamp ordering and the existing same lock permit
prefix removal. Strict10-second boundary,128-entry cap, rate rounding, fallback
precedence and fresh response construction preserved. CPU75%,RAM80%,70C,
Domain77, camera modes and calibrated-cloud restrictions untouched.

Builder `project_atlas/tools/vision3d/prepare_live_snapshot_patch.py` requires
the exact baseline SHA, exactly one occurrence of each old byte sequence,
identical AST outside _set/snapshot, byte-perfect reverse patch and compilation.
It only generates files locally; it has no deployment/service/network operations.

## Test results

-9 exact-live tests PASS: five differential histories/freshness tests, unrelated
 AST equality, changed-baseline rejection, isolated install/rollback and exact
 two-site byte reversal. Test fixture is the retained live source, not Git source.
-60 Linux dashboard tests PASS against an isolated project copy with the exact
 candidate installed: E-STOP/reset HTTP request behavior, drive refusal,
 no-reboot, executor/subscription preservation, camera-idle and telemetry panels.
-Steering/HTTP methods and all unrelated code are AST-identical and byte-preserved
 outside the two sites. No physical steering test performed or needed here.
-Isolated file replacement and restoration reproduced the original bytes.
-Tar contains only `scripts/atlas_status_web.py`; tar payload and installed
 scratch-copy hashes match the candidate. This is NOT a live service restart test.

Nine tests require ATLAS_LIVE_SNAPSHOT_BASE pointing to the private live source;
without it they explicitly skip, rather than imply a live-source pass in CI.

## Actual offline CPU results

WSL Ubuntu22.04 Python3.10; real methods extracted without starting ROS;100keys,
128recent timestamps/key, fixed clocks/empty fallback. Same synthetic fixture,
5batches of2,000snapshots and5batches of100,000callbacks as the earlier benchmark.

|Metric|Exact live baseline|Candidate|
|---|---:|---:|
|Median CPU per snapshot|0.487593ms|0.086112ms|
|Median CPU per _set callback|0.496457us|0.318662us|

Snapshot reduction82.34%; callback reduction35.81%. cProfile attributes0.532 of
0.731seconds to the original history-list scans (1,000profiled snapshots).
This measures one operation, not total dashboard or whole-Jetson CPU. A workload
of10requests/s would save~0.004CPU-seconds/s on this PC fixture. No claim that
this resolves the remaining aggregate CPU block or qualifies live3D Preview.

## Reproducible package and exact hashes

Local package: `artifacts/astra_concurrent_20261021/snapshot-live-package/snapshot-live.tar`.
Generated manifest stored beside it. No raw source backups/logs committed.

-Baseline: `fa62787f94c63b0103c666855cef0175b2c86e40022bf700beebe77e44adbd12`
-Candidate file: `98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79`
-Deterministic tar: `2aa2db41878ae99d6716f4a8fbcedc9582a98381d07a6ab44eb29c5ad3c67160`

Rebuild with `python3 project_atlas/tools/vision3d/prepare_live_snapshot_patch.py BASELINE NEW_OUTPUT_DIR`.
Builder refuses any baseline drift and refuses an existing output directory.
Benchmark supports `--baseline BASELINE --candidate CANDIDATE`.

## Pending owner-approved installation / rollback

Approval needed for THIS package, not the earlier full repository file:
1. Fresh safety/resources, E-STOP/manual-only/zero commands, Astra/recorder OFF,
   protected PIDs/restart counts and healthy sensor checks. Abort on failure.
2. Verify exact live baseline, candidate and package hashes. Capture matched
   parked CPU baseline with low-overhead persistent monitoring.
3. Create a new timestamped migration backup, preserving file metadata; verify
   original hash. No live backup is claimed created during this preparation.
4. Atomically install only this file, preserving original mode/ownership;
   restart only rover-status-web. Account for known restart spike; wait for
   settling, then check unchanged safety, sensors and protected identities.
5. Compare parked whole-Jetson/process CPU, RAM/temp/freshness under matched
   polling. Keep Astra OFF; no Start permission included.
6. On installation/health failure, restore the verified original bytes/metadata,
   restart only web and recheck original hash and protected services. Preserve
   error evidence. No automatic camera retry or safety-limit adjustment.

Existing deployments and rollback evidence remain untouched. Await approval.
