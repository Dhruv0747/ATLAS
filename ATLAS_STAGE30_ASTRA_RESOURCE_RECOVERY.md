# Stage30 — Astra resource-block recovery, 21 October 2026

Continues `4f7e6f1fd852356f7ebd5c31429bd1ce5bbdf21d` on
`agent/sync-developer-20261011`. **Stable viewing is NOT achieved.** No Stage30
production file, service, DDS setting, threshold, steering or navigation change.
No motors, goals, recordings, package installation or autostart. PC used only
for development/SSH; isolated hosts and camera work ran locally on Jetson.

## Status

| Requested status | Evidence-based result |
|---|---|
| ROOT CAUSE CONFIRMED | Partial: resource guard rejects real startup load; a camera-free ROS join reproduces a CPU failure. Exact native contention mechanism unresolved. |
| OPTIMIZATION TESTED | Batched identity query and shared safety snapshot tested; early CPU rejection regression passed. Not a whole-system CPU recovery pass. |
| VIEWER LIVE VERIFIED | **NO**: zero delivered depth/RGB frames in Stage30; no pixel accuracy/renderer success claimed. |
| RESOURCE BLOCKED | **YES**; failed samples preserved, thresholds unchanged. |
| DEPLOYMENT READY | Three-file observer/guard cleanup candidate only, pending owner approval. Not a proven stable-camera fix. |
| PRODUCTION DEPLOYED | **NO Stage30 changes**. Existing Stage29 page remains installed. |

## Fresh preflight

Git fetched, local/remote reference synchronized. All12 Vision Lab installed
hashes matched. Astra OFF. E-STOP latched, manual-only, commission disarmed,
source STOPPED, commands zero, mission READY, measured motor speed0, Stage20 OFF.
Required Pi camera/LiDAR/IM10A/all four encoder/drive telemetry freshness passed.
Protected service identities unchanged throughout checked trials:
camera1982/0, base3534/1, mux1975/0, EKF3260/0, localization5713/1,
LiDAR5523/5 (PID/restart count). Production web67677/0 was NOT restarted.
First CPU61.698%, RAM67.228%, hottest63.875°C; no thermal-failure claim.
Each actual camera test was separately admitted and hash-verified in isolation.

## Parked baseline attribution

Reused `settled_resource_probe` process accounting. Fifteen one-second safety
samples over15.88s, Astra OFF: mean65.2396%, min62.7350%, peak66.7769%; RAM68%,
thermal maxima approximately63.8°C. One sampled GPU reading0%; no GPU time-series
or startup GPU attribution. `/proc/pressure/cpu` unavailable, NOT zero pressure.
Profiler itself2.078% of one core (~0.346 whole-machine percentage points),19.7MiB.
One core100% is only16.667% of this six-logical-CPU machine.

| Process | One-core CPU % | Whole-machine % | RSS MiB |
|---|---:|---:|---:|
| rover-status-web |45.34|7.56|171.10|
| Pi camera_node |33.57|5.59|199.96|
| yahboom_base |27.27|4.54|75.20|
| voice_companion |25.63|4.27|83.73|
| sensor_recovery |16.81|2.80|71.95|
| command mux |16.00|2.67|69.13|
| safety reporter |13.35|2.23|69.52|
| rf2o laser odometry |10.77|1.79|35.27|
| localization monitor/search |10.45|1.74|79.84|
| AI annotator |10.45|1.74|329.25|

This is not every process. Exact AMCL/EKF/LiDAR CPU was not retained in the
top20 list; do not fabricate it from service-launcher PIDs. No service was
disabled and critical publisher frequencies were not changed.
Dashboard TIDs67726/67812 used26.764/14.295% of one core respectively; Python
comm names did not identify call paths, so neither is falsely labelled an executor.
Dashboard is the largest individual retained process, not the sole system load.
Earlier compact-JSON savings were already investigated and were not repeated.

## Startup sequence and discriminating evidence

POST creates the new viewing worker; worker hashes458 runtime files and requires
three fresh safety/resource samples. It launches one isolated Astra child. The
viewer lazily connects to existing Foxglove, loads message types, then accepts
frames/converts previews on request. No new viewer DDS node is created.

1. Instrumented normal startup: guard75.9434%, Astra59.8186% of one core,
   RSS58,936KiB. External sampling peaked81.6165% in a DIFFERENT interval. Zero
   delivered frames, so preview colorization/point clouds cannot explain this
   rejection. Point-cloud/IR/registration flags were false.
2. Startup-only owned-child pacing20ms run/30ms hold was tested, NOT deployed.
   Astra's sampled CPU fell, but isolated cold native message loading caused a
   request timeout and later96.2431% guard failure. These are confounded windows,
   not proof of global improvement or of the exact hot native function.
3. Test fidelity corrected: `get_message()` only warms Python classes;
   `deserialize_message()` lazily calls `check_for_type_support()`. Production
   web `/proc/maps` already contains sensor_msgs native support, NumPy/OpenBLAS.
   The isolated host initially did not. Complete native support warmup and
   single-threaded numerical-library environment were confined to the test host.
   A warmup-only run consumed0.41893CPU-s/1.01406wall-s and passed bounded guards
   (peak72.9107%). This was NOT camera validation.
4. Partially warmed test failed at91.6256%; fully warmed test stopped on a
   full-dashboard HTTP timeout despite the last successful CPU70.398% sample.
   External intervals reached100%; do not equate that old successful sample
   with safe load throughout the blocked request. Astra at the stopped sample
   used17.1784% of one core. No image delivered.
5. Shared-light-snapshot + batched-query trial still failed: guard83.2461%,
   Astra24.5610% of one core/RSS59,404KiB. External sample peak89.6200%, mean72.2998%
   over six unequal startup intervals. No delivered frame. This does not prove
   that all remaining CPU belongs to Astra or that the optimization solved it.
