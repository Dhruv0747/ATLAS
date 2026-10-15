# Corrected temperature probe: one Jetson check

15 October2026. Owner authorized the fixed probe on Jetson and requested the
safety/resource verdict, with ATLAS stopped and recording off. Source:
`75a6338bce20ee148117691a87dafa183a760992`, existing branch
`agent/sync-developer-20261011`.

**Verdict: BLOCKED. Not all safety/resource checks passed.**
The corrected reader produced temperatures and precise unavailable-zone errors.
No bridge connection, ROS subscription, recording, movement, restart or persistent
Jetson installation occurred. Probe ran from stdin through existing SSH once.

## Measured results

UTC start2026-10-15T03:47:47.813761+00:00 (09:17:47 IST).

| Check | Observation | Result |
| --- | --- | --- |
| CPU aggregate5×1s | 71.428571,69.897959,70.017331,69.270833,68.728522% | Under75% in every sample |
| CPU summary | Mean69.868643%, max71.428571% | Preflight window only |
| RAM | 66.460858% | Under80% |
| CPU temperature | 60.656°C | Under70°C |
| GPU temperature | 60.312°C | Under70°C |
| SoC0/1/2 | 59.812/60.375/59.625°C | Under70°C |
| TJ | 60.562°C | Under70°C |
| CV0/1/2 | No temperature returned | Required-data gate blocks |
| E-STOP, zero commands, manual-only, commissioning | Not completed | Unverified |
| Dashboard resource guard, sensor freshness, disk/service state | Not completed | Unverified |

Three exact failures:

`/sys/class/thermal/thermal_zone2/temp` (`cv0-thermal`)

`/sys/class/thermal/thermal_zone3/temp` (`cv1-thermal`)

`/sys/class/thermal/thermal_zone4/temp` (`cv2-thermal`)

Each returned `BlockingIOError: [Errno 11] Resource temporarily unavailable`.
The new evidence includes source paths and tracebacks. The probe exited2 with
`ValueError: temperature measurement incomplete; admission blocked` before
dashboard/service inspection. Unlike the previous attempt's unlocated TypeError,
this identifies the actual unavailable reads in this run. It does not establish
the reason these zones were unavailable or prove the precise historical failing
attribute. No overheating or hardware-fault conclusion is drawn from EAGAIN.

## Separate safety-status check

To answer the remaining safety questions without rereading temperature or
activating anything, one read-only dashboard/service query was attempted through
Tailscale. SSH timed out during banner exchange. The existing Wi-Fi endpoint was
then checked: SSH connect also timed out. No further attempts followed.

Consequently current E-STOP/zero-command/autonomy/commissioning and Stage20 OFF
state could not be freshly confirmed. The recorder was never activated by this
work; previous state is not substituted for a current observation. Neither
timeout proves that Jetson powered down or identifies a network root cause.

## Evidence and next action

Local evidence directory: `artifacts/offboard_temperature_check_20261015_0917/`.
Files: `terminal.txt`, `safety_status_terminal.txt`, `safety_status_lan_terminal.txt`.
Main evidence SHA256:
`558e97d12fc561d98c557b1d48e454d587efba522deeb8c83487a63dd782c80b`.
As-run PC source SHA256:
`4f9939c1c1c956c829b5a9b2bd8282a3d87a5e25cbb7dced517eb7eac5f8f562`.
Generated logs stay local, outside Git.

Next: establish whether CV-zone EAGAIN is expected under the installed Jetson
power state before proposing any change to the required thermal sensors. Keep
the existing gate blocked; do not ignore unavailable zones or change thresholds
solely to pass. Full safety/resource admission needs a fresh reachable snapshot.
No live recording retry was performed or requested here. No code changed in
this task, so the prior17 offline tests were not repeated.
