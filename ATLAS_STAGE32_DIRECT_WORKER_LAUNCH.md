# Stage 32: remove repeated shell/ROS setup before worker admission

2026-10-21; baseline072a22c; OFFLINE ONLY. No SSH, production installation,
restart, camera Start, recording or movement in this task.

## Evidence and measured contributors

The last retained attempt has baseline2863.510478374, worker entry2864.360986173
and CPU rejection2864.512527339: ~0.8505s between parent baseline and worker entry,
then ~0.1515s to rejection. CPU76.072607% over1.001s, sample_count0; no driver.
Control flow calls require_cpu before safety_snapshot and integrity hashing.
Therefore **hashing, live safety HTTP snapshots and Astra initialization had not
run and cannot be the cause of this particular first-sample rejection**.

The old launch runs `bash -lc`, sources `/opt/ros/humble/setup.bash`, then execs
Python. The repository web service already sources Humble and its workspace
overlay before starting the web Python owner. Repeating that setup at every
camera attempt is confirmed redundant launch work. Standard-library imports of
runtime/gate/probe still occur and remain covered by the same pre-launch baseline.

PC WSL Humble benchmark: seven alternating runs/case, RUSAGE_CHILDREN includes
shell/setup subprocess CPU, same inherited sourced environment, no worker()
invocation, ROS initialization, network subscription or hardware. Final medians:

| Case | CPU seconds | Wall seconds |
|---|---:|---:|
| Python startup only |0.016324|0.063805|
| Runtime import |0.031780|0.113903|
| Runtime + gate + probe imports, direct |0.055208|0.213837|
| Same imports, old login shell + ROS setup |0.162734|0.514282|

Measured launch CPU saving **0.107526s (66.1%)**, wall saving0.300445s (58.4%).
Earlier seven-run comparison independently gave0.154698 vs0.051680 CPU seconds.
Subprocess timeout polling adds wall-time granularity; CPU measurements are the
primary comparison. These are **PC figures, not Jetson aggregate CPU savings**.
Jetson profiles/login hooks can differ; a pass under75% is not predicted.
Reproducer: `project_atlas/tools/vision3d/profile_worker_launch_offline.py`.

Integrity hashing was already profiled in the preceding candidate: synthetic458
files/largest16MiB gave ~0.044–0.053 CPU seconds and ~0.44MiB peak traced allocation
with bounded hashing. That implementation is unchanged. It happens after first
admission and is not moved outside the guard or cached.

Live snapshot latency/CPU was not measured offline; its cost is NOT claimed zero
in general. It was not called in the rejected sample. Snapshot HTTP, freshness,
USB access, service and motor checks are all retained unmodified.

Earlier retained competing-process trace shows baseline~70% aggregate CPU and
web1992:48 ticks, Pi camera2644:30, telemetry3293:27, Python2045:25,
kcompactd0:17 in a ~1.05s interval (100 ticks/s, six cores). These are historical
contributors, not contemporaneous per-process attribution for the last attempt.
No evidence justifies disabling one. Full root cause of aggregate contention
remains unresolved; redundant launch work is the measured, safely removable part.

## Minimal correction and safety

Only production file: `project_atlas/scripts/atlas_vision3d_runtime.py`.
Replace shell/string launch with an argv list invoking `/usr/bin/python3` directly.
Inherit the already-initialized owner's environment. No prewarming, persistent
worker, cached sensor data, delayed guard or work moved before baseline capture.

The pre-spawn CPU baseline, first1s check,2s maximum,75/80/70 limits, every-byte
manifest verification, parent-death/lease handling, freshness, E-STOP, zero-command
and service checks remain unchanged. New driver environment still sets Domain77.
All mode arguments, Depth-only preview, IR640x480, UI and cloud gates unchanged.

Existing web service imports rclpy in its own initialized environment. Before
deployment confirm live service still uses the documented sourced environment;
if not, stop for review, do not silently drop required variables. Native PC
imports of rclpy, sensor_msgs.msg and tf2_ros using inherited environment passed
without rclpy.init. This does not replace native ARM64 driver validation.

## Tests and package

79 focused tests PASS: startup coverage14, guard13, cleanup9, Stage30 safety8,
IR15, USB6, preview4 and UI10 (actual Node JS tests, no dependency skips).
New tests assert direct argv, inherited ROS/overlay environment, Domain77 for
driver, stdin lease/new session ownership, and no hashing/sensor work/driver
after rejected first sample. Existing CPU/sensor/cancellation regressions retained.
Temporary-file install/rollback byte rehearsal passes. No live reliability claim.

Package: `artifacts/astra_concurrent_20261021/direct-launch-candidate.tar` (runtime
and manifest only, local artifact; no auto-installer).

- Package SHA256 `3003a63b3f7cf83804be57886ba3972217a1f3de28f23e06bb0e799eb5406571`
- Candidate SHA256 `ebaaa3c7990d982cfd8e65f217baae9a1a15c71a0aa396594cc597e5b04256b9`
- Expected original SHA256 `8f207dc9c7d06cdccc4ec7c82b3e7c6aae29a86121b39c2271ff4e8922226d63`

## Precise approval and rollback

Request installation-only approval for this ONE file plus ONE monitored
`rover-status-web` restart to load the changed parent launch method. Beforehand:
fresh safety/resources, owner ROS environment, hashes, camera/recorder OFF,
protected service identities, available disk and verified original-file backup.
Atomic replace; restart only web; monitor/allow settling without camera admission.
On failure restore backup atomically and use approved rollback web restart;
verify original hash, sensor health and protected identities. No other restarts.
The previous restart peaked99.83% before settling; do not claim restart is free.

Then request separate approval for ONE guarded Depth-only preview. No new Start
is authorized here. Success requires real depth-derived points rendered on the
Dashboard, not just a lower CPU benchmark or driver launch.

Calibration preparation remains independent of RGB startup: measured checkerboard
dimensions and depth target distances can be prepared now. Existing capture tools
remain unchanged. Calibrated-cloud activation needs validated physical calibration
and separate approval; Uncalibrated Preview does not.
