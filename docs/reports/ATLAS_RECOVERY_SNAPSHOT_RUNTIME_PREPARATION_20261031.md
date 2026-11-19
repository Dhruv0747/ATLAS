# Recovery snapshot runtime-validation preparation — 2026-10-31

Baseline d3eb492. Read-only live review and focused offline changes only.
No recovery restart/reload, opt-in, runtime directory creation, camera/inference,
movement, firmware/controller changes or PR merge.

## Verified current state

Installed hashes match the reviewed package:
- recovery: da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a
- snapshot helper: e37cfd130c716f5bc014b91b6c7cd8c5ebdae85be916718cf07949d9f68f7c9c
- strict Safety dependency: a26b364f85df17e4fbbe05ff3174972b42180da3d0f44809cece967065dd47c1

Recovery PID2005,active,NRestarts0,Restart=always,RestartSec=3. Unit depends in ordering
on cmd-vel-mux, no PartOf/BindsTo coupling. GNSS-disabled existing drop-in preserved.
EnvironmentFile optional ~/.config/project-atlas/hardware.env has no producer
assignment. Process/unit output disabled, snapshot absent. Recheck all before any
future execution; these observations are not fresh runtime admission.

## Prepared and tested primitives

recovery_snapshot_validation.py provides no CLI/service operations: independently
supplied strict HTTP/resource admission, durable one-activation/one-rollback budget,
five-second callback-fill deadline, real snapshot freshness/atomic-read validation,
update counting and40s validation bound. Snapshot readiness is never substituted
for independent safety before it becomes valid. Any admitted snapshot loss latches.
Independent safety older than1.5s rejects even when snapshot appears fresh.
Six focused offline tests PASS in0.022s. No synthetic performance benchmark repeated.

## Proposed controlled procedure (NOT executable authorization)

1. Lock single-use transaction; hash checks, verified config/file backups, private
   0700 jetson-owned runtime directory and no existing writer/symlink. Check actual
   PID environment and effective systemd environment; avoid EnvironmentFile override.
2. Start independent safety/resource supervision from unchanged Dashboard API.
   Use existing bounded HTTP<=0.5s requests, strict freshness/encoder/policy tests,
   one-second CPU intervals. Require CPU<75%,RAM<80%,temperature<70C admission;
   unchanged guard rejection CPU>75%,RAM>80%,temperature>=70C. Missing/invalid data
   fails closed; no averaging or startup exception. Dashboard stays running.
3. Ten-second baseline; record wholeCPU/RAM/temp and recovery PID CPU/RSS, wrapper
   cost separately. Confirm E-STOP/zero/stationary/LIVE/Astra OFF.
4. Owned temporary recovery-only drop-in Restart=no and explicit producer opt-in;
   user daemon-reload and verify effective values BEFORE restart. Preserve all
   other configuration. Reserve durable activation budget before issuing one
   nonblocking systemd restart. Continue independent sampling during job polling.
5. Require active new PID, unchanged protected PIDs and fresh complete callbacks
   within5s. Observe30s; record snapshots/receipt ages, update count, recovery CPU
   deltas with PID birth handling and RSS, wholeCPU/RAM/temp. No production failure
   injection, HTTP stop, process kill or stale-source fabrication. Producer failure
   handling remains offline-tested unless separately approved.
6. End bounded validation by removing opt-in under Restart=no, verify effective
   environment, reserve at most one recovery-only restoration restart, validate
   output OFF and safety. Then restore original Restart=always and verify exact
   config. This restoration restart must be included explicitly in future approval.
   Preserve original installed candidate files; no need to reinstall backend.

## Failure/rollback design and remaining execution blocker

Before activation restart: remove only owned override and restore original policy,
leaving original process untouched. After activation: stop the owned recovery unit,
remove opt-in, restore exact config. Only if current independent safety is valid
may the single reserved restoration restart be used. Otherwise leave recovery
explicitly stopped, preserve evidence and report manual recovery; E-STOP enforcement
and independent Dashboard safety remain running. Do not stop telemetry/mux/other
services. Never restore Restart=always while an uncontrolled failing start job is
pending. Cancel/quiesce jobs first; no repeated starts.

A crash-safe external cleanup owner and nonblocking restart-job orchestration are
NOT yet assembled/validated by the new primitive tests. Existing generic Policy
has blocking systemctl calls (15s), so it must not be used on the sole sampling
thread. A fully wired independent monitor plus ExecStopPost cleanup, SIGKILL/job
race tests and effective environment restoration tests are required before issuing
a runtime command. Source-level/state-machine tests are not proof of this lifecycle.

NO-GO for runtime activation at this checkpoint. No execution command or activation
approval requested until those remaining supervisor/cleanup tests pass. This is
preparation progress, not a claim that all requested runtime safety work is complete.
Actual recovery callback overhead and real HTTP-independent safety remain unverified.
