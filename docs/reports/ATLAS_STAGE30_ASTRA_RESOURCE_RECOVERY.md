# Stage30 — Astra resource-block recovery, 21 October 2026

**Latest deployment follow-up:** the approved three-file cleanup from `ac34cd3`
is now DEPLOYED and hash-verified, without service restarts. One real Dashboard
Depth start stopped at CPU80.7786%; zero frames delivered. Live viewing remains
RESOURCE BLOCKED. See the final section below. Earlier sections retain the
pre-approval investigation and are historical.

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

## Prepared package and final postflight

Code commit: `ac34cd3a042a45ddc414d4e84becd45faa72a863`.
Package `stage30-observer-cleanup-proposal-v1.tar.gz`, SHA256
`2d0bee9ff553bd52680c4ab75c1b31d196903797248d8b88628276464ebf867d`.
No pacing, UI, service unit, driver binary or policy change in the package.

| Candidate file | SHA256 |
|---|---|
| scripts/atlas_vision3d_runtime.py | `6a0e9c1cefcf89e1ed3623a786808a5fdd4a67b4ccf6972de71ddab84c19452d` |
| tools/vision3d/stationary_gate.py | `0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9` |
| tools/vision3d/stationary_ros_probe.py | `f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384` |

Unpacked/compiled only in
`/home/jetson/project-atlas-migration/astra-stage30-overhead-proposal-v1`.
Hashes and original live-target hashes verified; no production install.
Private three-file rollback fixture restored byte-identical originals.
Native early-rejection contract with synthetic76% input made NO HTTP call
(~0.983ms including mock/assert overhead); not a physical E-STOP latency test.
Native batched identities equal originals. Native evidence in that directory's
`native-proposal-validation.json`; raw logs/packages kept outside Git.

Final full preflight CPU65.147/68.741/66.667%, conservative RAM71%, hottest63.125°C.
E-STOP/manual-only/zero/READY/disarmed/recorder-OFF checks pass. All12 installed
Vision hashes and six protected identities unchanged; web67677/0 still active.
No Astra or test-host/graph-probe process remained. Temporary SSH forwards closed.
Pi camera returned HTTP200/25,274-byte JPEG, consumed in RAM and not saved.
GPU single final sample6.4% (not an active-camera GPU benchmark).

Final dashboard observation: encoder callbacks and control policy ~10Hz,
cmd_vel4.67Hz, mission1Hz; ages0–0.5s for retained required fields. Dashboard's
LiDAR-summary callback showed1.84Hz; this is not a measurement of raw `/scan`
publisher Hz. IMU composite rate was null: data fresh, cadence not quantified.
No critical source frequencies were altered. No sustained-camera sensor-timing,
memory-growth, actual stop-latency or USB-error qualification achieved.

No owner driving, target placement or repeated room loop is requested. The next
approval above is software-only and explicitly does NOT certify a stable viewer.

## Approved deployment and single Dashboard test

Owner subsequently approved the exact three-file package and ONE guarded Depth
test. Installed from code commit `ac34cd3a042a45ddc414d4e84becd45faa72a863`;
archive and all three candidate hashes match the table above. Fresh preflight
confirmed latched E-STOP, manual-only, disarmed commissioning, STOPPED source,
zero velocity and wheel commands, measured speed0, mission READY, recorder OFF,
fresh required sensors and correct Astra USB identities/access. Free disk
394,587,013,120 bytes. No active viewer. All three originals backed up before
atomic file replacement. Installed hashes verified again after the test; the
other nine Stage29 installed files also retain their original installed hashes.

Only the three approved files changed. No service restart, calibration, map,
driver binary, threshold, network, recording or motor change. Web67677/0 stayed
running and started the new worker from disk using the unchanged lease protocol.
The existing119 focused tests were reused; no source change required a rerun.

