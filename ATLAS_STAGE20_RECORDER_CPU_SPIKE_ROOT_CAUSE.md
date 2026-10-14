# Stage 20 recorder startup CPU investigation

## Decision

**ROOT CAUSE UNKNOWN. TESTED OFFLINE (startup profile only).**
No demonstrated unnecessary startup work justifies a production correction.
RESOURCE IMPROVEMENT VERIFIED, DEPLOYMENT READY and RECORDING VERIFIED are **not** claimed.
Do not repeat live activation, change the 75% safeguard, or deploy this profiler.

## Exact refusal

Baseline: `4a75c9afb3becee8a2850e1282fdd86fdd250529`.
Evidence directory on Jetson:
`/tmp/atlas-stationary30-avHg8uSb/live-once-85f4e81dbedb4e519fa314b94891c9e0`.
Activation ledger SHA256:
`9b3ed3b5f734809ca8d6fec1a1bc59af5e5c528c704dcea7c86d1e70617902e0`.

Systemd started the collector at 2026-10-14 17:32:11.002197 UTC.
The start command returned at 17:32:11.004249. This is process startup, not
sensor readiness. The subsequent 1.000806677-second CPU interval measured
76.22950819672131%; observation was recorded at 17:32:12.054241, rejection at
17:32:12.056957, and stop completed by 17:32:12.080769.
Therefore the refusal was **after process creation**, not a failed initial preflight.
The supervisor's generic `preflight` phase label does not supersede this sequence.

Five preceding CPU observations: 71.3568, 69.3739, 69.8653, 70.2886, 68.6644%.
Across these five plus the startup interval: mean 70.9631%, nearest-rank p95 and
peak 76.2295%. This six-observation summary is descriptive only: it must not average
away the rejecting sample. Cached dashboard CPU was 70%, RAM67%, temperature58C,
free disk394310217728 bytes; its measurement age was unknown.

No per-process CPU or phase markers were captured during that interval. Collector,
DDS discovery, SQLite initialization and an independent production workload remain
possible contributors, **not established causes**. No bag was created; that does
not establish whether a writer initialization had begun. Grant was consumed/revoked.

## One isolated native startup profile

New source: `project_atlas/tools/diagnostics/stage20_startup_profile.py`.
Executed once through the existing isolated Jetson launcher, separate network/PID
namespace and ROS domain187, without live graph, grant, bag, motor access or service changes.
This measures selected initialization phases, not the complete collector startup.

| Phase | Wall seconds | Process CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Capture module import | .093433 | .083989 | 18940 |
| rclpy import | .045861 | .035638 | 24904 |
| rosbag2_py import | .033763 | .020117 | 28480 |
| ROS initialization | .013708 | .009357 | 47944 |
| Node creation | .253401 | .165733 | 57944 |
| 35 known subscriptions | .462031 | .328568 | 67468 |
| Empty graph discovery | .000224 | .000032 | 67468 |
| Node destruction | .014458 | .008506 | 67592 |
| ROS shutdown | .000222 | .000162 | 67592 |

Total measured process CPU: **.652103424 seconds**. Subscription/node setup dominates
these measured phases. Single run; cache state uncontrolled; no live DDS matching,
message deserialization, SQLite writing or parameter queries measured. It cannot
attribute the historical excursion or establish steady-state resource admission.
No before/after improvement exists because no optimization was justified or applied.

Source inspection: required raw CDR subscriptions preserve payloads; control messages
are decoded for safety. Queue/writer setup precedes ROS readiness. Parameter/metadata
discovery and final hashes are separate work; removing evidence, delaying startup to
hide CPU, or lowering sensor rates is not justified by this profile.

## Current read-only observations, not historical attribution

One 5.104772-second process sample is retained at
`/tmp/atlas-stationary30-avHg8uSb/startup-readonly-current-load.json`.
CPU below is percent of **one core**, not percent of the six-core machine:
dashboard41.73%, camera32.32%, motor-board process27.43%, voice23.70%,
sensor recovery15.87%, command mux14.89%, AI annotator14.10%.
These observations cannot identify which process changed during the old failure.
Current dashboard aggregate: CPU70.2%, RAM72%, temperature58C.

Dashboard-reported receipt ages: LiDAR0.2s, IMU0.1s, encoder health0s,
odometry0s, AMCL quality0.5s, control policy0s, motor command0.2s.
These are receipt indicators, not independently measured source/callback latency.
Exact EKF/AMCL publication timing, ROS scheduling delay, physical E-STOP latency,
recorder queue occupancy and writer delay during the failure are **UNKNOWN**.
No physical safety-latency test was performed. No new recording-data integrity claim
is possible: there is no completed bag to validate.

## Changes and validation

Only an isolated diagnostic profiler and documentation were added; production
recorder, supervisor, EKF/AMCL, calibration, maps and all thresholds are unchanged.
Native profile completed all nine phases, created35 subscriptions and shut down.
Python syntax validation passed. Previously completed recorder regressions are not
repeated or presented as new live capture evidence. No activation, grant, service
restart, movement or deployment occurred in this investigation.

## Next bounded action and rollback

There is insufficient evidence to call the75% limit permanently incompatible, but
no demonstrated safe headroom for another identical activation. Keep recording OFF.
The smallest alternative to review is **offboard passive capture feasibility**, not
another live recorder attempt: evaluate an isolated PC receiver using the existing
required topic list and original ROS header timestamps. A later network qualification
would need separate approval and must measure additional Jetson DDS/network work.
Offboard capture moves Python/SQLite costs but does not eliminate publisher/network
cost, preserve Jetson callback receipt timing, or recover private EKF/AMCL state.
It is a proposal, not a validated replacement or permission to record.

No production rollback is needed because production was not changed. Existing
supervisor backup remains
`/home/jetson/project_atlas/data/backups/supervisor-e35006a-834bb41002014f03aa33a095819ba060`.
Do not invoke rollback/restart absent a separately authorized deployment.
The commit containing this report is provided with its exact URL in the handoff.
