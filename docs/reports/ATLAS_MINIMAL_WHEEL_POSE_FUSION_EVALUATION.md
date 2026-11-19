# Minimal wheel-pose fusion candidate — Track B

14 October 2026. Dedicated branch `agent/sync-developer-20261011`.
**BUILT; configuration TESTED OFFLINE; candidate performance BLOCKED; NOT DEPLOYED.**
No new native replay, production access, movement, tuning or service restart was
performed for this track. Stage 17B remains on HOLD. Existing Stage 18/19 findings
were reused, not re-run or renamed as new experimental results.

## Decision

Removing wheel X/Y pose observations is a precisely bounded candidate, not yet a
verified fix. It removes one route by which incorrectly integrated wheel heading
can affect EKF translation. It does **not** repair under-reading wheel velocities,
establish physical steering angles, guarantee unchanged EKF yaw, or prove the
cause of the five AMCL switches. Gyro authority already exists in the baseline.

Existing recordings support local **recorded wheel versus recorded EKF versus
screened LiDAR** comparisons. They do not support a trustworthy historical native
EKF A/B comparison, including a local-relative one: the prior cold-start baseline
still differed by up to 1.343 m / 18.401 degrees after removing the first rigid-frame
difference. Subtracting a start pose cannot recover missing filter covariance,
relative measurement anchors and reference history. A short-window restart or
invented convergence burn-in would not solve that problem.

Accordingly, no further known-unfaithful replay was run. No candidate AMCL jump
count, covariance improvement or post-stop stability improvement is claimed.
This does not block independent preparation of the 30-second recorder.

## Exact candidate, without a second replay implementation

Reuse `stage19_contract.variants()` and its existing fidelity gate. The new
`project_atlas/tools/diagnostics/fixtures/minimal_wheel_pose_candidate.json`
pins the real reviewed baseline, the two changed indices, complete selection
vectors, and the lack of deployment authority. It is a diagnostic manifest,
**not a ROS parameter overlay that can silently alter production**.

Baseline file: `project_atlas/config/atlas_ekf.yaml`.
SHA256: `69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`.
This matches the archived Stage 19 manifest's source hash. It is a source/archive
identity check, not a fresh live Jetson configuration attestation.

State order: X,Y,Z,roll,pitch,yaw,Vx,Vy,Vz,Vroll,Vpitch,Vyaw,Ax,Ay,Az.

| Parameter | Baseline A | Candidate B |
|---|---|---|
| `odom0_config` selected indices | 0,1,6,7 | 6,7 |
| `imu0_config` selected indices | 11 | 11 |
| wheel topic | `/yahboom/odom` | unchanged |
| IMU topic | `/im10a/imu/bias_corrected_candidate` | unchanged |
| relative wheel mode | true | unchanged |
| TF offset | +0.2 s | unchanged |
| queues, frequency, process/measurement covariances, frames | existing | unchanged |

The existing builder adds `use_sim_time=true` to **both** replay variants; this is
the common replay adaptation, not a candidate-only change. No scale, sign, bias,
map, steering command or navigation threshold changes. Physical steering commands
remain commands, not measured wheel angles. Measurement covariance values in bag
payloads would remain untouched. Removing an observation can change covariance and
state cross-coupling; the unchanged gyro source does not prove identical yaw output.

## Strongest valid numerical comparison already available

Provenance: saved Stage 18 output
`artifacts/stage18_motion_comparison_20261014_verified.json`, SHA256
`0c0f3c21dcb836661b3f48b6f647da13d877869aeba02e844173ad665f778f0b`.
Each bag's source hash is preserved inside that evidence. Existing reports:
`ATLAS_STAGE18_ODOMETRY_SENSOR_FUSION_REPORT.md` and
`ATLAS_STAGE19_NATIVE_EKF_AMCL_REPLAY.md`.

These are **previous results extracted from saved evidence**, not new experiments.
Median relative errors versus neutral-seed, reciprocal-screened LiDAR ICP:

| Recording | Screened / all motion windows | Wheel XY / yaw | Recorded EKF XY / yaw | Candidate B |
|---|---:|---:|---:|---|
| Hall return exact | 12 / 26 | 8.33 cm / 3.052 deg | 10.88 cm / 1.190 deg | not evaluated |
| Return retry2 | 11 / 29 | 9.02 cm / 2.163 deg | 9.89 cm / 1.058 deg | not evaluated |
| Outbound retry2 | 4 / 19 | 14.64 cm / 3.332 deg | 13.62 cm / 1.748 deg | not evaluated |
| Final roundtrip exact | 26 / 52 | 11.02 cm / 3.406 deg | 12.27 cm / 1.794 deg | not evaluated |
| Outbound 16:36 | 0 eligible | unavailable | unavailable | not evaluated |

