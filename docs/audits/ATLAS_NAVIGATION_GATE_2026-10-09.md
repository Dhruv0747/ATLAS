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
  stays enabled. The Hall endpoint failure below was subsequently corrected
  by saving a new operator-confirmed physical endpoint; the stale taught-route
  map ID and moving-localization validation still block a reliable round trip.

## Hall arrival and new destination

- The operator manually drove to Hall before the dedicated demonstration
  recorder was started; do not count that leg as a recorded route test. The
  operator confirmed the live map marker matches the stopped rover location.
- Fresh AMCL pose at Hall was about (6.279, -2.199, -1.686 rad), speed zero,
  LiDAR fresh (0.184 s) and 98.9% of 180 projected scan endpoints within
  15 cm of occupied map cells. The previous saved Hall point fit only 32.8%
  and failed the exact 0.18 m footprint-clearance check.
- The new point is known free and connected to saved Dhruv Room in the exact
  accepted map with unknown blocked and 0.18 m inflation. This is a grid
  connectivity check, not a Nav2 controller or no-contact driving pass.
- Backed up the old `named_places.json` at
  `/home/jetson/.local/share/atlas-backups/named_places.json.before-hall-resave-20261009`.
  First save exposed an Oct 8 stale `mapping_session.json` marked active even
  though saved-map localization was active and SLAM inactive. That incorrectly
  tagged Hall with an old mapping-session ID. Archived the stale marker as
  `mapping_session.json.stale-closed-20261009-hall` and re-ran the existing
  save command while stopped. Verified final Hall pose (6.279, -2.199) has
  accepted `map_id=d12a1f183177212a3cc8`, no session marker, connected
  map grid, and zero motor speed. No service restart or navigation command.
- The old taught route is still bound to a different map and must not be
  relabelled. A supervised, recorded navigation trial and repeatability checks
  remain. Also audit why a stale active-session marker survived localization
  startup so future waypoint saves cannot be misbound.

## Recorded manual Hall → Dhruv Room return and map-display lag

- The operator manually drove Hall → Dhruv Room after the dedicated recorder
  was verified active. The bag is
  `/home/jetson/project_atlas/data/demonstrations/hall_to_dhruv_20261009-20261009-122252`
  (about 192 MB); the recorder stopped successfully. This is manual route
  evidence, **not** an autonomous return-home pass.
- The operator confirmed the displayed final map location matches the rover
  in Dhruv Room. Stopped final map pose was about (0.313, -1.176,
  1.091 rad), 0.37 m and 14° from the saved home pose. That offset is not a
  measured localization error because the operator did not claim to park at
  the exact saved home point.
- The operator reported the map marker appeared about 20 seconds late. In
  the 53.9-second recorded remote-command window, `/scan`, `/odom`, `/tf`,
  `/yahboom/odom` and `/amcl_pose` had maximum receipt gaps of 0.268,
  0.116, 0.109, 0.121 and 1.174 seconds respectively. AMCL's header-to-bag
  receipt age was median 0.162 s, maximum 0.311 s. Stopped `/api/map` calls
  took 0.09–0.18 s and returned pose age about 0.05–0.39 s. These checks do
  not reproduce a 20-second message-transport or API lag.
- **Important deeper finding:** the full recording shows AMCL jumping among
  map hypotheses after remote commands stopped and `/odom` velocity was zero.
  Five AMCL position steps exceeded 0.5 m; the largest was 2.206 m with a
  130° heading step. The final pose agreed with the operator's observed
  Dhruv Room location, but this is localization correction, not smooth
  tracking. A 20-second apparent display delay may therefore include late
  AMCL correction as well as browser rendering. Do not claim the web change
  fixes localization. Do not infer wheel-distance scale from the 4.236 m
  odometry endpoint displacement versus 6.053 m between map-frame endpoints:
  the wheel-odometry path itself was about 6.77 m, and the different endpoint
  displacements reflect different estimated trajectories/headings. The run
  was not measured against a surveyed ground path.
