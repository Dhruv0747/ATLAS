# Archived scripts: do not run

These scripts are kept for history only. They were moved here on 2026-10-10
and are unchanged.

Both publish `geometry_msgs/Twist` straight to `/cmd_vel`. That topic is the
motor owner's input, *after* the command mux. Running either one while the
base driver is up therefore drives the wheels around every software safety
layer:

- the latched remote stop (Xbox B);
- `ATLAS_MANUAL_ONLY`;
- the stale-command watchdog;
- the encoder, localization and ultrasonic autonomy guards.

| Script | Commands it sends |
| --- | --- |
| `verify_metric_wheels_lifted.py` | about 0.8 s of forward motion |
| `verify_steering_lifted.py` | steering sweeps |

Lifted-wheel checks now go through the commissioning console. It requires
the motor owner's lease, a latched stop and operator confirmation. Port a
check there rather than restoring these scripts. If one must be run, review
it against the current wheel mapping and steering limits first, lift all
wheels, and keep the physical power switch within reach.
