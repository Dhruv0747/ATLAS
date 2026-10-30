# Original recovery restoration preparation — 2026-10-31

GO for separately approved ONE bounded original-recovery start. NOT executed.
Inert package staged and all hashes verified; ATTEMPT_USED absent.
Manifest:bc550860a4610f5f879464ab51909f360960da493728f6093e89c999f16856da.
Stage:/home/jetson/project-atlas-migration/recovery-original-restore-once-20261031.

Current correction: systemd original configuration/Restart=always restored, but
on-disk script still candidate da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a.
Original backup hash5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a
verified. Future command restores original bytes BEFORE the single start. Helpers
remain inert; no producer flag or snapshot runtime exists. RecoveryPID0 failed,
DashboardPID182915 active,NRestarts0. Unit and GNSS drop-in match exact backups.

Fresh read-only safety samples:CPU60.738/59.900/60.877%,RAM58.997–59.027%,temperature
63.000–63.281C; E-STOP latched,zero commands,stationary encoders,LIVE telemetry,
packet age0.018–0.032s. Rechecked automatically immediately before execution.

Procedure: separate HTTP/kernel resource watcher, no ROS/DDS participant; first
counter window includes watcher startup.10s admission baseline, temporary recovery
Restart=no, verified original file atomic restore, exactly1 nonblocking recovery
start,20s observation. Check journal READY marker for new PID, no auto restarts,
protected identities unchanged and producer disabled. Only then restore always.
Outer unit60s RuntimeMaxSec,30s cleanup timeout,192MiB memory cap; existing75%CPU,
80%RAM,<70C rules unchanged. No startup exemption. No Vision Lab/backend operation.

Two focused restoration-preparation tests PASS: stopped-only entry,policy bound
without start,duplicate attempt rejection. Reuse preceding native-systemd
nonblocking/job/timeout/SIGKILL cleanup tests; no repeated benchmark or live test.

Rollback/fail-closed: on guard failure, explicitly stop recovery/cancel pending job,
remove only owned temporary override, daemon-reload and verify original policy.
Leave original recovery source restored (do not reintroduce experimental candidate).
Preserve candidate backup and evidence. No retry or second restoration start.
ExecStopPost performs idempotent cleanup after timeout/crash. If quiescence fails,
retain Restart=no and report manual intervention. All unrelated services untouched.
Incident remains OPEN until actual start and readiness checks pass.

Prepared command, requires separate owner approval before execution:

```sh
cd /home/jetson/project-atlas-migration/recovery-original-restore-once-20261031 && printf '%s\n' 'bc550860a4610f5f879464ab51909f360960da493728f6093e89c999f16856da  SHA256SUMS' | sha256sum -c - && sha256sum -c SHA256SUMS && test ! -e ATTEMPT_USED && test ! -e /run/user/1000/systemd/user/atlas-original-recovery-restore-once.service && install -m 600 atlas-original-recovery-restore-once.service /run/user/1000/systemd/user/atlas-original-recovery-restore-once.service && systemctl --user daemon-reload && systemctl --user start atlas-original-recovery-restore-once.service
```

No sudo required. This starts optional supervisor which alone performs the bounded
recovery start. Do not invoke Python directly or bypass ExecStopPost. No command
above was run; only inert package copying/hash verification done.
