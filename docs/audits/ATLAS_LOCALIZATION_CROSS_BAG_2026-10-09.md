# ATLAS localization cross-bag and isolated AMCL audit — 2026-10-09

This continues the Hall → Dhruv Room investigation in
[the navigation gate](ATLAS_NAVIGATION_GATE_2026-10-09.md). It is not a new
physical trial. No rover movement, motor command, production parameter change,
or autonomous launch was made. The observed motor-base service remained
inactive. The production EKF file SHA-256 remained
`69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`.

## What the recorded drives establish

The read-only batch audit uses the overlapping wheel-odom and **bias-corrected
IM10A** timestamp interval. The older analyzer incorrectly mixed raw
`/imu/data` and corrected IM10A samples into one gyro series; that diagnostic
bug is fixed and tested. Approximate integrated yaw (degrees):

| Recording | Wheel model | Corrected gyro | Wheel minus gyro | AMCL jump data |
| --- | ---: | ---: | ---: | --- |
| Oct 2 fresh Hall mapping | -128.9 | -101.0 | -27.9 | unavailable |
| Oct 2 second mapping | -101.4 | -106.7 | +5.3 | unavailable |
| Oct 2 manual mapping | -321.2 | -352.4 | +31.2 | unavailable |
| Oct 4 Hall return | -107.0 | -193.5 | +86.6 | unavailable |
| Oct 8 left/right repeat | -44.2 | +2.5 | -46.7 | unavailable |
| Oct 8 left/right retry | -13.4 | -16.2 | +2.8 | unavailable |
| Oct 8 manual mapping c6 | -351.8 | -356.7 | +4.8 | unavailable |
| Oct 8 manual mapping deb | -381.0 | -354.1 | -27.0 | unavailable |
| Oct 9 Hall → Dhruv | -143.0 | -191.5 | +48.5 | five >0.5 m post-stop; max 2.206 m |

Two short/stationary bags were also inventoried; they do not establish dynamic
heading agreement. These are different routes, maps and hardware eras, so yaw
disagreement is **not** a single transferable calibration correction. Most
earlier bags have no `/amcl_pose`; this is *unavailable*, not zero jumps.

The exact recorded encoder-consensus calculation reproduced the Oct 8 and
Oct 9 wheel-odom deltas with zero selection mismatches and no sequence gaps.
M3 was accepted in 2,735/2,919 Oct 9 updates; it cannot be declared faulty
from this route. At Oct 9 t=185.23–189.58 s, the wheel model integrated
**+7.42°**, while the gyro integrated **-18.96°** and gyro-seeded LiDAR ICP
estimated **-16.09°**; zero-seeded ICP also estimated a negative turn
(**-11.98°**). All four encoder channels were selected in 35/44
updates. On Oct 8 t=44.56–46.61 s, front/rear *commanded* steering was 90°,
wheel-model yaw 0°, gyro +16.62°, and scan ICP +17.65° during a reverse
segment. ICP supports but does not independently prove true chassis yaw.
Commanded steering is not measured road-wheel angle; physical steering offset,
lag, traction and geometry remain distinguishable candidates. A 0–1 s
command-delay sweep did not eliminate the mismatch. A focused recheck of the
Oct9 wrong-sign interval found that applying 0.2, 0.5 and 0.75 s delayed
**commanded** steering to the recorded accepted distance changed wheel-model
yaw from +7.42° to +4.27°, +2.43° and +1.30° respectively—**still opposite**
the corrected gyro (-18.96°) and scan ICP (-16.09°). The same 0.5 s delay
made a later turn's wheel estimate -44.63° instead of -76.24°, farther from
the gyro's -77.45°. Across all moving samples, 0.5 s lowered yaw-rate RMSE
from 9.79 to 6.66°/s, but these opposing segment results rule out a single
global command delay as a verified repair. This sensitivity does not
recalculate wheel path normalization or measure servo lag.

