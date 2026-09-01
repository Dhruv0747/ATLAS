# Project ATLAS - Autonomous Service Rover

## Secure live-call intercom

ATLAS now has mutually exclusive AI Voice and on-demand WebRTC Live Call
modes. A live call requests browser echo cancellation/noise suppression, turns
the ESP32 speaker LED red, and automatically returns USB audio ownership to the
AI companion when the call ends. The server binds to loopback and must be
published only through authenticated Tailscale HTTPS—not the public Internet.

**Creator: Dhruv Kaushik**

Project ATLAS is an open robotics development project for a four-wheel autonomous service rover. It runs ROS 2 Humble on Ubuntu 22.04 with an NVIDIA Jetson Orin Nano Super 8GB and combines LiDAR SLAM, Nav2 autonomous navigation, wheel odometry, IMU sensor fusion, bounded recovery behaviours, AI vision, voice control, Foxglove, and wireless dashboards.

This repository is the searchable engineering record for ATLAS: ROS 2 source code, launch files, robot parameters, hardware integration, safety controls, autonomous mapping, recovery logic, diagnostics, operating documentation, and commissioning evidence.

The read-only [ATLAS Visual Cloud](docs/ATLAS_VISUAL_CLOUD.md) integration adds
an authenticated ROS graph/traffic agent, historical API and real-time browser
view. It has no cloud-to-velocity or cloud-to-motor interface; all safety and
control authority remains local on the Jetson.

**Search terms:** Project ATLAS rover, Dhruv Kaushik, autonomous rover, ROS 2 Humble, Jetson Orin Nano Super, Nav2, SLAM Toolbox, Explore Lite, LiDAR mapping, Ackermann steering, service robot, autonomous navigation, robot recovery, Foxglove, MCP robotics.

## Current autonomy maturity

- Core navigation foundation: operational with ROS 2, Nav2, LiDAR SLAM, encoder odometry and IMU/EKF fusion.
- Deterministic recovery: implemented for no-progress detection, LiDAR-validated bounded reverse, costmap clearing and replanning.
- Autonomous mapping: functional and under controlled endurance testing.
- Current engineering gate: repeatable TF/odometry reliability and 20/20 controlled dead-end recovery trials.
- Unattended operation is not yet approved; ground tests require a clear area and an operator at the physical emergency stop.

ATLAS uses its 360-degree LiDAR as the primary navigation and obstacle sensor. Ultrasonic sensors provide close-range secondary protection. AI may select high-level goals, but it cannot bypass the deterministic command mux, watchdog or emergency stop.

## Hardware

- Four-wheel rover with wheel encoders and Yahboom motor controller
- RPLIDAR A1, BNO08X IMU, ultrasonic sensors, and RD-03D radar
- Arduino Mega 2560 sensor hub carries the I2C sensors, L76K GNSS, RD-03D radar,
  and four sequentially sampled ultrasonic channels. See
  [`docs/MEGA_2560_SENSOR_HUB.md`](docs/MEGA_2560_SENSOR_HUB.md).
- IMX708 Camera Module 3 on a pan/tilt platform
- GNSS, BMS, BME680, AMG8833 8x8 thermal sensor, Wi-Fi, and cellular connectivity

The commissioned sensor transport now uses an Arduino Mega 2560. It forwards
the PCA9685 (`0x40`) discovery state, BME680 (`0x76`/`0x77`), AMG8833
(`0x68`/`0x69`), BNO08x (`0x4A`/`0x4B`), L76K NMEA, RD-03D frames and four
ultrasonic ranges over a fixed Jetson USB physical path. The Jetson bridge
republishes the original ROS 2 topic names, so Nav2, EKF, dashboards and
Foxglove do not depend on the physical bus.
- ESP32-S3 voice interface and 11-inch touchscreen dashboard

The web Command Center includes both a conventional 2D RD-03D radar scope and
a lightweight **3D PEOPLE** digital-twin view. The latter places up to three
avatars using live radar X/Y coordinates, distance and speed. It is an operator
visualization, not a depth-camera body scan, and it does not alter navigation or
motor commands.

## Mobile notifications

ATLAS can notify Dhruv's Android or iOS phone through the ntfy app when the
rover boots, when the main DALY BMS reaches 20%, and when charging remains at
99% or higher for three consecutive BMS readings. Alert state includes
hysteresis to avoid repeated notifications near a threshold. Notification HTTP
work runs in a separate worker and cannot block ROS motion control.

On the Jetson, run:

