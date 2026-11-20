# ATLAS commands and pages — the operator's handbook

Everything you can open or run on ATLAS, in plain words. Commands run **on the Jetson** unless marked *(Mac/PC)*.

> **Three rules before anything else**
> 1. Keep the remote in your hand. **B = stop.** It overrides every other command.
> 2. Restart drive-related services (base, mux, Nav2, LiDAR) **only while the rover is parked and the stop is latched**.
> 3. Nothing here is allowed to bypass a safety gate. If a gate blocks you, the Readiness page says why.

## Contents

1. [Connect](#1-connect)
2. [Dashboard pages](#2-dashboard-pages)
3. [Everyday service commands](#3-everyday-service-commands)
4. [What each service does](#4-what-each-service-does)
5. [Named places and navigation](#5-named-places-and-navigation)
6. [Record a drive](#6-record-a-drive)
7. [Check a drive afterwards (replay tools)](#7-check-a-drive-afterwards-replay-tools)
8. [Maps and virtual obstacles](#8-maps-and-virtual-obstacles)
9. [Run the tests](#9-run-the-tests)
10. [Build and deploy](#10-build-and-deploy)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Connect

| What | How |
|---|---|
| Dashboard | Open `http://<rover-ip>:8088/` on a phone, tablet or laptop (same Wi-Fi or Tailscale). |
| Terminal | `ssh jetson@<rover-ip>` *(Mac/PC)* |
| Foxglove | Connect Foxglove Studio to the read-only bridge; the drive panel lives in `foxglove_extensions/`. |

The rover's address is private; it is never written in this repository.

## 2. Dashboard pages

All pages are served by `rover-status-web` from `project_atlas/web/v2/`.

| Page | Path | Use it for |
|---|---|---|
| **Command Center** | `/` | Main page: live camera, drive buttons, E-STOP, battery, hardware health, map with named places, Go / Abort mission. |
| **Autonomy Readiness** | `/v2/readiness.html` | A checklist of everything that blocks autonomy, each with how to clear it. Start here before a drive. |
| **Live Mapping** | `/v2/mapping.html` | Build a new map while driving by remote; the map grows on screen. |
| **LiDAR Surround** | `/v2/lidar.html` | 360° view of what the LiDAR sees right now. |
| **Full-quality camera** | `/v2/camera.html` | Full-resolution IMX708 camera view. |
| **Camera settings** | `/v2/cameras.html` | Exposure, resolution and pan/tilt settings. |
| **3D Vision Lab** | `/v2/vision3d.html` | Astra depth / infrared preview (diagnostic). |
| **Stored 3D Maps** | `/v2/map3d.html` | Browse saved 3D captures. |
| **Motor & Encoder Test Lab** | `/v2/testlab.html` | Lifted-wheel motor and encoder tests, Speed check. |
| **Commissioning** | `/v2/commissioning.html` | Step-by-step hardware commissioning console. |
| **FlySky Driving** | `/v2/flysky-drive.html` | Drive with the FlySky transmitter; live channel view. |
| **FlySky Remote Test Lab** | `/v2/flysky-testlab.html` | Check the FlySky receiver, channels and failsafe. |
| **Wi-Fi Setup** | `/v2/wifi.html` | Join or change Wi-Fi networks. |
| **Classic** | `/v2/classic.html` | Older compact Command Center layout. |

**Buttons that matter most:** **E-STOP** (stop now, latched), **Abort mission** (switch to manual *and* cancel the Nav2
goal), **Go** (start the selected named-place goal; needs autonomy armed and the stop released).

## 3. Everyday service commands

All ATLAS services are **user** services (no `sudo`).

```bash
# Is everything running?
systemctl --user list-units 'atlas-*' 'rover-*' --no-pager

# Status of one service
systemctl --user status atlas-localization

# Follow its log live (Ctrl+C to quit). Always name the unit: an unfiltered log is heavy.
journalctl --user -u atlas-mission-control -f

# Last 10 minutes of the mux (safety decisions)
journalctl --user -u atlas-cmd-vel-mux --since "-10min" --no-pager

# Restart (parked + stop latched for anything that moves the robot)
systemctl --user restart atlas-localization
```

Do not run heavy ROS probes (`ros2 topic echo` loops, unfiltered `journalctl`) **while the rover drives**: they steal CPU
and can make localization stale. Check things while parked, or record a bag and look afterwards.

## 4. What each service does

**Driving and safety (restart only parked + latched)**

| Service | Job |
|---|---|
| `rover-base-telemetry` | Yahboom motor board: motors, steering, encoders, board IMU. |
| `atlas-cmd-vel-mux` | The single gate for every movement command. E-STOP first, then priorities, watchdog, LiDAR blind-spot guard, encoder consensus, ultrasonic stop. |
| `atlas-remote` | Xbox controller teleop. |
| `atlas-lidar`, `atlas-laser-tf`, `atlas-scan-filter` | RPLIDAR scans, its measured mounting transform, chassis self-filter. |
| `atlas-ekf` | Fuses wheel odometry, IMU and LiDAR-ICP velocity into `/odom`. |
| `atlas-icp-odometry` | LiDAR keyframe-ICP velocity for the EKF. |
| `atlas-localization` | Saved map + AMCL + Nav2 + the virtual-obstacle publisher (`/map_nav`). |
| `atlas-astra-obstacles`, `atlas-astra-bridge` | Astra depth → obstacle scan for Nav2 and the guard. |

**Missions and operator**

| Service | Job |
|---|---|
| `atlas-mission-control` | Named places, goals, return home, scan check before a drive, mapping sessions. |
| `rover-status-web` (+ `atlas-status-web-watchdog`) | The web dashboard on port 8088, restarted automatically if it stops answering. |
| `atlas-localization-monitor` | Continuous read-only LiDAR-vs-map position check. |
| `atlas-autonomy-voice` | Speaks why the rover stopped or replanned (listen-only). |
| `atlas-mode-manager` | Deterministic operating modes. |
| `atlas-uno-r4-sensor-hub` | Arduino UNO R4 bridge: ultrasonic, radar, BME680, AMG8833, pan/tilt PWM. |
| `rover-radar`, `atlas-radar-tracking` | RD-03D radar targets and tracks. |
| `atlas-mobile-notifier` | Phone notifications (boot, low battery, charged). |

**Mapping and research (started on demand)**

| Service | Job |
|---|---|
| `atlas-slam-fast` | SLAM Toolbox mapping mode. |
| `atlas-map-footprint-filter` | Removes the rover's own outline from mapping scans. |
| `atlas-explore` | Supervised frontier exploration. |
| `atlas-camera-tracker`, `atlas-person-sensor-fusion`, `atlas-vision-lidar-fusion` | Camera/LiDAR/radar person and object fusion. |
| `atlas-visual-cloud-agent`, `atlas-visual-cloud-server` | Read-only telemetry history and preview API. |
| `atlas-local-llm`, `atlas-agent-*` | On-device language model and agents (stopped-only, read-only). |

## 5. Named places and navigation

Normally done from the Command Center map (tap → save place; select place → **Go**). From a terminal:

```bash
source /opt/ros/humble/setup.bash
# Save the rover's current position as a named place
python3 ~/project_atlas/scripts/atlas_named_place_cli.py save "dhruv room"
# Send the rover to a named place (autonomy must be armed and the stop released)
python3 ~/project_atlas/scripts/atlas_named_place_cli.py navigate "hall"
# Cancel the current goal
ros2 topic pub --once /atlas/cancel_navigation std_msgs/msg/Empty "{}"
```

- Places are stored in `~/.config/project_atlas/named_places.json`, each tagged with the map it belongs to.
- A place closer than 0.35 m to a wall is refused. Keep goals about 0.5 m from furniture: ATLAS steers like a car.
- A goal counts as reached within **20 cm and about 35°**.

## 6. Record a drive

Record every test drive; all analysis is done on the recording afterwards.

```bash
source /opt/ros/humble/setup.bash
cd ~/project_atlas/data/lidar_tests
ros2 bag record -o my_test_$(date +%Y%m%d_%H%M) \
  /amcl_pose /scan /odom /yahboom/odom /tf /tf_static /plan \
  /cmd_vel /cmd_vel_nav /cmd_vel_joy \
  /astra/obstacle_scan /astra/obstacle_coverage \
  /ultrasonic/front_mm /ultrasonic/rear_mm /ultrasonic/validity \
  /atlas/mission_status /atlas/motion_safety /atlas/control_policy /atlas/encoder_health /atlas/speed_loop \
  /im10a/imu/bias_corrected_candidate /radar/targets /steering/front_angle_deg /steering/rear_angle_deg
# Stop with Ctrl+C when the drive is over.
```

## 7. Check a drive afterwards (replay tools)

All tools are read-only: they never publish or move anything. They live in this repository under
`project_atlas/tools/` and are not installed on the rover by default, so copy them over first *(Mac/PC)*:

```bash
scp -r project_atlas/tools jetson@<rover-ip>:~/project_atlas/
```

Then on the Jetson (rover parked):

```bash
source /opt/ros/humble/setup.bash && cd ~/project_atlas
# Stage-3 verdict: legs reached, return home, safe stop, turn sign, encoders
python3 tools/drive/stage3_autonomy_check.py data/lidar_tests/<bag> --home "dhruv room"

# How often the LiDAR blind-spot guard would stop the rover, per 1 m band of the map
TIGHT_ARC_SWEPT=1 BANDS=1 FREE_THRESH=0.196 VIRTUAL_OBSTACLES=config/virtual_obstacles.json \
  python3 tools/drive/replay_map_known_gaps.py maps/atlas_latest.yaml data/lidar_tests/<bag>
```

The guided-mapping replay needs no ROS, so it runs on a Mac/PC from this repository, after copying the bag folder
and the map over *(Mac/PC)*:

```bash
cd project_atlas
python3 tools/mapping/replay_guided_mapping.py <bag-folder> <atlas_latest.yaml> /tmp/replay \
  --virtual config/virtual_obstacles.json
```

## 8. Maps and virtual obstacles

| File | What it is |
|---|---|
| `~/project_atlas/maps/atlas_latest.yaml/.pgm` | The accepted map, used by AMCL. Grey = unknown, white = free, black = wall. |
| `project_atlas/config/virtual_obstacles.json` | Polygons for objects the LiDAR cannot see (black sofa, glass table, cabinet). Added on top of the map for Nav2 (`/map_nav`) and the safety guard. |

**To change a virtual obstacle** (e.g. the sofa moved): edit the polygon corners (map metres), then restart
`atlas-localization` and `atlas-cmd-vel-mux` with the rover parked and the stop latched.

**Careful:** the map's identity is a hash of the YAML *and* image. Editing `atlas_latest.yaml` changes it, so stored
named places, home pose and seed pose must be re-stamped with the new map id in the same step.

## 9. Run the tests

The unit tests are pure Python and need no robot.

```bash
cd project_atlas
python3 -m unittest tests.test_virtual_obstacles tests.test_lidar_map_known_gaps tests.test_lidar_availability
python3 -m unittest discover -s tests -p 'test_*.py'    # everything (some modules need ROS 2 / the Jetson)
python3 -m unittest $(grep -v '^#' tools/ci/offline_tests.txt)   # exactly what GitHub CI runs
```

GitHub runs the robot-free set automatically on every push and pull request
([`.github/workflows/offline-tests.yml`](../.github/workflows/offline-tests.yml)). Modules that need ROS 2, hardware or the
Jetson file layout are listed in `project_atlas/tools/ci/not_in_ci.txt`.

## 10. Build and deploy

```bash
# Build the ROS 2 workspace (on the Jetson)
cd ~/project_atlas_ws && colcon build --symlink-install && source install/setup.bash
```

**Deploy rules** (from [SAFETY.md](SAFETY.md)): test offline first, back up every file you replace, copy, restart only the
affected service (parked + latched), verify the new values are live, and write a dated entry in
[the blockers log](audits/ATLAS_CURRENT_BLOCKERS.md). Any change to the speed loop, `atlas_speed_loop.py` or
`yahboom_base.py` invalidates the speed evidence: run the dashboard **Speed check** until it passes twice.
Past deploy scripts are kept in `project_atlas/tools/deploy/` for reference.

## 11. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Dashboard shows "no data" / "connection delayed" | Wi-Fi power saving or a weak spot (e.g. hall doorway) | Turn Wi-Fi power save off on the rover; add a Wi-Fi extender. |
| "camera obstacles OFF" / goal cancelled | Astra depth stream stale, often when the rover's nose is closer than 0.35 m to a wall (depth camera blind) | Back away by remote, wait for the stream, retry. |
| "LIDAR AVAILABILITY STOP: unobserved motion sector" | A direction the rover will move into returns no LiDAR echo (dark, shiny or glass surface) | Put matte tape on that surface, or add it as a virtual obstacle if it never moves. |
| "ENCODER CRITICAL: fewer than three wheel channels agree" | Wheel encoders disagree | Stop, check wheels and encoder cables; see the Motor & Encoder Test Lab. |
| "LiDAR does not match the map at the current pose" | Localization not confirmed | Drive slowly in an open area, or use **Check my location** on the dashboard. |
| "map point refused: too close to a wall" | Goal within 0.35 m of a wall | Pick a point further into open space. |
| "belongs to a different map" | The map changed after the place was saved | Save the place again on the current map. |