Recorded p95 header-to-receipt ages on the Oct 9 drive were about 8 ms for
wheel odom, 6 ms for corrected IMU, and 94 ms for EKF. Scan receipt age
includes acquisition duration and must not be interpreted as transport lag.
Freshness alone did not prevent AMCL hypothesis switching after stopping.
Around the largest post-stop correction, 2,054 filtered scans had strictly
increasing header stamps, and scan receipt time minus acquisition `scan_time`
had 6.3 ms median/11.8 ms p95 in the ±5 s event window. Filtered-vs-raw
receipt lag had 4.6 ms median/11.5 ms p95. Recorded `/odom` and the
`odom→base_link` TF are internally consistent after accounting for the
configured 0.2 s future TF offset; they are generated from the same EKF and
therefore are **not** independent proof of correct physical pose. The large
AMCL switches began seconds after remote motion stopped, not at a data gap.

## EKF A/B across available recordings

The original EKF fuses wheel X/Y **pose** and velocity plus corrected gyro Z.
The wheel pose is already integrated using commanded steering-derived yaw.
Thus an erroneous yaw model can inject inconsistent X/Y updates into the
gyro-aided EKF even though wheel yaw and yaw rate are not directly fused.
Velocity-only omits that X/Y pose update; it is a candidate, not a fix.

| Isolated replay | Original pose+velocity | Wheel velocity-only | Interpretation |
| --- | ---: | ---: | --- |
| Oct 9 saved-map scan fit, median within 15 cm | 23.1% | 50.2% | Candidate better, still poor |
| Oct 8 manual mapping deb, max SLAM translation correction | 0.713 m | 0.614 m | Candidate better |
| Oct 8 manual mapping deb, final heading discrepancy | 1.47° | 3.04° | Candidate worse |
| Oct 8 left/right repeat, max SLAM translation correction | 0.273 m | 0.303 m | Candidate worse |
| Oct 8 left/right repeat, max SLAM yaw correction | 15.00° | 7.80° | Candidate better |

The Oct 8 replays are SLAM tests, **not** saved-map AMCL jump tests.
Improvements are mixed across metrics and recordings.
Not every inventoried bag has yet had both EKF variants replayed; older
recordings predate the current hardware/map state. The three directly compared
drives are the two Oct 8 mapping bags and the Oct 9 Hall return. No claim of
cross-route AMCL jump reduction is possible from this coverage.

## Saved-map AMCL replay of the Hall return

An additional isolated replay used ROS domain 179, the accepted saved map,
the same recorded Hall AMCL seed (0.333 s before clip start), 750 wheel-odom
messages, 751 corrected-IMU messages and 529 scans. Only wheel X/Y pose fusion
changed between variants. The input contained no actuator topics; no control
nodes were launched. Artifacts remain on the Jetson at
`/home/jetson/project_atlas/data/diagnostics/hall_amcl_ab_20261009/`.

| Measure | Original | Velocity-only |
| --- | ---: | ---: |
| AMCL poses | 121 | 126 |
| AMCL consecutive jumps >0.5 m within 2 s | 0 | 0 |
| Largest consecutive AMCL position step | 0.340 m | 0.234 m |
| Median AMCL XY standard deviation | 0.455 m | 0.361 m |
| Max map→odom translation correction step | 0.408 m | 0.194 m |
| Final ~20 s AMCL position span | 0.845 m | **1.789 m** |
| Final AMCL X/Y | (2.556, -0.934) m | (1.721, -0.889) m |

Both variants **failed to reproduce the original five >0.5 m jumps**. The
candidate reduced some local corrections and uncertainty, but its final-window
position span was over twice as large. Neither replay ended at the confirmed
home location (~0.254, -1.539 m). Therefore this test does **not** establish
that velocity-only reduces real AMCL jumps or yields stable orientation and
position after stopping. Replay has different startup/particle randomness and
cannot fully recreate live map/TF/history conditions; receipt-to-header ages
in the replay reflect playback-wall time and are not live latency metrics.

## Decision and remaining gate

