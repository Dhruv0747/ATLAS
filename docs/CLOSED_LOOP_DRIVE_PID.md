# ATLAS closed-loop wheel speed and yaw control

## Deployment state

The controller is implemented and integrated into the existing sole hardware
owner, `yahboom_base.py`. It is **not enabled**. Repository defaults deliberately
retain all current safety gates:

- `enabled: false`
- `hardware_commissioned: false`
- `navigation_validated: false`
- M4 encoder excluded
- measured track width unset
- wheel and yaw PID gains/feed-forward zero

Consequently, this commit does not authorize autonomous motion and does not
change proven manual/open-loop behavior. No second motor-command path or new
actuator service exists.

## Audited command path

`cmd_vel source -> command mux/safety owner -> /cmd_vel -> yahboom_base.py ->
Rosmaster.set_motor() -> Yahboom board`

`set_motor()` is raw PWM. The board library's internal PID belongs to
`set_car_motion()`, which ATLAS does not use. The new host controller therefore
does not stack two active velocity loops. The mux remains authoritative for
manual, Web, Foxglove, Nav2, recovery, watchdog and emergency-stop arbitration.

## Physical model and data sources

- Four-wheel steering (4WS), not mecanum and not differential drive.
- M1 rear-left, M2 rear-right, M3 front-left, M4 front-right.
- Wheelbase: 0.367 m; wheel diameter: 0.125 m.
- Track width is not yet measured and must not be guessed.
- Per-wheel speed is derived by the existing base driver from encoder deltas.
- `/odom` angular Z is the authoritative fused yaw-rate feedback. The existing
  EKF uses corrected IM10A gyro Z; magnetic heading remains excluded.
- Existing counts/revolution predate final motor replacement and must be
  recommissioned per wheel.

## Controller architecture

The hardware-independent core is `scripts/atlas_closed_loop_control.py`.

- Per-wheel bounded P/I/D with feed-forward and static-friction term.
- Output saturation, output slew limit, filtered derivative, conditional
  anti-windup, stop reset and direction-reversal reset.
- Symmetric counter-steer 4WS wheel targets preserve inside/outside speed ratio.
- Pure lateral and spin-in-place commands fail closed.
- Bounded yaw-rate correction adjusts steering only when its configured mode is
  enabled and feedback is fresh.
- State machine: DISABLED, COMMISSIONING, MANUAL, AUTONOMOUS, FAULT_STOP.
- Re-entry from a latched fault requires an explicit reset while command is zero.

All safety and tuning values are in `config/drive_pid.yaml`.

## Fail-closed conditions

The active controller produces zero output and latches FAULT_STOP for emergency
stop, motor-link loss, ownership timeout, command timeout, encoder timeout,
invalid/nonfinite values, implausible encoder jumps, reversed feedback, frozen
feedback, missing required M4 feedback, stale required yaw data, unsupported
lateral commands or unvalidated autonomous operation. Commissioning mode always
inhibits traction.

## Diagnostics

`/atlas/drive_pid/diagnostics` publishes JSON containing:

- state, active/inhibited/fault reason;
- commanded/measured yaw rate and steering correction;
- per-wheel target and measured speed, error, P/I/D/feed-forward terms, final
  output, saturation/anti-windup flags, encoder validity and age.

The Web dashboard shows a DRIVE PID health item and touch/click detail view.

## Staged commissioning

The commissioning recorder never commands a motor:

```bash
cd /home/jetson/project_atlas
python3 scripts/atlas_pid_commissioning.py --stage static
python3 scripts/atlas_pid_commissioning.py --stage simulation
```

Powered stages require the operator to prepare the rover and provide the exact
confirmation plus measured observation. Evidence is written under
`commissioning/drive_pid/` and must be reviewed before changing a later gate.

1. `static`: code/configuration checks with traction power off.
2. `simulation`: simulated encoder, IMU, ownership and fault tests.
3. `lifted_direction`: wheel identity and motor direction.
4. `encoder_counts`: direction/sign and counts per revolution, each wheel.
5. `one_wheel_response`: feed-forward/deadband and PID, one wheel at a time.
6. `lifted_four_wheel`: low-speed combined response.
7. `ground_straight`: bounded straight-line test.
8. `distance_forward_reverse`: measured forward/reverse distance.
9. `measured_turns`: measured left/right curvature and safe recentering.
10. `stop_timeout`: emergency-stop, stale command and stopping distance.
11. `manual_yaw_tuning`: bounded correction after wheel-speed stability.
12. `nav2_low_speed`: only after every preceding gate passes.

