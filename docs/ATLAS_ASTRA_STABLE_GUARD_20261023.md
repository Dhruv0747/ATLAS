# Astra stable-port guardian — 23 October 2026

## Verified correction and deployment

Owner authorized the guardian correction with no camera start or reboot.
The exact live baseline used `/dev/bus/usb/001/014` and `001/011` inside
`extra_safety`; legitimate USB renumbering therefore invalidated the check.
The repository had a newer error-reporting helper, not yet on this live baseline.
Live-to-candidate diff was reviewed: one `stat` import, one USB resolver function,
and replacement of the four-line USB-only check. All other live code is unchanged.

Only `project_atlas/tools/vision3d/stationary_ros_probe.py` was installed.
The resolver reads current sysfs attributes on each call, selecting only controller
`3610000.usb`, ports `2.3.1.2` (2bc5:0403 Depth/IR) and `2.3.1.1`
(2bc5:0501 RGB). Bus/device numbers are derived, not cached. It validates the
character-device major/minor and effective-user RW access, then rechecks identity
and node metadata to fail closed on changes during the check. An existing stable
udev alias must agree; absent aliases are supported through the same physical-port
identity. No same-model substitution on another port or automatic ACL repair.

This is topology identity, not cryptographic device authentication: these interfaces
do not expose USB serial descriptors. Moving the camera to a different physical
port requires a reviewed topology update. Arbitrary hot-unplug races cannot be
eliminated by a preflight check; later driver errors and repeated guards still stop.

## Hashes and rollback

- Before: `f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384`
- Installed: `f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd`
- Backup/evidence: `/home/jetson/project-atlas-migration/admin-diag-20261023/stable-guardian-yfhbb91g/`
- Files there: original `stationary_ros_probe.py`, complete `result.json`.
- Result: `INSTALLED_VERIFIED_NO_RESTART`.

Rollback while Astra is OFF: verify the installed and backup hashes above, restore
the backup to `/home/jetson/project_atlas/tools/vision3d/stationary_ros_probe.py`,
then verify the original hash. No service restart is necessary: a future separately
authorized viewer worker imports the probe when it starts. Existing admin installers
with old probe hash pins must deliberately refuse this new baseline; do not bypass
their pins or rerun them as a repair.

## Validation

WSL Ubuntu 22.04: 9 USB guardian tests (including multiple negative subcases),
16 stationary-gate tests, 23 startup coverage/shutdown tests and 8 Astra udev tests:
**56 passed**. Synthetic fixtures change both bus and device numbers; test wrong
controller/VID, missing/ambiguous ports, stale aliases, wrong node type/major,
access denial, mid-check renumbering, invalid numbers and read failure. Tests do
not open hardware. This is not a physical reconnect pass.

Three fresh 1-second checks before and after installation passed unchanged limits:

| Observation | Before | After |
|---|---:|---:|
| Whole-Jetson CPU range | 69.93–72.70% | 70.94–72.79% |
| RAM range | 64.98–65.06% | 65.01–65.13% |
| Maximum temperature | 60.00°C | 60.062°C |

This short safety check is not a CPU performance comparison. All samples retained
E-STOP latched, manual-only, commissioning disabled, STOPPED source, zero commands
and recorder inactive. Required Pi Camera, LiDAR, IMU and four encoder freshness,
wheel outputs and mission-idle checks passed. Both actual Astra nodes resolved and
had effective RW access. Protected service PIDs/restart counts were unchanged:
camera1890/0, telemetry3485/1, mux1884/0, EKF3182/0, localization6009/2,
LiDAR5930/5, web2013/0. Nonzero restart counts predate this change.

## Permanent access status and remaining gate

The owner-installed two-interface rule is present, root:root0644, SHA256
`54a8bc029e21364d1d259f11ebf3cefcf10ad263c45ae98aabda880393c2e7c4`.
Group `atlas-astra` contains jetson. Existing web PID2013 has not inherited group994;
current nodes still work through named jetson ACLs. Aliases are not yet created
because no reconnect/udev trigger was performed. A separately authorized controlled
reboot/full session renewal is needed for service-group inheritance and persistence
validation. No reboot, reconnect, udev trigger, service restart, camera start,
recording, motion, networking change or safety-limit change occurred in this task.
CPU75%, RAM80%, temperature70°C, Domain77, Depth/IR modes and calibration/cloud
restrictions remain unchanged. No live preview success is claimed.
