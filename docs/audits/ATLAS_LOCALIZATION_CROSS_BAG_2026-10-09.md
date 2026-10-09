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
estimated **-16.09°**. All four encoder channels were selected in 35/44
updates. On Oct 8 t=44.56–46.61 s, front/rear *commanded* steering was 90°,
wheel-model yaw 0°, gyro +16.62°, and scan ICP +17.65° during a reverse
segment. ICP supports but does not independently prove true chassis yaw.
Commanded steering is not measured road-wheel angle; physical steering offset,
lag, traction and geometry remain distinguishable candidates. A 0–1 s
command-delay sweep did not eliminate the mismatch.

Recorded p95 header-to-receipt ages on the Oct 9 drive were about 8 ms for
wheel odom, 6 ms for corrected IMU, and 94 ms for EKF. Scan receipt age
includes acquisition duration and must not be interpreted as transport lag.
Freshness alone did not prevent AMCL hypothesis switching after stopping.

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
