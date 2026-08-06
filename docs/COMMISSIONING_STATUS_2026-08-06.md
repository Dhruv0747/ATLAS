# Project ATLAS commissioning status - 2026-08-06

## Outcome

Project ATLAS has completed its Jetson Orin Nano Super migration and primary
manual-drive, encoder-odometry, SLAM, Nav2, autonomous-exploration, map-save and
reboot/autostart commissioning sequence.

## Verified hardware geometry

| Item | Verified value |
|---|---:|
| Rover body | 0.50 m long x 0.36 m wide |
| Nav2 footprint | `[[0.25,0.18],[0.25,-0.18],[-0.25,-0.18],[-0.25,0.18]]` |
| Wheel centre spacing, front to rear | 0.367 m |
| Wheel diameter | 0.125 m |
| LiDAR centre to front chassis edge | 0.30 m |
| LiDAR x relative to chassis centre | -0.05 m |
| LiDAR z | 0.18 m |

## Motor and encoder mapping

| Channel | Physical wheel | Forward motor polarity | Counts/revolution |
|---|---|---:|---:|
| M1 | Front-right | Positive | 4048.7 |
| M2 | Front-left | Negative | 3300.6 |
| M3 | Back-right | Negative | 4080.1 |
| M4 | Back-left | Positive | 2697.8 |

All four motor and encoder channels passed forward/reverse lifted-wheel tests.
Ground distance calibration was subsequently verified with measured short moves.

## Navigation configuration

- ROS 2 Humble on Ubuntu 22.04, Jetson Orin Nano Super 8GB.
- Rectangular 0.50 x 0.36 m footprint in global and local costmaps.
- Inflation radius 0.28 m; cost scaling factor 15.0.
- Obstacle minimum range 0.05 m.
- Encoder-distance odometry is published on `/yahboom/odom`.
- Robot Localization EKF owns filtered `/odom` and the odom transform.
- LiDAR static transform: x=-0.05 m, y=0, z=0.18 m, yaw=pi.
- Nav2 uses `atlas_ackermann_fail_stop.xml`, a one-shot ComputePath/FollowPath
  tree that fails safely without repeated recovery movement.
- Explore Lite holds one active frontier goal and requests guarded recovery only
  after consecutive genuine Nav2 aborts.

## Final verification evidence

| Test | Result |
|---|---|
| Xbox manual drive and command mux | Passed |
| Four motor outputs and encoders | Passed |
| Measured 20 cm and 50 cm movement | Passed |
| Physical return to home | Passed; final pose within about 4 cm |
| LiDAR self-filter and footprint alignment | Passed at clear start position |
| Bounded autonomous mapping | Passed |
| Collision prediction and abort | Passed |
| Automatic mapping safety stop | Passed |
| Automatic map save | Passed |
| Saved map | 82 x 195 cells, 0.05 m/pixel |
| Reboot/autostart | Passed for 15 required services |
| Unexpected autonomous motion after boot | None; Explore Lite inactive |

## Operational safety

The command priority is REMOTE, WEB, FOXGLOVE, then NAV2. A stale-source
watchdog publishes a stop and releases the source. Explore Lite is deliberately
not enabled at boot. Always retain access to the physical emergency stop during
ground navigation and mapping.

## Remaining non-blocking work

- Run a longer full-room endurance map when a suitable clear area is available.
- Continue tuning tight-corner frontier selection from additional field data.
- Complete the CrowPanel wireless controller as a separate project phase.
- Periodically recheck encoder calibration, wheel freedom, LiDAR mounting,
  battery health and sensor wiring after mechanical changes.
