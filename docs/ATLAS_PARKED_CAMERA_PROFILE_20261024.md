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

## Offline validation — real Nav2 1.1.20, Jetson's live parameters (19/19 pass)

Environment: RoboStack Humble, **Nav2 1.1.20 and rclpy 3.3.21 (the Jetson's exact versions)**, Python 3.12, x86;
loopback-only network namespace (cannot reach ATLAS). The five real navigation servers plus map_server, AMCL and
both lifecycle managers run with the **live `nav2_params.yaml` (`2411371c…`) and live behaviour trees**
(`atlas_ackermann_fail_stop.xml` `36d3a49a…`), `bond_timeout` 4.0, respawn enabled, `cmd_vel→cmd_vel_nav` remaps —
as in the live launch file. Synthetic 20 × 20 m map, fake odometry/TF/scan, fake Dashboard API. Harness:
`project_atlas/tools/vision3d/parked_profile_offline/run_offline_validation.py`.

| Scenario | Result |
|---|---|
| Real Nav2 bring-up: 5 navigation + 2 localization nodes active | PASS (18 s) |
| Planner works while active (ComputePathToPose) | PASS — 85-pose path |
| Refuse: no owner approval / E-STOP not latched / policy not stopped / mission not READY / motor command nonzero / AMCL stale | 6 × PASS — nothing changed in each case |
| Pause: 5 navigation servers `inactive`, map_server + AMCL `active` | PASS |
| Paused state stable 40 s (10× the 4 s bond timeout), no bond-break reset | PASS |
| Planner refuses goals while paused (no autonomy possible) | PASS — `REJECTED` |
| Navigation CPU (5 servers), % of one core | PASS — **16.9 → 3.2** |
| Second pause refused while a pause is recorded | PASS |
| Resume: all 5 `active`, record cleared | PASS |
| Planner works after resume | PASS — 85-pose path |
| Resume is idempotent | PASS |
| Watchdog: pause with a 15 s window and walk away → automatic resume, record cleared | PASS |
| Resume while map→odom is genuinely absent (boot −3 condition, recreated by pausing localization for 15 s): reports `RESUME_INCOMPLETE`, restarts nothing; activation completes once localization returns | PASS |
| Full `session`: pause → settle → READY → simulated Vision Lab session start/end → resume | PASS |

Unit tests (`project_atlas/tests/test_parked_camera_profile_unit.py`, no ROS): 8 pass — every unsafe condition
refuses, approval required, systemd watchdog command bounded to `resume`, watchdog armed before PAUSE, arming
failure refuses before pausing, a watchdog-run resume never kills itself and clears the record, no service
start/stop/restart code.

Defects found and fixed during validation (before any ATLAS use): a harness argument-order bug (two servers
crashed at start); a watchdog self-termination bug in the test watchdog path that left a stale pause record —
fixed in the tool for both paths (record cleared first; a watchdog-run resume never disarms itself), with a unit
test; a TF-loss injection that did not reproduce the real failure (tf2 cached the old transform) — replaced by
pausing localization so map→odom is truly absent.

## Expected effect on ATLAS (estimate, not a measurement)

On 21 Oct (navigation inactive) the parked Jetson measured 65.5%; with navigation active it measures ~71%
(72.9% in the light-observer capture). The 24 Oct capture puts the five navigation servers plus the navigation
lifecycle manager at roughly 25–30% of one core; pausing should recover most of that, ≈ **4–5 points of
whole-Jetson CPU**. The 08:35 Depth attempt failed by 0.21 points. This is the first change whose expected size
exceeds the measured margin, but only a live session will show whether the 1-s guard passes.

## Rollback

Nothing is installed. `resume` (or the armed watchdog, at most 600 s after pause) restores navigation. If resume
ever reports `RESUME_INCOMPLETE`, navigation stays paused (safe: no autonomy) and the owner decides; the known
remedy is the existing `atlas-localization` service restart, which needs its own approval.

## On-robot procedure (needs separate owner approval; nothing below has been run)

1. Copy the tool to `~/project-atlas-migration/parked-profile/` on the Jetson, verify SHA256; no production file changes.
2. `check` (read-only; the robot must already be parked, E-STOP latched, camera off).
3. Run `session` as a persistent user unit; when it reports `READY_FOR_CAMERA`, the owner opens the Vision Lab,
   selects Depth, presses Start **once**, ticks Uncalibrated preview, then lets it end.
4. The tool resumes navigation and verifies all five servers active; read-only post-checks (E-STOP, policy,
   commands zero, recording off, camera off, mission READY, protected service identities unchanged).

## On-robot run 1 — 24 Oct 2026 13:37–13:43 IST (owner approval 13:25)

- Staged `~/project-atlas-migration/parked-profile/` (tool `8aef5337…`, includes the get_state retry added after
  the first live `check` showed one slow first discovery; offline suite re-run 19/19 before use).
- `check`: parked, E-STOP latched, mission READY, commands zero, navigation + localization active.
- `session` (persistent user unit): **pause OK** — 5 navigation servers `inactive`, map_server + AMCL `active`,
  systemd resume timer armed (600 s). CPU settled immediately: 64.9, 69.4, 64.8, 68.4, 67.0% (before the pause:
  71.6, 73.9, 67.7, 72.9, 70.7, 70.5, 77.8, 68.5%).
- **No camera session was started** within the 300-s window (Vision Lab state unchanged since 08:35).
- **Resume OK** at the window end: all 5 navigation servers `active`, localization active, timer disarmed,
  pause record cleared. No service restarted; E-STOP latched throughout.
- Result: the pause/resume mechanism is live-verified; the 3D preview itself remains untested. A new window needs
  the owner at the browser.
