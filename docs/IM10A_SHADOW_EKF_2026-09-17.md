# IM10A isolated EKF result

Bounded stationary comparison completed on Jetson. Source deployed only to
`/home/jetson/project-atlas-migration`; not installed as an autostart service.
Results: `/home/jetson/project-atlas-migration/im10a_shadow_pn33wdzc/`.

- 634 accepted gyro samples, zero rejected (includes discovery/preflight).
- 603 wheel messages received; not proof that the faulty M4 encoder works.
- Wheel-only output: 551 samples, all finite, zero displacement/yaw change.
- Wheel-plus-gyro output: 556 samples, all finite, zero displacement/yaw change.
- Final IMU/wheel reception ages: 0.096 / 0.031 seconds.
- Live EKF configuration byte-for-byte unchanged.
- Runtime parameters verified `publish_tf=false` on both shadow filters and
  only yaw angular velocity selected in `imu0_config`.
- `/odom` had exactly one publisher, the original `/ekf_filter_node`.
- Two unit tests passed; invalid, stale, future and repeated inputs rejected.
- Baseline log contained one update-rate warning: 0.312 seconds. The fused
  log contained only the shutdown message. Load/timing qualification remains.
- Both test processes exited; live EKF, IMU and remote remained active.
- Manual-only mux environment preserved. No motion or steering commands.

Interpretation: stationary isolated integration passed. Dynamic benefit,
turn accuracy, sensor-loss behavior of a production fusion setup and load
reliability have not been established. Covariance is provisional. Magnetic
heading, Euler orientation, acceleration and historical bias were excluded.
Authoritative EKF still uses its existing wheel input only. M4 replacement
and controlled dynamic comparison are required before autonomous validation.
