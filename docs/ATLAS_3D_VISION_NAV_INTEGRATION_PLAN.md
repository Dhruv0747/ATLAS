# ATLAS: Astra Pro depth for obstacle awareness and navigation

Architecture audit and staged integration plan. Audited 26 Oct 2026, read-only, on the live Jetson (ATLAS parked, E-STOP latched). No navigation, costmap, TF or service change was made during the audit.

## 1. What runs today (live audit)

| Area | Live configuration | Source |
|---|---|---|
| Localization mode (default) | `atlas-localization`: `tortoisebot_bringup/atlas_localization.launch.py`, i.e. map_server + AMCL + Nav2 (controller, planner, behaviors, bt_navigator, waypoint follower, velocity smoother); map `maps/atlas_latest.yaml` (0.05 m) | systemd user unit |
| Mapping mode | `atlas-mode-manager` switches to `atlas-slam-fast` (slam_toolbox async, `/map` remapped to `/map_raw`) + `atlas-nav2`. Both inactive now. | `atlas_mode_manager.py` |
| Nav2 params (authoritative) | **installed** `project_atlas_ws/install/tortoisebot_bringup/share/.../config/nav2_params.yaml` (sha 24620bf4). The repo copy `config/nav2_params.yaml` differs (2411371c). | sha256 |
| Controller | Regulated Pure Pursuit, 10 Hz; BT `config/atlas_ackermann_fail_stop.xml`; four-wheel steering (Ackermann-like), footprint 0.50 × 0.36 m | nav2_params |
| Local costmap | rolling 3 × 3 m, 0.05 m, `odom` frame, 5 Hz; `obstacle_layer` (ObstacleLayer, **source `scan` only**) + inflation 0.28 m | nav2_params |
| Global costmap | `map` frame; static + obstacle (`scan` only) + inflation | nav2_params |
| Camera source in costmaps | A `semantic_camera` PointCloud2 source (`/camera/semantic_obstacles`) is **defined but not listed in `observation_sources`**, so it is inactive. Its publisher `atlas-vision-lidar-fusion.service` (Pi-camera semantics + LiDAR) is enabled but **not running**. | nav2_params, systemd |
| Collision monitor | Package `nav2_collision_monitor` installed, **not configured** | dpkg, nav2_params |
| Odometry | `atlas-ekf` (robot_localization, 2D, 10 Hz): `/yahboom/odom` + `/im10a/imu/bias_corrected_candidate`; publishes `odom→base_link` | `config/atlas_ekf.yaml` |
| Extra odometry (candidates) | `rf2o_laser_odometry` → `atlas-lidar-odom-gate`; `atlas-ekf-lidar-candidate` → `/odom/lidar_fused_candidate` (not used by Nav2) | systemd |
| LiDAR | RPLIDAR A1 → `/scan_raw` → `atlas_scan_self_filter` → `/scan` (~7.9 Hz, `laser_frame`) | systemd |
| TF tree | `map→odom` (AMCL), `odom→base_link` (EKF), static `base_link→base_footprint` (identity), static `base_footprint→laser_frame` (−0.05, 0, 0.18 m, yaw π). **No URDF / robot_state_publisher. No camera frames. The IMU frame is `im10a_sensor_unvalidated`.** | processes, units |
| Drive safety (cmd_vel mux) | Inputs `/joy`, `/scan` (side/front stop sectors, `auto_side_stop_m` 0.28), `/ultrasonic/validity`, `/radar/speed_guard`, `/atlas/voice/stop`; E-STOP latch, manual-only and commissioning policy; remote has priority | `atlas_cmd_vel_mux.py` |
| Localization quality | Latest check: `UNKNOWN, ambiguous: two places fit almost equally (0.94 vs 0.91)`; dashboard reports localization degraded | `localization_verdict.json` |
| Compute | Orin Nano 8 GB, 6 cores, 25 W mode, JetPack R36.4.3. Parked baseline CPU ~60–67 %, RAM ~61 %, ~64 °C, GPU idle. | live |

## 2. Astra Pro: what exists and what is missing

