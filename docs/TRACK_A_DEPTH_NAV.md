# Track A: Astra depth for navigation obstacles (STAGED, inactive)

Goal: the rover sees obstacles the 2D LiDAR misses, such as table tops, chair seats, low boxes and anything above or
below the LiDAR's scan plane. That makes it safer to drive further.

## Design (revised 2026-11-06: audit, then factory calibration + owner mount values)

```
Astra (private ROS domain 77, depth only 160x120 @15 fps)
  -> scripts/atlas_astra_obstacle_scan.py  (one node; geometry in scripts/atlas_astra_obstacle_core.py)
       - refuses to start (exit 78) on an incomplete/implausible mount or scan config
       - intrinsics = FACTORY / driver CameraInfo, validated at runtime (docs/TRACK_A_FACTORY_CALIBRATION.md);
         nothing is published before a valid CameraInfo, or after one turns invalid
       - rays, mount -> base_link; band floor+4 cm+r*tan(1 deg) .. 1.0 m, 0.35-3.0 m, +-30 deg
       - invalid depth (0/NaN/inf) never becomes an obstacle or free space
       - publishes ONLY fresh (<= 0.5 s) frames with >= 30 % valid pixels; otherwise NOTHING (never all-clear)
       - status 1 Hz on /astra/obstacle_scan_status: OK | STALE | BLINDED | NO_FRAMES | BAD_FRAME |
         NO_CALIBRATION | BAD_CALIBRATION (+ calibration source and K)
       - driver respawned by the launch after 3 s if it dies (sensor only; scan is STALE meanwhile)
  -> /astra/obstacle_scan (LaserScan, base_link, original capture stamp)
  -> domain_bridge (ONLY this LaserScan; starts only while parked, never auto-restarts) -> domain 0
  -> Nav2 local costmap SEPARATE "astra_layer" (expected_update_rate 0: an Astra outage never stalls LiDAR nav)
```

Why a separate layer: in the same layer as the LiDAR, an Astra "no return" ray (glass, black surfaces, < 0.35 m,
blinded sensor) could clear obstacles the LiDAR marked. With its own layer and `inf_is_valid: false`, the Astra can
only ADD obstacles and clear its OWN marks up to a real hit. The LiDAR layer and the global costmap are untouched.

Replaced (audit defects D1-D7): the first staged version used depth_image_proc + pointcloud_to_laserscan in the
LiDAR's layer with inf clearing. Now only one extra apt package is needed (`ros-humble-domain-bridge`).

## Files (staged; nothing installed, enabled or running)

| File | Purpose |
|---|---|
| `scripts/atlas_astra_obstacle_core.py` | Pure NumPy geometry + gates (unit-tested) |
| `scripts/atlas_astra_obstacle_scan.py` | ROS node; `--preflight` = gate check only |
| `launch/atlas_astra_obstacles.launch.py` | Driver (depth only) + viz TFs + node; refuses outside domain 77 / without gates |
| `config/astra_obstacles.yaml` | Mount (owner values + provenance), band, ranges, stale/blind thresholds, rate cap |
| `scripts/atlas_astra_bridge_parked_check.py` | Bridge interlock: start only if cmd_vel, motor speed and odom are zero/fresh |
| `config/astra_obstacles_bridge.yaml` | Bridges `/astra/obstacle_scan` only |
| `config/nav2_astra_obstacles_LIVE_SNIPPET.yaml` | Separate `astra_layer` (G5 only) |
| `tools/track_a/check_nav2_merge.py` | Proves LiDAR layer/global costmap unchanged; `--write` at G5 |
| `systemd/user/atlas-astra-{obstacles,bridge}.service.in` | No `[Install]`; ExecCondition preflight gate (unit skipped, no restart loop, verified on Jetson); memory caps |
| `tests/test_track_a.py` | 32 tests (simulated data; isolated ROS domain 91) |
| `deploy/track_a/{install,verify,rollback,apply_g5}.sh` | Deployment, gate check, undo, G5 merge |

## Activation gates (each needs a real PASS and the owner's approval for that step)

| Gate | What | PASS means |
|---|---|---|
| **G1** | **SUPERSEDED 2026-11-06** (owner): factory / driver calibration accepted as baseline; custom 22-view calibration and `depth_160x120.json` removed from the deployment path | Runtime: CameraInfo finite, 160x120, correct frame, fx 114-172 px, principal point near centre (PASS on hardware 2026-11-06) |
| **G2** | **Config complete 2026-11-06** from owner-supplied values (x candidate, y prior, z/pitch measured; height = engineering bound) | Physical check still open: a box at a tape-measured spot appears within 3 cm (part of G4) |
| **G3** | Installed; join spike measured 2026-11-06: ~4.5 s at ~100 % CPU (any new domain-0 participant does this; minimal rclpy node ~3.5 s). No service restarts | Original < 75 % criterion NOT met; mitigated: bridge starts only while parked (interlock), never auto-restarts |
| **G4** | Shadow: obstacle scan visible on the dashboard or in Foxglove, **not** in the costmap; walk objects in front of the parked rover | Table edge, chair seat and low box all appear; no phantom obstacles in 10 minutes of an empty view |
| **G5** | Live: `bash deploy/track_a/apply_g5.sh`, then restart Nav2 when parked; slow supervised driving, E-STOP in hand | Stops or plans around a table top the LiDAR misses; no phantom stops on an open floor |

Rollback at any gate: stop the two services, and for G5 restore `nav2_params.yaml` from its backup.

## Mount measurement (owner, rover parked, E-STOP latched; tape measure)

All distances are in metres, from **base_link**: the robot centre, at floor level, using the same point as the
LiDAR's `laser_frame` origin projection.

1. **x_m:** forward distance from the robot centre to the **Astra's front glass** (positive = forward).
2. **y_m:** sideways offset of the Astra's centre from the robot centre line (left = +, right = -).
3. **z_m:** height of the Astra's **lens centre above the floor**.
4. **pitch_deg:** downward tilt. Use a phone level app on the Astra's top: 0 if level, positive if looking down.
5. **max_height_m:** height of the **highest point of the rover** above the floor, plus 0.05.

Photograph the tape readings; enter them in `config/astra_obstacles.yaml`.