```bash
bash /home/jetson/project_atlas/scripts/setup_mobile_notifications.sh
```

Install the ntfy app on the phone and subscribe to the private random topic
printed by the setup helper. The private topic is stored only in
`~/.config/project-atlas/notifications.env`; it must not be committed.

## Planned wireless controller upgrade

The broken 11-inch Jetson-connected display will be replaced by a removable 10.1-inch CrowPanel Advanced ESP32-P4 HMI with its optional camera. It will operate as ATLAS's wireless dashboard and manual controller while the Jetson remains responsible for motors, safety, ROS 2, navigation and AI. See `docs/CROWPANEL_WIRELESS_CONTROLLER.md` for the approved architecture and installation checklist.

## Repository layout

- `project_atlas_ws/src/`: ROS 2 packages and launch/configuration files
- `project_atlas/scripts/`: operational nodes, dashboard, diagnostics, voice, and recovery tools
- `project_atlas/config/`: robot configuration
- `project_atlas/maps/`: current mapping assets

## Citation and authorship

Project ATLAS was created by **Dhruv Kaushik**. Academic papers, articles and derived projects should cite the repository using the metadata in [`CITATION.cff`](CITATION.cff).

Suggested attribution:

> Dhruv Kaushik, Project ATLAS: ROS 2 Autonomous Service Rover, 2026.

## AI and MCP control

`project_atlas/scripts/atlas_mcp_server.py` exposes a small MCP interface for
status, sensors, camera snapshots, navigation stop, emergency stop, mapping and
return-home. It uses the commissioned Jetson gateway and ROS 2 mission/mux
interfaces; it never accesses the motor controller directly.

Motion-capable tools are locked by default. Commission status, sensor, camera
and stop behavior first. Only then set `ATLAS_MCP_ENABLE_MOTION=1` in the MCP
client environment while an operator has access to the physical emergency stop.
The MCP process uses stdio and must be launched by the trusted MCP client. It is
not a standalone systemd daemon or an unauthenticated network API.

Install its isolated dependency set with:

```bash
python3 -m venv /home/jetson/project_atlas/.venv-mcp
/home/jetson/project_atlas/.venv-mcp/bin/pip install \
  -r /home/jetson/project_atlas/requirements-mcp.txt
```

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

## Safety-constrained mission agent

`atlas_agent_supervisor.py` adds an observe-plan-act-verify layer above the
commissioned ROS 2 stack. It accepts natural mission requests on
`/atlas/agent/command`, creates a maximum four-step plan from a fixed tool
allowlist, publishes its operator-visible state, requires confirmation for
motion, rechecks live safety data, dispatches only high-level mission topics,
and verifies the resulting status. It never publishes velocity commands.

The service is commissioned in `MONITOR_ONLY` mode. In that mode cloud or
offline planning can be tested, but no physical action is dispatched. Runtime
execution can be enabled through `/atlas/agent/set_execution_enabled`; motion
plans still require `/atlas/agent/confirm_plan` and must pass the deterministic
LiDAR, odometry, SLAM, manual-control and battery preflight.

Useful interfaces:

- `/atlas/agent/state`, `/status`, `/plan`, `/decision`, `/response`: dashboard
  and Foxglove visibility
- `/atlas/agent/command` (`std_msgs/String`): natural mission request
- `/atlas/agent/confirm_plan`, `/cancel_plan`: explicit operator gate
- `/atlas/agent/set_execution_enabled`: monitor-only/active selection
- Persistent bounded event memory:
  `~/.config/project_atlas/agent_memory.json`

### INA219 address requirement

The external INA219 must not use its factory-default `0x40` address on ATLAS.
Jetson I2C bus 1 already reserves `0x40` for NVIDIA's onboard INA3221, and the
camera-servo PCA9685 also uses `0x40` on the external sensor bus. Set the
INA219 A0 address jumper to `0x41`, then configure the cellular telemetry
service with `ATLAS_INA219_ADDRESS=0x41` and the bus to which it is wired.
The telemetry node detects a kernel-owned address and reports the conflict
without repeatedly opening or disrupting the bus.

## Archived Portenta H7 migration record

The earlier Portenta H7 sensor-hub prototype is retained only as engineering
history. It is disabled and is not part of the active ATLAS hardware route.
The commissioned sensor hub is the Mega 2560 described above.

See [docs/PORTENTA_SENSOR_HUB.md](docs/PORTENTA_SENSOR_HUB.md) only when
reviewing the superseded prototype and its electrical test record.
