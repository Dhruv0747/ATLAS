# Stage 32 approved startup guard deployment — 21 October 2026

## Subsequently approved ONE Depth-only attempt

Owner separately approved one guarded Depth-only Preview check. Fresh admission
CPU67.4740/68.5358/70.3704%, RAM64.10–64.13%, maximum60.593 C; safety/freshness
and deployed hash passed. Browser initially remained OFF after an accessibility
click selected the Depth radio; API confirmed no worker/session. The single
actual Start was then activated using the identified Start button.

Worker31100 failed its FIRST startup CPU window:76.072607%, window1.001s.
Baseline monotonic2863.510478374; worker began2864.360986173; rejection2864.512527339.
No driver_spawned event, no camera hardware opened, no frames or 3D points.
The Dashboard displayed RESOURCE BLOCKED. No retry, no movement or recording.
This verifies that the new pre-launch guard catches startup load before hashing
or driver launch; it does NOT establish that Depth hardware or preview is faulty.

Postflight E-STOP/manual-only/zero commands/recorder OFF and sensor freshness all
passed. Protected PIDs remained1824/3293/1814/2868/4595/1815 with restart counts0;
no Astra process. RAM64.3379%, maximum60.437 C. Failed CPU sample intentionally did
not collect fresh RAM/thermal values; postflight values are not substituted for it.
Scalar worker evidence retained at PC
`artifacts/astra_concurrent_20261021/depth-only-startup-blocked.json`.
Next work is offline launch-cost investigation; no further Start approved.

Source: `74ff38f9e9b07a9b58b52ff2560fbdffc0bc1de3`.
Branch: `agent/sync-developer-20261011`.

**DEPLOYED AND INSTALLATION-VERIFIED. No Astra start or live guard exercise.**
Only `scripts/atlas_vision3d_runtime.py` was replaced. Only `rover-status-web`
was restarted. No USB changes, recording, motor movement, calibration or clouds.

## Admission, hashes and rollback

Three immediate installation CPU samples:72.1254/70.5401/71.8381%; RAM63.00–63.07%;
maximum temperature60.812 C. E-STOP latched, manual-only true, commissioning false,
source STOPPED, zero velocity and four zero wheel commands, mission READY,
measured motor speed0. Required sensor freshness and Astra access checks passed.
Astra absent and Stage20 recorder inactive. Free space394,344,198,144 bytes.

- Original runtime SHA256: `feedd883cbb9335569dcf50d33aaf5f66e3db85352dab54b2b3dba76c9137500`
- Installed and read-back SHA256: `8f207dc9c7d06cdccc4ec7c82b3e7c6aae29a86121b39c2271ff4e8922226d63`
- Backup and full evidence: `/home/jetson/project-atlas-migration/astra-20261021/coverage-20261021T211557/`
- Original backup: `atlas_vision3d_runtime.py`; original hash verified before replacement.
- Scalar evidence: `deployment.json`, `cpu.jsonl` in that directory.
- deployment.json SHA256: `1c78197c7e36779ee82c1af78af1995bd6bab1564cdfa08c34fe0fbd22add7ee`

Rollback was not needed. With fresh stationary admission and Astra OFF, verify
the backed-up original hash, copy it to a sibling temporary file, atomically
replace the runtime, then restart only the web service to reload the parent
implementation. Verify restored hash, all protected identities, sensor freshness
and resource settling. Do not start a camera as a rollback test.

## CPU trace and settling

Low-overhead persistent /proc sampling started before replacement/restart.
Restart monotonic timestamp2666.452582860. Rows below are relative seconds,
actual window seconds and aggregate CPU percent. These are scalar deployment
telemetry, not camera/ROS recordings. Original full precision is preserved locally.

