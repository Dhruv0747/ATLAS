# Stage 28 maintenance deployment: aborted before installation

Source approved: 8736c73cd8ee53d5b082b4fbb9066421143fc4f2. One attempt on 2026-10-27. Result: ABORTED_BEFORE_INSTALL. No production files changed, daemon-reload or service restart occurred. No state initialized, bootloader entry, serial access, flash operation or B1 attempt.

## Preflight and backup

Reached Jetson through existing Tailscale SSH after Wi-Fi SSH timeout. Post-reboot boot ID 5bfabd14-3765-42df-b0a1-f5da65af34bb. Recovery source and base/recovery primary service hashes exactly match reviewed pre-candidate baseline. Existing priority and GNSS-disabled drop-ins inspected; no maintenance drop-in or state existed.

Initial measured CPU61.67%,RAM57.77%,maximum available temperature59.875C; free disk391308337152bytes. E-STOP latched, manual-only, commissioning unarmed, sourceSTOPPED and zero velocity commands. Encoder packets20624->20648; LIVE, no serial checksum/write errors.

Baseline archive verified on Jetson AND Windows before the installation attempt. SHA256: 6f583eb097236eb675986d472b7ece3c74722a051f1867a58e0b98fed2bda87a.

Candidate archive SHA256: a28c5ea60de2b9276a2a275d1c2bb0bd303d959a61821b7f0217dc05a428a756. All six candidate files verified against the approved commit's manifest. Candidate extraction was staging only.

## Failure and confirmed cause

The transactional deployment driver's resource check raised `TypeError("can't concat NoneType to bytes")` before its first production write. It used Path.read_text on every thermal zone. Follow-up read-only per-zone diagnosis identifies cv0-thermal, cv1-thermal and cv2-thermal as those failing reads; all six CPU/GPU/SoC/TJ zones returned temperatures, maximum59.968C.

This is a deployment-wrapper probe regression, not evidence of overheating or an interlock-code failure. The repository already has an Orin Nano-aware reader in project_atlas/tools/diagnostics/offboard_bridge_preflight.py: read_thermal uses bounded os.read, records unavailable CV hardware only for the verified Nano platform, and still rejects genuine required-sensor errors. The wrapper should have reused it. No CPU/temperature threshold was changed and no failed admission was bypassed.

No deployment retry was performed. The proposed next correction is to reuse that existing tested probe in the deployment wrapper and test the wrapper integration offline; no new thermal exception policy is needed. A separately authorized maintenance retry is required afterward. Do not request B1 approval before maintenance installation succeeds.

## Post-abort verification

- Base: active PID3333, NRestarts1 before/after.
- Sensor recovery: active PID1918, NRestarts0 before/after.
- Recovery file remains c6b5ac7979b6aff24c2f1a13a365d039b833da4c37997d3a8a07b21a928daaf5.
- Interlock module, maintenance drop-in and state directory all ABSENT.
- E-STOP/manual-only/zero commands remain confirmed; encoder packets26513, LIVE, age0.035s, no serial checksum/write errors.
- No maintenance active; no B1/readback began. No rollback required because installation never began.

## Retained evidence and rollback readiness

Jetson: /home/jetson/project-atlas-migration/b1-maintenance-8736c73-20261027/ contains candidate.tar, baseline-backup.tar, deploy_once.py, terminal.log and result.json. The proposed rollback directory was not created because preflight aborted; the independently verified baseline archive is available.

Windows: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/b1-maintenance-deploy-20261027/ contains the matching baseline archive, candidate, preflight, post-abort data and result. Private service/configuration archives and generated raw logs are retained there, not committed.

Verdict: NOT DEPLOYED; physical B1 NO-GO. Fix and offline-test deployment-probe integration, then request approval for one maintenance-only retry with unchanged safeguards. No BOOT0/RESET action is needed from the owner now.
