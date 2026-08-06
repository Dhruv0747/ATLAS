# Project ATLAS

Project ATLAS is a ROS 2 Humble autonomous service rover running Ubuntu 22.04 on an NVIDIA Jetson Orin Nano Super 8GB.

## Hardware

- Four-wheel rover with wheel encoders and Yahboom motor controller
- RPLIDAR A1, BNO08X IMU, ultrasonic sensors, and RD-03D radar
- IMX708 Camera Module 3 on a pan/tilt platform
- GNSS, BMS, BME680, AMG8833 8x8 thermal sensor, Wi-Fi, and cellular connectivity
- ESP32-S3 voice interface and 11-inch touchscreen dashboard

## Planned wireless controller upgrade

The broken 11-inch Jetson-connected display will be replaced by a removable 10.1-inch CrowPanel Advanced ESP32-P4 HMI with its optional camera. It will operate as ATLAS's wireless dashboard and manual controller while the Jetson remains responsible for motors, safety, ROS 2, navigation and AI. See `docs/CROWPANEL_WIRELESS_CONTROLLER.md` for the approved architecture and installation checklist.

## Repository layout

- `project_atlas_ws/src/`: ROS 2 packages and launch/configuration files
- `project_atlas/scripts/`: operational nodes, dashboard, diagnostics, voice, and recovery tools
- `project_atlas/config/`: robot configuration
- `project_atlas/maps/`: current mapping assets

Generated ROS directories, local environments, models, logs, credentials, and historical backups are intentionally excluded.

## Engineering policy

Reliability and safety come before new capability. Implement one feature at a time, build and test it, update documentation, and commit it. Emergency stop must override manual, web, voice, and autonomous commands.

## Development baseline

1. Verify hardware diagnostics and TF.
2. Validate wheel odometry and IMU fusion.
3. Validate localization and Nav2.
4. Tune perception and human-aware behavior only after navigation is stable.

## Commissioned navigation baseline - 2026-08-06

The Jetson migration and primary navigation commissioning sequence are complete.

- Physical footprint: 0.50 x 0.36 m; Nav2 footprint is `[+/-0.25, +/-0.18]`.
- Costmap inflation radius: 0.28 m with cost scaling factor 15.0.
- Wheel order: M1 front-right, M2 front-left, M3 back-right, M4 back-left.
- Installed 125 mm wheels use independently calibrated encoder counts per revolution:
  M1 4048.7, M2 3300.6, M3 4080.1 and M4 2697.8.
- LiDAR centre is 0.30 m behind the front chassis edge, placing it 0.05 m behind
  `base_footprint`; the authoritative static transform is x=-0.05 m, z=0.18 m,
  yaw=pi.
- `/yahboom/odom` is encoder-distance-derived and is fused by the EKF onto `/odom`.
- Nav2 uses the one-shot fail-stop behavior tree. It does not accumulate recovery
  movement after a failed short goal.
- Explore Lite holds one frontier goal until completion, abort or genuine
  no-progress timeout. It no longer preempts goals as the frontier boundary moves.
- Exploration stop automatically saves `maps/atlas_latest.yaml` and
  `maps/atlas_latest.pgm`.
- Reboot/autostart verification passed for the base, sensors, SLAM, Nav2, command
  mux, remote, camera, AI, mission controls, Foxglove and dashboard. Autonomous
  exploration remains off after boot until explicitly requested.

Ground autonomous tests always require a clear area and an operator at the
physical emergency stop. The priority command chain remains REMOTE > WEB >
FOXGLOVE > NAV2, with stale-command stopping.
