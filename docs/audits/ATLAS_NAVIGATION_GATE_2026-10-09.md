# ATLAS navigation gate — stopped check, 2026-10-09

This began as a read-only check on the charging rover. After the operator
confirmed the exact saved Dhruv Room spot and heading, AMCL was reseeded
while stopped. No motor, steering, map, navigation parameter, service, or BMS
safety gate was changed.

## Confirmed stationary localization repair

- Operator confirmed ATLAS was physically at the saved Dhruv Room/home spot
  and facing the saved direction. The prior AMCL pose (-3.351, -0.298,
  -2.061 rad) was in unknown saved-map cells despite fresh LiDAR and zero
  odometry motion. Its fresh scan put only about 27–30% of endpoints within
  15 cm of mapped walls; the saved home point put about 94–96% there.
- Backed up the old localization seed at
  `/home/jetson/.local/share/atlas-backups/localization_seed_pose.json.before-confirmed-home-reseed-20261009`.
  Used the existing `seed_atlas_localization.py --place dhruv_room` service
  path once. It succeeded and persisted the accepted-map-bound named pose.
- Post-seed authoritative map pose was (0.187, -1.477, 1.330 rad), about
  9 cm from the saved position. A separate fresh scan scored the subsequent
  live AMCL pose (0.208, -1.407, 1.355 rad) in known free space, with 99%
  of 197 endpoints within 15 cm of mapped walls, versus 92.4% at the exact
  saved point. Motor speed stayed zero, `web_drive=STOP`, mission `READY`.
- This repairs the current stopped pose mismatch; it does not prove AMCL
  will remain stable after a reboot or during movement. The start-cell guard
  stays enabled. Charging/BMS invalidity, Hall endpoint footprint failure,
  and the stale taught-route map ID still block an autonomous round trip.

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
- An exact saved-PGM lookup at the later reported pose (-3.22, -0.25) found
  unknown value 205 in its centre and surrounding 5-by-5 cells. The saved
  Dhruv Room point and its surrounding cells were known free (254). A 15 s
  stopped diagnostic saw fresh scans (median age 0.137 s), zero EKF/wheel
  odometry drift, and AMCL pose drift of 0.004 m / 1.09 degrees during that
  window. This rules out a stale scan at the check but does not prove which
  physical/map coordinate is correct. The accepted map cannot safely plan
  from its current reported unknown start.
- A separate read-only live-scan comparison used the exact accepted map and
  verified `base_link -> laser_frame` TF (-0.05 m X, 180-degree yaw). Across
  three fresh scans, only about 27–30% of endpoints projected from the live
  AMCL pose fell within 15 cm of mapped occupied cells. The saved Dhruv Room
  point and heading achieved about 94–96%; saved Hall achieved roughly
  57–60%. At the live pose, only about 2–3% of endpoints were in known map
  cells. This strongly favors the Dhruv Room hypothesis but is **not** a
  localization proof: map symmetry, moving objects, unknown space, and
  endpoint-only scoring can mislead. The diagnostic changed no pose or
  command. See `project_atlas/scripts/atlas_stationary_scan_map_fit.py`.
- At today's localization startup, Nav2 logged multiple robot-out-of-map
  positions and a scan/TF cache drop before the pose settled. This is stronger
  evidence of a startup-localization problem than the stationary pose alone.
  The localization unit also restarted six times: its start-preflight exited
  with timeout status 124 while the LiDAR driver repeatedly reported hardware
  operation timeouts. Missing scans likely caused those preflight failures;
  they do not establish that the saved seed caused the restarts. The current
  LiDAR feed later recovered and was fresh at the stopped check.

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
   This was completed once with operator confirmation and a fresh scan-map
   check. Repeat stability checks after reboot or movement; do not assume one
   successful seed proves repeatability.
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