- Read-only bag review found 65 of 2,919 encoder-update intervals marked
  `feedback_unavailable`, all during the remote-drive window. In 32 of these,
  traction was applied and `/atlas/encoder_health` was `CRITICAL` with
  `autonomy_ready=false`; the autonomous command mux is coded to stop on that
  state. The other 33 occurred without applied traction. M3 was rejected in
  184 of 539 drive-window samples, more often than the other wheels. This is
  intermittent wheel-consensus loss, not evidence that all four encoder
  packets or the USB link disappeared. Remote manual movement does not
  qualify autonomous movement through these intervals.
- The last nonzero remote command was about 214.77 s into the bag. The five
  >0.5 m AMCL steps occurred at 217.63–227.84 s, **after** that command.
  During the driven interval wheel-odometry yaw changed about -143 degrees,
  while the IM10A/EKF reported gyro yaw-rate integrated to about -192 degrees.
  The EKF pose heading changed about -125 degrees. These disagreeing motion
  estimates need a same-time heading/TF audit; the bag alone does not prove
  which source is physically correct or that the encoder losses caused the
  later AMCL jumps. Preserve the current EKF/Nav2 configuration until that
  distinction is measured.
- A same-time scan/map comparison on the accepted 5 cm grid supports the
  **hypothesis-switching** explanation for the post-stop corrections. At
  223.63 s, the pose near (0.30, -1.11) placed 100% of 217 usable scan
  endpoints within 15 cm of mapped occupied cells; the competing pose near
  (1.57, -0.24) placed 86.6% there. AMCL nevertheless switched back to the
  weaker hypothesis at 224.71 s, then returned near Dhruv Room at 227.84 s.
  The particle cloud remained broad and AMCL XY/heading standard deviations
  were already about 1.12 m/58.5° at the end of the remote drive. These are
  independent indications of uncertain localization, not TF transport lag.
- Motion evidence narrows the likely source of that uncertainty. Over the
  driven window, wheel steering/encoder integration yielded -142.8° yaw and
  the IM10A gyro integrated to about -191.5°. Most of the discrepancy arose
  in the 175–190 s turning window: wheel +57° versus gyro +12°. Both IMU and
  odometry message ages were below 0.13 s maximum there; LiDAR was below
  0.28 s. Steering was **commanded only**, with front/rear commands ranging
  66–109°/71–116°; no physical steering-angle sensor measured actual wheel
  angle. An offline, Hall-anchored dead-reckoning check at 214.85 s gave 83.1%
  of scan endpoints within 15 cm of mapped walls using gyro-integrated
  heading, versus 6.7% for wheel-steering heading and 2.6% for the recorded
  EKF pose. This strongly favors gyro heading for this run, but endpoint
  proximity is not a full ray-casting likelihood or surveyed ground truth.
  The wheel/IMU discrepancy and dropped encoder-consensus intervals are
  plausible contributors to particle spread; the recording cannot apportion
  their individual causal effects or prove a physical steering defect.
- Current production safety already fails closed: the mux rejects AMCL XY
  standard deviation above 0.25 m, heading standard deviation above 20°,
  and large pose jumps. No actuation guard was weakened. A read-only map
  display correction now surfaces AMCL uncertainty and recent jumps, so a
  fresh TF estimate is not presented as confidently localized. **This does
  not resolve the underlying AMCL jumps or qualify autonomous travel.**
- A later stopped scan fit the final live pose in known free space: 95.7%
  of 209 endpoints were within 15 cm of mapped occupied cells, versus 67.5%
  at the exact saved home point. This supports the operator's statement that
  the displayed final pose is physically plausible; it does not excuse the
  preceding large jumps or qualify autonomous operation.
- The map page previously launched a new fetch every 750 ms without waiting
  for the prior fetch and re-fetched even an unchanged saved-map PNG every
  1.5 s. The web-only repair uses one in-flight request, a 2 s timeout,
  immediate foreground refresh, client-elapsed pose age, and a stale-pose
  label instead of presenting old coordinates as live. It treats a latched
  saved map as loaded rather than wrongly calling it stale because its one
  `/map` publication is old; static map PNGs refresh at most every 30 s.
  No ROS, map, motor or safety service restarted. Live HTTP check returned
  200 and fresh pose; a moving phone-browser test is still needed to confirm
  browser responsiveness. Autonomous motion remains blocked on localization
  repeatability, not merely map-page update speed.

