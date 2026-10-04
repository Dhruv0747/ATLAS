# Yahboom diagnostic publication cadence — 2026-10-04

## Problem and boundary

With ATLAS stationary under the full workload, `yahboom_base.py` used about
31% of one CPU core. Its 10 Hz board-state callback published more than forty
ROS messages per second group. Navigation and safety require 10 Hz raw encoder,
IMU, wheel-odometry, encoder-health, and motor-owner processing, but the legacy
dashboard wheel/motor summaries do not.

This change is intentionally limited to ROS publication cadence. It does not
change serial polling, encoder selection, odometry integration, IMU sampling,
motor writes, steering writes, the 100 ms motor keepalive, the 100 ms
board-state callback, command deadman, E-stop priority, topics, message types,
QoS, or frame names.

## Change

The following existing diagnostic topics are now emitted at 2 Hz while their
values continue to be calculated from every 10 Hz board sample:

- `/yahboom/motion/vx`, `/yahboom/motion/vy`, `/yahboom/motion/vz`
- the four `/yahboom/wheel/*/rpm` topics
- the four `/yahboom/wheel/*/speed_mps` topics
- the four `/yahboom/wheel/*/distance_m` topics
- `/motor/front_left`, `/motor/front_right`, `/motor/rear_left`,
  `/motor/rear_right`, `/motors/left`, `/motors/right`, and `/motor_speed`

This removes up to 176 redundant publications per second. A delayed executor
callback emits one current update and never replays a catch-up burst.

The following authority-bearing streams remain on the original 10 Hz callback:

- all four raw encoder topics
- `/yahboom/odom` and `/yahboom/odom_source`
- all raw/calibrated/system IMU topics
- `/atlas/encoder_health`
- motor keepalive and all control/safety processing

## Offline verification

- `test_yahboom_diagnostic_cadence.py`: four tests passed.
- `test_yahboom_lifted_owner.py`: eight motor-owner safety tests passed.
- Existing opposite-steering geometry checks passed.
- `yahboom_base.py` and the new test compile with Python 3.

The reviewed node was later deployed while the remote stop was latched. No
hardware-motion command was sent.

## Stationary deployment result

1. `/yahboom/odom`, `/imu/data`, all four raw encoder topics, and
   `/atlas/encoder_health` remain between 8 and 12 Hz.
2. Every topic listed in the low-rate group remains between 1.5 and 2.5 Hz and
   never exceeds 1.0 second message age.
3. The mux reports no new stale encoder fault, the base service has no restart,
   and zero motor output remains confirmed.
4. Median `yahboom_base.py` process CPU falls at least four percentage points
   from the same-load baseline, with no RAM increase above 25 MiB.
5. Jetson temperature remains below 80 C and no ROS deadline/TF fault appears.

The live check passed the interface boundary: `/yahboom/odom`, the board IMU,
raw encoders, and encoder health remained approximately 10 Hz, while
`/motor_speed` measured approximately 1.81 Hz. Encoder health was `READY`, all
four current channels were fresh, command velocity remained zero, steering
remained 90/90, and the service stayed active with zero restarts. Process CPU
settled near 23.4% versus the prior roughly 30.1% sample. The rollback file is
`data/deploy_backups/20261004_cpu_yahboom/yahboom_base.py.before`.

This result validates stationary cadence and safety continuity only. Restore
that backup and restart only `rover-base-telemetry.service` if the 10 Hz
authority streams regress in later operation.
