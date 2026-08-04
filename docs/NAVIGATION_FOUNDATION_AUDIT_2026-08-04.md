# Navigation foundation audit - 2026-08-04

## Scope

Read-only audit of the live ATLAS telemetry and GitHub source. No wheel, steering, navigation or autonomous command was issued.

## Live observations

- LiDAR was live on `laser_frame`, reporting 186/360 points and a nearest return of approximately 0.319 m.
- Ultrasonic sensing was live: front 964 mm, left 668 mm and right 392 mm at the sample time.
- Steering was centred at 90 degrees front and rear; commanded motor speed was zero.
- Encoder counters were highly asymmetric while stopped: M1 23706, M2 2, M3 1 and M4 -1.
- Published odometry was stationary at approximately x=2.165 m, y=-1.032 m.
- IMU telemetry reported roll 83.54 degrees, pitch -42.51 degrees and heading 282.08 degrees. Physical mounting/orientation must be checked before fusion.

## Source findings

### Odometry is not calibrated wheel odometry

`project_atlas/scripts/yahboom_base.py` uses commanded linear/angular velocity to integrate odometry only when recent encoder change confirms motion. The encoder counts do not currently determine measured travel distance or measured yaw. This prevents quantitative odometry calibration and makes localization dependent on command assumptions.

### EKF is absent

No active `robot_localization`/`ekf_node` configuration was found in the clean live source snapshot. Wheel odometry and BNO08X IMU are therefore not fused as required by the master manual.

### TF definitions are inconsistent

- The URDF defines `base_footprint -> base_link -> laser_frame`, with `laser_frame` at z=0.18 m and zero rotation.
- `tortoisebot_all.launch.py` separately publishes `base_footprint -> laser_frame` at z=0.18 m with roll=pi.
- `start_laser_tf_pi.sh` contains the same separate roll=pi transform.
- The motor node publishes `odom -> base_link`, while SLAM is configured with `base_frame=base_footprint`.

These duplicate/inconsistent parentage and orientation choices must be resolved from measured physical mounting before further Nav2 tuning.

### Stale ROS distribution reference

`project_atlas/services-disabled/rover-frame-bridge.service` references `/opt/ros/jazzy` even though ATLAS runs ROS 2 Humble. The service is disabled but must not be re-enabled in this form.

## Required correction order

1. Lift all four drive wheels and record the start/end counter of each encoder during short individual forward tests.
2. Establish each encoder's wheel mapping, sign, counts per revolution and rollover behaviour.
3. Measure actual wheel diameter and effective steering/wheelbase geometry.
4. Replace command-integrated distance with calibrated encoder-derived odometry while preserving the stale-feedback safety gate.
5. Measure the physical IMU and LiDAR axes/mounting offsets.
6. Create one authoritative URDF TF tree and remove duplicate static publishers.
7. Align odometry, SLAM and Nav2 on a consistent base frame.
8. Add and tune `robot_localization` EKF using measured wheel odometry and validated BNO08X IMU data.
9. Perform a measured straight-line test, rotation test and closed-loop return test.
10. Only after those tests pass, resume SLAM/Nav2/autonomous exploration tuning.

## Safety gate

Steps 1-4 require explicit confirmation that all four wheels are clear of the ground. Ground navigation tests require a clear test area and an operator at the physical emergency stop.

## Lifted-wheel encoder test results

The operator confirmed all four wheels were lifted and clear. Each motor was commanded independently for 0.50 seconds at +60 PWM, stopped, and then tested at -60 PWM. The normal base telemetry service was stopped only while the test owned `/dev/yahboom` and was automatically restarted afterward. Final motor command was verified as zero.

| Commanded motor | Forward encoder delta | Reverse encoder delta | Assessment |
|---|---:|---:|---|
| M1 | `(2792, 0, 0, 0)` | `(-2774, 0, 0, 0)` | M1 encoder is responsive and directionally consistent |
| M2 | `(350, 2, 0, 0)` | `(-260, -1, 0, 0)` | M1 change is residual coast; M2 count is effectively inactive |
| M3 | `(0, 0, 0, 0)` | `(0, 0, 0, 0)` | No encoder response |
| M4 | `(0, 0, -1, 1)` | `(0, 0, 1, 0)` | Only single-count noise; no usable encoder response |

M1 produced closely matched forward/reverse magnitudes, confirming the board protocol and M1 decoder work. M2-M4 cannot currently support odometry. Before implementing encoder-derived odometry, inspect the physical encoder power/signal wiring, connector mapping, motor/encoder compatibility and controller input channels for those three wheels. Software scaling cannot repair absent counts.

### Operator-observed motor confirmation

A second forward observation test used 50 PWM, a 1.0-second pulse per motor and a 2.0-second stopped gap in the order M1, M2, M3, M4. The operator visually confirmed that all four physical motors moved. Encoder deltas were M1 `+4160`, M2 `0`, M3 `-1` and M4 `0`. This isolates the defect to encoder sensing/wiring/controller inputs rather than motor power outputs. No further motor test is required until the M2-M4 encoder hardware paths have been inspected.

### Cold-boot confirmation

After a complete physical power cycle, all counters restarted at zero and the ordered 50 PWM/1.0-second test was repeated. Deltas were M1 `+4408`, M2 `0`, M3 `0` and M4 `+1`. The normal service restarted active and final motor speed was zero. Rebooting does not restore M2-M4 feedback; stale software state and accumulated counters are ruled out.
