# M1: CPU budget for the full-time Astra and 3D mapping (2026-11-05, read-only)

These measurements are read-only; nothing was stopped or changed. Rover parked, E-STOP latched, navigation stack up.
Windows: 60 s per-service accounting from cgroups, plus three 25 s Astra windows. Limit: 75 % whole-Jetson CPU
(6 cores). Target from the 31 Oct handover: mapping mode at about 45 % or less.

## Measurements

| State | Whole Jetson CPU |
|---|---|
| Normal (nav up, no extras) | **60.7 % / 61.8 %** (two windows) |
| + Foxglove bridge | about the same (bridge 4 % of a core) |
| + Astra depth 160x120 streaming via the web viewer | **61.1 %** (Astra about 1 %; status-web +10 % of a core for preview PNGs) |

**Conclusion:** the Astra itself is not the problem. RTAB-Map (not installed) is the unknown, heavy part, and
needs headroom.

## Per-service cost now (60 s; % of one core / % of the whole Jetson)

| Service | Core | Jetson | Mapping mode | Notes |
|---|---|---|---|---|
| rover-status-web | 44.3 | 7.4 | **KEEP** | Dashboard, E-STOP UI, Vision Lab, exporter source. Optimizing it is a separate task. |
| atlas-camera (IMX708) + nvargus | 43.3 | 7.2 | **PAUSE?** owner | Open handover question. The Astra provides RGB during mapping. |
| rover-base-telemetry | 28.8 | 4.8 | KEEP | Motor base, encoders: safety |
| atlas-voice-companion | 22.5 | 3.7 | PAUSE | Already in mission-control's mapping pause list |
| atlas-localization (AMCL+Nav2) | 19.3 | 3.2 | KEEP for now | RTAB-Map may replace it while mapping; decide in M3 |
| atlas-cmd-vel-mux | 18.7 | 3.1 | KEEP | Velocity priority/E-STOP path |
| atlas-sensor-recovery | 17.5 | 2.9 | KEEP | Sensor fault handling |
| atlas-safety-status | 13.0 | 2.2 | KEEP | Safety |
| atlas-lidar-odom / -gate / ekf-lidar-candidate | 19.8 | 3.3 | PAUSE | Shadow only; atlas_ekf uses wheel odom + IMU. Tested pausable today. |
| atlas-localization-monitor | 12.0 | 2.0 | PAUSE | Read-only, suggest-only |
| atlas-mission-control | 10.7 | 1.8 | KEEP | Runs the mapping session itself |
| atlas-uno-r4-sensor-hub | 10.0 | 1.7 | KEEP | Ultrasonic (low obstacles) |
| atlas-tight-recovery | 8.9 | 1.5 | KEEP | Recovery tool |
| atlas-im10a (IMU) | 8.4 | 1.4 | KEEP | Needed for EKF and mapping |
| atlas-camera-joystick | 3.7 | 0.6 | PAUSE | D-pad camera remote |
| atlas-gnss | 3.7 | 0.6 | PAUSE indoors | No fix indoors (known fault) |
| atlas-agent-supervisor | 3.1 | 0.5 | PAUSE | Mission agent, not needed for manual mapping |
| atlas-local-llm, atlas-visual-cloud-agent | ~3.5 | ~0.6 | PAUSE | Non-safety extras |
| atlas-feature-on-demand | 2.4 | 0.4 | **DO NOT stop** | Its stop runs `restore-all`, which turns always-on AI back on |

## Proposed "3D mapping mode"

| Option | Pauses | Expected whole-Jetson CPU before RTAB-Map |
|---|---|---|
| **A, no camera change** | voice, loc-monitor, shadow odom trio, camera-joystick, gnss, agent, llm, visual-cloud | **about 51 %** |
| **B, A + IMX708 camera paused** (owner decision) | A + atlas-camera + nvargus | **about 44 %** |

With B, about 30 % of the whole Jetson (about 1.8 cores) stays free under the 75 % limit for RTAB-Map at a low
rate/resolution.

**Mechanism:** extend mission-control's existing `MAPPING_BACKGROUND_UNITS` list (it already pauses Foxglove,
voice, camera tracker and follow-person during mapping, and records and restores them), rather than adding a new
system. Everything is restored when mapping ends.

## Owner decisions

1. **2026-11-05: option B approved.** The IMX708 camera (and its pan-tilt view) may pause during **3D (RGB-D)
   mapping** sessions only, not during ordinary 2D mapping. Implement in M3 as a 3D-mapping-specific pause list,
   restored on exit.
2. M3 needs approval to install RTAB-Map (apt `ros-humble-rtabmap-ros`, about 300 MB).

## Next

M2 (calibration) is still required before any 3D map or depth obstacle is trusted. M3 measures RTAB-Map's real
cost with the rover stationary, in the chosen mode, and stops if it exceeds the budget.
