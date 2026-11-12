# M3 step 1: RTAB-Map parked test (2026-11-12 11:31-11:37, rover parked, E-STOP latched)

RTAB-Map 0.23.13 was installed by the owner (`ros-humble-rtabmap-ros`). Tools are in `project_atlas/tools/m3/`:
* `m3_rtabmap.launch.py`
* `m3_odom_bridge.yaml`
* `m3_parked_test.sh`: pauses, maps, measures, then restores via a trap.

## Architecture

* Everything runs in the Astra's private ROS domain 77. Track A's driver supplies the depth.
* `rtabmap_util/point_cloud_xyz` turns depth into a 3D point cloud at 0.35-3.0 m, with a 3 cm voxel.
* `rtabmap_slam/rtabmap` builds the map:
  * ICP registration, scan-cloud mode;
  * external odometry from the EKF (`/odom`, `odom -> base_link`);
  * 1 Hz updates.
* A second, receive-only domain_bridge copies only `/odom` and `/tf` from domain 0 into 77. Nothing goes back to 0.
* The Astra has no usable RGB in this setup, so RTAB-Map runs without images. Image-based loop closure is off;
  space-proximity ICP is used instead.
* "3D mapping mode" (owner option B, 2026-11-05) pauses 11 user units and restores them on exit:
  * atlas-voice-companion, atlas-localization-monitor
  * atlas-lidar-odom, atlas-lidar-odom-gate, atlas-ekf-lidar-candidate
  * atlas-camera-joystick, atlas-gnss
  * atlas-agent-supervisor, atlas-local-llm, atlas-visual-cloud-agent
  * atlas-camera (IMX708)
* atlas-feature-on-demand is never stopped.

## Results (2 runs)

| Measure | Result |
|---|---|
| Pause and restore | 11/11 paused, **11/11 restored** both runs ("not active: none") |
| Whole-Jetson CPU | baseline 66-68 % to 65-67 % right after pausing; **61 % while mapping** (40-70 s windows) |
| Process cost while parked | rtabmap 0.83 %, depth->cloud 0.83 %, odom/tf bridge 0.16 % of the 6-core Jetson |
| RAM | rtabmap 180-189 MB, cloud node 143-146 MB |
| Rates | depth cloud 14.2-14.3 Hz; RTAB-Map 1 Hz, 0.02-0.04 s per update |
| Temperature | Tj 63.8 C |
| Data | run 2 database: 58 snapshots (about 20 KB each, 2.2 MB) |
| First snapshot | 3,808 points; base_link x 0.85..2.62, y -0.94..1.03, z -0.24..1.21 m |
| Sensor transform | stored at (0.21, 0, 0.23) m, matching the taped mount |

Snapshot export: `maps3d/m3_parked_20261112-113452_node1.ply`.

Notes:
* Run 1 kept no snapshot (`Mem/NotLinkedNodesKept=false` discards the only, unlinked node when parked). Now
  `true` by default.
* `rtabmap-export` refuses a graph with 0 links ("no odometry poses"); a parked rover never links snapshots. Expected
  to work after a mapping drive. The parked snapshot was decoded directly from the database instead.
* Pausing the extras saved less than the 2026-11-05 estimate (that baseline was about 61 %, now 66-68 % with Nav2
  fully active and Track A). RTAB-Map's moving cost (ICP per new node) is not yet measured.
* Points below the floor (z down to -0.24 m) are the known glossy-floor mirror image. Filter z < -0.05 m in maps.

## Next: step 2, mapping drive (owner drives by hand, slowly, E-STOP in reach)

Mapping mode on, RTAB-Map with `M3_KEEP_UNLINKED=false`, 3-5 min around the room, then export and restore. Measure
CPU while moving.

## Dashboard "3D map" window (2026-11-12 11:46-12:00)

* Feed `scripts/atlas_map3d_live.py`:
  * runs in the M3 mapping launch only (domain 77, read-only);
  * every 3 s, reads RTAB-Map's `/cloud_map`, removes floor-mirror points (z < -0.05 m) and points above 2.5 m,
    keeps one point per 5 cm voxel, at most 10,000 points;
  * writes `web/v2/map3d_live.txt` (JSON, integer cm) with the rover position from `/odom`;
  * rewrites every tick during a session, so the window can tell that mapping is live even when the map is
    unchanged.
* Home card `cardMap3d` (index.html + home-cards.js; backups `*.before-map3d-card-20261112-114600`):
  * points coloured by height (blue floor to red 1.5 m+), rover triangle;
  * slow auto-rotation, drag to rotate, wheel to zoom; no external libraries;
  * states: Off / Mapping (sequence seen changing within 12 s) / Last map;
  * link to the stored-maps page.
* Verified: window "Last map" before the run, **"Mapping · Live · 971 of 1,138 points"** during it, back to "Last map"
  after.
* Test tool fix: the M3 launch survived SIGINT while its feed kept respawning (two leftover launches made the window
  show "Mapping" falsely).
  * Leftovers killed.
  * The script now stops the whole process group (INT, wait 15 s, TERM, KILL), also in the trap.
  * The feed no longer respawns.
  * Re-verified: "mapping launch fully stopped after 2 s", "restored: 11 units, not active: none", "leftover mapping
    processes: 0", live file unchanged afterwards.
* 35/35 tests (new: feed point reduction).