Verified proximate failure: AMCL switched hypotheses after the remote stopped
while wheel-derived and gyro/scan-supported heading disagreed during the
drive. The wheel-model disagreement is upstream and recurrent. The exact
physical mechanism and its causal share of AMCL switching are **not proven**.
The original EKF has a plausible inconsistency from wheel-integrated X/Y pose
updates, but velocity-only has not passed cross-recording or stationary
stability regression. **Do not deploy it. Localization jumping remains
unresolved and autonomous room-to-room travel remains gated.**

Before release: establish measured physical steering angles or a controlled
signed-turn reference; compare wheel/gyro/scan heading on one frozen hardware
baseline; investigate scan/map ambiguity and AMCL covariance; repeat saved-map
AMCL replays (including a true post-stop window) with deterministic seeds;
then, only with operator approval, perform a low-speed supervised physical
moving-and-stopped localization trial. Preserve the current EKF/Nav2 config
and safety gates until a candidate beats baseline on AMCL jumps, final pose,
post-stop stability and confidence across runs.

## Steering-interface and engineering-reference follow-up (2026-10-09)

The supplied *Embedded Robotics*, fourth edition (2022), sections 5.4, 5.7,
5.9, 6.5, 7.5, 10.5, 10.7, 14.1, 14.11, 14.12, 15.3 and 17.2 distinguish
encoder feedback from commanded motor/servo output, require measured geometry
for dead reckoning, treat pose as uncertain, and require physical validation and
safe manual override. The separately supplied *Mobile Robot Design and
Applications with Embedded Systems* PDF is the second edition (2006), not the
requested fourth; its chapter numbering differs. Neither book's front-only
Ackermann or Mecanum equations can be copied directly into ATLAS's front-and-
rear-counter-steered, four-driven-wheel model.

Read-only runtime check: active user unit `rover-base-telemetry.service` executes
`/home/jetson/project_atlas/scripts/yahboom_base.py`. Both that file and its
`Rosmaster_Lib.py` match the repository SHA-256. The production driver writes
front PWM channel 2 and rear PWM channel 1 using `set_pwm_servo(id, angle)`.
That serial request sets a PWM target; it does not query or return shaft
position. The vendor library has `get_uart_servo_angle`, but that is a
**different bus-servo interface** and is not proof that these installed PWM
steering servos have readable feedback. The retired ST3215/Waveshare
`motor_config.yaml` is not the live steering path. The physical servo model
and its wiring/feedback lead have not been independently identified. Therefore
shaft-position readback is **not available through the current interface**;
`/steering/*_angle_deg`, `steering_command_deg` and `*_applied_angle` are
commands, not physical shaft or road-wheel measurements. No read-only
position-register probe is justified on the live controller.

The driver calculates curvature as
`(tan(front_command - 90 deg) - tan(rear_command - 90 deg)) / 0.367 m`.
Its 0.260 m track-width correction then uses that curvature **before** encoder
consensus; wheel yaw and integrated X/Y pose use it afterward. This is a
specific, unvalidated servo-command-to-road-wheel-angle assumption, not a
verified linkage law. The wheel radius/CPR and wheelbase/track are provisional
measured values; the record does not support changing them to force agreement.
Wheel PID and its yaw controller remain disabled, so adding or tuning PID does
not diagnose this turn. Motor PWM commands differ on inside/outside wheels,
but the bag contains signed encoder changes, not measured traction or road-
wheel angles; unequal speed/slip remains a candidate, not a confirmed cause.

Focused hypothesis checks against the existing Hall-return bag:

