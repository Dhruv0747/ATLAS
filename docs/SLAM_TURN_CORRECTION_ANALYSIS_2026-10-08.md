# ATLAS SLAM turn-correction analysis — 2026-10-08

## Evidence

The controlled manual-mapping bag is:

`manual_mapping_debdd698e59b-20261008-113519`

Recorder process creation does not prove subscriptions were ready before SLAM
startup. Also, starting an already-active SLAM service does not reset its map.
These runs must not be described as independently initialized fresh maps.

The route was manually driven, so joystick timing and exact wheel tracks are
not expected to be identical between runs.

## Result

The latest run passed round-trip closure:

- translation closure: **0.082 m**
- heading closure: **2.99 deg**

It still failed the TF continuity gate:

- largest `map -> odom` correction: **0.747 m**
- largest yaw correction: **10.70 deg**

The prior run measured 1.199 m / 14.20 deg. This is an improvement, but different
manual trajectories and retained SLAM state prevent attributing it solely to
gentler turns. The remaining correction exceeds the current promotion gate.

## Attribution

The prior `c6c7d28d` run was classified by the analyzer as a SLAM
scan-matching/pose-graph correction during a turn. In that run:

- largest `/odom` step: 0.061 m
- largest `/yahboom/odom` step: 0.057 m
- filtered LiDAR remained live
- encoder feedback was live

This locates the discontinuity in map correction; it does not establish the
root cause. Smooth odometry can still have scale/heading error. Loop closure
can legitimately correct accumulated drift. Duplicate TF authority must also
be excluded before assigning blame. Preserve the acceptance threshold and map
while investigating.

## Next gate

Perform one software-only SLAM A/B evaluation against this bag. Keep steering,
encoder selection, and the accepted map unchanged. Only a configuration that
reduces the TF correction while preserving closure may proceed to one final
controlled mapping loop. Rebind Dhruv Room and Hall only after the candidate
map passes all acceptance gates. Candidate endpoints must first be measured
in that candidate's frame for connectivity checks; merely relabeling old
coordinates with a new map ID is invalid.

## Completed offline comparison

On 2026-10-08, replayed the exact `debdd698e59b` input twice in localhost ROS
domain 177. The input bag contained only 1,236 scans and non-map transforms;
recorded map transforms and all command topics were excluded. Each variant
started a separate SLAM process using the live service's parameters, changing
only `do_loop_closing`. Playback ran at 0.5x under Nice=15 and a one-core CPU
quota. Neither run logged scan drops. Both output recordings closed normally.

| Metric | Loop closure on | Loop closure off |
| --- | ---: | ---: |
| Recorded replay scans | 1,236 | 1,236 |
| Map messages | 243 | 243 |
| Largest map correction | 0.770482 m | 0.770482 m |
| Largest yaw correction | 11.197887 deg | 11.197887 deg |
| Approximate endpoint displacement | 0.087227 m | 0.087227 m |
| Approximate endpoint heading difference | 1.503205 deg | 1.503205 deg |

Endpoint values use the most recently received correction, not interpolated
time-aligned TF, and are diagnostic estimates, not acceptance certification.
Scan counts prove recording completeness, not that every scan was matched.

**Decision:** keep the live loop-closure setting. Disabling it did not improve
this input. The replay reproduces the correction with one SLAM map-transform
publisher, so duplicate live TF publishers are not required to reproduce it.
This narrows investigation to scan matching/its odometry prior and does not
prove encoder scale or heading estimates are accurate. No live steering,
navigation, IMU, or encoder parameter was changed.

A further manual loop is not needed to investigate this comparison. Next use
the saved input to inspect odometry-versus-scan alignment around the jump and
map geometry; do not promote a map solely because endpoint closure is small.

## Recorded turn sensor comparison

Ran `atlas_turn_sensor_audit.py` read-only against the deb bag. Largest
translation correction receipt time: 1791439656.648584. Comparisons use scan
header times, interpolated odometry yaw and integrated candidate IMU gyro Z.

