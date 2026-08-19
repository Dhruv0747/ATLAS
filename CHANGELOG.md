# Changelog

## Unreleased

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
