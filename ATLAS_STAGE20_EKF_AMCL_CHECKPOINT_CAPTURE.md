# Stage 20 — checkpoint capture development checkpoint

14 October 2026. Branch `agent/sync-developer-20261011`; base
`d27e204cf61c96d1a90f4ca8b9d6a0f7b5b18389`. **Partial Stage 20 delivery, not a
completed deployment package or localization repair.** The commit containing
this report is identified by the final GitHub delivery link; a file cannot
embed its own Git commit hash.

## 1. Preserved blocker

Stage 19 already established failure of replay fidelity: five original parked
AMCL jumps versus eight replay pre-stop corrections. A cold EKF and a first
published AMCL mean do not restore the original estimators. This work did not
repeat that replay, tune calibration, run B–E or request another route.
Missing historical state cannot be recovered by a new collector.

## 2. Exact EKF feasibility

Audited installed Humble robot_localization 3.5.4 headers and
[versioned upstream filter API](https://github.com/cra-ros-pkg/robot_localization/blob/3.5.4/include/robot_localization/filter_base.hpp).
The public C++ API exposes initialized status, last measurement time, all 15
state elements and the 15×15 estimate covariance. `/odom` has separate pose
and twist covariance blocks, not this full cross-covariance.

`RosFilter` exposes `getFilter()`; its protected `initial_measurements_` map
contains actual relative-pose references. A subclass can observe this without
editing upstream filter mathematics. The new isolated observer successfully
captured the synthetic wheel reference `(18,-3,0)` and all 225 covariance entries.
It does not substitute the first collector-observed wheel message as the anchor.

Not captured completely: measurement queue/history, every consumer callback
order, every reset between 100 ms samples, TF buffer state and timer phase.
The observer is **not a complete restorable checkpoint**. It reads state on
the same single-thread executor as the filter; diagnostic publish exceptions
are swallowed, not allowed to change filter processing.

## 3. Exact AMCL feasibility and new limits

[AMCL 1.1.20](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_amcl/src/amcl_node.cpp)
publishes poses **and weights** in `nav2_msgs/ParticleCloud`. Publication follows
sensor update and, when selected, resampling; it is not a pre-resampling snapshot.
The existing processing overlay remains useful for processing/scan timing,
but is not rebranded as a PF checkpoint.

[The matching particle-filter implementation](https://github.com/ros-navigation/navigation2/blob/1.1.20/nav2_amcl/src/pf/pf.c)
uses `srand48(time(NULL))`, hidden RNG progression, two sample sets, KLD trees,
cluster statistics, convergence and recovery averages `w_slow/w_fast`.
Those are not all present in the public cloud. This version's `amcl_node.cpp`
does not expose the newer `random_seed` parameter; do not apply newer ROS
documentation to this installed version. Exact historical RNG restoration is
unavailable through its public interface. No custom AMCL binary was installed
or built during this milestone.

Native `hasattr(rclpy.client.Client, 'configure_introspection')` returned False.
Therefore a passive Humble topic collector cannot claim to see service calls.
Prepared opt-in ATLAS hooks record the existing seeder's initial-pose and
no-motion calls and the existing mission owner's no-motion calls. Request CDR,
type, hash, request/response times and correlation ID are recorded. Empty
response means transport completed, not that AMCL accepted or used that scan.
Other callers and server processing/resample events remain evidence gaps.

## 4. Architecture and source changes

- `stage20_capture.py`: finite sandbox-only public-topic collector. Reuses
  `TOPICS`, `STEERING_VALIDATION_EXTRA`, `RosbagSink`, `Sample`, `QueuedWriter`;
  no second SQLite writer or motion-control path. Also subscribes to
  initialpose, parameter/lifecycle events and diagnostic state/event topics.
- Receipt ledger stored **in the bag**, not published: global callback sequence,
  original payload hash, source header stamp where present, ROS receipt time and
  monotonic receipt time. TF retains its original per-transform stamps in CDR.
  This is collector order, NOT estimator consumption order.
- Unique session/boot IDs, input-file hashes, publisher endpoint/QoS descriptions,
  read-only parameter snapshots, bag checksums and explicit incomplete flags.
  Parameter events retain later changes; a snapshot is not startup proof.
- `stage20_ekf_observer.cpp` and CMake: links installed `librl_lib.so`, inherits
  upstream EKF, emits one diagnostic String topic at 10 Hz. Native build passed.
  It refuses execution outside the private development network/PID/device
  sandbox. It is not a production drop-in executable.
- `atlas_initialization_observer.py`: defaults OFF. `ATLAS_CHECKPOINT_EVENTS=1`
  opts in to best-effort diagnostic publication; original call is made exactly
  once and its original Future/exception is preserved. No retries or new seeds.
  Seeder and mission-control call sites prepared; neither live file updated.
- `stage20_contract.py`: fail-closed evidence checklist and prospective numeric
  EKF criteria. Does not weaken Stage 19's existing candidate gate.

## 5. Startup order design — not installed

Future approved collection must be ready before wheel/IMU/LiDAR producers,
EKF and localization start. Merely starting before AMCL is insufficient because
EKF may already have consumed wheel/IMU inputs. Existing EKF `After/Wants` base
and UNO and localization `After/Wants` EKF/LiDAR dependencies must be preserved.

An optional early collector plus readiness/actual consumer-event proof is
required. Never add collector `Requires` dependencies to motor/mux/E-STOP units:
collection failure must not block safety. Do not create ordering cycles with
`default.target`. Any future boot should preserve Stage 16 scan evidence and
failed-start verdict history and create a new session, never overwrite them.

**Not implemented/validated yet:** early known-type subscription readiness,
consumer startup/reset event instrumentation and complete service/server-event
coverage. Current collector explicitly sets `startup_before_sources=false`,
`consumer_order_verified=false` and `complete_restorable_checkpoint=false`.
Discovery/readiness is not treated as proof of capture before initialization.
No normal startup was triggered for this investigation.

## 6. Fidelity contract

Before any candidate comparison: identical source payloads/header times,
parameter/map/package identity, real initialization/relative reference, complete
TF/service/reset history and measured loss/order proof. Full state 15 and full
covariance 225 must be finite; 36-element output covariance is rejected.

Prospective deterministic comparison limits, declared before such comparisons:
maximum matched-time EKF position difference 0.01 m, yaw 0.5°, covariance
relative difference 1%, zero TF lookup failures. These are engineering gates,
not measured present results or ground-truth accuracy. The comparator and exact
covariance normalization still need implementation and validation.

AMCL needs exact internal/RNG restoration OR verified from-startup ensemble
replay, at least 20 runs per baseline, preserving the same external sequence.
Before running ensembles, specify statistical equivalence intervals for jump
counts/times/magnitudes, parked pose/heading, uncertainty and scan consistency.
That statistical specification remains pending; no convenient tolerance has
been selected from a successful run. A missing state flag or zero jumps does
not pass. Candidates B–E remain blocked. Original localization is UNRESOLVED.

## 7. Tests

7 new checkpoint tests: missing flags, covariance truncation/nonfinite values,
map/parameter mismatch flags, missing particle/RNG proof and no baseline failure
reproduction. A synthetic all-true schema demonstrates checklist mechanics,
not actual fidelity. 5 new hook tests: default OFF, exactly one original call,
same Future, unchanged original request/response exceptions, diagnostic failure.
16 reused recorder/writer tests passed, including queue overflow, disk error,
ordering, timestamp preservation and evidence preservation. **28 offline tests.**

Native private ROS smoke: actual installed EKF library, synthetic wheel/gyro/scan,
read-only parameter queries, isolated harmless Empty service, CDR writer/read-back.
Passed actual anchor and full covariance capture, paired request/response,
sequential receipt ledger, original bag receipt timestamps and missing-AMCL
incomplete status. No publishers on cmd_vel, NAV2/recovery commands or initialpose.
This is NOT a faithful native AMCL replay or moving-rover test.

Earlier development attempts failed on missing exported Eigen/tf2/angles/library
dependencies, missing private `/proc/self/io`, rclpy nanoseconds property usage
and upstream constructor's required node-name argument. These were corrected;
failed capture directories remain preserved. No false successful baseline.

## 8. Resource evidence

12-second native collector + hook smoke (not full production graph): 2.525696
CPU seconds / 12.071548 wall seconds = 20.9% of one core, approximately 3.5% of
six-core capacity; collector peak RSS 69.06 MiB. This includes its writer thread,
not the synthetic publisher or EKF observer. Total observer overhead versus
unmodified EKF and sustained full-graph load are **not yet measured**.
First successful native capture finalized ~1.51 MB across bag and manifests.
Free filesystem space ~395.74 GB. File size is logical written evidence, NOT
physical NVMe bandwidth. Private proc I/O was unavailable and rusage block-write
counter was zero, so physical disk-write throughput is unmeasured, not “zero I/O”.
Host snapshots before/after: CPU 70.3→72.0%, RAM 5191→4719 MB, temperature 62→62°C;
these are non-attributable system snapshots, not recorder overhead estimates.

Root retention ceiling 500 MiB, per-session unique rotation, 8 MiB queue and
storage reserves. Quota exhaustion stops new capture; no old or active bag is
deleted. Bag/SQLite overhead means this is approximate retention, not a hard
filesystem quota. No continuous service. Full-rate saturation, process-kill
recovery, early-start ordering and hard-bound tests remain pending.

## 9. Safety, deployment and rollback

Native sandbox: private network/PID, domain187/localhost, read-only host root,
private pseudo-device `/dev` with no serial/actuator devices; affinity cores4/5,
nice15. Only a new `/tmp/atlas-stage20-1XtzyCrM` development directory was used.
No production binary/configuration/unit/map changed; no restarts, reboot,
seeding, steering or motor commands. Fresh pre/post policy remained STOPPED,
stop_latched=true, final lin=0/ang=0. Stage17B HOLD.

Read-only live hash verification still matches Stage19:
EKF `69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`;
Nav `2411371c89751eba9f817b3e6728ab08fa3e8820f6727c08713298c18ee08631`;
map YAML `d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4`;
PGM `4beb26d5a9990db537df53ba71404d549f88f717d72ca59fc03e0b72a3684a1e`.

Rollback now: terminate isolated test processes only; preserve captures. No
production rollback is needed. Future installation must pin source/package
hashes, back up exact live files/drop-ins into a new timestamped directory,
reject unexpected live drift, install optional diagnostic-only hooks, and test
fail-open collector ordering/fail-closed evidence. Restore backed-up unit/files
and unset diagnostic environment to roll back; no calibration/map restoration
should be necessary. Automated production installer/rollback is NOT built yet.

## 10. Status and next necessary action

**BUILT / TESTED OFFLINE / NATIVE ROS VALIDATED** applies to the scoped public
collector, EKF observer and synthetic service hooks above.
**DEPLOYMENT READY: NO. DEPLOYED: NO. LIVE CAPTURE VERIFIED: NO.
REPLAY FIDELITY VERIFIED: NO. LOCALIZATION FIX VERIFIED: NO.**

Next action is offline consumer/startup/reset-event and AMCL initialization/
resampling instrumentation plus equivalence, failure and total-resource tests.
Do not run another failed historical replay or request a drive to fill those gaps.
After those pass, the owner approval request must name early collector ordering,
EKF observer deployment, seeder/mission hook files and any AMCL overlay, explicitly
state whether a future normal boot or restart is required, and attach hashes,
backup/automatic rollback and measured limits. **No installation approval is
requested at this incomplete milestone.**
