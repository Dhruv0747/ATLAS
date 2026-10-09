# ATLAS navigation gate — stopped check, 2026-10-09

This is read-only evidence from the charging rover and saved files. No motor,
steering, map, navigation parameter, service, or BMS safety gate was changed.

## Current observed state

- The Jetson web API showed a complete, fresh four-cell Daly packet while the
  pack was charging at about +2.9 A. The intermittent Bluetooth connect-stage
  fault is not repaired. A fresh BMS packet remains mandatory for movement;
  prioritizing navigation does not waive that safety condition.
- Encoder-health packets were fresh (roughly 0.01–0.03 s) and selected M1–M4.
  Their zero interval deltas and lack of recent count changes are expected while
  stopped. This does not validate loaded wheel distance or M3 repeatability.
- The loaded EKF uses `/yahboom/odom` for translation and the IM10A
  bias-corrected candidate for gyro-Z. IMU magnetic heading and orientation
  are not fused. The loaded AMCL model is `DifferentialMotionModel`; EKF
  `transform_time_offset` remains 0.2 s. No tuning was made.
- Over five samples spanning about 21 seconds while stationary, map pose
  remained approximately (-3.17, -0.22, -2.40 rad), `/odom` x remained
  15.34 m in its separate odom frame, reported speed and gyro-Z were near
  zero, and BMS status was fresh. Different map/odom coordinates alone do not
  indicate drift. The operator confirmed ATLAS is physically in Dhruv Room,
  but has not yet confirmed whether it is at the exact saved home point.
- The current `/amcl_pose` agrees with the web map pose. Its covariance
  diagonal is approximately (-9e-13, -2e-15, +3e-14) for x/y/yaw; the tiny
  negative x/y values are not a usable proof of localization accuracy. Mission
  control clamps negative covariance to zero before checking its uncertainty
  gate. A stable, apparently confident pose therefore does not establish that
  the physical pose matches the saved map.
- The saved `dhruv room` point is (0.254, -1.539), about 3.67 m from today's
  reported pose. This comparison is a warning, not proof of a wrong pose,
  because the rover may be elsewhere within the room. The localization seed
  file is at (0.877, 0.097) and carries a mapping-session ID but no
  accepted-map ID. Do not overwrite either saved place to make the numbers
  agree without an independently checked physical position and heading.
- At today's localization startup, Nav2 logged multiple robot-out-of-map
  positions and a scan/TF cache drop before the pose settled. This is stronger
  evidence of a startup-localization problem than the stationary pose alone.

## Saved-map route blocker

- Accepted map bytes currently identify as `d12a1f183177212a3cc8`. The
  Dhruv Room and Hall named places are bound to that same map.
- The saved taught route is bound to older map `a8e7035836f61cbac5f3`.
  Mission control correctly ignores a route whose map identity does not match;
  changing only its ID would falsely certify stale coordinates.
- The exact saved-map clearance check with unknown blocked and 0.18 m
  inflation accepted the Dhruv Room start but rejected the saved Hall goal:
  `candidate goal is not clear for the inflated rover`. Its centre pixel is
  free, but nearby occupied pixels consume the footprint clearance. No goal
  was moved automatically.
- An Oct 4 candidate map audit was also rejected: disconnected exact candidate
  map, 1.222 m map→odom jump and 20.596° yaw jump. That audit concerns a
  different candidate map and must not be presented as a fresh measurement of
  today's accepted map.

## Safe next gate

1. Confirm whether ATLAS is at the exact saved Dhruv Room/home spot and its
   physical heading while it remains stationary. Compare an independently
   checked scan/map alignment to the live pose before trusting localization.
   Do not drive autonomously while this discrepancy remains unexplained.
2. When not charging, with a safe route and remote stop available, verify a
   physically safe Hall endpoint on the *current* map and save it deliberately.
   Do not relabel the old taught route or silently shift the saved Hall point.
3. Run one bounded low-speed straight/turn validation with measured physical
   distance and wheel/IMU/scan/TF logs. Then test a supervised named-place
   route and return. Repeatability is required before unattended operation.

The BMS Bluetooth transport investigation can follow the navigation-specific
offline work, but any stale/invalid BMS reading still blocks movement. The
local ROS logs and dashboard remain the evidence source while Visual Cloud's
configured destination is a nonworking example address.
