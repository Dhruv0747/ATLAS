# B1 aborted attempt and recovery — 2026-10-27

## Verified sequence

- Approved b6d402f scripts were staged and hash-verified. Host calibration was backed up; all five hashes matched the Windows copy.
- At 11:50:35 Jetson local log time, B1 stopped rover-base-telemetry. Shutdown logged an rclpy invalid-context exception.
- At 11:50:38 atlas-sensor-recovery explicitly logged `RECOVERING: encoder_health ... restarting rover-base-telemetry.service, attempt 1/1`.
- Telemetry PID 89113 reopened ttyUSB0 and logged board-ready at 11:50:46. The readback tool subsequently refused the occupied port before opening it. No ROM read/write/erase/unlock commands were sent by the backup tool.
- The authorized attempt ended with readback status 2. No full flash backup, chip ID, flash-size or RDP evidence was obtained.
- After the owner's reset, the service remained active but packets stayed stale. A running process was not evidence of a working board link.
- After the owner's subsequent power/reset action, the same PID 89113 reported LIVE, packet age 0.019 s, READY, 24034 valid packets / 6007 encoder packets, zero checksum/write errors. E-STOP latched, manual-only, commissioning unarmed, linear/angular commands zero. No agent-initiated restart or second B1 attempt occurred.

## Cause and uncertainty

The B1 failure cause is verified: recovery was not isolated during intentional maintenance and reclaimed the port. The recovery log identifies the exact actor; this was not inferred from PID changes alone.

The stale interval's exact board state is unresolved. Startup code enables auto-report once; serial reads use blocking timeout=None. The node can remain active while waiting for board bytes. No serial probe was sent to distinguish bootloader mode, disabled reporting, reset state or power instability. Subsequent recovery with an unchanged host PID confirms the path can receive again, but does not identify which board condition caused silence. No evidence establishes damaged firmware or a faulty motor/encoder.

## Offline prevention candidate

`b1_run.sh` now refuses to proceed unless atlas-sensor-recovery is explicitly inactive, checked both at entry and immediately before stopping base telemetry. Active, transitional, failed, missing/ambiguous state and command errors fail closed. The script does not stop or disable recovery itself. This is a prevention gate, not a deployed maintenance lease or a complete retry authorization. Other possible service starters must be reviewed before a retry.

Tests: 9 isolated mocked bash gate cases plus 17 existing simulated readback tests: **26 passed**. These tests never invoke B1, ROS, a serial port or a real systemctl operation. No production file was changed for this candidate.

## Next safe procedure and approvals

No immediate recovery restart is needed now that packets are live. Keep actuators disconnected, transmitter OFF and E-STOP latched.

Before a future B1 retry, review a bounded maintenance plan that prevents all competing base starts, preserves safety monitoring, checks free serial ownership immediately before ROM access, and restores the original recovery-service state on every exit. The current camera-only maintenance hold does not cover base telemetry and must not be repurposed blindly. Stopping recovery, installing a maintenance change and retrying B1 each need explicit approval for the reviewed plan. A simple inactive-state gate does not protect against an external start after the check.

The restoration check also needs to distinguish fresh board packets from a new board-ready log: `systemctl start` on an already-active service creates no new initialization log. Do not restart merely to manufacture that log. Use fresh packet progression and actual safety state as evidence; stale data must remain a failure.

B2 remains NOT APPROVED. No erase, unlock, protection change or motor test is authorized.

## Evidence

Jetson calibration: `/home/jetson/project-atlas-migration/b1_firmware_backup_20261027_115023`.
Jetson operation/recovery logs: `/home/jetson/project-atlas-migration/b1_approved_b6d402f/`.
Windows copy: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/b1-evidence-20261027/`.
These are calibration/log evidence only, NOT an MCU recovery image. Private calibration files are not committed.
