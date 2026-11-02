# Current encoder-fault recovery preparation

2026-11-02: preparation only, execution NO-GO. No latch reset, restart, firewall change or movement performed.

## Evidence

Owner-read first fault: October 31 18:40:47 IST, watchdog `encoder movement`; M2 -126 to -127 while other counts unchanged. Commands and reported speed zero, E-STOP latched, fresh telemetry; CPU 61.726%, RAM 64.119%, temperature maximum 63.062 C. Subsequent firewall refusals explicitly reference the retained latch. Trigger confirmed; physical movement versus encoder jitter remains UNKNOWN. Do not add a one-count tolerance. The older October 30 unknown fault is separate.

Current guard hash: 27d4cacae47044a1675cf911aad60a69fc78dd5b85de14bdb6d5480288a560e1. Exporter hash: 0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d. Firewall failed/78; watchdog/exporter inactive, all PID0 and restart count0.

Three read-only samples using existing guard validation: CPU 65.35â€“65.91%, RAM 64.95â€“64.97%, temperature 60.406â€“60.500 C. E-STOP latched/manual-only, commissioning false, commands and reported speed zero. Counts [43,-40,-27,-15] unchanged; guarded topic ages at most 0.5 s. Samples are a short observation, not proof that the earlier count change cannot recur. Current counts must not be compared directly with an earlier boot to infer movement.

## Remaining preparation gate

Owner read-only evidence at 2026-11-02 09:43:19 IST completes the firewall check: legacy IPv4 contains the existing Tailscale rules only; IPv6 has empty ACCEPT policies; nftables has no rules. No ATLAS_MONITOR chain or TCP 9118 restriction is installed. All eight state hashes match the previous owner read. Physical stationary/no-touch confirmation is received.

Current FAULT.json SHA256: fc5479c96fd42ee003a565b0ccb7e63caaf9d29c43a383eff5291a3c938302fd. The physical cause remains UNKNOWN.

Package blocker confirmed by source inspection: existing recover_once.py still pins the older 3715b150... fault and attempt-5 identity/ancestry. Its archive_state also requires every JSON file to be an object, while the current fault-events.json is a list. Do not run this old transaction: its evidence checks correctly refuse the new incident. The smallest remaining correction is incident-specific rebinding plus bounded list validation for fault-events.json only, followed by focused archive/cleanup tests and independent review. No corrected execution package or hash is claimed yet.

Latest read-only safety samples recorded during preparation: CPU 65.51–66.78%, RAM 66.04–66.07%, temperature 60.38–60.47 C; latched/manual-only, commissioning false, zero commands/speed, counts [43,-40,-27,-15] unchanged and guarded ages at most 0.4 s. These expire and must be repeated immediately before any separately approved execution.

## Proposed single attempt, separately authorized only

1. Bind the existing wrapper to exact current evidence/runtime/unit hashes and a new unique evidence directory/unit name. Reuse archive, safety polling, expiry and cleanup; no new framework.
2. Fresh admission: latched E-STOP, manual-only, commissioning disabled, zero commands/speed, fresh MCU/odometry and unchanged encoders; CPU strictly below75, RAM below80 and temperature below70. No numeric threshold relaxation.
3. Archive current latch, event history, observer marker and associated state; verify every byte/hash before any reset. Keep older fault archives intact. Reset only specifically reviewed monitoring state after separate approval.
4. One monitoring-only start ordered firewall verification â†’ watchdog READY â†’ exporter. Existing bounded restart override; no restart loops. Observe 300s with existing worker/fallback cleanup limits. Any count change, resource failure, stale/missing data, firewall mismatch or HTTP failure aborts.
5. Verify existing 15s scrapes, both Grafana dashboards and authenticated Pulse View. No synthetic traffic for live acceptance; pulse absence after freshness expiry is expected, not a reason to relax guards.
6. Failure: stop exporter first, verify no listener before removing only owned monitoring rules as reviewed; preserve the new rejection and original archive, restore restart policies, leave monitoring OFF. No automatic retry. Failed cleanup retains protection and is an OPEN incident.

Monitoring remains BLOCKED, not CLOSED. No latch reset or service/firewall mutation was performed. Execution approval must be requested only after the corrected transaction passes focused validation.

Next standalone mapping implementation step after this gate: reuse existing onboard_adapter.py/onboard_supervisor.py/onboard_store.py and Jetson-hosted map3d viewer; validate recorded RGB/depth, CameraInfo, synchronization and TF against their existing configuration checks. Missing calibration/recordings remain explicit blockers. Do not activate a camera or imply accurate metric mapping from a depth preview.

Limited preparation completed: bounded event-list validation corrected; all 58 focused transaction tests PASS, including six new list/integrity/rollback cases. Existing attempt identity and fault pins intentionally unchanged. No executable current-incident package issued. Monitoring development stops here per owner scope.

2026-11-02 final binding preparation PASS; see [current procedure](M2_RECOVERY_READY_20261102.md). Recovery remains DOWN pending separate execution approval. Earlier blockers above remain historical evidence.