| Window relative to correction | Fused yaw | Wheel yaw | IMU yaw | Diagnostic scan-fit yaw |
| --- | ---: | ---: | ---: | ---: |
| -1 s, duration 1.047 s | -20.31 deg | -21.51 deg | -21.02 deg | -22.43 deg |
| +1 s, duration 0.919 s | -2.90 deg | -16.54 deg | -3.16 deg | -5.99 deg |

Main turn agreement does not support ignoring the IMU. The subsequent wheel
heading discrepancy warrants investigation. Live EKF configuration uses IM10A
gyro Z and excludes wheel yaw/rate, but includes wheel X/Y pose and velocity.
Source inspection shows wheel X/Y is integrated using heading derived from
encoder distance and commanded front/rear steering angles. Thus excluding
wheel yaw alone does not remove its influence on wheel position. This is a
testable contributor, not a proven cause of this map correction.

The event window also contains two CRITICAL encoder-consensus samples despite
a live board link; earlier broad exclusion of encoder involvement was premature.
Scan receipt minus header age was median 136 ms, p95 269 ms in that window;
candidate IMU age median 2.6 ms, p95 6.9 ms. Receipt age is not automatically a
sensor timestamp error. Live EKF TF offset is +0.2 s; do not blindly shift
odometry message timestamps by that amount.

Diagnostic ICP has no scan deskew or global optimization, so it is not ground
truth. The +3 s window is initialization-sensitive (-2.21 to -4.23 deg).
Known-transform and insufficient-point unit checks passed; full recorded-bag
execution succeeded. No robot motion or production parameter change occurred.

Next controlled software comparison: preserve the baseline, replay velocity-only
wheel input plus IMU versus current wheel-pose-plus-velocity fusion in an isolated
domain, then compare downstream SLAM corrections and geometry. Do not promote
either configuration without measured improvement and ground validation. No
additional manual loop is needed to perform that comparison.

## Completed isolated EKF/SLAM comparison

Replayed the same deb bag in unused localhost domain 178, at 1x, starting fresh
EKF and SLAM processes for each variant. Only `odom0_config` X/Y pose selection
changed; wheel velocity, IMU gyro Z, noise settings and +0.2 s TF offset remained
identical. Recorded map/odom transforms were removed. The input contained 1,236
scans, 1,802 wheel odometry messages, 1,861 candidate IMU messages and two static
TF messages. No command topics or actuator nodes were present.

| Metric | Pose + velocity | Velocity only |
| --- | ---: | ---: |
| Scans recorded | 1,236 | 1,236 |
| Map messages | 122 | 122 |
| EKF output messages | 1,837 | 1,833 |
| Largest map translation correction | 0.712702 m | 0.614011 m |
| Largest map yaw correction | 12.797585 deg | 12.797585 deg |
| Approximate endpoint displacement | 0.093105 m | 0.066087 m |
| Approximate endpoint heading difference | 1.465881 deg | 3.035907 deg |
| Final map dimensions (cells) | 211 x 246 | 210 x 243 |

**Decision: do not deploy this candidate.** Translation correction decreased
about 14%, but remains large. Endpoint heading consistency worsened and the
maximum yaw correction did not improve. This does not establish wheel-pose
fusion as the sole/root cause. One replay per variant cannot establish
repeatability; scheduling can vary. Endpoint estimates are not time-interpolated
TF or surveyed ground truth, and map geometry is not independently certified.

Both runs closed successfully without scan-drop warnings. Each logged one
initial simulated-clock backwards transition. Filter diagnostics were healthy
in 361 samples per run; frequency diagnostics included two no-event and eight
low-frequency reports per run, which must not be represented as uniformly
healthy timing. Recording every scan does not prove every scan was matched.

Replay resource observations: approximately 161–185 MB memory, sampled Jetson
temperature approximately 61 C, total 62.2 CPU seconds over about 6.6 minutes;
Nice 15, CPU quota 150%, memory cap 900 MB. These are observations, not peak-load
certification. Three offline configuration/safety checks passed.

Artifacts remain on Jetson at
`/home/jetson/project_atlas/data/diagnostics/fusion_ab_20261008/`.
The original live EKF YAML SHA-256 before and after was identical:
`69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`.
No steering, motor, accepted map or production fusion configuration was changed.
Rollback is unnecessary for production; the isolated test unit has exited.

