# Changelog

## 2026-08-25 - Reject corrupt-map starts and restore LiDAR SLAM correction

- Added a strict return-home campaign preflight that checks the exact
  0.50 m x 0.36 m footprint against the live global costmap before every
  outbound and return goal. Any lethal, unknown, stale, or missing footprint
  data now stops the campaign before Nav2 can command motion.
- Diagnosed the first 20-run campaign failure as a corrupt accepted occupancy
  map: AMCL moved while EKF and wheel odometry stayed exactly at zero, and the
  saved map contained occupied cells inside the physical rover envelope.
- An isolated ROS-domain replay proved the old round-trip bags cannot safely
  rebuild the map: one round trip ended 3.91 m from its odometry start and
  accumulated 8.88 m of reported travel.
- Restored LiDAR scan matching and loop closure in the workspace SLAM config;
  the enabled mapping service already requests both and the source defaults
  now agree.
- Kept the rejected offline candidate separate and preserved rollback copies
  of the accepted map. A new calibrated mapping pass is required before the
  20/20 motion campaign resumes.
- Reduced the guarded forward-recovery sensor threshold from 0.65 m to
  0.60 m after a verified 3 cm recovery. With LiDAR 30 cm behind the nose,
  this still preserves about 30 cm physical forward clearance.
- Corrected the autonomous side-stop threshold from the 0.18 m physical
  half-width to 0.28 m, preserving the commissioned 10 cm wheel-edge margin
  when fresh side ultrasonic data is available.
- Replaced the corrupted accepted occupancy map with the guarded fresh-mapping
  result. The promoted map has synchronized home/localization identity
  `54de8f1f3a3c0b34fa7c`, a clear exact rover footprint, and no ghost rooms.
- Added a motor-command localization watchdog. In saved-map mode, Nav2 output
  now stops immediately if AMCL data becomes stale or exceeds 0.25 m position
  or 12 degree heading uncertainty, and sudden 0.20 m/15 degree pose jumps are
  latched; sensor-bounded recovery remains available.
- Preserved Yahboom odometry across same-boot CH341 USB/service restarts using
  a 5 Hz tmpfs checkpoint. A transient motor-controller USB disconnect can no
  longer reset `/yahboom/odom` to `(0,0)` and corrupt EKF/SLAM coordinates.

## 2026-08-25 - Gate missions on stationary AMCL convergence

- Added a repeatable localization diagnostic that records AMCL covariance and
  stationary drift alongside EKF odometry, raw wheel odometry, LiDAR age and
  TF availability.
- Measured a 0.70 m stationary AMCL correction while both odometry sources
  remained exactly still. LiDAR latency remained healthy, proving that the
  immediate failure was map localization rather than drivetrain or compute
  timing. The installed AMCL model was already DifferentialMotionModel, so no
  unsupported motion-model change was made.
- Mission control now requests periodic no-motion AMCL updates while stopped
  and requires an eight-second stable pose window in addition to covariance
  limits before Home or autonomous goals can be accepted.
- Added a near-Home guard that commands zero and completes locally within 5 cm
  and 10 degrees, preventing Nav2 recovery from moving a rover already Home.
- Made bounded tight-space recovery arc toward the wider side when left/right
  clearance is meaningfully unbalanced, preserving all existing LiDAR,
  odometry, displacement and watchdog limits.
- Removed four verified static-map self-imprint cells at the converged Dhruv
  Room pose, aligned the startup seed, and promoted map
  `88b70c1600f73777ede2` with rollback backups.
- Live validation completed an autonomous return with 0.05 m final error and
  zero lethal footprint cells. A second return request correctly reported
  `HOME ALREADY REACHED` at 0.006 m / 0.2 degrees without moving ATLAS.

## 2026-08-25 - Remove saved-map self-imprints before localization

- Added a bounded occupancy-map sanitizer that clears only cells inside
  ATLAS's commissioned 0.50 m x 0.36 m rotated footprint at the verified
  localization seed; obstacles outside the physical body envelope remain
  unchanged.
- Integrated sanitation into atomic map acceptance after confirming that the
  localization seed belongs to the active mapping session.
- Backed up and repaired the accepted Dhruv Room map after a costmap audit
  found one stale occupied map cell inside the rover footprint. The repaired
  map identity is `2aaf97cdec712662c8fb`.
