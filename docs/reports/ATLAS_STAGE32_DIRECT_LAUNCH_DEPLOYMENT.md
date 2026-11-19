# Stage 32 direct-worker launch deployment

2026-10-21. Owner-approved installation-only candidate
`ed450f95443f65f13b22ad955c43b58b9e1b7f25`: DEPLOYED AND VERIFIED.
Only `scripts/atlas_vision3d_runtime.py` replaced. Only rover-status-web restarted.
No camera Start, ROS recording, USB permission change, movement or calibration.

## Admission and integrity

Fresh CPU samples71.8430,71.3629,69.3780%; RAM68.0%; maximum temperature60.593C.
E-STOP latched, manual-only, commissioning disarmed, source STOPPED; zero cmd_vel
and four wheel outputs; mission READY. Recorder inactive. Required Pi Camera,
LiDAR, IMU and all encoder messages fresh within2s. Disk free394306715648bytes.
Astra001/014=2bc5:0403 and001/011=2bc5:0501 verified with effective user RW access.
Owner environment confirmed ROS_DISTRO=humble, Humble and workspace overlay
AMENT_PREFIX_PATH/PYTHONPATH. No environment values changed.

- Original/backup SHA256: `8f207dc9c7d06cdccc4ec7c82b3e7c6aae29a86121b39c2271ff4e8922226d63`
- Installed SHA256: `ebaaa3c7990d982cfd8e65f217baae9a1a15c71a0aa396594cc597e5b04256b9`
- Package SHA256: `3003a63b3f7cf83804be57886ba3972217a1f3de28f23e06bb0e799eb5406571`
- Deployment evidence SHA256: `313ecff0bdd4164c3aeccef140f353a4d43ac225fca36cd657dc8d468d8016f4`
- Persistent CPU trace SHA256: `529abf8807d81d3021a3a0fb50268dcdaf9879e064d2802ef3ea24dc28e03548`

Two helper-only aborts preceded installation: missing convenience function in
the live probe, then helper expecting RESOURCE_BLOCKED instead of actual
RESOURCE BLOCKED. Neither changed a production file or restarted services.
Helper corrected to perform the same explicit VID/PID/effective-access checks
and require driver_stopped=true for the retained blocked state. No failed live
safety/resource check was bypassed. Evidence retained in sibling directories
direct-20261021T212619 and direct-20261021T212640.

## Persistent CPU evidence

Low-overhead /proc/stat monitoring began before installation/restart, sampling
about1s (maximum1.0333s). Restart monotonic3326.272402656. Full scalar sequence
below, in chronological order; first two samples precede restart:

```text
3325.097753 70.1874
3326.102977 70.7846
3327.105308 83.6735
3328.106203 87.9865
3329.107031 81.5254
3330.107832 73.3884
3331.108698 73.3884
3332.109636 74.5791
3333.110386 91.0000
3334.143665 99.8387
3335.144582 99.6672
3336.149603 99.1722
3337.150386 99.6667
3338.151561 100.0000
3339.152369 99.5000
3340.153120 99.0050
3341.153942 99.0000
3342.154737 99.6661
3343.155511 99.3300
3344.156308 96.9900
3345.157140 96.1603
3346.157910 90.1893
3347.158906 77.6144
3348.159712 81.1980
3349.160504 75.9536
3350.161309 71.4521
3351.162439 69.8176
3352.166305 70.5686
3353.167083 67.6271
3354.168045 73.1466
3355.168851 73.0263
```

Five consecutive passing samples completed ~27.90s after restart. Peak100%
was restart overhead, NOT a camera session. Camera admission remained disabled
by non-activation; thresholds were not changed. This does not measure savings
from launching an Astra worker, which was not launched.

## Postflight

CPU73.1466%; RAM67.9028%; max60.687C. E-STOP/manual-only/zero commands and
recorder OFF reverified. Astra summary OFF and no native Astra driver process.
Summary driver_stopped=false is the new idle session's unset flag, not an active
process; mode null and all frame rates null. Calibration UNVALIDATED/read-only.
Both USB interfaces still accessible; permissions unchanged.

Web PID28561 ->34740, active, NRestarts0 (manual restart).
Protected identities unchanged, all active/NRestarts0:

|Service|PID before and after|
|---|---:|
|atlas-camera|1824|
|rover-base-telemetry|3293|
|atlas-cmd-vel-mux|1814|
|atlas-ekf|2868|
|atlas-localization|4595|
|atlas-lidar|1815|

Fresh Pi Camera, LiDAR, IMU and M1–M4 encoder messages verified again.
Web adapter, geometry, UI JavaScript, live mode config, stationary gate and ROS
probe hashes unchanged. Runtime is byte-identical to the79-test candidate:
prelaunch guard,1s window,75%/80%/70C, Domain77, Depth/IR settings and calibrated
cloud restrictions preserved. No physical preview test performed.

## Backup and rollback

Jetson evidence/backup directory:
`/home/jetson/project-atlas-migration/astra-20261021/direct-20261021T212657/`
contains original runtime, deployment.json and cpu.jsonl. Backup hash verified
before atomic replacement. Rollback was not needed. Restore that runtime
atomically after validating the original hash; restart only rover-status-web
under stationary safety checks and reverify protected identities and sensor
freshness. Do not overwrite unrelated files or change permissions.
PC copies retained under artifacts/astra_concurrent_20261021/direct-deployment.json
and direct-cpu.jsonl; raw diagnostic artifacts are not committed.

Next separate approval: ONE guarded stationary Depth-only Uncalibrated Preview
test after fresh admission, no recording/movement and no retry on failure.
Real point delivery and Jetson worker CPU savings remain unverified.