| Hypothesis | Supporting evidence | Contradictory/limiting evidence | Result |
| --- | --- | --- | --- |
| One encoder/channel sign or packet outage caused the wrong-sign turn | M3 raw change was lower than other channels in that interval | All four were accepted in 35/44 updates; zero stale snapshots, sequence gaps or replay selection mismatches; other turns agree well | Not established; do not exclude M3 |
| A constant steering-command lag caused it | 0.5 s shift reduced aggregate yaw-rate RMSE | Wrong-sign interval remained +1.30 deg even at 0.75 s versus gyro -18.96 deg; another turn worsened | Rejected as a single global repair |
| Servo command is an inaccurate proxy for road-wheel angle | No external PWM readback or linkage calibration; commanded 90/90 also coincided with a measured turn in a separate bag | Physical angle, slip, and mechanical load were not measured | Plausible, unproven |
| LiDAR/TF timing alone caused the post-stop jumps | AMCL changed hypothesis after stopping | Scans were monotonic/fresh and EKF odom/TF internally consistent; consistency is not physical truth | No single timing fault proven |

**Decision:** no production software correction or calibration was made in
this follow-up. The five original post-stop AMCL jumps (max 2.206 m) remain
the live baseline; no replay has demonstrated jump reduction. An offline
command-vs-command comparison cannot establish servo tracking. Next, without
powering movement, identify the installed front/rear servo model and number
of wires from accessible labels/photos. If there is an independently wired
feedback signal, review its electrical specification before designing a
read-only diagnostic. Otherwise, with fresh operator permission and a secure
lift, measure physical front/rear road-wheel angle against a fixed chassis
reference at center and small symmetric left/right commands, recording both
axles, command time, arrival time, hysteresis and unloaded/loaded behavior.
Do not infer wheel angle directly from shaft angle. Only then fit an offline
servo-to-road-wheel map and regress the recorded wheel/gyro/scan and saved-map
AMCL tests before any deployment or autonomous trial.

## Post-stop event correlation and operator steering evidence (2026-10-09)

The operator supplied overhead photos at the existing 90-degree center command
and at right/left remote commands, and reports that the current steering
response is satisfactory. The photos demonstrate visible wheel deflection,
but their changing viewpoints do not provide calibrated physical wheel angles,
servo arrival times or loaded linkage behavior. **Preserve the current steering
controls, centers and limits.** No further steering actuation or calibration
is justified by these photographs.

The read-only Hall-return bag analyzer now emits one context row for every
AMCL step >0.5 m within 2 s. Its seven unit tests passed in the Jetson ROS
environment; the original bag again yielded five such steps. Each row used
AMCL receipt time, nearby wheel-pose header times, corrected-gyro header times
and LiDAR scan header times. The wheel samples matched each AMCL endpoint
within 0.2 s. The scan count establishes continuing acquisition, not correct
scan-to-map association.

| Time after last remote command | AMCL XY step | AMCL heading step | Wheel XY step | Corrected gyro turn | Scans between poses | AMCL XY std before→after |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.856 s | 0.565 m | +46.56° | 0.000 m | 0.000° | 6 | 1.152→1.137 m |
| 7.847 s | 2.206 m | -130.25° | 0.000 m | 0.000° | 6 | 1.251→1.322 m |
| 8.872 s | 1.549 m | +60.34° | 0.000 m | 0.000° | 8 | 1.322→1.330 m |
| 9.932 s | 1.549 m | -60.29° | 0.000 m | 0.000° | 7 | 1.330→1.353 m |
| 13.063 s | 1.481 m | +52.58° | 0.000 m | 0.000° | 8 | 1.389→1.384 m |

This confirms **stationary AMCL hypothesis switching**, with no recorded
encoder/gyro motion pulse *at the jump times*. The AMCL XY
standard deviation was already >1 m around all five events, so a fresh pose
message did not imply a trustworthy pose. Upstream turn-model/gyro disagreement
could have weakened the filter before stopping; ambiguous scan/map geometry is
also still possible. This correlation cannot apportion their contributions
or prove a repair. The production EKF and Nav2 remain unchanged; autonomy
remains gated.

## Particle-cloud and same-scan follow-up (2026-10-09)

Continued from commit `54e6519`, using the **same** Hall-return bag. The new
read-only analyzer examines the recorded `/particle_cloud`, the last scan
received before each AMCL step, the saved map, odometry and map→odom TF. It
does not publish or command anything. A diagnostic endpoint fit counts LiDAR
endpoints within 15 cm of occupied map cells; this is **not** AMCL's internal
likelihood or an independent ground-truth pose. The cloud's published weights
were uniform (effective count equalled 1,397–2,000 particles), so nearby
particle fractions are not calibrated hypothesis probabilities.