- Verified after reload that the live footprint contains zero lethal costmap
  cells and completed a bounded 20 cm Nav2 goal. Return-home remained safely
  blocked when AMCL position uncertainty rose above the existing 0.60 m gate,
  isolating localization confidence as the next reliability issue.

## 2026-08-25 - Match Nav2 curvature in the four-wheel steering driver

- Replaced the former proportional yaw-rate steering approximation with
  signed four-wheel opposite-steering kinematics based on the commissioned
  wheelbase and commanded linear/angular velocity.
- Preserved the correct reverse curvature direction and clamped both steering
  axles to their commissioned mechanical endpoints.
- Added a steering-settle gate so traction remains stopped until both steering
  axles are within 8 degrees of the curvature assumed by Nav2.
- Corrected a rejected AMCL recovery seed by publishing a live ROS timestamp;
  localization accepted the reconstructed stationary pose and returned to low
  covariance before any further movement.
- Extended the mission gate to reject named-place goals whenever the safety
  monitor reports a sensor/odometry fault or an explicit stop condition, so a
  stale LiDAR process cannot dispatch Nav2 from an old dashboard reading.
- Changed bounded recovery pulses to allow steering-settle time while imposing
  an 8 cm odometry cap; recovery now ends on measured body displacement rather
  than losing its entire fixed window while the steering axles travel.
- Added a LiDAR-guarded reverse-arc escape toward the clearer side and reduced
  the powered displacement cap to 4 cm after field measurement showed up to
  roughly 8 cm of additional drivetrain coast.
- Raised recovery's forward-selection threshold to 0.65 m at the rear-offset
  LiDAR, preserving approximately 30 cm ahead of ATLAS's physical nose.
- Activated the existing three-attempt recovery budget: a no-progress forward
  action now clears costmaps and automatically tries a LiDAR-confirmed reverse
  arc toward the clearer side instead of immediately requiring human help.
- Moved the recovery distance cap from fused `/odom` to high-rate raw
  `/yahboom/odom` and added a discontinuity abort, preventing delayed EKF/SLAM
  corrections or a motor-driver restart from overrunning a short escape pulse.
- Re-arm a recovery lockout after fresh LiDAR and wheel odometry confirm that
  an operator has held ATLAS in a usable corridor for one second; re-arming
  never commands motion. Live mapping then completed three sensor-guarded
  recoveries (0.078-0.093 m), resumed Nav2 each time, and accepted map
  `5674a1b39b86379ce214` instead of remaining permanently blocked.

## 2026-08-25 - Block autonomy when saved-map localization is uncertain

- Recorded a fresh Dhruv Room to Hall baseline and Hall to Dhruv Room A/B run
  with Visual Cloud monitoring and complete navigation telemetry.
- Traced the large map-to-odom corrections to startup localization being seeded
  at Hall while the rover was physically in Dhruv Room; wheel odometry, EKF and
  normal LiDAR timing remained healthy.
- Rejected and reverted an isolated `update_min_d` 0.25 m to 0.10 m trial after
  maximum translation/yaw corrections worsened to 0.364 m / 7.94 degrees.
- Re-seeded the stopped rover at Dhruv Room, reducing median observed AMCL
  uncertainty from approximately 1.05 m / 38.7 degrees to 0.38 m / 11.1 degrees.
- Added a mission-control confidence gate that blocks named-place and
  return-home goals above 0.60 m or 25 degrees of AMCL uncertainty.
- Extended demonstration bags and analysis with AMCL pose, covariance,
  particle-cloud/map evidence and correction-event timestamps.

## 2026-08-24 - Add read-only ATLAS Visual Cloud foundation

- Added a lightweight subscription-only Jetson agent for ROS nodes, topics,
  publishers, subscribers, services, actions, TF, rates, age and compact
  navigation telemetry.
- Added an authenticated ingest/history API and real-time pipeline dashboard.
- Added requested failure taxonomy, Git/config version evidence and bounded
  system metrics while explicitly excluding every cloud-to-motion interface.
- Added a ROS CLI daemon diagnostic that verifies `--no-daemon` discovery
  before resetting the CLI daemon; live execution waits for motors-off startup.
- Added CPU/RAM service limits, deployment guidance and ROS-independent tests.

## 2026-08-24 - Record tight-recovery localization failure

