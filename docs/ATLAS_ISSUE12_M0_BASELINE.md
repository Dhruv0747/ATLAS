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

**SUPERSEDED 26 Oct 22:48 (camera remounted):** draft camera transform for M2, not deployed: `base_footprint → astra_link`: xyz = (0.100, 0.000, 0.275), rpy = (0, 0, 0). The optical frame gets the standard camera rotation (z forward, x right, y down). It will be validated and refined in M2: floor-plane fit for height, pitch and roll; depth/LiDAR wall agreement for yaw and x.

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


---

## M0: physical measurements vs configured geometry (owner measurements, 26 Oct 2026, 21:45 IST)

Recorded as stated. **Nothing was modified or deployed**: TF, self-filter, localization, Nav2 and safety configuration are all unchanged.

### Owner measurements
Reference: midpoint between the front and rear axles = physical centre of the rover body (owner-confirmed). x forward, y left, z up from the floor.

| Sensor | x | y | z | Other |
|---|---|---|---|---|
| RPLIDAR A1 (scan centre) | **0.00 m** | **0.00 m** | **0.40 m** | 0.25 m from the front and the rear body edge; 0.13 m from the left and the right body edge |
| Astra Pro IR lens | **+0.10 m** | ≈ 0.00 m | **0.275 m** | fixed, facing forward, tilt ≈ 0°; camera centre is 0.134 m from the front body edge |

### Reconciliation with what is configured / previously "verified"

| Item | Live configuration | Where it lives | 6 Aug commissioning doc | Owner, 26 Oct | Difference |
|---|---|---|---|---|---|
| LiDAR x | −0.05 m | `atlas-laser-tf.service` (file dated 6 Aug); `atlas_scan_self_filter.py` `LASER_X_M`; inactive `atlas_vision_lidar_core.py` default | −0.05 m ("centre 0.30 m from the front edge of a 0.50 m chassis") | **0.00 m** (0.25 m from each end) | **5 cm** |
| LiDAR z | 0.18 m | `atlas-laser-tf.service` | 0.18 m | **0.40 m** | **22 cm** |
| LiDAR yaw | π (180°) | TF; self-filter `LASER_YAW_RAD`; mux `lidar_guard_yaw_deg 180` | π | **not measured** | open |
| Body width | 0.36 m (footprint ±0.18; self-filter ±0.23) | nav2_params, self-filter, mux `auto_side_stop_m` comment | 0.36 m | **0.26 m** (0.13 m each side of the LiDAR) | 10 cm, **needs clarification** |
| Body length | 0.50 m (footprint ±0.25) | nav2_params | 0.50 m | 0.50 m | consistent |
| Camera x | none | — | — | IR lens +0.10; camera centre 0.25 − 0.134 = **+0.116** | the lens is on the front face, so it should be *ahead* of the camera centre. 1.6–4 cm inconsistent; one value is off. M2 settles it. |

The saved map (`maps/atlas_latest`, 2 Oct) and every recorded localization result were produced with the current LiDAR TF.

### Impact of the LiDAR discrepancy (analysis only)

**z: 0.18 → 0.40 m**
- *SLAM, AMCL, rf2o:* no effect. All are 2-D and ignore the sensor height.
- *Nav2 costmaps:* no effect on marking or clearing. The `scan` source accepts points between 0 and `max_obstacle_height` 2.0 m, so 0.18 and 0.40 are treated the same.
- **Real effect (safety model):** the LiDAR sees nothing below **40 cm**, not 18 cm. Every LiDAR-based protection is blind to objects lower than 40 cm: Nav2 costmaps, the mux LiDAR guard and AMCL. That includes low boxes, stools, bed frames, steps, pets and toys. Docs, commissioning notes and the Issue #12 plan assumed 18 cm.
  - Ahead of the robot, such objects are covered only by the front ultrasonic sensor (and the radar, for moving targets).
  - The planned depth camera (lens at 0.275 m) would see them from about 0.66 m ahead.
  - This **raises the priority of M3/M4** and widens the near-field blind zone that depth can't cover (closer than ~0.5 m ahead of the front edge).