All 126 existing motion windows are accounted for: 53 screened and 73 unknown.
The fifth drive has no eligible comparison, not a zero-error pass. Screened ICP
is an independent relative-motion proxy, not surveyed ground truth; repeated
geometry, scan distortion and uncalibrated confidence remain limitations.

The gyro-heading/wheel-distance **non-EKF shadow** previously gave 8.28 cm /
1.080 deg in the Hall return and 11.37 cm / 0.944 deg in the final roundtrip.
It is not Candidate B: it lacks native EKF measurement updates/covariance. It
must not be substituted into the Candidate B column. The recorded EKF's lower
yaw error but mixed translation result motivates isolating pose observations;
it does not prove those observations cause the error.

## Metric disposition and what cannot be inferred

| Requested comparison | Available baseline evidence | Candidate B result |
|---|---|---|
| Relative heading / translation | table above, four eligible drives | unknown |
| EKF continuity / post-stop stability | Hall recorded stop span 0.01140 m; old cold replay 0.01138 m | unknown |
| Uncertainty | recorded output covariance; not full cross-covariance/checkpoint | unknown |
| Wheel / IMU / LiDAR disagreement | existing screened windows and wrong-yaw traces | inputs unchanged; removal effect unmeasured |
| TF validity | old native baseline had zero backwards odom-TF transitions | no candidate output to validate |
| Original parked AMCL jumps | five, maximum 2.206 m | unknown, not zero |

The old native baseline produced eight moving jumps and zero parked jumps; that
was an inaccurate reproduction, not a fix or Candidate B result. The accepted
archived Jetson map identity remains in the Stage 19 contract; no new global map
comparison was attempted. No map-match percentage is used as success evidence.

## Smallest missing evidence — separate local and AMCL gates

For a reproducible **local EKF** A/B comparison, retain the actual EKF initialization
sequence from a future normal startup (full effective parameters, versions, first
relative wheel-pose reference, every selected observation and original timestamps,
TF/static-TF and frame identity), or a complete restorable filter checkpoint:
state, full covariance, relative-reference transforms and relevant time/history.
Recorded `/odom` means and its 6x6 pose/twist covariance blocks alone are not that
checkpoint. Initial conditions must be declared from actual events, not fitted
to the desired outcome. No restart or private instrumentation is authorized here.

To claim the original **AMCL** failure is corrected additionally requires its
genuine initialization/events or restorable particle/weight/RNG/cluster state,
the accepted map, parameter history, no-motion service-event timing, scan/TF
receipt and source times, and a baseline that recreates the failure conditions.
Published particle output alone cannot restore that state. Public-only stationary
recording can validate capture integrity, current freshness/TF and stopped motion;
it cannot retroactively recover the October 9 state or prove moving performance.

No new full-house route is requested. Once approved evidence capture actually
includes the missing initialization history, evaluate local A/B first. A later
separately approved short measured movement is needed for physical validation;
a stationary 30-second bag alone cannot establish moving-localization accuracy.

## Tests, resource impact, rollback and approval

Four new real-baseline contract tests passed on Windows in 0.024 seconds:
exact pinned hash; only two selection flags changed with full configuration
equality otherwise; no new sensor/motion authority; public outputs cannot unlock
the historical fidelity gate. These extend the existing Stage 19 tests with the
actual production-source YAML, rather than another synthetic EKF model.

Command: `.venv/Scripts/python.exe -X utf8 -m unittest discover -s
project_atlas/tools/diagnostics -p test_minimal_wheel_pose_candidate.py -v`.
No native resource benchmark or performance improvement is claimed. No new Jetson
process was run for Track B. No production file changed, so live rollback is not
needed. Stop using the diagnostic manifest/tests to roll back source preparation;
preserve the recordings and prior trial evidence. Runtime candidate installation
remains unauthorized. No recording, movement or steering test is requested now.

**Final disposition: candidate BUILT and configuration TESTED OFFLINE; moving
localization and the original five AMCL jumps remain UNRESOLVED.**