- Preserved a 12,760-message manual tight-recovery demonstration from the
  failed Hall autonomous start to the physical Dhruv Room.
- Classified the autonomous failure as planner/costmap localization: Smac
  Hybrid found no valid path and later reported the start footprint lethal.
- Measured 2.06 m accumulated map-to-odom correction, including a 0.341 m / 8
  degree correction step, and documented the stale named-place mismatch.
- Added a stationary-first map and named-place realignment procedure for the
  next controlled session; no further motion or blind AMCL tuning was done.

## 2026-08-24 - Correct four-wheel-steering odometry yaw sign

- Added a bounded LiDAR/odometry-guarded arc commissioning tool using the
  isolated recovery command channel and an explicit zero-command tail.
- A physically confirmed left arc travelled 0.263 m but wheel odometry
  reported -7.24 degrees and fused odometry -7.76 degrees.
- Corrected the front/rear servo-to-wheel delta convention so physical left
  steering produces positive ROS yaw and physical right produces negative.

## 2026-08-24 - Localization teaching-route diagnosis

- Recorded manual Dhruv Room to Hall and Hall to Dhruv Room teaching bags
  with LiDAR, TF, fused/wheel odometry, steering, encoders, safety and camera.
- Extended the route analyzer to quantify `map -> odom` correction jumps.
- Confirmed the failed return contained a false 2.55 m / 24.43 degree AMCL
  correction while wheel and fused headings agreed and LiDAR median delay was
  only 3.56 ms.
- Rejected a one-variable A/B trial increasing AMCL `max_beams` from 60 to
  120: despite an initially stable sample, stationary localization later
  jumped to x=0.383 m, y=-0.312 m, heading 63.89 degrees. Restored 60 beams.
- Added a repeatable stationary AMCL/LiDAR stability monitor with forced
  no-motion scan updates. Beam skipping improved the stationary sample but
  was rejected after the movement loop still produced a 0.98 m AMCL jump and
  failed pose closure. Restored the commissioned non-beam-skipping model.
- Kept costmap tuning unchanged after separately detecting a blocked start
  region; it must be diagnosed as the next isolated variable.

## 2026-08-24 - Bounded recovery experience feedback

- Added deterministic classification for localization, TF timing, costmap,
  planner, controller, traction, sensor and blocked-space failures.
- Added a durable mission-result ledger that records every terminal success or
  failure with status, final odometry pose and safety/autonomy context, and
  publishes cumulative success, failure and success-rate statistics.
- The persistent experience store now retrieves collision-free successful
  recoveries for the same failure class and publishes a structured
  `/atlas/experience/recommendation`.
- Fed that evidence into the Mission AI live-state snapshot. Unproven history
  remains advisory; only validated candidates may influence recovery, and all
  motion remains subject to deterministic Nav2, sensor and safety gates.

## 2026-08-24 - Commissioned house map and room localization

- Promoted the clean wheel-heading SLAM map recorded on the final Dhruv Room
  to Hall round trip and tied all saved locations to map ID
  `a8e7035836f61cbac5f3`.
- Commissioned normalized poses for Dhruv Room (Home) and Hall and added the
  bidirectional semantic room connection backed by the recorded route.
- Changed AMCL from the impossible omni-directional prediction model to the
  closest available non-holonomic `DifferentialMotionModel` for ATLAS 4WS.
- Made localization seeding use AMCL's `/set_initial_pose` service with a
  topic fallback and an immediate no-motion scan update.
- Verified AMCL accepted the normalized Home pose and Nav2 computed an
  8.411 m, 100-pose path from Dhruv Room to Hall without commanding motion.
- Re-taught Hall from the live manual route after commissioning exposed that
  the earlier Hall waypoint was not the physical destination. The corrected
  free-space pose is x=1.853 m, y=-1.461 m and is backed by demonstration
  `teach_dhruv_room_to_hall-20260824-190151`.

## 2026-08-24 - Navigation heading-fusion correction

- Added repeatable rosbag fusion and isolated offline-SLAM diagnostics.
- Measured BNO08X rotation-vector changes of 100-175 degrees while its own
  integrated gyro reported only 1.7-6 degrees on the same routes.
- Removed magnetically distorted IMU yaw/yaw-rate from the navigation EKF;
  the IMU remains live for dashboard and health monitoring.
- Fused commissioned wheel pose yaw and yaw rate, which agreed within about
  one degree in both recorded routes.
