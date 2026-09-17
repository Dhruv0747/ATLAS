# IM10A stationary verification — awaiting replacement M4

Read-only live ROS subscriptions on 2026-09-17. No motor commands, serial
reconfiguration, service restarts or EKF parameter changes were issued.

## Measurements

- Duration: 60.060 s; 603 samples; 10.026 Hz.
- Maximum reception gap: 0.1282 s.
- Maximum ROS message delivery age: 0.0379 s (receipt-time sensor timestamps;
  this does not measure internal sensor latency).
- Non-increasing timestamps: 0. Reported checksum errors: 0.
- Mean acceleration magnitude: 9.7581 m/s².
- Gyro means X/Y/Z: -0.00034449 / -0.00002827 / 0 rad/s.
- Gyro standard deviations X/Y/Z: 0.0019832 / 0.0016194 / 0 rad/s.
- Integrated reported Z gyro: 0 degrees.
- Sensor Euler yaw net change: +0.01648 degrees.
- IM10A service active, NRestarts=0; EKF service active.
- Four software tests passed: mounting rotation arithmetic, bias arithmetic,
  orientation exclusion, and absence of an enabled EKF IMU input.

## Interpretation and gate

This supports short-term stationary delivery and stability only. Exact zero
reported stationary Z rate does not establish zero physical bias, resolution,
or accurate response during rotation. Euler yaw is diagnostic, not ground truth.

Fusion remains disabled; saved bias remains disabled; magnetic heading remains
excluded. Existing EKF continues wheel odometry. Manual-only mux mode remains
enabled, preserving the remote and its stop mechanism.

The unresolved gate is a physically measured left/right rotation with raw gyro
timestamps and independent angle reference. Prior dashboard-based turn capture
had Euler/gyro disagreement and cannot validate gyro scale. M4 is not necessary
for a stationary IMU check, but full powered rover odometry/fusion validation
requires the replacement encoder to be commissioned first. Do not enable
autonomous driving or claim navigation qualification from this report.
