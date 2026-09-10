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

The repeatable excess travel was a low-speed actuation/stopping limitation, not
lost encoder telemetry. ATLAS had mapped every nonzero motion request to the
90-PWM manual breakaway floor; at that power the recorded rover speed and coast
distance were too large for an exact 0.10 m stop. Encoder scale was not changed
to hide the result; manual and autonomous power floors were separated instead.

### Autonomous low-speed calibration

- Separated the manual and autonomous motor floors. Manual remote driving keeps
  its commissioned 90-PWM floor; Web/Nav2/recovery approach motion now uses 60.
- At 72 PWM, 0.10 m tests stopped at 0.142 m forward and 0.131 m reverse.
- At 60 PWM, 0.10 m tests stopped at 0.127 m forward and 0.131 m reverse.
- A 50-PWM comparison reached 0.104--0.106 m in short tests but then stalled in
  a longer loaded test and triggered the M3 encoder guard. It was rejected.
- After restoring 60 PWM and requalifying all encoders, the 0.20 m out-and-back
  test stopped at 0.234 m forward and 0.219 m reverse. Both legs passed and
  encoder health returned to `READY`.
- Encoder scaling was not changed. The accepted result improves close-range
  control while retaining reliable loaded traction.

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

## One-wheel degraded operation

- Held the physical motor service offline and stopped automatic recovery, so
  the test could not move the rover.
- Injected a simulated `M2_FRONT_LEFT` encoder fault with state `DEGRADED` and
  requested 0.10 m/s through the isolated recovery command channel.
- The recorded mux output contained 45 samples at exactly 0.05 m/s and one
  final zero sample. This proves the required 50% command limit and stale-source
  stop behavior.
- Recording: `/tmp/encoder_single_fault_bag` on the Jetson (124 messages over
  5.68 seconds).
- The ROS CLI graph initially missed command topics. Restarting the ROS CLI
  daemon restored discovery; the running ATLAS ROS nodes themselves had not
  failed.
- Production motor and sensor-recovery services were restored after the test.
  Encoder health returned to `READY` with four accepted channels.

## Remaining validation

1. Repeat Nav2 return-home accuracy from a saved pose.
2. Continue the room-to-room mapping and recovery reliability campaign.