- Offline real-time replay produced a substantially cleaner, coherent map with
  no EKF replay warnings. The candidate remains quarantined pending one fresh
  live ground mapping validation.

## 2026-08-24 - Tight-space recovery command isolation

- Gave bounded tight-space recovery its own `/cmd_vel_recovery` mux input.
- Preserved physical remote as the highest-priority override and applied the
  autonomy proximity guard to both recovery and Nav2 commands.
- Enabled Reeds-Shepp reverse-capable planning and controller reversing for
  collision-checked exits from tight spaces.
- Removed stale semantic-camera points from navigation costmap marking; LiDAR
  remains the commissioned collision authority.
- Ground verification passed: recovery advanced 0.048 m, watchdog-stopped,
  cleared costmaps, and resumed Nav2.
- Added `/atlas/start_manual_mapping` for versioned, remote-driven teaching
  sessions that can atomically save and promote a map without Explore Lite.
- Refuse to store a temporary SLAM pose as Home unless a versioned mapping
  session is active, preventing coordinates from an unaccepted map being used
  for return-home.

## Unreleased

- Removed the planner/controller kinematic contradiction: Smac Hybrid now uses
  forward-only `DUBIN` paths to match Regulated Pure Pursuit
  `allow_reversing=false`, while the separate short LiDAR-checked backup
  behavior remains available for recovery.
- Synchronized the two authoritative Nav2 parameter copies and replaced the
  obsolete provisional encoder YAML values with the commissioned per-wheel
  counts already used by the runtime Yahboom driver.
- Permanently repaired the autonomous mapping/localization startup chain:
  navigation now waits for synchronized clock, odometry and LiDAR data; SLAM
  uses scan matching and loop closure; Nav2 retains the rectangular 50 x 36 cm
  footprint with 28 cm inflation; LiDAR-guarded backup recovery is available;
  and the mapping readiness timeout covers Smac Hybrid initialization.
- Made map acceptance transactional and session-aware. A stopped/failed
  Explore Lite process can no longer overwrite `atlas_latest`; accepted maps
  are backed up, home/localization poses are tied to a map identity, and stale
  coordinates are rejected after a map replacement.
- Added on-demand full-duplex WebRTC intercom with exclusive AI Voice / Live
  Call audio ownership, disconnect recovery, and a red privacy indicator.
- Added ESP32 audio protocol-v2 low-latency streaming playback (`0x85`).

- Unified the web AI switch, object list and bounding-box camera feed with the
  existing TensorRT annotator. AI OFF now skips inference to save GPU power,
  while AI ON uses one detector instead of launching duplicate dashboard work.
- Recovered the face-first camera tracker from its stale failed state, fixed
  clean ROS shutdown, aligned its tilt range with the commissioned B0283
  driver, and added its enabled systemd unit to the tracked deployment source.
- Restored native Jetson I2C camera pan/tilt control, made it the sole
  authoritative feedback route when the UNO has no PCA9685, synchronized new
  control clients periodically, and aligned web tilt direction, limits and
  CENTER with the physically verified Arducam B0283 mounting orientation. The
  server translates screen-space tilt direction so already-open dashboards
  cannot retain the reversed physical behavior through browser caching.
- Removed the RD-03D service's invalid `After=default.target` ordering, which
  formed a boot cycle with the enabled camera/LiDAR/radar person-fusion unit.
  Camera–LiDAR–radar fusion can now start normally after its sensor services.
- Smoothed Xbox remote driving in the Yahboom base driver with a bounded PWM
  acceleration/deceleration ramp, a mandatory zero crossing before reversing,
  faster slew-limited four-wheel steering updates, and a 450 ms fallback
  watchdog. Explicit zero commands and safety stops remain immediate.
- Hardened the UNO R4 sensor-hub firmware for rover-length I2C wiring with a
  1.2-second sensor power-up delay, a 50 kHz bus clock, periodic Wire/Wire1
  reselection, and per-bus device counts in live diagnostics. Deployed and
  verified the build on the ATLAS UNO R4.
- Added an independent ntfy mobile-notification service for one-per-boot ATLAS
  online alerts, hysteresis-protected 20% main-battery warnings and stable 99%
  full-charge alerts. HTTP delivery is retried outside all motion callbacks,
  and a setup helper generates a private random subscription topic.