| Relative seconds | Window seconds | CPU % |
|---:|---:|---:|
| -1.048 | 1.002 | 69.1910 |
| -0.045 | 1.003 | 68.8663 |
| 0.955 | 1.001 | 85.1100 |
| 1.956 | 1.001 | 87.0307 |
| 2.957 | 1.001 | 83.2479 |
| 3.958 | 1.001 | 74.0550 |
| 4.959 | 1.001 | 72.2127 |
| 5.960 | 1.001 | 75.0000 |
| 6.960 | 1.001 | 91.0473 |
| 7.961 | 1.001 | 99.6672 |
| 8.962 | 1.001 | 99.6667 |
| 9.963 | 1.001 | 99.8325 |
| 10.964 | 1.001 | 99.8342 |
| 11.965 | 1.001 | 98.8314 |
| 12.965 | 1.001 | 99.6661 |
| 13.966 | 1.001 | 99.8328 |
| 14.967 | 1.001 | 99.3322 |
| 15.968 | 1.001 | 97.9933 |
| 16.969 | 1.001 | 98.3165 |
| 17.970 | 1.001 | 97.4790 |
| 18.971 | 1.001 | 95.3099 |
| 19.972 | 1.001 | 94.2664 |
| 20.973 | 1.001 | 86.3406 |
| 21.974 | 1.001 | 75.8037 |
| 22.974 | 1.001 | 70.4082 |
| 23.975 | 1.001 | 71.6263 |
| 24.976 | 1.001 | 69.7232 |
| 25.977 | 1.001 | 70.7106 |
| 26.978 | 1.001 | 71.7949 |
| 27.981 | 1.003 | 69.1379 |

Restart transient peaked99.8342%. Per approval, waited without camera admission;
five consecutive <=75% samples occurred at+22.974 through+26.978s. Postflight
RAM64.1071%, hottest60.687 C. This is not a claim that CPU stayed below75% during
restart, nor a demonstration that combined streaming can fit under the limit.
No safety threshold was changed. Monitoring terminated after postflight.

## Protected services and installed-code verification

Pi camera1824, telemetry3293, mux1814, EKF2868, localization4595, LiDAR1815 remained
active with identical PIDs and NRestarts0. Approved web PID1992 became28561,
active/NRestarts0 (manual restart does not increment automatic-restart counter).
Pi camera metadata/publisher, LiDAR, IMU and all four encoder feeds passed <=2s
freshness checks after restart. This validates telemetry health, not physical
accuracy. E-STOP/zero-command/manual-only/recorder-OFF checks passed again.

Installed file was copied back and hash-matched to the reviewed source. The new
web process loads that source. Its parent baseline capture precedes worker launch,
and the worker samples before and during hashing;12 offline startup-coverage tests
were rerun successfully, including overload during hashing/no driver spawn.
No worker was activated on Jetson: live overload behavior is not newly validated.

Before/after hashes of web receiver, geometry, browser JS, live configuration,
stationary gate and ROS probe were unchanged. Those exact hashes are in retained
deployment evidence. Six driver mode argument vectors were previously tested
unchanged. Depth-only Preview, IR640x480, Domain77, calibrated-cloud restriction,
75/80/70 and1s-window policies are preserved. Dashboard reports OFF, calibration
UNVALIDATED. No Astra process remains. A fresh web summary's driver_stopped=false
is an unset session flag, not an assertion that a driver exists; process absence
was checked independently.

## Independent calibration preparation and next approval

Six offline calibration validation tests pass. Existing target and tools are
ready; no calibration file was installed or declared valid. Combined RGB is not
a prerequisite for IR intrinsics or depth scale work.

Owner preparation (no camera start needed): print the prepared A4/25mm target at
actual size; measure both100mm scale bars and9-square/6-square spans; mount flat.
Report measured values. Prepare a large flat depth target and tape-measured
distances from the Astra front face, plus target width/height. Do not substitute
nominal print dimensions for actual measurements.

Next approval should prioritize ONE guarded Depth-only Uncalibrated Preview
verification, not require RGB first. Calibration image capture/IR-depth sessions
require separate explicit approval and the measured targets. Calibrated metric
PointCloud2 remains disabled until physical calibration validation passes.