| Measurement | Actual result |
|---|---|
| Pre-install CPU, three samples |64.6667 /66.2992 /65.6693%|
| Post-install CPU, three samples |64.0893 /64.2512 /65.6012%|
| Installation RAM / hottest |69% /61.093°C|
| Dashboard worker / driver PID |94780 /94840|
| Driver launch / failed check elapsed |3.6102s /4.1635s from worker start|
| CPU guard rejection |80.7785888%, threshold75% preserved|
| Astra process at rejected sample |43.5182% of one core,54,440KiB RSS (~53.16MiB)|
| Guardian process at rejected sample |1.4173% of one core,20,576KiB RSS|
| Independent observer peak CPU |99.6759% in a different sampling interval|
| Independent observed RAM / thermal maxima during new session |69.9160% /61.187°C|
| Depth frames received by Dashboard |0; no dimensions, timestamp or measured FPS|
| Result |RESOURCE BLOCKED; driver stopped automatically; no retry|

Independent samples span startup and shutdown and must not be substituted for
the guardian's failed interval. CPU80.7786 was rejected before the HTTP request;
its contemporaneous RAM/thermal are explicitly unmeasured. The independent
observer supplies separate nearby measurements. The old successful resource
sample retained by the UI is not the failed sample. No claim that the small
before/after parked CPU difference is a sustained optimization benefit.

The real existing page `/v2/vision3d` was used, Depth-only selected, Start clicked
once. The Dashboard visibly showed the new worker's RESOURCE BLOCKED reason and
Depth unavailable; server stream counter `received=0` confirms no delivered frame.
No second isolated web host or startup pacer was used. Screenshot retained locally.
The approved attempt is consumed. Another camera start requires a new plan.

Twenty lightweight observer samples retained scalar data only. Maximum observed
ages: LiDAR summary0.4s, IMU0.2s, each encoder0.2s, camera_info0.9s, drive_pid0.2s,
mission0.9s, measured speed0.5s, control policy0.2s, cmd_vel0.2s. No observer errors.
These are sampled freshness, not a continuous callback-deadline or raw scan-rate
qualification. Every observed policy remained stopped/manual-only/latched.

Final postflight passed: CPU66.0163/63.8231/67.6656%, RAM<=69.4055%, hottest61.187°C.
No worker/driver remains. All six protected owner PIDs/restart counts and web
PID/restart count unchanged; recorder inactivePID0. Pi camera HTTP200 returned a
valid23,949-byte JPEG (in-memory check, no image recording). E-STOP stays latched,
commands zero, commissioning disabled, mission READY. No autonomous work done.

### Evidence and rollback

Jetson evidence/backup directory:
`/home/jetson/project-atlas-migration/stage30-approved-deploy-20261021-133843/`.
Contains `backup/` (three original relative paths), `rollback-ledger.json`,
`result.json`, `dashboard-test-observer.jsonl`, `dashboard-final.json`,
`postflight.json`, `pi-camera.json`. A matching PC copy is preserved under
`artifacts/astra_stationary_20261021/`; raw evidence is intentionally outside Git.

Evidence SHA256:
- installation result: `fd2f0a5597b3ce83d3593aa718d7943d0a6bbb2dc25b9476dec9370c18444177`
- observer: `0a999bab715ec6f4dde3b1a7cabba3aa25ed79832277c08b1113aeae740043c7`
- Dashboard result: `647c961603631a5bf1c936b5cc828628506976ca0879b4bc7d24b369e84f2cfe`
- postflight: `cc072aae37c47ef409cea121985f58d44702442016b9978c586cb68e43b9450a`
- rollback ledger: `257223fec766be7c52f89bc41a63bdbfe8b1110095135346e772a09e470fc5fc`

Rollback: with camera worker OFF and stationary admission passing, verify current
three hashes against `installed` and backups against `expected_original` in the
ledger; restore only those three relative paths from `backup/` atomically to
`/home/jetson/project_atlas/`, then verify originals and unchanged service identities.
No service restart needed. Previously exercised private rollback fixture restored
byte-identical originals. Rollback was not necessary: cleanup functioned as tested,
but did not solve the pre-existing startup resource failure.

Next engineering step: obtain native-process/graph startup attribution using a
separately approved bounded diagnostic plan. Prior camera-free reproduction and
this real-parent failure do not establish the precise hot native/kernel path.
Do not repeat camera starts, weaken75%, or call viewing fixed from this deployment.
