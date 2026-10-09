# ATLAS live round-trip AMCL replication — 2026-10-09

This is a read-only analysis of the operator's low-speed manual Dhruv Room →
Hall → Dhruv Room drive. The rover was not driven by a diagnostic script. No
motor, steering, EKF, AMCL, Nav2, or production parameter change was made.
The current steering controls and calibration were preserved.

## Preserved recordings

Both bags are on the Jetson under
`/home/jetson/project_atlas/data/demonstrations/`:

| Leg | Bag directory | Duration | Messages | SHA-256 of `.db3` |
| --- | --- | ---: | ---: | --- |
| Dhruv Room → Hall | `amcl_hall_outbound_20261009_retry2` | 174.54 s | 36,318 | `0ca6424649838ab88c62a9e9ea566e1dbb0b07a4585392ad9df2d5e6cc4612d2` |
| Hall → Dhruv Room, including post-stop hold | `amcl_hall_return_20261009_retry2` | 246.97 s | 51,716 | `e34111bd45a2572059cae85386abc9a8150d918d39a120da9392b91a65538671` |

The bags contain filtered/raw LiDAR, map, AMCL pose/particles, wheel and EKF
odometry, corrected IM10A gyro, all four encoder counts/health, commanded
steering, command topics and TF. The second bag was kept running after the
operator reported arrival. The operator visually confirmed the final map
marker in Dhruv Room; that is not a surveyed ground-truth pose measurement.

## Measured result

| Measure | Outbound | Return |
| --- | ---: | ---: |
| Wheel-odom start → end yaw | -151.22° | -112.26° |
| Integrated corrected IM10A gyro Z | -183.76° | -170.72° |
| Wheel minus gyro net turn | +32.54° | +58.46° |
| Maximum consecutive `/amcl_pose` XY step | 0.157 m | **2.904 m** |
| Return AMCL XY standard deviation at largest event, before → after | — | 1.477 → 1.506 m |

Net turn comparisons are route-level diagnostics; they do not establish true
physical yaw, a constant steering offset, or which source was wrong. Commanded
steering angles are not measured road-wheel angles. The outbound wheel and EKF
odom paths show real travel, unlike the earlier stationary-only recording.

The return bag has two AMCL steps above 0.5 m. The first was 0.532 m while
odom changed 0.0448 m, so it must **not** be classified as a stationary event.
The second occurred around 16:54:24 IST, after movement stopped:

- `/amcl_pose` changed **2.904 m and -32.63°**; the corresponding composed
  `map→base` step was 2.905 m.
- Wheel odom changed **0.0007 m** between AMCL pose samples. The event's
  five-second context had zero commanded yaw rate, near-zero corrected gyro
  rate, four selected encoder channels with fresh packets, and 70 filtered
  scans. Neither `/yahboom/odom` nor EKF `/odom` teleported.
- The recorded particle cloud was dispersed (XY standard deviation about
  1.5 m) before and after the step. Its published weights were uniform after
  resampling, so this cloud cannot reveal the pre-resampling likelihood or a
  unique winning particle cluster.
- Using the **same preceding scan** and the frozen map, an approximate
  endpoint-within-15-cm score changed from **41.4% to 98.6%** at the two AMCL
  poses; median endpoint-to-wall distance changed from 0.176 m to 0.030 m.
  This supports a switch from a poor map hypothesis to a much better-fitting
  one. It is not AMCL's internal likelihood or independent physical ground
  truth.
- The raw/filtered LiDAR pair stream stayed live. On the return bag, filtered
  scan header stamps had no duplicates or regressions; median raw-to-filtered
  receipt gap was 4.68 ms. A simple scan blackout does not explain this jump.

The associated `map→odom` translation **component** changed 9.663 m because
the odom frame origin is far from the rover and the transform also rotated
32.63°. This is **not** a 9.663 m physical rover move: composing with the
steady `odom→base_link` transform yields the 2.905 m map-frame pose step.

## What this establishes, and what it does not

The stationary AMCL-hypothesis-switching failure from the earlier
Hall → Dhruv Room bag has been independently observed again in a fresh live
return. The pose correction originated in localization/map alignment, not an
odometry teleport, absent LiDAR, or encoder outage at that instant. The final
map marker looked correct only **after** a large correction, so visual endpoint
agreement cannot be counted as stable localization or an autonomy pass.

The upstream reason AMCL became so uncertain remains unverified. The new
wheel-versus-gyro turn disagreement is consistent with the prior investigation
and is a candidate contributor; commanded-versus-physical steering angle,
wheel slip/modeling and scan/map ambiguity have not been separated. Production
AMCL's pre-resampling weights, cluster selection and RNG state were not
captured in these route bags. Isolated historical replay has not reproduced
the live jump, so zero jumps in that replay cannot validate an EKF or AMCL
change. Do not deploy wheel-velocity-only EKF or tune AMCL on this evidence.

## Next gate

No further manual drive is needed to establish that the failure exists. Keep
autonomous room-to-room navigation gated. First use these two complete bags to
compare turn segments against corrected gyro and scan motion, and examine why
AMCL covariance rose before the post-stop switch. A proposed correction must
then reproduce and reduce the live-type jump **without** worsening final pose,
post-stop stability, scan fit or confidence across recordings. If the missing
internal AMCL likelihood/cluster trace is indispensable, use a separately
approved bounded diagnostic capture; do not silently run a continuous shadow
AMCL under the Jetson's existing workload.
