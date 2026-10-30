# End-to-end recovery snapshot runtime safety preparation — 2026-10-31

Continues d26aa6c. No Jetson deployment, restart, enablement or live test. Only PC
WSL fake units were operated. Existing installed producer/backend remain untouched.

## Implemented integration

recovery_snapshot_runtime.py: atomic owned recovery-only drop-in; durable restart
reservations before commands; systemctl --no-block restart/stop; bounded client
polling with independent safety checks. Exactly one activation permitted, at most
one restoration restart. No automatic retry. Original unit and application files
are never edited; only the owned temporary drop-in is added/removed.

recovery_snapshot_supervisor.py: separate Python watcher consumes unchanged
Dashboard API, kernel CPU/RAM/Orin temperatures; no ROS node/subscriber. It never
reads producer snapshots as its safety source. Watcher runs while recovery stops,
initializes or fails. If HTTP fails, timeout/missing/stale observation aborts rather
than falling back to recovery. Production snapshot checks additionally validate raw
callback freshness, strict zero commands and encoder values after readiness.

Fresh preflight precedes watcher spawn. Its first aggregate window starts from
counters captured BEFORE Python watcher startup, preserving genuine initialization
CPU. One-second intervals accepted only0.9–1.1s. CPU>75%,RAM>80%,temperature>=70C
reject; admission requires below limits. No warmup exemption or averages used to
admit unsafe samples. HTTP total deadline0.5s, stale watcher age1.5s rejects.

10s baseline, one recovery activation restart (job deadline8s), at most5s callback
fill after service active,30s observation, one explicit output-disable/restoration
restart (8s),3s recovery verification. Outer systemd RuntimeMaxSec90,Restart=no,
TimeoutStopSec30,KillMode=control-group. Owned producer state directory0700 and
snapshot0600. Monitoring unit MemoryMax192MiB,TasksMax32,LimitFSIZE16MiB,UMask0077.
Evidence: per-second system resources, raw recovery PID CPU/start ticks/RSS (do not
combine counters across PID births), watcher CPU, snapshot update/freshness results,
protected service identities and final result. Peak/RSS/counters must be analyzed
as actual observations, not inferred savings. No synthetic benchmark repeated.

## Crash cleanup and rollback

ExecStopPost is a separate systemd-executed process, independent of Python finally.
On timeout/SIGKILL/failure after activation it cancels/quiesces recovery, removes
only owned opt-in override, reloads original policy and leaves recovery explicitly
STOPPED. Restoring Restart=always on an explicitly stopped service does not start
it. Cleanup never starts/restarts anything. Before activation it preserves the
original healthy PID while restoring temporary config. Cleanup is idempotent.
If quiescence fails, retain Restart=no and report failure; do not remove the bound
and create a loop. Ownership mismatch also stops cleanup with evidence.

Healthy completion uses the one restoration restart with opt-in removed under
Restart=no, verifies protected units/files/safety, then restores original policy.
Output is OFF at completion. This bounded test does NOT leave producer enabled.
Original installed file hashes checked before/after; no application-file rollback
write necessary. Unit files/previous drop-ins remain unchanged. Private runtime
files removed only after producer disabled/stopped and inode ownership verified.

Following supervisor SIGKILL, systemd stops watcher cohort and runs cleanup; no
restoration restart is attempted without independent safety. Existing E-STOP/mux,
telemetry and Dashboard remain running. Failed test may leave automatic sensor
recovery unavailable until explicit operator recovery; never report that as healthy.
Host power loss/systemd failure is not proven by these tests. No reboot test run.

## Focused offline evidence

PC Ubuntu WSL native systemd fake-unit tests:
- Safety check invocations continue during delayed nonblocking restart.
- Activation/rollback duplicate requests rejected; healthy original policy restored.
- Guard failure during restart: service quiesced, opt-in removed, cleanup idempotent.
- SIGKILL after prepare and after activation, plus RuntimeMaxSec timeout: real
  ExecStopPost restored policy/config, preserved original fixture file bytes and
  no automatic restart; NRestarts0.
- Full supervisor flow with real fake recovery process, synthetic callback snapshots
  and independent synthetic safety watcher: PASS; producer output disabled, runtime
  directory removed and original policy restored. No real rover safety inferred.
Three watcher tests additionally verify missing/failed/stale/future rejection,
no producer-safety dependency and inclusion of startup CPU counters. Seven focused
test methods total (multiple crash subcases); previously passing safety tests reused.
Systemd unit syntax verification passed; host snapd RestartMode warning is unrelated.

## Package and approval

Prepared on PC only:work/snapshot-runtime-package-20261031.
SHA256SUMS digest:
d7b6008a20933349165fb382fa72ac78015656e02f77b6ff074ed231ba2f82b5.
Manifest committed as tools/vision3d/recovery_snapshot_runtime_SHA256SUMS.
Future stage must be /home/jetson/project-atlas-migration/snapshot-runtime-once-20261031,
private0700, fresh unused path. Verify this manifest and all hashes before starting.
Install the reviewed temporary user unit atlas-snapshot-runtime-once.service with
ExecStopPost intact; never invoke supervisor directly. Do not enable unit at boot.
User daemon-reload does not restart other services. No commands executed on Jetson.

GO for separate owner approval of ONE bounded runtime validation, including:
- temporary recovery-only policy/opt-in and private runtime directory;
- one activation restart and at most one restoration restart of recovery only;
- outer supervision/ExecStopPost cleanup and unchanged safety/resource gates.

Before execution recheck installed/package/config hashes, EnvironmentFile precedence,
original service health, fresh E-STOP/zero/stationary/LIVE resources and ownership.
No camera, AI, web restart, backend activation, protected telemetry restart or PR
merge is included. If failure leaves recovery stopped, preserve logs and policy,
verify opt-in absent plus safety, then seek separate manual restoration approval;
do not rerun consumed package. Actual Jetson recovery startup cost remains unknown.