| Post-stop event | AMCL step | Odom step | Scan receipt age | Same-scan endpoint fit before→after | Mapped obstacle before endpoint, before→after |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.565 m / +46.56° | 0.0004 m | 0.030 s | 58.4→51.1% | 69.4→29.2% |
| 2 | 2.206 m / -130.25° | 0.0000 m | 0.034 s | 62.0→87.3% | 27.7→14.1% |
| 3 | 1.549 m / +60.34° | 0.0000 m | 0.012 s | 87.6→100.0% | 12.9→3.2% |
| 4 | 1.549 m / -60.29° | 0.0000 m | 0.030 s | 100.0→86.6% | 3.2→13.4% |
| 5 | 1.481 m / +52.58° | 0.0000 m | 0.011 s | 87.1→94.0% | 13.8→8.3% |

All five had fresh recorded particle clouds (0–3 ms old), fresh preceding
scans, known map endpoints and AMCL XY standard deviation 1.14–1.39 m. The
cloud's spatial spread was similarly ~1.14–1.38 m. Events 3→4 visibly
reversed between approximately `(1.57,-0.24,0.14 rad)` and
`(0.30,-1.11,1.20 rad)` while the same-scan map fit *worsened* on event 4.
Thus the verified immediate failure is an uncertain, spatially dispersed AMCL
pose estimate switching between competing map hypotheses while the rover is
stationary. It is not explained by a missing scan, wheel motion, or one
seconds-long sensor blackout. The diagnostic ray score is approximate and
ignores dynamic obstacles/scan deskew, so it does not prove why AMCL preferred
one hypothesis. Earlier wheel-model/IMU yaw disagreement may have seeded the
uncertainty, but map ambiguity and AMCL scoring are not separately identified.

Map→odom TF updates did not align one-for-one with AMCL message receipt:
the largest AMCL jump's TF change appeared in the following event window.
Map→odom TF receipt ages at event endpoints were about 0.14–0.28 s; its
forward-dated header stamps were about 0.56–0.72 s ahead of AMCL receipt.
These timestamps warrant care but do not establish TF timing as the cause.

Two isolated, command-free saved-map replays compared the current
`likelihood_field` laser model against the `beam` model, each with the current
pose+velocity EKF and the previously suggested wheel velocity-only EKF. The
original live five jumps **did not reproduce** in any replay. Results below
use >0.5 m AMCL steps and the final ~20 s position span; 31 evenly sampled
scan/pose pairs per output gave a *separate* median endpoint fit metric. This
sampling is not comparable to the older 23.1%/50.2% Hall-anchored metric.

| Replay | Jumps | Max step | Final position span | Largest heading step | Median XY std | Median sampled scan fit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current laser + current EKF | 0 | 0.340 m | 0.845 m | 9.97° | 0.455 m | 74.0% |
| Current laser + velocity-only EKF | 0 | 0.234 m | 1.789 m | 5.39° | 0.361 m | 74.4% |
| Beam laser + current EKF | 0 | 0.254 m | 2.865 m | 7.22° | 0.416 m | 77.5% |
| Beam laser + velocity-only EKF | 1 | 0.657 m | 1.725 m | 19.32° | 0.340 m | 74.0% |

The isolated replays have different startup/scan counts and cannot demonstrate
that a candidate reduces the live five jumps. The beam alternative worsened
position stability; velocity-only fusion still has mixed stability. Neither
is deployed. Production EKF, AMCL, steering and motor behavior remain intact;
autonomous navigation stays gated. The next discriminating step is a
repeatable offline replay that preserves original AMCL initialization,
particle/random state and timing closely enough to reproduce stationary
switching, or a separately approved *stationary-only* localization recording.
No additional manual driving is justified by the present data.