- Added an operator-selectable live RD-03D digital-twin view to the ATLAS web
  dashboard. It renders up to three moving-person avatars from the radar's real
  X/Y, distance and speed telemetry, with proximity colours and an explicit
  distinction between coordinate avatars and a true 3D body scan.
- Consolidated the rover's low-speed I2C devices behind the Arduino UNO R4
  sensor hub: PCA9685 camera/scan servos, BME680 environment, AMG8833 thermal
  array, BNO08x IMU and L76K GNSS now retain their existing ROS 2 topic
  interfaces while using one persistent USB serial transport. Added live I2C
  address/status telemetry and bounded automatic sensor re-probing.
- Hardened the Arduino GNSS baud detector with printable NMEA checksum
  validation, commissioned the L76K at 9600 baud, and enabled its existing ROS
  fix/satellite/HDOP/NMEA topics through the UNO R4 sensor hub.
- Fixed agent action verification so Nav2 `RETURN HOME FINISHED status=6`
  (aborted) is reported as failure; only action status 4 is accepted as a
  successful return-home completion.
- Corrected the 180-degree LiDAR mounting yaw in operator clearance and
  tight-recovery sector calculations. Front/left/right labels and bounded
  recovery direction now use the rover base frame rather than raw scan angles.
- Bounded Explore Lite's stop-time map saver with a forced-kill grace period
  and aligned mission-control's wait time, preventing a successfully saved map
  from leaving `atlas-explore.service` stuck in deactivation or failed state.
- Removed the tight-recovery helper's reverse dependency on the velocity mux,
  eliminating a systemd boot ordering cycle that could leave recovery inactive.
- Added a safety-gated stdio MCP server for AI access to ATLAS status, sensors,
  camera, stop, mapping and return-home through the existing mission controller
  and command mux; motion tools are locked by default and require explicit
  clear-area confirmation after commissioning.
- Pointed the MCP defaults at the commissioned Jetson status gateway on port
  `8088`.
- Pinned the MCP SDK below 2.0 to preserve the FastMCP import used by the ATLAS
  stdio server.
- Completed live Jetson read-only MCP commissioning for status, sensors and
  camera with motion disabled, and recorded the deployed environment.
- Added a safety-constrained mission agent with OpenAI/offline planning,
  allowlisted high-level ROS tools, explicit motion confirmation, deterministic
  live preflight, action verification, bounded persistent memory and
  operator-visible state topics. Deployment defaults to monitor-only mode.
- Added a dedicated mission-control navigation-cancel topic/service and a user
  service for the existing sensor-guarded tight-space recovery tool; neither
  bypasses the velocity mux, watchdog or emergency-stop priority.