Next investigate timestamp-aligned scan/odom geometry at the correction, including
the TF time offset and scan acquisition timing, before choosing another bounded
offline comparison. Do not request another manual route merely to repeat this
saved-data analysis or weaken the map-promotion threshold.

## Scan/TF timing measurements

Read-only analysis of the original deb recording around correction receipt time
1791439656.648584, using scans stamped within +/-5 seconds:

- 1,247 raw scans and 1,236 filtered scans overall; every filtered scan retained
  a matching raw header stamp. Neither stream had non-increasing stamps. This
  does not certify why 11 raw scans lack a filtered counterpart.
- 68 raw and 68 filtered scans in the event window. Median scan acquisition
  duration 130.04 ms, maximum 267.80 ms. Median filtered receipt age 136.12 ms;
  after subtracting declared scan duration, median 5.24 ms, maximum 18.69 ms.
- Full-run paired raw-to-filtered bag receipt difference median 4.66 ms, p95
  12.26 ms. Some negative differences occur because receipt times are observer
  scheduling, not a precise measurement of filter execution latency.
- At the same scan times, recorded TF yaw versus `/odom` yaw differed by up to
  6.56 deg (p95 3.38 deg). Shifting only TF stamps back 0.2 s aligned these two
  representations to numerical precision. This verifies the configured temporal
  offset, not absolute physical heading accuracy or the mapping root cause.
- IMU-integrated rotation during one scan peaked at 8.89 deg over 267.80 ms,
  beginning 0.492 s before the correction was received. Motion distortion is a
  plausible contributor; per-ray acquisition ordering must be verified against
  the installed driver before implementing deskew. Do not rewrite scan header
  stamps to publication time or assume one rigid pose is ground truth.

Four numerical checks passed (wrapped-angle interpolation, extrapolation
rejection, known timestamp shift, empty statistics). No production settings
were changed by this audit.

## Completed TF-offset comparison

Fresh isolated domain-178 replay of the same deb bag, rate 1.0, current
pose+velocity wheel fusion retained. Only `transform_time_offset` varied.

| Metric | Current +0.2 s | Zero offset |
| --- | ---: | ---: |
| Recorded scans / map messages | 1,236 / 122 | 1,236 / 122 |
| EKF output messages | 1,840 | 1,838 |
| Largest translation correction | 0.722693 m | 0.812860 m |
| Largest yaw correction | 12.397661 deg | 9.998114 deg |
| Approximate endpoint displacement | 0.091970 m | 0.096671 m |
| Approximate endpoint heading difference | 1.865806 deg | 1.715834 deg |

**Reject zero offset for live deployment on this evidence.** It reduces the
largest yaw correction but worsens the largest translation correction by about
9 cm. The current-offset baseline is close to the previous 0.712702 m replay,
but repeat scheduling is not deterministic. Neither configuration passes the
map-promotion gate, and these diagnostic endpoint estimates are not ground truth.

Both recordings closed successfully; no scan-drop, extrapolation or error lines
were found in EKF/SLAM logs. Each run has two no-event and eight low-frequency
diagnostic samples, so timing is not certified uniformly healthy. Four fusion
configuration checks and four timing-math checks passed. The transient replay
unit exited successfully. Artifacts are retained at
`/home/jetson/project_atlas/data/diagnostics/timing_ab_20261008/`.
Live EKF SHA-256 remains
`69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`.

Next bounded investigation is the scan geometry at the specific high-rotation
scan: verify installed driver's per-ray timing/order before testing motion
compensation or scan-quality gating offline. The 8.89-degree acquisition motion
is a measured candidate, not proof that deskew will solve this. Do not combine
that experiment with wheel-fusion or TF-offset changes, and do not alter working
steering or ask for another manual route while this saved data suffices.

## Driver audit and scan-rotation sensitivity

