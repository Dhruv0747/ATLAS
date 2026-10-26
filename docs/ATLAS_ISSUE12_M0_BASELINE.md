# Issue #12, M0: baseline and source of truth (26 Oct 2026)

All work here was read-only. ATLAS stayed parked the whole time: E-STOP latched, source STOPPED, manual-only, commissioning disarmed, drive controller DISABLED, zero commands. Nothing was deployed, no ROS participant was added (measurements came from the dashboard's existing connection plus `/proc` and sysfs), and Issue #11 and the camera system were untouched.

Raw evidence on the Jetson (not committed: telemetry):
- `~/project-atlas-migration/m0_20261026/baseline.jsonl` (sha 21aa54b5, 171 samples)
- the sampler that produced it, `sampler.py` (sha 30955c34)

## 1. Resource baseline: parked, localization stack running, Pi camera on, Astra off
Window 19:21:08–19:24:07 IST, 1 sample/s.

| Metric | mean | p50 | p95 | min | max |
|---|---|---|---|---|---|
| CPU total % | 63.0 | 62.5 | 65.4 | 59.8 | **76.0** (1 sample) |
| Hottest core % | 67.7 | 67.3 | 72.0 | 62.6 | 80.2 |
| RAM % | 62.2 | 62.2 | 62.3 | 62.0 | 62.4 |
| GPU % | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Hottest thermal zone °C | 64.8 | 64.8 | 64.9 | 64.6 | 65.0 |

Board: Orin Nano 8 GB, 6 cores, 25 W mode, L4T R36.4.3.

Headroom to the existing 75 % camera admission guard is about 10 % at the mean and about 9.6 % at p95. One of 171 samples was above 75 %.

## 2. Sensor rates and freshness

| Stream | Measured | How |
|---|---|---|
| `/scan` (RPLIDAR A1, filtered) | **7.4 Hz** mean, 7.6 p50, 8.3 p95 (one 3.7 sample); stamp age 0.20 s p50 / 0.34 p95 | dashboard scan receipt intervals and header stamps |
| `/odom` (EKF output) | 10.0 Hz | dashboard subscription |
| Encoder health / drive PID / control policy | 10.0 Hz each | dashboard |
| Yahboom board IMU | 10.0 Hz | dashboard |
| IM10A IMU (EKF input `/im10a/imu/bias_corrected_candidate`) | fresh (age ≤ 0.1 s); **rate not measured**. Acquisition timer 50 Hz, serial 9600 baud | needs a production subscriber (see risks) |
| Remote `/joy` | 16.6 Hz | dashboard |
| cmd_vel (mux output while latched) | 4.7 Hz (zero keepalive) | dashboard |
| Radar link | 16.7 Hz | dashboard |
| Ultrasonic validity | 3.5 Hz | dashboard |
| Pi camera | **10.0 fps** (30 frames / 2.9 s, from frame timestamps) | Issue #11 Measure |
| Astra | off (Vision Lab only); detected on USB 2.3.1 | dashboard |

## 3. TF availability

| Transform | Status | Evidence |
|---|---|---|
| `base_link → laser_frame` at scan time (via `base_footprint`) | **OK on 171/171 samples** | dashboard exact-time lookup |
| `odom → base_link` (EKF, `publish_tf: true`) | available (indirect) | EKF `/odom` at 10 Hz; local costmap (`odom` frame) logs no TF errors |
| `map → odom` (AMCL) | **MISSING since boot (18:57)** | AMCL logs `cannot publish a pose or update the transform. Please set the initial pose` about every second; global costmap logs `Timed out waiting for transform from base_link to map … Invalid frame ID "map"`, 3,081 times this boot |
| Camera frames (Astra, Pi) | **none exist** | no URDF / robot_state_publisher; only 2 static publishers (`base_link→base_footprint` identity, `base_footprint→laser_frame` −0.05, 0, 0.18, yaw π) |
| IMU frame | `im10a_sensor_unvalidated` (no TF) | IM10A observer |

## 4. Localization stability
- **Current boot: not localized.** The seeder refused at 18:57:23 with `AMCL not seeded; ambiguous: two places fit almost equally (0.93 vs 0.93)`. That's the safe behaviour. The localization check reports `INPUT_STALE: AMCL pose stale` on every sample, and the dashboard has no map pose (0/171).
- **History** (`localization_verdict_history.jsonl`, 32 entries): **15 VERIFIED / 17 UNKNOWN (47 % verified)**. Recent UNKNOWN reasons: two places fit almost equally (fit 0.93–0.98, margin 0.005–0.034), or the scan doesn't match well enough anywhere (best 0.84–0.93, below the 0.93 bar).
- The localization monitor logged one short `moving` → `stopped` episode at 19:09:07–19:09:08 IST while ATLAS was latched (a 1-s motion report, then a 2-s settle). Cause not investigated: it may have been a bump or a handled wheel. No drive command was issued.
- **Consequence:** localization stability and the global costmap/planner can't be baselined live until AMCL has a confirmed position. Setting it is a live action and needs separate approval.

## 5. Nav2 configuration: deployed vs GitHub (no file changed)

Nav2 loads the **installed copy** `project_atlas_ws/install/tortoisebot_bringup/share/tortoisebot_bringup/config/nav2_params.yaml`, a regular file. The launch files in `install/` are symlinks to `src/`, but this config file is a copy made at build time.

| File | Live sha | Jetson src/config sha | GitHub sha | Difference |
|---|---|---|---|---|
| nav2_params.yaml (installed = live) | 24620bf4 | 2411371c | adfb5b38 | **1 parameter** (below). Jetson src and GitHub are identical apart from CRLF line endings. |
| atlas_localization.launch.py | cc8ef0d5 | (symlink) | cc8ef0d5 | identical |
| nav2_rover.launch.py | 87fc5141 | (symlink) | 3738d5b9 | CRLF/whitespace only |
| nav2_launch.sh | 80445985 | — | 80445985 | identical |
| atlas_ackermann_fail_stop / recovery / through_poses.xml | 36d3a49a / fdda394b / 67e62320 | — | same | identical |

The only parameter difference:
- `controller_server.FollowPath.inflation_cost_scaling_factor` is **absent in the live file** (so RPP uses its built-in default) and **15.0** in Jetson src and GitHub.
- It was added by commit `6b0f462` ("Match RPP cost-distance conversion to existing inflation layer"), but the installed copy was never refreshed. So the live RPP converts costmap cost to distance with a different scaling than the local costmap's `cost_scaling_factor: 15.0`.

Live costmap configuration (unchanged):
- **Local:** rolling 3×3 m, 0.05 m, `odom`, 5 Hz update / 2 Hz publish, footprint 0.50×0.36 m. ObstacleLayer with `scan` only (`/scan`, marking + clearing, raytrace ≤ 3.0 m, obstacles 0.05–2.5 m), inflation 0.28 m / factor 15.
- **Global:** `map`; static + obstacle (`scan`) + inflation.
- An inactive `semantic_camera` PointCloud2 source is defined but not in `observation_sources`.
- No collision monitor configured.

SLAM (`atlas-slam-fast`, inactive): slam_toolbox async, `/map` remapped to `/map_raw`, scan 0.20–8.0 m, update interval 1.5 s, loop closing on. Parameters are set inline in the systemd unit (no YAML).

## 6. Astra mounting measurements needed from the owner
No position or orientation is assumed. The base reference point is **not documented** either: there is no URDF for the real robot, and only `base_footprint→laser_frame` is defined. So that comes first.

Measure with ATLAS on a level floor, at rest, with normal load. Measure positions to ±5 mm and angles to ±1°. Positive directions: **x forward, y left, z up**.

**A. Confirm the reference point** (where `base_link` / `base_footprint` is)
1. Which point you consider the robot centre. Proposal to confirm or correct: the floor point midway between the front and rear axles and midway between the left and right wheels.
2. Cross-check against the existing LiDAR transform: forward/back distance from that point to the LiDAR's rotation centre (config says 5 cm **behind**), the LiDAR's sideways offset (config says 0), and the height of the LiDAR scan window above the floor (config says 18 cm). If these don't match, tell me; the LiDAR TF or the reference point is then wrong.

**B. Astra mount**
3. Is the Astra **fixed rigidly**, or on an adjustable bracket or the pan/tilt servos? If it can move, say how, and whether it has been moved since mounting.
4. Is it **upright** (logo/text the right way up), upside down, or rotated?
5. Which of the three front openings is which: IR projector, colour camera, IR (depth) camera. A clear front photo is enough.

**C. Position of the depth (IR camera) lens centre** relative to the reference point
6. **x:** forward distance, from the reference point to the front face of the IR lens.
7. **y:** sideways offset from the robot's centreline (left +, right −).
8. **z:** height of the IR lens centre above the floor.

**D. Orientation**
9. **Pitch:** tilt down (+) or up (−) in degrees. A phone inclinometer on the camera's flat top works.
10. **Roll:** sideways tilt in degrees.
11. **Yaw:** is it pointing straight ahead? Measure the distance from the centreline to the left and right front corners of the camera body (equal = straight), or give the angle.

**E. Photos**
12. Front, side (with a tape measure visible), and top view of the mount.
13. Anything that might be in the camera's view: bumper, cables, robot parts, floor close to the robot.

## 7. Risks and blockers before M1
1. **AMCL not localized (blocker for localization baselines).** No `map` frame since boot, and the global planner can't run. M1 (stationary depth validation in domain 77) doesn't need it. M4–M6 comparisons do. Fixing it needs an owner-approved initial pose ("Check my location" or a set pose); not done in M0.
2. **Installed `nav2_params.yaml` lags its source by one parameter.** Any future costmap overlay (M4) must target the installed path or reinstall it. Refreshing the installed copy is a live change: it alters RPP behaviour and restarts Nav2, so it needs a separate decision. No file was changed.
3. **CPU headroom is ~10 %, with occasional spikes above 75 %** (1/171 samples). The depth node must stay very light (160×120, stride, no RGB), and Vision Lab admission can refuse at spike moments.
4. **Measurement gap:** the true rate of the IM10A topic and a direct `odom→base_link` TF lookup need a production-domain subscriber. Joining that domain causes the known 3–8 s CPU spike. Proposal: one owner-approved 10-s `ros2 topic hz` / `tf2_echo` session, or measure them later from inside the M3 bridge node.
5. **No URDF / undocumented base reference point:** resolved by section 6A. Without it the camera TF can't be trusted.
6. **Line-ending drift** (CRLF on the Jetson, LF on GitHub) in config and launch files makes sha comparisons noisy. Cosmetic, but worth normalising later with owner approval.
7. **Localization reliability is 47 % verified** in recorded history. M6 needs a fixed test protocol (same start places, same number of checks) so before/after numbers are comparable.


---

## M0: Astra mount measurements (owner, 26 Oct 2026 21:32 IST)

Reference point: the rover centre, i.e. the midpoint between the front and rear axles (x forward, y left, z up, floor = 0).

| Item | Owner value | Status |
|---|---|---|
| Mount | fixed (not on servos), facing straight forward | recorded |
| x (lens centre) | **+0.100 m** forward of the axle midpoint | recorded |
| y | **≈ 0** (on the centreline) | recorded; see open item 1 |
| z (IR lens centre) | **0.275 m** above the floor | recorded |
| pitch / roll / yaw | **≈ 0° / 0° / 0°** (no tilt) | recorded as approximate; to be verified from the floor plane in M1/M2 |
| Lens centre to front body edge | 0.134 m, so the front edge is at x ≈ +0.234 m | consistent with the Nav2 footprint front edge at +0.25 m |

Draft camera transform for M2, not deployed: `base_footprint → astra_link`: xyz = (0.100, 0.000, 0.275), rpy = (0, 0, 0). The optical frame gets the standard camera rotation (z forward, x right, y down). It will be validated and refined in M2: floor-plane fit for height, pitch and roll; depth/LiDAR wall agreement for yaw and x.

### Open items
1. **Which lens was measured?** The Astra Pro has three front openings (IR projector, colour camera, IR camera), a few centimetres apart. Depth comes from the **IR camera** lens. If the centre opening was measured, the IR lens is off the centreline by a few cm, and y won't be 0. Please confirm which one, with a front photo.
2. **LiDAR cross-check:** the message was cut off at "LiDAR reference". The configured LiDAR transform is 0.05 m **behind** the axle midpoint, on the centreline, scan plane 0.18 m above the floor. Please confirm or give the measured values.
3. **"No tilt" is by eye.** M1/M2 will measure pitch and roll from the floor plane in the depth data, and height from the floor distance. That checks the 0.275 m and 0° values without any extra hardware.

### Geometry consequence (calculated, for planning)
- With the lens at 0.275 m and 0° pitch, the bottom edge of the depth view (vertical FOV 45.5°) first meets the floor **0.66 m** ahead of the lens. That is 0.76 m from the rover centre, or ~0.52 m ahead of the front edge.
- The camera also can't measure anything closer than ~0.6 m.
- Pitching the camera down wouldn't help much. At 15° down the floor would enter the view at 0.36 m, but that point is only ~0.45 m from the lens, still inside the 0.6 m minimum range.
- **So the 0° mount is reasonable. But there is a near-field blind zone: low obstacles (under the 0.18 m LiDAR plane) within roughly 0.5 m ahead of the front edge are invisible to both LiDAR and depth.** The front ultrasonic sensor (and the radar) remain the only coverage there. M3/M4 acceptance must state this limit, and depth must never be described as covering it.
- Horizontal coverage: ±0.56 m wide at 1 m ahead (58.4° FOV), wider than the 0.36 m body, from about 0.66 m onward.
