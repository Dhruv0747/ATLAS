# Track A: Astra depth for navigation obstacles (STAGED, inactive)

Goal: the rover sees obstacles the 2D LiDAR misses, such as table tops, chair seats, low boxes and anything above or
below the LiDAR's scan plane. That makes it safer to drive further.

## Design (revised 2026-11-06 after audit)

```
Astra (private ROS domain 77, depth only 160x120 @15 fps)
  -> scripts/atlas_astra_obstacle_scan.py  (one node; geometry in scripts/atlas_astra_obstacle_core.py)
       - refuses to start (exit 78) without a measured, plausible mount and a physically validated calibration
       - undistorted rays, measured mount -> base_link; keeps floor+4 cm .. rover-top band, 0.35-3.0 m, +-30 deg
       - invalid depth (0/NaN/inf) never becomes an obstacle or free space
       - publishes ONLY fresh (<= 0.5 s) frames with >= 30 % valid pixels; otherwise NOTHING (never all-clear)
       - status 1 Hz on /astra/obstacle_scan_status: OK | STALE | BLINDED | NO_FRAMES | BAD_FRAME
  -> /astra/obstacle_scan (LaserScan, base_link, original capture stamp)
  -> domain_bridge (ONLY this LaserScan) -> domain 0 -> Nav2 local costmap SEPARATE "astra_layer"
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
| `config/astra_obstacles.yaml` | Mount (MEASURE placeholders), band, ranges, stale/blind thresholds, rate cap |
| `config/astra_obstacles_bridge.yaml` | Bridges `/astra/obstacle_scan` only |
| `config/nav2_astra_obstacles_LIVE_SNIPPET.yaml` | Separate `astra_layer` (G5 only) |
| `tools/track_a/check_nav2_merge.py` | Proves LiDAR layer/global costmap unchanged; `--write` at G5 |
| `systemd/user/atlas-astra-{obstacles,bridge}.service.in` | No `[Install]`; ExecCondition preflight gate (unit skipped, no restart loop, verified on Jetson); memory caps |
| `tests/test_track_a.py` | 25 tests (simulated data; isolated ROS domain 91) |
| `deploy/track_a/{install,verify,rollback,apply_g5}.sh` | Deployment, gate check, undo, G5 merge |

## Activation gates (each needs a real PASS and the owner's approval for that step)

| Gate | What | PASS means |
|---|---|---|
| **G1** | IR calibration (`tools/vision3d/astra_calibration_live.py`) + installation of `depth_160x120.json` | Train RMS < 0.5 px, held-out < 0.8 px, coverage >= 60 %, >= 2 tape distances within max(1 cm, 1 %), plane RMS <= 5 mm |
| **G2** | Mount measurement (below) filled into `astra_obstacles.yaml` | A box at a tape-measured spot appears at that spot in `/astra/obstacle_scan` within 3 cm |
| **G3** | `bash deploy/track_a/install.sh`, `sudo apt install ros-humble-domain-bridge`; measure the bridge's domain-0 join spike with the rover parked | Whole-Jetson CPU stays < 75 % through the join; no service restarts |
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
