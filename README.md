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