Example evidence record (this still does not move ATLAS):

```bash
python3 scripts/atlas_pid_commissioning.py \
  --stage lifted_direction \
  --confirm "LIFTED CLEAR ESTOP READY" \
  --observation "M1 forward; measured sign negative; counts recorded separately"
```

Do not set `enabled`, `hardware_commissioned`, `navigation_validated`, remove M4
from exclusions, enter a track width, or tune gains without corresponding
physical evidence. Tune one value at a time and keep only measured improvements.

## Verification matrix

The offline suite covers disabled defaults, no lateral/mecanum motion, 4WS
inside/outside targets, forward/reverse, missing geometry, every encoder dropout,
stale/frozen/reversed/jump feedback, communication and command timeouts, E-stop,
owner transitions, restart with no stale command, saturation, anti-windup,
steering-alignment gating, commissioning inhibition and diagnostic completeness.

Physical proof still required: measured track width; fresh M1–M4 encoder counts;
M4 repair; counts/revolution after motor replacements; polarity; lifted direction;
low-speed response; stopping distance; E-stop; sustained forward/reverse; turning;
reboot recovery; and low-battery behavior.

## Before/after verification result

| Area | Before | After this change |
|---|---|---|
| Low-level traction | Open-loop PWM through `set_motor()` | Same active behavior; closed-loop implementation present but disabled |
| Wheel feedback control | Encoders used for odometry/health only | Independent bounded PID design for M1–M4, gated from hardware |
| Yaw correction | Nav2/high-level steering only | Bounded EKF-yaw-rate correction implemented, zero-gain and disabled |
| Fault handling | Existing mux, stop latch and watchdogs | Existing safety retained plus controller-local latched fault reasons |
| Diagnostics | Encoder health/count/speed | Per-wheel target/measured/error/P/I/D/FF/output/age plus yaw/state |
| Offline result | Not applicable | 20 controller tests pass; 34 relevant existing safety/dashboard tests pass; dashboard JS syntax passes |
| Physical result | Existing historical evidence only | Not run and not claimed; M4/geometry/tuning gates remain open |

The Windows development Python lacks PyYAML, so its repository-default test uses
a deterministic text fallback. The Jetson static stage must exercise the real
YAML loader before deployment. Python compilation and dashboard JavaScript
parsing pass.

## Rollback

The normal rollback is configuration-only: keep `enabled: false` and restart the
existing base service. To remove the integration entirely, revert this commit
and redeploy the previous known-good tree. Never roll back the mux, E-stop,
watchdogs or M4 exclusion independently.

## Exact deployment (only after review)

From a clean checkout containing the reviewed commit:

```bash
rsync -av project_atlas/ jetson@project-atlas-jetson:/home/jetson/project_atlas/
ssh jetson@project-atlas-jetson 'python3 -m py_compile /home/jetson/project_atlas/scripts/atlas_closed_loop_control.py /home/jetson/project_atlas/scripts/atlas_pid_commissioning.py /home/jetson/project_atlas/scripts/yahboom_base.py /home/jetson/project_atlas/scripts/atlas_status_web.py'
ssh jetson@project-atlas-jetson 'cd /home/jetson/project_atlas && python3 scripts/atlas_pid_commissioning.py --stage static && python3 scripts/atlas_pid_commissioning.py --stage simulation'
ssh jetson@project-atlas-jetson 'systemctl --user restart rover-base-telemetry.service rover-status-web.service && systemctl --user --no-pager --full status rover-base-telemetry.service rover-status-web.service'
```

Keep `enabled: false` during this deployment. Verify the new DRIVE PID dashboard
card says `DISABLED / controller_disabled` and prove the normal manual remote,
stop latch and watchdog behavior before any physical PID commissioning.

Rollback to the commit immediately preceding the PID change:

```bash
git revert <closed-loop-pid-commit-sha>
rsync -av project_atlas/ jetson@project-atlas-jetson:/home/jetson/project_atlas/
ssh jetson@project-atlas-jetson 'systemctl --user restart rover-base-telemetry.service rover-status-web.service'
```

If only the tuned controller must be deactivated, set `enabled: false` in
`config/drive_pid.yaml`, validate the YAML, deploy that single configuration and
restart `rover-base-telemetry.service`. That restores the legacy output path.
