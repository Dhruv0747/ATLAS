# Encoder safety validation — 2026-09-10

## Stationary baseline

- Main BMS: 100%, 14.2 V.
- All four encoder topics fresh; 15-second stationary deltas were `[0, 0, 0, 0]`.
- Stationary Yahboom IMU heading change was 0.052 degrees in 15 seconds.
- `/atlas/encoder_health`: `READY`, no faults, scale 1.0.
- Core motor, mux, EKF, LiDAR, localization, recovery, sensor-hub, radar, and
  dashboard services were active.

## Controlled ground movement

- Forward target 0.10 m at 0.10 m/s: stopped safely at 0.189 m measured travel.
- Reverse target 0.10 m at -0.10 m/s: stopped safely at 0.165 m measured travel.
- Return recording:
  `/home/jetson/project_atlas/bags/encoder_guard_return_20260910_142345`
- Recording contains 463 messages over 4.27 seconds, including all four
  encoders, IMU, raw/EKF odometry, LiDAR, command input/output, and encoder
  health.
- Recorded encoder deltas were M1 -1360, M2 +1529, M3 +1380, M4 -1533.
- Encoder health was only `HEALTHY` while moving and `READY` while stopped.

The repeatable excess travel is a low-speed actuation/stopping limitation, not
lost encoder telemetry. ATLAS maps every nonzero motion request to the verified
72-PWM breakaway floor; at that floor the recorded rover speed and coast distance
are too large for an exact 0.10 m stop. Do not hide this result by changing
encoder scale. Treat low-speed stopping control as the next navigation issue.

## Shared-link failure and recovery

- Stopped `rover-base-telemetry.service` while ATLAS was stationary.
- Recovery detected stale encoder health in 3.1 seconds.
- Exactly one bounded restart was issued (`attempt 1/1`).
- Encoder health passed its validation interval and recovery reported healthy.
- No motor command was issued during this recovery test.

## Autonomous stop guard

- Stopped the motor service so physical motion was impossible.
- Injected a nonzero `/cmd_vel_nav` request.
- Every observed `/cmd_vel` output was zero.
- Mux logged `AUTONOMY STOP: ENCODER ... feedback unavailable`.
- Restored the motor service; encoder health returned to `READY` with no faults.

## Remaining validation

1. Bench simulation or physical channel isolation for the one-wheel degraded
   case (50% speed, maximum five seconds).
2. Correct/compensate minimum-speed stopping behavior with one isolated change.
3. Repeat controlled ground distance and return-home tests.
4. Continue the room-to-room reliability campaign only after stopping accuracy
   is acceptable.
