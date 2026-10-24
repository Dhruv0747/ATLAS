# Localization monitor profile and offline executor trial

## Outcome

Capture completed; source/payload hashes verified. A minimal executor-adapter
candidate was tested offline, but is NOT approved for deployment: savings vary
by workload and no Jetson savings or Astra readiness has been established.
No production files, services, camera, steering, safety limits or voice/UI changed.

## Captured evidence

Owner-authorized diagnostic CPU-report-only capture:
`/home/jetson/project-atlas-migration/localization-cpu-20261024/evidence-nc93hixt/`.
Private local copy: `artifacts/localization_cpu_20261024/` (not committed).

| Artifact | SHA256 |
|---|---|
| python-threads.json (16245 bytes) | `0d53dd6906e20c42ec17cbcd46864b334e35a7bf09b649259bb3f16cedaa7299` |
| result.json | `0119d56ae754a5e066894e45457df971ef1ad3592c41bb9592be2f8a27495409` |
| telemetry.jsonl | `3bb23af8c9dca748eccd76f85c6b90a676e7e25da8ee4c6a85aa5b226183fd77` |

Profiler exited 0. Protected service PIDs/restart counts match before and after.
20 health samples passed remaining safety checks: latched stop/manual-only,
zero commands, recorder OFF, fresh required sensors, zero wheel output and
mission READY. No Astra start or production change occurred.

Whole CPU mean 72.5793%, peak 76.5921%. Phase means: baseline 72.6425%, profile
72.8148%, postflight 72.0449%. These are unmatched short windows, NOT a measured
profiler-overhead subtraction or an optimization comparison. RAM peak 72.3356%;
temperature peak 60.375 C. Production 75%/80%/70 C policies remain unchanged.

## What the profile does and does not establish

- 199 samples, 0.05-second weights, one Python MainThread profile, 9.95 seconds.
- 151 leaf samples (75.88%) at rclpy/executors.py line 678. The installed source
  was checked: this is `wait_set.wait(timeout_nsec)`. Sampling that boundary is
  NOT proof of Python busy-waiting, CPU consumption in that line, or a lock bug.
- 177 samples include `_spin_once_impl` line 797; 176 include callback-generator
  dispatch; 12 include subscription taking line 400. Counts are stack occupancy,
  not independently additive CPU percentages.
- Linux main TID 1948 accrued 220 ticks over 19.027984 seconds at 100 Hz:
  11.562% of ONE core. Remaining stable native threads total approximately
  0.789% of one core. This is not whole-Jetson percentage.
- No search-worker Python profile appeared. This short window does not establish
  the periodic global search is cheap, disabled or faulty. No calibration,
  odometry, AMCL or localization-confidence defect is established by this trace.
- Callback dispatch and underlying wait/RMW activity remain candidates for CPU
  work, not a verified explanation for all system load.

## Offline candidate and bounded experiment

Reused the existing reviewed private executor adapter instead of creating a new
executor. Candidate changes only the monitor's `rclpy.spin(node)` call to a local
import and `private_spin(node)`. No algorithm, subscriptions, timer periods,
thresholds, reseed behavior or cleanup changes. The helper generates this patch
only from the exact live SHA256:
`cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b`.
Candidate SHA256:
`58e5d86b21e59546cd44e5fcc87d99df910e4e9e9220d1701e24080de393a4da`.
ManualLocationCheck captured SHA256:
`eec177795434870f53102482a92b3dbc1ced4d3e4a90589e22e9fe4261681690`.
Original Humble executor SHA256:
`e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010`.

Native ROS Humble runs were on PC WSL, localhost-only Domain 213. No Jetson ROS
participant was created. Fixture includes seven streamed subscription entities,
map subscription, real TF buffer/listener, publisher, client, manual-check services
and .25/1/.25-second timers. Payloads include 720-range scans. It is a burst
dispatch test, NOT live-rate replay: actual callback algorithms, TF traffic, map
search, disk status writes, request/cancel operations and shared-topic delivery
are not replayed. No physical safety or AMCL improvement is inferred from it.

Six alternating original/candidate pairs per batch:

| Batch | Rounds/run | Original mean CPU seconds | Candidate mean CPU seconds | Median paired saving | Pairs improved |
|---|---:|---:|---:|---:|---:|
| A | 500 | .283442 | .283381 | -0.7864% | 2/6 |
| B | 2000 | 1.144899 | 1.116943 | 3.7125% | 5/6 |
| C | 2000 | 1.176553 | 1.147986 | 2.4236% | 5/6 |

All 378000 expected messages arrived; no duplicate/unexpected callback exception
or shutdown failure. One-second timers did not fire in short batch A; they fired
in B/C. Timing differences can change timer counts; identical timing is not claimed.
Candidate slows some pairs (batch C worst -6.6536%). Small burst-workload gains
are insufficient to establish robust parked-system headroom. **Hold candidate.**

Result SHA256 A/B/C:

- `ce35ed2e94bfcc55d94f8d46e00e9a939e3a5974e5ce044b6b44d62d43974c7e`
- `158807891c46343bc7f402cfbe520ab6b6406fc9b0d0b9169440099952bd426b`
- `d3b741950bebb96fb9d29a38bddac35adb4f201a9c343b79df948aa848920fc5`

## Tests and next action

60 unit/state tests passed: 3 new candidate-contract tests, 29 profiler/shared
tests, 28 existing localization monitor/state tests. These preserve the existing
state-machine evidence, not a production candidate deployment qualification.

Reproduction: source ROS Humble on PC, set ROS_LOCALHOST_ONLY=1 and
ROS_DOMAIN_ID=213, run `project_atlas/tools/diagnostics/benchmark_localization_executor.py`
with captured monitor/manual/executor paths and `--output`, `--rounds 2000`.
No runtime candidate is installed. Rollback is unnecessary on Jetson; source
changes consist only of offline benchmark/tests and documentation.

Next discriminating work is a rate-matched offline workload including TF and
the existing callbacks, using available recorded traffic rates. Do not request
another identical 10-second capture or deploy this adapter merely because two
burst batches improved. Native wait/RMW attribution and periodic-search duty
cycle remain evidence gaps if existing captures cannot resolve them. No camera,
motion, production restart or new live profile is authorized by this report.
