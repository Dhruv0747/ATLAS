# Parked camera profile — pause Nav2 navigation around ONE stationary Vision Lab session

**Status: built and validated offline against real Nav2 1.1.20; NOT run on ATLAS.** Owner approved option 1
(12:43 IST) as: design, check dependents offline, build a tested tool. Running it on ATLAS needs a separate approval.

## Why

`ATLAS_CPU_BASELINE_SHIFT_NAV2_20261024.md`: the only camera session that passed the unchanged 75% guard
(21 Oct) ran while Nav2's navigation servers were inactive. Since every later boot activated them, the parked
Jetson sits ~5 points higher, and the owner's 24 Oct 08:35 Depth attempt was blocked at **75.21%** CPU
(Vision Lab state file: `RESOURCE BLOCKED`, 0.78 s after start). This tool reproduces the measured 21 Oct state on
purpose, for one session, and restores full navigation afterwards.

## What it does

`project_atlas/tools/vision3d/atlas_parked_camera_profile.py`

| Command | Effect |
|---|---|
| `check` / `status` | read-only: parked preconditions + Nav2 lifecycle state |
| `pause` | arm resume watchdog → `/lifecycle_manager_navigation/manage_nodes` PAUSE → verify |
| `resume` | RESUME (idempotent) → verify `is_active` and all five servers `active` → disarm watchdog |
| `session` | pause → wait for CPU to settle → owner presses Start once → session ends → resume |

Paused: `controller_server`, `planner_server`, `behavior_server`, `bt_navigator`, `waypoint_follower`
(lifecycle `inactive`, processes and identities unchanged). **Never touched:** `map_server` and `amcl`
(`/lifecycle_manager_localization`), all systemd units, parameters, guards (75/80/70), viewer lease, E-STOP,
motors, maps, the Vision Lab code. The camera is started only by the owner.

Upstream semantics (Nav2 Humble `lifecycle_manager.cpp`): PAUSE sets the system inactive and destroys the bond
timer **before** deactivating the servers, so a pause cannot trigger the bond-break hard reset; RESUME activates
them and recreates the bond timer; `is_active` reports the result.

## Safety design

- `pause` refuses unless: owner approval; E-STOP latched; policy `stop_latched`, `manual_only`, commissioning
  disarmed, source `STOPPED`; commands zero; measured motor speed zero; mission `READY`; AMCL fresh (so the
  costmaps can find map→base_link on resume); navigation and localization both active; no Astra/Vision Lab
  process; no earlier pause record.
- A systemd **user timer is armed before the pause** (`atlas-parked-camera-resume`, default 600 s): navigation is
  resumed even if the tool, the SSH session or the PC dies. If arming fails, nothing is paused.
- The tool joins ROS only in short-lived client processes (UDPv4 transport, like `atlas-localization`), for
  pause/resume/status. During the camera session it watches only `/proc/stat` and the Vision Lab state file
  (tmpfs) — no ROS participant joining (Stage 31 measured join spikes), no dashboard polling.
- Resume failure is reported as `RESUME_INCOMPLETE` and left for the owner. Navigation then stays paused
  (no autonomy possible); the tool never restarts a service.

## Dependents checked against the LIVE sources (hash-verified read-only copies)

| Component | Effect of paused navigation |
|---|---|
| Vision Lab admission (`stationary_gate`, `stationary_ros_probe`) | requires policy/commands/sensors fresh, mission READY, protected service identities unchanged — lifecycle pause changes none of these |
| `atlas_mission_control` | publishes `READY` at start and re-publishes every 1 s; checks Nav2 only when dispatching a mission. A mission request while paused is rejected by the inactive action server (safe direction) |
| `atlas_cmd_vel_mux` | Nav2 is the lowest-priority channel (`/cmd_vel_nav`); manual-only blocks it. A deactivating controller publishes one zero command — cannot move the rover |
| `atlas_safety_status` | reacts only to Nav2 goal status / BT logs; a pause produces neither |
| `atlas_localization_monitor` | uses `/scan`, `/odom`, `/amcl_pose` only — AMCL stays active |
| `atlas_sensor_recovery` | explicitly never restarts Nav2 |
| `atlas_tight_space_recovery` | uses the exploration resume topic, not Nav2 lifecycle; idle while parked |

RESULTS_PLACEHOLDER
