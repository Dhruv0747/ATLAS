# Stage 28 B1 interlock and strict readback — 2026-10-27

Status: OFFLINE CANDIDATE. No deployment, service restart, serial access, bootloader operation or firmware read performed. Hardware retry remains NO-GO pending independent review, deployment validation and separate owner approval. Historical recovery findings in 7e3c4dc are preserved.

## Implemented corrections

- atlas_b1_interlock.py provides durable atomic state, two bounded flock locks, session/boot identity, 2-second supervisor freshness, 900-second overall bound and 180-second read window. Crashes, corrupt state and expired leases never restore IDLE automatically. Explicit reconciliation can authorize restoration only, not another read.
- atlas-sensor-recovery holds the dispatch lock across the base restart subprocess. Admission refuses an in-flight dispatch; queued workers recheck durable state before restart. Other recovery targets and fault reporting remain active.
- Candidate base ExecCondition denies starts while maintenance is held. This covers Restart=on-failure without removing that normal policy. Restoration grants exactly one start; a failed restoration cannot automatically retry. The gate uses a separate state lock to avoid deadlock with systemctl restart.
- Readback CLI requires a live READING token and exclusive serial ownership. Every flash chunk checks the supervisor. The legacy runner now exits before doing anything; it cannot accidentally apply the old inactive-service-only safeguard.
- Strict readback accepts only PID 0x0414, exactly 256 KB from the capacity register, and a complete option-byte record with RDP/complement A5/5A. Missing/invalid values abort. NACK is not proof of RDP; it is recorded as DENIED/UNKNOWN. No default capacity, unlock or write.
- PID 0x0414 identifies a family, not the exact RC package or manufacturer authenticity. Owner-confirmed STM32F103RCT6 marking remains mandatory; software cannot independently prove that marking.
- Two full passes are saved separately and compared byte-for-byte, with SHA256s. BACKUP STARTED is emitted only after first successful flash data returns. Interrupted/incomplete attempts are not success. Existing output directories are not overwritten.

## Offline validation

78 focused tests pass in Ubuntu 22.04 WSL. Tests use synthetic AN3155 responses, local temporary files/locks and mocked services only. Includes in-flight dispatch exclusion, pending systemd job rejection, modeled Restart=on-failure denial, queued recovery refusal, separate-lock deadlock avoidance, serial-ownership restoration refusal, stale/crashed monitor, boot mismatch, corrupt/missing state, explicit timeout reconciliation, one-start restoration, failed restoration hold, rollback byte preservation, unknown chip, wrong/zero capacity, missing metadata, RDP ambiguity, timeout, interrupted read and premature start-message prevention. Existing sensor recovery regressions pass.

Limit: ExecCondition systemd semantics are modeled, not yet validated on the production user manager. No physical backup reliability claim. Independent review must check deployment ordering, actual live unit/drop-ins, all base restart owners, status schema, stable USB identity and monitor behavior. Native systemd validation should use an isolated fake unit before production approval. This is a real implementation, but offline unit success is not authorization to attach hardware.

## Deployment package / approval 1 (not executed)

Review B1_CANDIDATE_SHA256SUMS.json. Its hashes describe repository candidate bytes, NOT current live files. Capture current live hashes before installation; abort on unreviewed divergence.

1. Fresh safety/resource checks under existing limits. Confirm actuators disconnected, transmitter OFF, E-STOP latched, zero commands, physical power arrangement unchanged.
2. Back up live recovery/readback files, service unit and all drop-ins with hashes. Preserve calibration/configuration and diagnostic evidence. Do not overwrite any previous MCU evidence.
3. Independently review and approve installation of atlas_b1_interlock.py, updated atlas_sensor_recovery.py, readback and supervised runner; initialize the state directory once as jetson (0700; state/locks 0600). Existing state must not be overwritten.
4. Install candidate b1-maintenance.conf under the base user unit drop-in directory; verify exact ExecCondition path and user. Reload the USER systemd manager only after approval. No base restart for deployment.
5. Restart only atlas-sensor-recovery after separate approval included in this maintenance deployment. This is necessary: old running Python does not acquire the new lock. Confirm its new process/file identity and unchanged unrelated services. No maintenance can begin with the old recovery process.
6. Confirm state IDLE and gate success, unchanged E-STOP/zero, telemetry freshness, recovery/fault reporting and rollback. Native fake-unit test must verify ExecCondition denial does not invoke a serial-opening ExecStart or produce a competing restart.

