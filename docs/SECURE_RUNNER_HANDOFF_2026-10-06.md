# ATLAS Secure Runner Handoff — 2026-10-06

## Current goal
Establish a secure, read-only GitHub self-hosted runner path for ATLAS first.
Deployment and motion-capable automation remain intentionally disabled.

## Completed on Jetson
- Repository visibility changed to PRIVATE.
- Dedicated Linux user created: `atlas-runner`.
- `atlas-runner` has no sudo, hardware, dialout, video, i2c, gpio, or jetson group membership.
- Runner architecture: ARM64/aarch64.
- Runner name: `ATLAS-JETSON`.
- Runner labels: `self-hosted`, `Linux`, `ARM64`, `atlas`, `jetson`, `ros2`.
- Runner installed as a system service and confirmed active/running under user `atlas-runner`.
- No second Runner.Listener process was found.
- `/home/jetson/actions-runner` exists but is empty.
- `/opt/atlas-ci` exists as `root:root` mode 0755.
- ROS environment observed from mission control: ROS 2 Humble, ROS_LOCALHOST_ONLY=0, no explicit ROS_DOMAIN_ID seen, therefore default domain 0 is currently assumed.
- No motion command was issued during setup.

## Live safety evidence observed
- `/atlas/safety_status`: `READY: STOPPED - FRONT 0.51 m CLEAR`
- `/atlas/mission_status`: `READY`
- `/atlas/control_policy`:
  - `stop_latched=true`
  - `commission_armed=false`
  - `commission_remaining_s=0.0`
  - `source=STOPPED`
  - stop reason: `REMOTE STOP: joystick unavailable`
- `/atlas/motion_safety`: `REMOTE STOP: joystick unavailable`
- `/atlas/drive_mode`: `STOPPED`
- final `/cmd_vel`: all linear/angular components zero
- no sample was observed on `/cmd_vel_nav` or `/cmd_vel_recovery` during the bounded read-only check
- `/atlas/encoder_health`:
  - state READY
  - packet_fresh=true
  - link_state=LIVE
  - consensus_state=AVAILABLE
  - selected encoders 1,2,3,4
  - faults=[]
  - traction=false
  - navigation_validated=true
  - autonomy_ready=true

## Relevant live service state
Confirmed active/running:
- atlas-mission-control.service
- atlas-cmd-vel-mux.service
- atlas-safety-status.service
- atlas-camera.service
- atlas-ekf.service
- atlas-lidar.service
- atlas-scan-filter.service
- atlas-uno-r4-sensor-hub.service
- rover-base-telemetry.service
- rover-radar.service
- atlas-lidar-odom.service
- atlas-lidar-odom-gate.service
- atlas-im10a.service
- atlas-sensor-recovery.service

Confirmed inactive/dead at observation:
- atlas-explore.service
- atlas-nav2.service
- atlas-slam-fast.service
- atlas-map-footprint-filter.service

## Repository-side secure runner work
Branch: `setup/atlas-secure-runner`

Added:
- `.github/workflows/atlas-health.yml`
- `docs/SECURE_RUNNER_PHASE1_2.md`
- `ops/trusted-reference/atlas-health-check`
- `ops/trusted-reference/atlas-ci-health.sudoers`
- `ops/trusted-reference/README.md`

Trust model:
- Workflow is manual `workflow_dispatch` only.
- No push or PR trigger on Jetson runner.
- Workflow does not execute repo copy of the trusted checker.
- Runtime checker must be installed once at `/opt/atlas-ci/atlas-health-check` as root-owned code.
- Runner may invoke only `sudo -n /opt/atlas-ci/atlas-health-check`.
- Trusted checker accepts no arguments.
- Fixed outputs:
  - `/home/atlas-runner/atlas_health.json`
  - `/home/atlas-runner/atlas_health.txt`
- No ROS publish, service call, motion command, restart, or deployment exists in Phase 1/2.

## Jetson trusted checker status
The trusted checker is now installed at `/opt/atlas-ci/atlas-health-check` with
`root:root` ownership and mode 0755.

The sudoers rule is installed at `/etc/sudoers.d/atlas-ci-health`, validated by
`visudo -cf`, and permits only the zero-argument command:

`sudo -n /opt/atlas-ci/atlas-health-check`

A direct run as `atlas-runner` completed successfully with:

- overall: PASS
- control_policy: PASS
- drive_mode: PASS
- safety_status: PASS
- mission_status: PASS
- encoder_health: PASS
- cmd_vel: PASS
- required_services: PASS
- mapping_exploration: PASS

No motion command, service restart, deployment, or ROS service call was issued.

## Next step
Run the manual GitHub Actions workflow `ATLAS Read-Only Health` from the
`setup/atlas-secure-runner` branch and confirm it invokes the trusted local
checker and uploads the JSON/text reports. Deployment automation remains
disabled until that end-to-end read-only path is verified.

## Important constraints
- Do not add broad sudo to `atlas-runner`.
- Do not grant runner access to the `jetson` user bus broadly.
- Do not place PATs, registration tokens, SSH credentials, or passwords in repo files.
- Do not enable automatic runner jobs from pushes or pull requests.
- Do not issue physical motion from CI.
- Missing/stale safety evidence must fail closed.
- Physical e-stop remains independent of all software automation.

## Separate security item for later
ROS currently reports `ROS_LOCALHOST_ONLY=0` on default domain behavior. LAN DDS exposure should be reviewed separately before enabling any deployment/control automation.
