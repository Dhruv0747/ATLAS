# Changelog

## Unreleased

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
- Added a compact 10 Hz IMU dashboard stream while preserving full-rate navigation IMU topics, and consolidated radar/ultrasonic dashboard subscriptions to reduce ROS callback load.
- Disabled only the obsolete local HDMI dashboard autostart after migration to the wireless web/CrowPanel interface; preserved the launcher for manual diagnostics.
- Audited live Jetson resource use and removed duplicate raw-camera ingestion, duplicate MJPEG frames and per-client shell polling; essential safety, motor, SLAM, Nav2, LiDAR, camera, AI, Foxglove and voice services remain enabled.
