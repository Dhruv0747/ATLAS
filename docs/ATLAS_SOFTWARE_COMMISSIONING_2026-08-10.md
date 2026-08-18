# ATLAS software commissioning — 2026-08-10

## Scope

This commissioning pass prepares the autonomy software while the rover is
stationary and charging. It does not claim that hall motion tests have passed.

## Implemented

- A single user-managed `robot_localization` EKF owns `/odom` during the soak
  test and fuses live Yahboom wheel odometry with the BNO08X IMU.
- Sensor recovery diagnoses raw wheel odometry separately and may restart the
  EKF only while the rover is stopped.
- The deterministic mode manager exposes mutually exclusive `IDLE`, `MAPPING`,
  and `LOCALIZATION` modes. Startup observes the current mode and never starts
  exploration or sends a goal by itself.
- The Mission AI supervisor is execution-enabled, but motion still requires a
  fresh deterministic preflight and explicit operator confirmation.
- Named places are persistent map-frame poses. The offline planner understands
  commands such as `save this as kitchen`, `go to kitchen`, and `come back to my
  room`. Unknown names fail closed; named-place motion requires confirmation.
- The bounded SQLite experience store records mission, safety, recovery, pose,
  and outcome events without images or audio. High-rate state changes are
  sampled to protect storage and CPU.
- The lightweight specialist-role board reports Mission Director, Safety,
  Driver, Mode Manager, Localization, Perception, Recovery, Experience, and
  Voice health on `/atlas/agent_team/state`.
- Dashboard system telemetry now includes Mission AI, agent-team, and experience
  memory status. Camera, thermal, BME680, and other essential telemetry remain
  enabled.
- Dashboard and recovery health polling were consolidated/cached to reduce
  avoidable subprocess work. No essential service was disabled.

## Safety architecture

One planner chooses only allowlisted high-level tools. Deterministic ROS roles
own safety, localization, navigation, recovery, and verification. Internet
research is not part of the motion loop and is allowed only while safely
stopped, with human review before any learned change is promoted.

## Privileged migration still required before reboot

The obsolete system-level `atlas-ekf.service` is still enabled but inactive.
It must be disabled once so it cannot race the commissioned user-level EKF at
the next boot:

```bash
sudo bash /home/jetson/project_atlas/scripts/finalize_atlas_ekf_root.sh
systemctl --user enable atlas-ekf.service
```

## Verification gates still open

1. Finish the stationary 30-minute EKF/TF/sensor soak with zero stale samples
   and exactly one `/odom` publisher.
2. Reboot after the privileged EKF migration and re-check publisher ownership.
3. With adequate battery and a clear hall, test controlled motion, mapping,
   obstacle recovery, automatic map save/load, named-place navigation, and
   return-home accuracy.
4. Commit and publish the autonomy implementation only after these physical
   tests pass.