**Already integrated (Issue #11 and Stages 29–32; keep, don't duplicate):**
- Port-independent USB identity, udev access, dashboard connection state, USB start-failure explanation (`scripts/atlas_astra_usb.py`).
- Isolated ARM64 driver runtime; the driver runs in **private ROS domain 77**. Measured 21 Oct: a participant joining the production domain wakes ~34 nodes (65 % → 92 % CPU for ~3 s).
- Vision Lab: leased, ≤60 s, viewing only, guarded (75 % CPU / 80 % RAM / 70 °C, E-STOP latched + zero speed). Depth 160×120@30 and 320×240@30, IR 640×480@30, depth+RGB measured.
- Camera settings (Issue #11): per-camera modes, USB budget, runtime OpenNI detection.
- Geometry: `atlas_vision3d_geometry.py` (calibration gate, undistort, back-projection, PointCloud2 layout, plane fit). `atlas_vision3d_cloud_node.py` publishes `/astra/points` in domain 77, but **only with a VALIDATED calibration, which does not exist yet**.
- Measured load, 60-s dual-camera run (26 Oct): guard CPU avg 63 %, max 66.7 %; Astra driver ~8 % of one core, 85 MiB.

**Missing for navigation:**
1. **Calibration.** Factory intrinsics read as NaN, and no validated intrinsic or depth-scale calibration exists.
2. **Extrinsics / TF.** No `base_link → astra_*` transform. The physical mount position and tilt are not recorded.
3. **Continuous supervised operation.** The only Astra owner is the 60-s viewing session. Navigation needs a long-running, resource-guarded owner, with defined arbitration against the Vision Lab (one camera owner).
4. **Path into the production graph.** Depth lives in domain 77, and Nav2/costmaps run in the default domain. Nothing carries depth across.
5. **Depth obstacle product.** Nothing turns depth into ground-removed, height-banded obstacles; there's no costmap source and no expected-rate/timeout handling.
6. **Health and fail-safe.** No depth monitor in sensor recovery or the dashboard navigation view; no defined LiDAR-only fallback test.
7. **Evaluation.** No baseline-vs-depth comparison of costmaps, obstacle detection, mapping or localization.

**Physical limits to design around** (product specs; to be confirmed on this unit in M1):
- Depth minimum range is about **0.6 m** (maximum about 8 m), so obstacles closer than ~0.6 m are invisible to depth. LiDAR and ultrasonic stay responsible for close range.
- Structured-light IR fails on glass, mirrors, black or absorbent surfaces and in direct sunlight. Depth must only **add** obstacles, never clear LiDAR obstacles.
- The LiDAR scans one plane at 0.18 m. Depth's real value is obstacles **outside that plane**: low objects below 0.18 m, table tops and overhangs above it, chair and table legs the LiDAR resolves poorly.
- Narrow FOV (58.4° H × 45.5° V): forward-looking only.

## 3. Design decisions (proposed)

- **D1 Domain bridge, not domain merge.** Keep the driver and raw images in domain 77. One new long-running node (`atlas_depth_obstacles`) subscribes to depth in domain 77 and publishes only compact products into the production domain. That's one production participant, created once at service start (DDS spike measured and accepted once), instead of image topics on the production graph.
- **D2 Obstacle product = 2-D "depth virtual scan" first.** A `sensor_msgs/LaserScan` in `base_link`: for each bearing, the nearest return within a height band above ground (proposed 0.03–0.60 m, set by the footprint and mount height). Cheap, works with the existing ObstacleLayer (marking + raytrace clearing), easy to compare against `/scan`. Optional later: a down-sampled `PointCloud2` for a VoxelLayer.
- **D3 Add, never subtract.** Depth is a separate observation source: marking always; clearing only within its own valid range band (raytrace ≤ obstacle max range, min ≥ 0.6 m). It never clears LiDAR marks. On timeout, the costmap falls back to LiDAR-only, and Nav2 never blocks on depth.
- **D4 Shadow before live.** Each stage runs in shadow first: products published, recorded and compared, not used by Nav2. Enabling it in the local costmap is a separate, reversible parameter overlay with an automatic rollback script.
- **D5 Localization unchanged.** AMCL and EKF stay LiDAR/encoder/IMU-based. Depth is evaluated for localization only in M6 (comparison), with no change unless the evidence justifies it.
- **D6 Camera ownership.** One Astra owner at a time. The navigation depth service and the Vision Lab arbitrate through the existing "refuse a second owner" check. Later the Vision Lab may view the navigation stream instead of starting the driver. The Issue #11 settings and Vision Lab code are reused, not rewritten.
- **D7 Mux safety later, optional.** The cmd_vel mux safety stops (LiDAR sectors, ultrasonic, radar) stay authoritative. A depth slow/stop input is considered only after M5 evidence, as its own approved change.

## 4. Staged plan and acceptance criteria

Every stage: ATLAS parked (E-STOP latched, motors disabled, zero commands) unless a later stage is separately approved; backups + automatic rollback for each deployment; offline tests first; no change to existing safety limits, manual control, or the Issue #11 camera settings.

**M0 Baseline and source of truth** (no live change)
- Reconcile the installed vs repo `nav2_params.yaml` (document the diff; make the repo match the installed file, or record why not).
- Record the baseline: TF tree, costmap configuration, CPU/RAM/temp/GPU at parked idle, 2 localization checks, local costmap snapshot.
- Owner: measure the Astra mount (x, y, z from `base_footprint`, pitch/roll/yaw), with a photo.
- **Accept:** baseline report committed; install/repo diff explained; mount measurement recorded.

**M1 Depth validation and point cloud (stationary, domain 77 only)**
- Confirm on this unit: minimum/maximum range, depth units, frame rate and stability at 160×120 and 320×240, data-loss behaviour.
- Validate depth scale against tape-measured targets at 0.6 / 1.0 / 1.5 / 2.0 / 3.0 m and against LiDAR range on a flat wall.
- **Accept:** median depth error ≤ 2 % (or ≤ 2 cm), whichever is larger, at 0.6–3 m on a matte target; ≥ 25 fps at 160×120 over 60 s; results and data committed (no raw images, no bags).

**M2 Calibration, TF and timestamps**
- Intrinsic calibration (checkerboard on IR at 640×480, scaled to depth mode), stored as a versioned calibration file with a physical validation record. This makes the existing calibration gate VALIDATED.
- Static TF `base_footprint → astra_link → astra_depth_optical_frame` from the M0 measurement, refined by LiDAR/depth wall agreement (yaw/pitch/height).
- Timestamp check: driver stamps vs system clock, end-to-end age at the production topic.
- **Accept:** reprojection RMS ≤ 0.5 px; a wall seen by depth and LiDAR agrees within 3 cm and 1.5° after TF; depth stamp age ≤ 100 ms (p95) at the bridge output; `/astra/points` passes the existing calibration gate; TF tree has no conflicts and no duplicate parents.

**M3 Depth obstacle node (shadow mode)**
- New `atlas_depth_obstacles` service (always-on, supervised, guarded like the Vision Lab: 75/80/70, no camera start unless parked during development). It bridges domain 77 → production: `/depth/obstacle_scan` (LaserScan, `base_link`) plus a status JSON (rate, age, valid fraction, health).
- Ground removal and height band from TF; range gating 0.6–3.0 m; NaN/zero handling; per-frame CPU budget.
- Dashboard: depth health on the Hardware/Drive panel. sensor recovery: diagnose-only monitor first.
- **Accept:** stationary scenes (box below 0.18 m, table top, chair, open floor, wall): depth marks each out-of-plane object that LiDAR misses, with no false obstacles on open floor over 10 min. CPU increase ≤ 6 % total with Pi camera and Nav2 running; RAM ≤ 80 %; temp ≤ 70 °C; graceful stop/restart and a single owner with the Vision Lab. Unit and regression tests pass with no new failures.

**M4 Nav2 local costmap integration (stationary)**
- Parameter overlay adds `depth` to the **local** costmap obstacle layer only: marking + bounded clearing, `expected_update_rate`, `observation_persistence`. The global costmap stays LiDAR-only.
- Automatic rollback script restores the previous params and restarts only the affected Nav2 stack.
- Fail-safe tests: unplug/stop depth → source times out, costmap falls back to LiDAR-only, Nav2 keeps running, the dashboard shows the depth fault. Depth never clears LiDAR obstacles.
- **Accept:** in a parked costmap snapshot, depth-only obstacles appear in the local costmap within 0.5 s and clear within 2 s after removal; the depth-stop test passes; manual control, mux safety, E-STOP, AMCL and EKF unchanged (same params and PIDs); rollback tested once.

**M5 Supervised motion tests (separate owner approval required)**
- Low-speed manual driving first, then supervised Nav2 goals in a cleared area with depth-only obstacles (low boxes, table). Owner present with the remote; E-STOP rules unchanged.
- **Accept:** Nav2 plans around depth-only obstacles that LiDAR-only Nav2 does not avoid (A/B, same course); no new false stops on open floor; no collisions; recovery behaviour unchanged.

**M6 Mapping and localization comparison**
- Same routes before and after: AMCL verdicts, map→odom stability, localization-check fit and margin, SLAM map quality (wall straightness, duplicates).
- Depth is not fed into AMCL or SLAM unless this evidence supports a separate proposal.
- **Accept:** a documented A/B table; no localization regression from enabling depth in the local costmap.

**M7 Benchmarks, regression tests and release**
- 30-min parked and supervised-motion benchmarks: CPU/GPU/RAM/temp, DDS participant count, depth rate/age, Nav2 controller rate.
- Regression suite: geometry, TF, obstacle extraction, costmap overlay, timeout/fallback, ownership arbitration, guards; full suite with no new failures.
- **Accept:** CPU ≤ 75 % sustained (existing guard), temp ≤ 70 °C, controller ≥ 9 Hz, depth age p95 ≤ 150 ms; all tests green; documentation, rollback and owner sign-off.

## 5. Risks

- **CPU headroom** is about 8–12 % over the parked baseline before the 75 % guard. Use 160×120 depth first, a stride-based scan, no RGB, and GPU work only if needed.
- **DDS spike** when the bridge joins the production domain: once at service start. Measure it and schedule start at boot or while parked.
- **Ownership conflict** with the Vision Lab: make it explicit (D6).
- **Minimum range 0.6 m and IR failure surfaces:** depth is additive only; LiDAR/ultrasonic keep close-range and stop responsibility.
- **Mount rigidity:** recheck calibration after any bump; the TF has a validation record and date.
- **AMCL is already ambiguous** in places. Depth in the costmap won't fix localization; that's a separate workstream (M6 evidence first).