6. Final camera-free discriminator: one explicitly parent-approved diagnostic
   ROS participant, no explicit user-topic pubs/subs/services, no camera opened.
   Guard81.6817%, hottest63.656°C. Node startup reported1.3024s. The guard stopped
   only that owned test process; KeyboardInterrupt traceback retained as expected
   cancellation evidence. Camera images/USB capture are not necessary for the
   reproduced failure. RMW/native initialization/graph processing is implicated;
   precise native/kernel CPU attribution is still unproven. FastDDS RMW is
   installed; no middleware/configuration change was attempted.

The isolated host's first fixed port8091 collided with an existing aiohttp
listener (404); no camera launched. Host was corrected to request a free loopback
port and emit readiness. Existing listener untouched. Failed evidence preserved.
All later attempts changed a documented condition; no unchanged failure loop.
No more camera starts after the camera-free discriminator.

## Verified minimal corrections (not installed in production)

1. `stationary_gate.services()`: one systemctl read for all six identities,
   instead of six processes. Exact original dictionaries retained; missing,
   duplicate or unexpected records fail closed. Three native comparisons:
   old85.396/80.882/72.388ms, batched25.825/21.953/23.780ms, all equal.
   Median elapsed-query saving70.60%. This is RPC/process overhead, NOT measured
   whole-machine CPU savings.
2. `stationary_ros_probe.safety_snapshot()`: existing read-only
   `/api/commissioning` returns the SAME fresh `ROS.snapshot()` without unrelated
   network/system discovery. One captured snapshot feeds policy AND original
   extra-sensor validation, instead of two full-dashboard GETs. Fresh local RAM
   and all six thermal sources remain checked; CPU75/RAM80/70°C unchanged.
   Four alternating request trials show full-dashboard9.13–91.92ms versus
   light13.24–28.11ms while parked, all111 ROS keys present. This does not prove
   a matched sustained CPU reduction or eliminate every possible HTTP stall.
3. **Early rejection correctness:** old code read a CPU sample, then could wait
   for dashboard HTTP before rejecting a known failed sample. `require_cpu()`
   now rejects >75/nonfinite BEFORE blocking HTTP, including before the shared
   snapshot request. Failed CPU remains recorded; unknown contemporaneous RAM/
   thermal values are explicitly not invented. Tests prove no HTTP attempt on
   an already-failed CPU sample. A CPU spike arising DURING an initially-safe
   HTTP request can still take up to the existing3s timeout to detect; this is
   not an independently scheduled hard-real-time watchdog.
4. Worker/Astra CPU/RSS/timing captured before the failure check, so the rejected
   sample no longer loses process attribution. Sampling itself is not a profiler
   of native call stacks.

Rejected startup pacing and its first-frame release hook were removed from the
proposal; archived locally at
`artifacts/astra_stationary_20261021/stage30_runtime_rejected_startup_pacing.py`.
No global cgroup/quota/affinity/security change. No essential process paced or
paused. No production change to import/thread environment. Parent/worker command
and lease protocol unchanged, so this worker-only proposal needs no web restart.

## Tests and remaining gates

119 focused native-Humble/offline tests pass (not whole-repository certification):
existing camera/CDR/core checks plus batch identity parity/rejection, same sensor
requirements, all four zero-output checks, mission idle, shared-read no duplicate
GET, process-exit unknown state, and early CPU failure before HTTP.
Synthetic tests are NOT physical accuracy/ROS moving-navigation certification.

| Validation configuration | Result |
|---|---|
| A: Astra OFF | bounded baseline passed |
| B: Depth startup | still resource/availability blocked |
| C: sustained Depth viewer | not reached |
| D: RGB-only | not attempted after failed prerequisite |
| E: concurrent RGB/depth | not attempted after failed prerequisite |

No real Depth/RGB FPS, pixel Z or freshness result from these trials. No known
target test or ±3mm claim. Existing Stage29 streams are separate historical
evidence. USB errors/warnings were not fully instrumented; no USB failure inferred
from CPU. Calibration NaNs, registration and metric-cloud blockers unchanged.
CPU/resource rejection is not proof of thermal or hardware failure.

Policy/control/source ages passed each successful guard; these are freshness
checks, NOT E-STOP actuation latency measurements. Physical stop response and
callback deadlines under sustained camera load are not validated. No threshold
increase is justified from this incomplete timing evidence.

## Proposal, rollback and exact next approval

Prepare a THREE-FILE observer/guard cleanup only:
`scripts/atlas_vision3d_runtime.py`, `tools/vision3d/stationary_gate.py`,
`tools/vision3d/stationary_ros_probe.py`. No HTML/JS/design, driver binary,
service unit, calibration, mapping or safety-policy edit. No rejected pacer.
Preparation tool refuses a package containing that experiment. Package details
and final postflight are appended after preparation.

Installation requires a separate approval: fresh full preflight, exact live
baseline hashes, backup all three files, stage/compile/rehearse restore and
atomic install. No production-service restart is required: only a subsequently
explicitly started viewing worker reads these files. Parent's existing command/
stdin lease protocol is unchanged. If any hash/safety/resource check fails, abort.
Rollback restores the three original files; pause/stop the owned viewer first.
No essential service restart or threshold change is part of rollback.

**Requested approval:** install only the tested three-file observer/guard cleanup
without restarting services, then perform ONE fresh-admitted bounded depth test
through the existing production page. This tests the real already-warm parent
rather than adding a second web host. Stable viewing is not promised; stop and
preserve evidence on any failed check. If not approved, leave all production
deployments unchanged and camera OFF. Deeper native ROS startup contention
remains an engineering blocker, not a reason to loosen the guard.
