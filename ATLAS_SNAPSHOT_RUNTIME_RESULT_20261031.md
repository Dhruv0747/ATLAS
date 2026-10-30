# One recovery-only snapshot runtime validation — FAIL — 2026-10-31

One explicitly approved attempt from24f0343; no retry. Reviewed manifest SHA256
`d7b6008a20933349165fb382fa72ac78015656e02f77b6ff074ed231ba2f82b5` verified.
Original unit and GNSS drop-in copied and hash-verified before execution.

## Timeline (Jetson journal IST)

- 00:27:50: bounded supervisor started. Fresh preflightCPU61.616%,RAM62.743%,
  temp63.218C; E-STOP/zero/manual/stationary/fresh telemetry and Astra OFF passed.
- Independent watcher collected13 accepted samples. Last two CPU66.724% then
  74.099%; new recoveryPID221686 observed at monotonic27690.829678.
- 00:28:04: single controlled recovery activation restart, originalPID2005 ended.
- 00:28:06: CPU81.3445378% rejected at monotonic27691.788617. Independent watcher
  failed closed and supervisor entered cleanup. Snapshot readiness remained false:
  no state.json had become available. No real callback validation success.
- 00:28:08: recovery process exited after cleanup requested stop. Journal then
  logged rcl node context invalid during parameter publisher creation. This occurs
  AFTER CPU rejection/stop, consistent with interrupted ROS initialization; it
  does not prove an independent publisher bug or exact CPU root cause.
- 00:28:09: supervisor ended FAIL; original restart policy restored, recoverySTOPPED.

Exactly1 activation restart reserved/used; rollback/restoration restart0. No
additional ROS observer or camera subscribers started; the existing recovery ROS
process was restarted as authorized. No Astra/AI/web/backend/controller activation.

## Measurements and limits

Accepted13 samples: CPU average63.015%,range58.059–74.099%; RAM average62.867%,
peak62.966%; temperature peak63.375C. CPU rejection81.3445% is NOT included in that
accepted-sample average. Failure path records CPU reason in health.json but does
not collect full rejected-window per-process counters/RAM/temperature. Exact CPU
attribution therefore remains unresolved. New recovery process lifetime systemd
CPU1.787s includes initialization and shutdown, not adapter overhead. No producer
steady-state cost can be measured because snapshot readiness was never reached.

Postflight3 read-only samples: CPU60.269/58.893/60.365%,RAM62.303–62.366%,temperature
63.093–63.218C. E-STOP latched,zero commands,stationary encoders,LIVE telemetry;
packet age0.004–0.013s. Astra OFF/empty worker inventories. No safety exemptions.

## Cleanup verified

- Original unit/GNSS drop-in byte-match verified backups; Restart=always restored.
- Temporary producer opt-in removed; service Environment only ATLAS_GNSS_ENABLED=0.
- Owned producer runtime directory and temporary restart override absent.
- RecoveryPID0,ActiveState=failed,NRestarts0: explicitly STOPPED, not healthy/running.
- DashboardPID182915 active,NRestarts0. All other atlas-*/rover-* identities match
  baseline (excluding test unit and expected recovery change).
- Three installed code hashes unchanged. No application rollback necessary.
- Temporary outer test unit file removed after it exited; daemon-reload only.
- No automatic retry or restoration start. Background sensor recovery is unavailable
  until separately approved restoration; telemetry/mux/Dashboard remain operational.

Evidence: /home/jetson/project-atlas-migration/snapshot-runtime-once-20261031/
Includes result,transaction,cleanup,postflight,samples,snapshot-validation,original
config backups and runtime-journal.txt. Local copy:work/snapshot-runtime-evidence-20261031.
JSON/JSONL evidence manifest verified:
`c8255782e58f3667415523f59eead442ffae35421cd3c172271d3b0ac77f40f0`.
Journal retained separately after that manifest. Private raw logs are not committed.

## Decision and manual recovery gate

FAIL; backend activation NO-GO. Snapshot producer runtime safety remains unverified.
Do not rerun consumed test or blindly start Restart=always service. Next operation
must be separately approved recovery-only restoration with snapshots DISABLED:
reverify current safety and original config/code, temporarily bound Restart=no,
perform at most one monitored normal recovery start, verify health before restoring
original policy. Stop on any guard violation; no camera/backend or producer test.
This report does not execute or authorize that next operation. Current state matches
the approved fail-closed plan: recovery stopped rather than an unsafe restart loop.