**x: −0.05 → 0.00 m**
- *Scan self-filter* (`/scan_raw` → `/scan`; feeds Nav2, AMCL, SLAM and the mux guard). The removal box is ±0.30 × ±0.23 m around where the filter thinks the LiDAR is. With the LiDAR really at the centre, the box covers **x −0.25 … +0.35 m**, not −0.30 … +0.30.
  - **Front:** returns up to **10 cm beyond the front body edge** are deleted, instead of the intended 5 cm. Real obstacles in that band are removed from `/scan` before any consumer sees them.
  - **Rear:** the margin behind the body is 0, so rear chassis/wheel returns can leak into `/scan` as false obstacles.
  - Sides: with a 0.26 m body (if correct), ±0.23 deletes up to 10 cm beyond each side, instead of the intended 5 cm.
  - At 0.40 m the LiDAR may sit above the body and see little or no chassis, which would make most of this filter unnecessary. To be verified.
- *Costmaps:* points are placed 5 cm rearward of reality. Obstacles ahead appear 5 cm **closer** (conservative). Obstacles behind appear 5 cm **farther** (5 cm less safety margin when reversing).
- *AMCL / SLAM:* every pose is internally consistent with the map, which was built with the same TF, but `base_link` is estimated **5 cm ahead of the true centre**. During any turn the assumed laser position swings on a 5 cm lever arm that odometry doesn't predict. That adds scan-matching and AMCL motion-model error in turns, and may contribute to the open localization problems (47 % verified; "ambiguous" refusals). This is unproven and needs measurement.
- *Saved places and home pose* are `base_link` poses. Correcting the TF moves `base_link` 5 cm relative to the laser, so each saved place shifts up to 5 cm and should be re-checked.
- *rf2o laser odometry candidate:* uses the same TF, so it has a 5 cm lever-arm error in turns. It doesn't feed Nav2.
- *Mux LiDAR guard:* uses only the frame and yaw (180°), not x or z. No direct effect.

**Yaw (unmeasured).** The handoff (§10) recorded an unexplained ~5.5° heading offset and named "LiDAR mounting yaw" as a candidate. The owner measurement doesn't cover yaw yet.

### Proposed correction path (for owner approval; nothing done)
1. **Read-only physical check first.** The 6 Aug "verified" values contradict today's measurement, so confirm which one is right before changing anything. Park ATLAS square to a flat wall (front edge at a tape-measured distance D, e.g. 1.00 m), read the LiDAR range straight ahead from the dashboard, then repeat with the rear to the wall.
   - LiDAR at the centre → both readings ≈ D + 0.25 m.
   - Old config → D + 0.30 m forward and D + 0.20 m rearward.
   - A side wall gives the same check for yaw. No configuration change is involved.
2. Then, as **one separately approved change with automatic rollback**:
   - the static TF (x 0.00, z 0.40, yaw as confirmed);
   - the self-filter (`LASER_X_M` and the body envelope from the confirmed width);
   - documentation.
   - Afterwards: parked AMCL verification on the existing map, re-check of saved places, then supervised turn tests. A re-map only if the evidence shows it's needed.
3. **Clarify the 0.36 vs 0.26 m width** (is 0.36 the outer wheel width?) before touching the footprint, the side stop or the self-filter.

### Questions for the owner
1. Was the LiDAR **moved or raised** after 6 Aug? The commissioning doc measured 0.30 m from the front edge at 0.18 m height.
2. What is the outermost width **including the wheels**? Is 0.26 m the body deck only?
3. LiDAR orientation: which way does the RPLIDAR's cable/motor side face (front or rear)? The config assumes the scanner is rotated 180°.
4. The camera: please re-check the IR lens x (+0.10) against "camera centre 13.4 cm from the front edge" (implies +0.116). The lens should be the more forward of the two.

### M0 status and M1 readiness
- M0 deliverables are done: baseline, deployed-vs-GitHub Nav2 diff, mount measurements recorded and reconciled with impact analysis. **M0 is complete as documentation.** The LiDAR geometry discrepancy is carried forward as an open, approval-gated item, not fixed in M0.
- **M1 (stationary depth validation in private domain 77) is ready to start once approved.** It doesn't depend on the LiDAR TF. M1 uses tape-measured targets as ground truth, and compares depth with **raw LiDAR range in the laser frame**, not TF-transformed points, so the discrepancy can't contaminate it.
  - The step-1 wall test above fits naturally into the M1 session.
  - It needs Vision Lab-style depth sessions (camera streaming, guarded, ATLAS parked) and someone to place targets.
- **Not ready:** M2 (TF and calibration) needs the LiDAR geometry confirmed or corrected first, because the camera extrinsics are validated against the LiDAR.
