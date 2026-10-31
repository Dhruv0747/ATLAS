# Named-place dry-run safety correction — 2026-10-31

Scope: repository-only correction of `--verify-place --dry-run`. No deployment,
Jetson execution, pose publication, service restart or Recovery restoration.

The existing matcher runs once in a killable child. The parent reuses
`snapshot_benchmark_once` and `stationary_gate` for independent one-second HTTP
safety observations and resource counters. HTTP absence or timeout fails closed.
CPU >=75%, RAM >=80%, temperature >=70 C, released E-STOP, nonzero commands,
nonstationary encoders or stale/malformed telemetry abort the attempt. Counter
intervals include preflight request and process-launch overhead; they are not
reset to hide startup work.

The same seeder ROS node validates scan/odometry timestamps and scan-time TF,
then continues receiving while matching runs. No second safety ROS node is
created. Sensor timestamps/arrivals must be within one second; duplicate,
backward or future stamps are rejected. Invalid frame IDs, nonfinite geometry,
non-unit TF rotations and moving odometry fail closed. Parent heartbeat checks
terminate matching when this observation stops. The existing 0.06 uniqueness
threshold is unchanged. UNKNOWN/ambiguity never retries or publishes a pose.

Bounds: worker OS alarm 30 seconds including initialization and processing;
parent overall deadline 32 seconds including preflight, followed by existing
bounded child termination/kill cleanup. Parent death kills the child on Linux.
One-second polling is discrete monitoring, not instantaneous protection.
The bounded HTTP request is 0.5 seconds; scheduling delays are rejected.

Validation: 14 focused tests PASS on Ubuntu WSL, including the real existing
window helper, six resource/safety rejection cases, sensor/TF invalidity,
no-seeding paths, one-attempt behavior and a native Linux OS-alarm test against
a blocked fake worker. No ROS node or hardware was started by these tests.

GO for separate controlled deployment/dry-run approval, conditional on exact
live-file comparison, utility dependency/hash verification and fresh physical
and safety preflight. NO-GO for running the unchanged live version. Jetson ROS
callback scheduling, TF availability and resource headroom remain unverified.
A test pass does not identify ATLAS's position or validate physical reliability.
Recovery remains STOPPED; its separate incident remains OPEN.
