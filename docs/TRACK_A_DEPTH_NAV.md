# Track A: Astra depth for navigation obstacles (STAGED, inactive)

Goal: the rover sees obstacles the 2D LiDAR misses, such as table tops, chair seats, low boxes and anything above or
below the LiDAR's scan plane. That makes it safer to drive further.

## Design (2026-11-06)

```
Astra (private ROS domain 77, depth only 160x120 @15 fps)
  -> atlas_astra_calibrated_info   (validated K/D, refuses without physical validation)
  -> depth_image_proc PointCloudXyz -> /astra/obstacle_points
  -> pointcloud_to_laserscan (floor+4 cm .. rover top+5 cm, in base_link, 0.35-3.0 m) -> /astra/obstacle_scan
  -> domain_bridge (ONLY this LaserScan) -> domain 0 -> Nav2 local costmap (added next to the LiDAR, never replacing it)
```

Why this shape: the Astra joining the production domain spiked CPU 65 -> 92 % (21 Oct). Depth images stay private,
and only a small scan crosses over. Measured 5 Nov: the Astra depth stream costs about 1 % of the Jetson.

## Staged files (nothing installed, enabled or running)

| File | Purpose |
|---|---|
| `scripts/atlas_astra_calibrated_info.py` | Republishes validated CameraInfo; exits 78 without validation |
| `launch/atlas_astra_obstacles.launch.py` | The chain above; refuses while any MEASURE value is null or the domain is not 77 |
| `config/astra_obstacles.yaml` | Mount TF and scan band; **MEASURE placeholders** |
| `config/astra_obstacles_bridge.yaml` | Bridges `/astra/obstacle_scan` only |
| `systemd/user/atlas-astra-obstacles.service.in`, `atlas-astra-bridge.service.in` | No `[Install]`, so never at boot |
| `config/nav2_astra_obstacles_LIVE_SNIPPET.yaml` | Final costmap source, applied only at step G5 |

## Activation gates (each needs a real PASS and the owner's approval for that step)

| Gate | What | PASS means |
|---|---|---|
| **G1** | IR calibration (`tools/vision3d/astra_calibration_live.py`) + installation of `depth_160x120.json` | Train RMS < 0.5 px, held-out < 0.8 px, coverage >= 60 %, >= 2 tape distances within max(1 cm, 1 %), plane RMS <= 5 mm |
| **G2** | Mount measurement (below) filled into `astra_obstacles.yaml` | A box at a tape-measured spot appears at that spot in `/astra/obstacle_scan` within 3 cm |
| **G3** | apt install `ros-humble-depth-image-proc ros-humble-pointcloud-to-laserscan ros-humble-domain-bridge`; measure the bridge's domain-0 join spike with the rover parked | Whole-Jetson CPU stays < 75 % through the join; no service restarts |
| **G4** | Shadow: obstacle scan visible on the dashboard or in Foxglove, **not** in the costmap; walk objects in front of the parked rover | Table edge, chair seat and low box all appear; no phantom obstacles in 10 minutes of an empty view |
| **G5** | Live: apply the LIVE snippet; slow supervised driving, E-STOP in hand | Stops or plans around a table top the LiDAR misses; no phantom stops on an open floor |

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