### Isolated EKF comparison on this same recording

**Follow-up cross-bag and saved-map AMCL result:**
[the cross-bag audit](ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md) found
wheel-versus-corrected-gyro heading disagreements across several drives, but
only this Hall return had sufficient AMCL samples to count jumps. An isolated
saved-map AMCL A/B on this Hall clip produced 121/126 AMCL poses and zero
>0.5 m jumps in both variants, so it **did not reproduce** the five live
post-stop jumps. Velocity-only lowered median AMCL XY standard deviation
(0.455 to 0.361 m) and maximum map→odom translation correction
(0.408 to 0.194 m), yet **worsened** final ~20 s AMCL position span
(0.845 to 1.789 m). It is not a verified fix. No experimental EKF parameter
was deployed; moving/stopped localization remains a release blocker.

- A 75 s clip of the Hall return, including 750 wheel odometry messages,
  751 IM10A messages and 529 scans, was replayed in isolated ROS domain 178.
  Only recorded sensor/TF topics were played. EKF and SLAM were started for
  each variant; no joystick, command mux, motor or other actuator topic was
  replayed. The production `atlas_ekf.yaml` SHA-256 stayed
  `69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`.
  Artifacts are under
  `/home/jetson/project_atlas/data/diagnostics/hall_return_ekf_ab_20261009/`.
- The sole configuration difference was disabling wheel-derived X/Y **pose**
  fusion while retaining wheel X/Y velocity and IM10A gyro Z. Hall-anchored
  estimates were compared with the existing accepted map at 31 recorded
  scans. Median percentage of usable scan endpoints within 15 cm of mapped
  occupied cells improved from **23.1% (current pose+velocity fusion)** to
  **50.2% (velocity-only)**; in the last 10 s it improved from **11.1%** to
  **52.2%**. At the arrival scan (~214.85 s), the comparison was **8.7%**
  versus **49.2%**. The velocity-only EKF net yaw was about -191°, consistent
  with the gyro; current fusion replay net yaw was about -142°. This is strong
  evidence that wheel-derived position updates pull the fused trajectory away
  from the scan-supported route on **this** recording.
- The velocity-only candidate is **not deployed**. Its endpoint scan fit is
  still far below the scan-supported AMCL final hypothesis, and an earlier
  Oct 8 replay on a different mapping bag had mixed results and rejected the
  same change. This A/B does not prove repeatable Nav2 localization, physical
  steering accuracy, or safe autonomous driving. Production EKF and Nav2
  parameters remain byte-for-byte unchanged; the next decision requires an
  offline comparison that also checks saved-map AMCL confidence and a bounded
  supervised physical validation when the operator permits movement.
- The diagnostic-only `/api/map` confidence display was deployed with exact
  backups under `data/diagnostics/map_confidence_backup_20261009/`. Replay of
  all 384 original `/amcl_pose` messages flagged all five post-stop jumps;
  five unit tests, Python compilation, browser-script parsing, live HTTP 200
  and fresh AMCL confidence fields passed. The dashboard service alone was
  restarted; odometry remained stationary and no motor command was issued.

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
  inflation accepted the Dhruv Room start but rejected the **previous** saved Hall goal:
  `candidate goal is not clear for the inflated rover`. Its centre pixel is
  free, but nearby occupied pixels consume the footprint clearance. The Hall
  point was later deliberately replaced at the rover's confirmed physical
  stop, as documented above; no goal was moved automatically.
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
2. The operator-confirmed Hall endpoint was saved on the *current* map and
   passed exact grid clearance. Do not relabel the old taught route. Verify
   an actual Nav2 plan and no-contact controlled travel separately.
3. Run one bounded low-speed straight/turn validation with measured physical
   distance and wheel/IMU/scan/TF logs. Then test a supervised named-place
   route and return. Repeatability is required before unattended operation.

The BMS Bluetooth transport investigation can follow the navigation-specific
offline work, but any stale/invalid BMS reading still blocks movement. The
local ROS logs and dashboard remain the evidence source while Visual Cloud's
configured destination is a nonworking example address.
