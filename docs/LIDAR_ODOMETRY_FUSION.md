# ATLAS LiDAR Odometry Fusion

## Architecture

`/scan` -> RF2O -> `/lidar/odom_raw` -> ATLAS gate -> `/lidar/odom` -> shadow EKF -> `/odom/lidar_fused_candidate`

The shadow EKF also consumes wheel velocity from `/yahboom/odom` and the
configured IMU yaw-rate. It publishes no TF. The existing authoritative EKF,
`/odom`, AMCL, SLAM, Nav2, collision guard and motor control are unchanged.

RF2O is pinned to upstream commit
`313bb4c4123bcc0cc2e042f278312b19a3c46f31` from the Humble branch. Install or
repair the dependency and user services with:

```bash
bash /home/jetson/project_atlas/scripts/install_lidar_odometry.sh
```

## Safety properties

- RF2O publishes no transform, preventing duplicate `odom -> base_link` owners.
- Non-finite, out-of-order, excessive translation and excessive yaw updates are
  rejected before fusion.
- When fresh wheel and final-command evidence indicate the rover is stopped,
  the gate rebases raw RF2O drift and publishes a fixed pose with zero twist.
- Stale input stops gated publication; it cannot invent continued movement.
- LiDAR yaw is excluded from EKF fusion because a straight-run replay produced
  a false -17.6-degree yaw change. The configured IMU retains yaw-rate authority.
- The candidate has no Nav2 authority until physical commissioning passes.

## Evidence on 2026-09-25

- Twenty-second stationary check: raw RF2O drift 0.0048 m and -7.32 degrees;
  gated and fused candidate drift 0.00 m and 0.00 degrees.
- Isolated replay of an operator-measured 0.30 m straight run: RF2O translation
  0.2793 m (6.9% low). The same run's wheel odometry was 0.192 m.
- Replay included only `/scan`; no motor or joystick command topic was played.

## Promotion gate

Do not remap the candidate to `/odom` until a fresh supervised campaign passes:
stationary, 0.30 m, 1.0 m, clockwise/counter-clockwise turns, forward/reverse,
LiDAR dropout failover, and return-home repeatability. Promotion must remain a
single reversible configuration change after evidence review.