- Exposed agent status, state and decision telemetry through the ATLAS web API.
- Established a clean source-control baseline from the live ATLAS Jetson deployment.
- Added repository policy, safety exclusions, architecture overview, and development instructions.
- Approved a camera-equipped 10.1-inch CrowPanel ESP32-P4 as the removable wireless dashboard/controller replacing the broken 11-inch display; documented integration and safety requirements.
- Defined battery-powered, cable-free normal operation with automatic authenticated ATLAS discovery, reconnection, state synchronization and link-loss stopping.
- Added a read-only navigation-foundation audit identifying uncalibrated command-derived odometry, absent EKF configuration and inconsistent LiDAR/base TF definitions.
- Performed safe forward/reverse lifted-wheel encoder tests: M1 feedback passed; M2-M4 feedback was inactive and requires hardware-path inspection before odometry work.
- Visually confirmed all four motors operate during an ordered lifted-wheel test, isolating the remaining M2-M4 fault to encoder feedback rather than drive output.
- Repeated encoder testing after a complete physical power cycle; M2-M4 remained inactive, ruling out stale counters or a transient service condition.
- Verified the replacement M2 motor/encoder: feedback now passes in both directions (`+5466`/`-5404`); M3-M4 remain unresolved.
- Confirmed all four motor encoder channels now provide strong, correctly signed forward/reverse feedback; hardware feedback blocker resolved.
- Passed the final permanent-installation acceptance test for all four motors and encoders; outputs stopped cleanly and the normal telemetry service was restored.
- Calibrated encoder-derived ground odometry for the installed 125 mm wheels using independent M1-M4 counts-per-revolution values.
- Added the measured LiDAR mounting offset (0.05 m behind chassis centre) to the static TF and scan self-filter.
- Added and deployed EKF fusion so the motor driver no longer publishes the authoritative `/odom` transform directly.
- Replaced the accumulating Nav2 recovery tree with a one-shot fail-stop behavior tree and enabled controlled reverse paths for return-home.
- Fixed Explore Lite frontier-goal churn by holding an active Nav2 goal until completion, abort or genuine no-progress timeout.
- Verified a bounded autonomous mapping run, collision abort behavior, automatic safety stop and successful map serialization (`82 x 195` cells at `0.05 m/pixel`).
- Passed reboot/autostart verification for all required base, sensor, navigation, visualization and control services; exploration remains opt-in after boot.
- Added touch-open live detail views for all three ultrasonic sensors, IMX708 camera, full BNO08X attitude/acceleration/gyro/magnetometer data, AMG8833 8x8 thermal pixels, and BME680 temperature/humidity/pressure/gas/IAQ telemetry.
- Added a live dual-route I²C inventory to the web dashboard: native Jetson I²C-7 sensor health and addresses are shown separately from Arduino Wire bridge freshness and its reported device list.
- Added a compact 10 Hz IMU dashboard stream while preserving full-rate navigation IMU topics, and consolidated radar/ultrasonic dashboard subscriptions to reduce ROS callback load.
- Disabled only the obsolete local HDMI dashboard autostart after migration to the wireless web/CrowPanel interface; preserved the launcher for manual diagnostics.
- Audited live Jetson resource use and removed duplicate raw-camera ingestion, duplicate MJPEG frames and per-client shell polling; essential safety, motor, SLAM, Nav2, LiDAR, camera, AI, Foxglove and voice services remain enabled.
## 2026-08-18

- Verified saved-map reload, localization autostart, and return-home with about
  5 cm final position error.
- Corrected the polygon-footprint inflation radius to provide 10 cm clearance
  outside the rover's physical edges.
- Added explicit INA219 bus/address configuration and kernel-driver conflict
  detection. ATLAS now identifies the Jetson INA3221 reservation at
  `i2c-1/0x40` and instructs re-addressing the external INA219 to `0x41`.
- Added an autostarted INA3221 ROS 2 telemetry service for live Jetson input,
  CPU/GPU and SoC rail voltage/current/power, including undervoltage and
  high-power status. The web/touch dashboard now displays these live values.
- Made cellular labels follow the modem's live access technology: NR displays
  as 5G, LTE as 4G, UMTS/HSPA as 3G, and GSM/EDGE/GPRS as 2G.
- Added autostarted Waveshare JETSON-ORIN-IO-BASE health telemetry covering
  NVMe capacity, RTC, USB, CSI video, I2C/UART/CAN availability, network links
  and the active NVIDIA power mode; exposed it in the dashboard health and
  system panels.
- Ultrasonic sensors are intentionally disconnected; LiDAR remains the primary
  ranging and navigation safety source.
# 2026-08-19

- Added a compact `TALK / LISTEN` control to the main web dashboard for the secure two-way rover intercom.
- Added bounded boot recovery for Tailscale `NoState` startup failures and automatic restoration of the intercom Serve route.
- Changed intercom navigation to the current dashboard tab so the MJPEG camera stream releases CPU during calls; added a return-to-dashboard control.
# 2026-08-25 — Doorway recovery and taught-corridor navigation

- Made tight-space recovery use the same conservative LiDAR sectors as the
  main safety monitor after a narrower sector missed a door/wall edge.
- Added rear-direction and straight-direction LiDAR guarding to the bounded
  arc commissioning tool; unsafe arcs now stop before wheel motion.
- Extracted the successful Dhruv Room → Hall manual demonstration into a
  127-pose, 3.813 m map-frame taught route.
- Added collision-checked `NavigateThroughPoses` room routing so named-place
  navigation can follow the demonstrated doorway turn instead of aiming only
  at the final room pose.
- Added atomic taught-corridor map promotion with backup and map-ID rebinding.
- Field result: localization remained stable and wall escape succeeded, but
  final autonomous traversal remains blocked because the current footprint is
  inside the live costmap safety envelope and low-speed pulses overshoot their
  targets. Precision base stopping must be corrected before reduced-clearance
  autonomous recovery is enabled.