Installed package: `ros-humble-rplidar-ros 2.1.4-1jammy.20260607.092451`;
`dpkg -V` reported no differences. Runtime settings: inverted false,
flip_x_axis false, angle_compensate true. Reviewed the matching
[ROS release source](https://raw.githubusercontent.com/ros2-gbp/rplidar_ros-release/release/humble/rplidar_ros/2.1.4-1/src/rplidar_node.cpp).
It measures duration around a data-read call, sorts/angle-compensates the
returns, and reverses output indexing for this configuration while publishing
a positive uniform time increment. Exact per-ray acquisition times are not
recoverable from this bag alone. In particular, the prior 8.89 deg estimate is
rotation over the **reported time window**, not verified physical scan distortion.

Executed read-only rotation-only sensitivity analysis on 68 consecutive scan
pairs near the correction. Both forward and reverse uniform-time hypotheses
use the same integrated IMU and local ICP method; no translation compensation
or modified ROS messages are introduced. The nine sharper-turn pairs have
over 2 deg integrated motion in at least one reported scan window.

| Diagnostic median ICP residual | Unchanged | Forward-time hypothesis | Reverse-time hypothesis |
| --- | ---: | ---: | ---: |
| All 68 pairs | 7.00 mm | 7.06 mm | 7.01 mm |
| Nine sharper-turn pairs | 8.96 mm | 9.35 mm | 9.25 mm |
| Pairs improved against unchanged | — | 30/68 | 32/68 |

Both hypotheses reduce some upper-tail residuals, but neither consistently
improves the median. Residuals measure nearest-neighbour fit, **not** surveyed
map accuracy, navigation accuracy or correct data association. Unknown timing
phase, angular rebinning, translation and moving objects remain confounders.
These results neither prove nor rule out motion distortion; they do not justify
deploying guessed per-ray timing or claiming the mapping fault fixed.

Two rotation-math checks passed, and the complete recorded-data analysis ran
successfully. Full pair results are saved on Jetson at
`/home/jetson/project_atlas/data/diagnostics/scan_rotation_sensitivity_20261008.json`.
No motors, steering, production driver, EKF or accepted map changed.

Decision: retain the live baseline. Next evidence needed is a geometric review
of scan-to-submap correspondences at the jump, not another guessed timing knob.
If physical per-ray deskew is pursued, it needs verified SDK/acquisition timing
before a ground trial. This investigation has not validated autonomous mapping.

## Frozen prior-map geometric comparison

Compared eight scans from -0.749 to +0.297 seconds around the original deb
correction against a 5 cm occupancy grid received 1.548 seconds before the
correction (before every tested scan). Occupied cells >=65 form the reference.
Recorded laser extrinsics and interpolated odom->base_link TF are composed
with each map->odom hypothesis at the same scan timestamp. No map updates or
post-event map are used for scoring.

All eight scans have lower median endpoint-to-occupied-cell distance under the
**after** hypothesis. For the scan at -0.098 seconds, median error changes
9.25 cm -> 2.53 cm, p90 29.14 cm -> 4.51 cm, and endpoints within 10 cm of
occupied cells increase 53.8% -> 100%. This supports correction of an inaccurate
pose prior; it does not support the initial presumption that SLAM necessarily
matched the wrong corridor. Repeated geometry can still alias, and this grid
does not expose optimizer correspondence IDs, constraint scores or ground truth.

Important metric correction: the ~0.747 m map->odom translation change is an
origin-dependent frame-transform change, **not** a 0.747 m robot displacement.
Composing both hypotheses with the same odom pose yields ~0.232–0.236 m robot
position correction and -9.75 deg heading correction across these scans.
Prior replay tables remain accurate as *transform-component* measurements,
but those values alone cannot rank physical localization error. Review any
acceptance gate based solely on map->odom translation before using it as a
physical-distance gate; do not simply loosen it to pass this run.

Three geometry unit checks passed, including a case with large frame-origin
translation and zero robot-position change. Results saved on Jetson at
`/home/jetson/project_atlas/data/diagnostics/scan_map_jump_pose_20261008.json`.
No motion, live parameter, steering or map changes occurred.

Next: evaluate same-time map->base_link correction and prior-map consistency
across the saved run, then compare odometry prediction against those corrections.
The evidence suggests examining accumulated odometry/heading error rather than
suppressing this geometrically beneficial correction. It does not prove its
hardware/software source or authorize autonomous navigation.
