# Sensor-recovery idle CPU optimization — 2026-10-04

## Scope

`atlas_sensor_recovery.py` was observed using roughly 20% of one CPU core while
ATLAS was stopped. The node subscribed to several large or high-rate streams,
including compressed camera images, LiDAR scans, both odometry streams, and
IMU data. For those streams it used no message fields: it only recorded the
arrival time and the fact that data had arrived.

## Bounded change

Freshness-only subscriptions now request serialized ROS messages (`raw=True`).
This avoids constructing full Python message object trees solely to refresh a
timestamp. The callback still runs for every received message and updates the
same monotonic `last_seen` value, so stale-message detection retains its exact
source cadence and thresholds.

The raw policy applies only to:

- LiDAR `/scan`
- compressed camera frames
- primary IMU
- fused and wheel odometry
- the diagnostic M1 encoder stream
- the latched map

Status-bearing radar, ultrasonic, thermal, ambient, BMS, cellular, and encoder
health messages remain decoded. GNSS also remains decoded because its fix
status is classified. No topic, message type, QoS profile, timer, threshold,
systemd service, restart budget, stop guard, or actuator authority changed.

## Verification and deployment gate

Focused offline tests must confirm:

1. only the explicitly freshness-only channels request raw transport;
2. a serialized arrival updates freshness exactly as before;
3. structured fault parsing, stale detection, bounded attempts, and the motor
   restart stop/latch guards still pass their existing regression tests;
4. the script compiles without importing robot hardware.

The reviewed script was deployed while ATLAS was stationary and stop-latched.
The service remained active with zero restarts; LiDAR, camera graph health,
IMU, odometry, encoder health, radar, ultrasonic, thermal, ambient, BMS, and
cellular ages remained fresh. Process CPU fell from roughly 20.0% to 15.3% of
one core in the settled sample. Command velocity stayed zero and no recovery
action was triggered by the deployment. The rollback copy is
`data/deploy_backups/20261004_cpu_sensor_recovery/atlas_sensor_recovery.py.before`.
