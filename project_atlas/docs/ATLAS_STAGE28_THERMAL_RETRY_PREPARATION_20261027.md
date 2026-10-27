# B1 maintenance thermal-probe correction and retry preparation

2026-10-27. Follow-up to d674543. Status: PREPARED AND TESTED, NOT DEPLOYED. No service restart, BOOT0/RESET, MCU operation, camera start or motor command.

## Correction

The aborted wrapper directly read every thermal temp file with Path.read_text. Native CV0/CV1/CV2 reads returned EAGAIN, producing a Python TextIOWrapper TypeError. It did not use the already-established Nano-specific probe.

The new version-controlled deploy_maintenance_once.py imports the **unchanged** read_thermal function from offboard_bridge_preflight.py. There is no duplicated thermal parser or added exception whitelist. On a verified Orin Nano, only documented CV temperature EAGAIN is not applicable. Required CPU/GPU/SoC/TJ readings must all be available. Other errors, malformed values, absent trustworthy temperatures and unknown-model CV failures block admission. Missing CV values remain null, never zero. Valid high CV temperatures still count toward the maximum.

CPU75%, RAM80%, maximum temperature70C remain exact admission and postflight limits. The CPU window remains one second; no delay/bypass was introduced. Measurement evidence is saved before validation, full exception traceback is retained, and failed validation returns a nonzero process exit.

The maintenance runtime candidate remains exactly commit8736c73cd8ee53d5b082b4fbb9066421143fc4f2. Only the deployment wrapper changed. No interlock, recovery logic, map, calibration or safety thresholds were edited.

## Transaction and approval controls

The wrapper is import-safe and requires --approve-maintenance-install plus an explicit new --staging directory. Existing candidate/rollback/result directories cause refusal, preserving the aborted attempt. Python optimization mode is rejected so assertions cannot disappear.

Package and exact live baseline hashes, preflight, verified independent baseline archive and per-file backups precede writes. Safety/resources are rechecked immediately before mutation. Writes use unique temporary files, fsync and atomic rename; failed copies remove their temporary files. Injected partial-write and validation failures restore original recovery bytes and remove only the newly added condition/module. A recovery restart is issued on rollback only if the approved restart had already been attempted. Uncertain active maintenance prevents automatic rollback.

A preflight failure leaves production files and service identities untouched. A post-restart failure restores original configuration but may require a recovery-only restart to load the original code; it cannot preserve that process's PID. No code path intentionally restarts base telemetry or any other protected service. This is not a power-loss-proof multi-file filesystem transaction: abrupt kill/power loss requires inspection of retained backups/result/state before any further operation.

## Tests

**147 tests passed** in native Linux Python under Ubuntu22.04 WSL. Coverage includes the existing thermal suite, new deployment wrapper integration/failure tests, strict readback, interlock, recovery regressions and PTY operator prompts.

New wrapper tests exercise: normal measurements; verified Nano CV EAGAIN; required-zone absence; all temperatures unavailable; blank, malformed and NaN data; above-limit temperatures including125C; exact75/80/70 boundaries; unknown-model rejection; actual resource() delegation/evidence preservation; no-approval and reused-directory refusal; failure on each preflight; failures after each production write; postflight failure; successful fake deployment; atomic partial-copy failure. Services/files in transaction tests are fake, with an assertion forbidding base-service restart.

The earlier native systemd fake-unit validation is unchanged and was not repeated unnecessarily. No real deployment was run in these tests.

## Read-only native Jetson validation

The unchanged thermal reader plus corrected resource validator ran once via existing SSH/stdin, without installing files or running service commands:

- Model: NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super.
- CPU60.23890785%; RAM58.19455957%; maximum temperature60.0C.
- All six required thermal zones returned valid readings.
- CV0/CV1/CV2: errno11/EAGAIN; reported not_applicable, temperature null.
- No thermal_read_errors or platform_model_error; READ_ONLY_RESOURCE_PASS.

This validates the corrected native measurement path, not deployment success. Fresh safety, telemetry, hashes and resources must be repeated after retry approval. Local evidence: work/b1-maintenance-deploy-20261027/native-corrected-result.json. Read-only probe SHA256 e398cb7c281efd2ce1cbc0c2a5c18954f38d76c81394f0f80083d6977502bf54. Generated raw evidence is retained outside Git.

## Prepared package

Local package: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/b1-maintenance-deploy-20261027/corrected-retry-package.tar

SHA256: 12fbd59a38e2553e84474f5e2f889fb6a1f7467c5725947956fd38474b09f1cb.

B1_THERMAL_RETRY_PACKAGE.json records exact LF-byte hashes for the wrapper, unchanged thermal reader and unchanged runtime candidate archive. The private baseline archive is NOT included or committed. Its expected SHA256 remains6f583eb097236eb675986d472b7ece3c74722a051f1867a58e0b98fed2bda87a, already verified on Windows and Jetson. Copy it into the NEW retry staging directory only after approval; never reuse/overwrite the aborted directory.

## Next approval needed

Approve ONE corrected maintenance-only deployment retry: fresh E-STOP/manual-only/zero-command/LIVE telemetry/resource checks, exact live/package hashes, backup verification, installation of the reviewed interlock/recovery/condition and diagnostic files, user daemon-reload and restart ONLY atlas-sensor-recovery. Keep maintenance IDLE and do not start B1. If any check fails, stop or use the reviewed rollback; no automatic retry.

No approval for base restart, BOOT0/RESET, physical MCU reads/writes, erase/unlock or movement is requested. After successful deployment and postflight, request a distinct approval for one B1 operation. Current verdict: GO TO REQUEST MAINTENANCE RETRY APPROVAL; physical B1 remains NO-GO.