## B1 operation / approval 2 (not executed)

One separately approved read-only attempt. No erase/unlock/write/B2 authorization.

- Recheck full physical isolation: M1–M4, S1–S4, serial servo, CAN and other actuator paths disconnected; receiver only on SBUS with no independent supply/outputs; transmitter OFF. Main switch ON throughout, stable battery supply, Jetson feed from battery/BMS side. Do not switch OFF or rely on USB-only power.
- Snapshot Jetson calibration and scripts and verify hashes before touching the board. Verify chip marking and USB physical topology/VID/PID, not tty numbering alone.
- Arm via interlock CLI (fresh stopped policy and no pending base jobs). Start a separate supervised `watch --session TOKEN` process with durable logging. Confirm heartbeat advancing. If it fails, keep hold; do not enter bootloader.
- One controlled stop of base, then verify inactive, MainPID zero, empty cgroup/no base jobs and serial port free. The new start gate blocks delayed automatic starts. Check competing serial owners again before opening. Do not stop unrelated recovery or safety.
- Run b1_supervised_read.sh with the approved session, verified port and NEW output directory. It gates the read and waits separately for DONE after each instruction:
  1. Press and HOLD BOOT0 now.
  2. While holding BOOT0, press and release RESET.
  3. Now release BOOT0. Do not press any button again.
- Display is not bootloader evidence. The tool confirms protocol/identity/protection/capacity before flash. BACKUP STARTED — DO NOT PRESS BUTTONS means actual flash bytes returned. Timeout/first error ends attempt; no retry.
- Require both 262144-byte passes identical, matching SHA256 and complete settings/options/UID metadata. Copy evidence to Windows and back to a verification directory if needed; compare bytes and hashes on both hosts. Vendor image compatibility is a separate recovery check, never proof of a successful backup.

## Explicit restoration and rollback

Never delete/reset the latch or remove ExecCondition while attachment is uncertain. No automatic service resume on timeout/crash.

1. Confirm reader process exited, serial descriptor released, no pending job. Keep physical isolation and safety monitoring.
2. Tell owner to release BOOT0 and press RESET once with main switch ON; wait for confirmation. No bootloader GO command.
3. If supervisor expired, independent operator reconciliation uses Interlock.reconcile with fresh safety, confirmed normal reset and actual port-free check. This creates restoration-only ABORTED state; never another read authorization.
4. Interlock.resume requires fresh monitor, reset confirmation and actual port-free callback. Only then issue ONE approved base start; ExecCondition consumes RESUMING to VERIFYING.
5. Require fresh changing raw telemetry packets, expected board identity, zero commands and E-STOP. Do not rely only on an old ready log. Interlock.release additionally requires explicit operator confirmation and verified-restored callback. Only then IDLE returns normal recovery. Failed start stays held, reported and requires review.
6. After verified normal operation, rollback may restore hash-verified original recovery/readback files and original drop-in set, approved user daemon-reload and recovery-only restart. If bootloader state is uncertain, retain interlock and independent monitor rather than removing protection. Expired watch must be replaced by supervised reconciliation; do not leave a pending board unattended.

No live restoration wrapper is auto-executed. The review must bind restored/port-free callbacks to actual deployment evidence before execution. Stale policy blocks restoration; resolve that explicitly without bypassing safety. Exact live compatibility and independent review remain approval gates.

## Superseding native review
See ATLAS_STAGE28_B1_NATIVE_REVIEW_20261027.md: 94 offline tests and native PC systemd fake-unit tests pass after expiry, single-use-reader and restoration corrections. Deployment remains approval-gated; no hardware operation performed.
