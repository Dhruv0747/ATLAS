# Original Recovery startup diagnostic — final offline preparation, 2026-10-31

Base09fb3ea. Priority incident remains open. Recovery last verified STOPPED.
No Jetson connection, staging, restart, camera/AI activation or live test this turn.

## GO / approval scope

GO for requesting ONE separately approved bounded original-Recovery startup
attempt using this exact package, subject to fresh safety/configuration/hash checks.
This is diagnostic restoration, not a promise that startup will stay below75%CPU.
No previous activation command or consumed attempt marker may be reused.

Scope to approve: stage package; install only the temporary user-systemd supervisor
unit; user daemon-reload; temporary Recovery-only Restart=no drop-in; at most ONE
start from STOPPED; independent observation; on success restore original policy
and leave verified original Recovery operating; on failure stop Recovery, restore
policy only after quiescence and leave it STOPPED. ZERO restoration/retry starts.
No production Python file replacement is necessary or implemented.

## What changed / reused

New recovery_startup_diagnostic.py integrates the verified passive collector/checks
with the existing bounded Transaction cleanup. New user-unit template, focused tests
and PC package builder. Existing collector, passive safety predicates and transaction
module bytes unchanged. Original Recovery source and its independent saved backup
must BOTH hash to:
5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a
If either differs, abort rather than overwrite. Snapshot opt-in must be absent from
service environment/config; runtime snapshot output must be absent.

The actor reserves its single start durably BEFORE systemctl --no-block start.
Original Restart=always must be verified before temporary Restart=no is installed.
No restart command, retry branch or producer activation exists in the new actor.
Nonblocking systemctl polling uses independent health checks; client deadline3s,
service-start deadline8s. Supervisor systemd RuntimeMaxSec60s, Restart=no,
TimeoutStopSec30s, KillMode=control-group, MemoryMax192M, TasksMax32,16MiB per-file
limit. Observer lifetime45samples maximum, with the existing16MiB collector quota.

## First interval / PID and cgroup attribution

Three fresh preflight samples precede observer creation. The last counter endpoint
is passed to the observer; Python startup is included. Three full observer windows
must pass before the actor starts Recovery. Counters are NEVER reset at start.
The actor records the first observed MainPID plus /proc birth tick atomically,
then rejects any unexpected PID identity change. All visible PIDs are already
sampled regardless of target discovery, permitting identity-based retrospective
joining of a first sample captured before the target file appeared.

The observer lazily reads that PID's actual /proc/PID/cgroup, double-checks birth
identity around membership access and resolves the kernel mount. It attaches
Recovery cgroup accounting when available, without fabricating a stopped-service
path or zero baseline. First cumulative group values remain raw; interval deltas
require two compatible group identities. Missing PID/cgroup is explicit. A tracked
Recovery exit fails closed with its endpoint saved. Independent safety is existing
Dashboard HTTP; no Recovery callback or extra ROS/DDS node supplies this observer.
Dashboard must remain UP; this is NOT a web-restart procedure.

CPU>75%, RAM>80%, temperature>=70C, invalid/missing/stale safety data, nonzero
commands, wheel motion, released E-STOP or observer failure abort. Admission is
strictly CPU<75%, RAM<80%, temp<70C. Sampling intervals outside0.9–1.1s reject.
Health age>1.8s or exited observer rejects the actor. CPU rejection marks health
failed, retains the complete acquired raw PID/group endpoint and raises; no further
HTTP/thermal probe follows an already failed CPU sample. Cleanup stops Recovery
while the observer can finish writing; observer termination follows cleanup, with
at most300ms extra evidence-flush grace. No safety threshold exemption is present.

Limits: polling cannot guarantee identification of a process that lives and exits
entirely between polls; kernel/process endpoints are sequential, not simultaneous.
SIGKILL/storage loss during a write can lose the in-flight sample. Completed atomic
files survive. Never call incomplete attribution exact, or infer a cause from
missing counters. The historical93.624%cause remains UNKNOWN.

## Success requirements and bounds

After the one start, observe20s with independent safety checks. Require same target
PID, ActiveState active, NRestarts0, real READY line from CURRENT boot/current PID
and time since this start, original source hash unchanged, snapshot producer not
enabled, Astra OFF and all unrelated service identities unchanged. Only then restore
original Restart=always while observation remains active and mark transaction
committed. This restores ordinary original service policy, not indefinite proof of
future reliability. A failure before commit invokes fail-closed cleanup.

## Offline validation

8 focused tests PASS (no benchmark rerun):
- Initially missing target, actual membership attachment, target exit.
- PID reuse rejection.
- Integrated FIRST rejected CPU interval preserves PID and cgroup deltas.
- Tracked exit preserves failed endpoint.
- Missing/failed/stale independent observation blocks actor.
- Native PC WSL fake service: one start, PID tracking, no second start, successful
  original policy restoration.
- Native fake service: guard failure stops target, restores policy, idempotent
  cleanup, no restoration start.
- Native fake supervisor: SIGKILL AND RuntimeMaxSec timeout both execute independent
  ExecStopPost cleanup, targetPID0, Restart=always, NRestarts0 afterward.

Tests operate only on uniquely named /run/systemd/system fake PC WSL units, guarded
by Microsoft-kernel/root checks; they cannot run native unit operations on Jetson.
Prior passive collector/guard tests and Jetson benchmark are reused. No full
production startup rehearsal was possible/offline claimed. Package imports and
all file hashes verified without execution.

Reused Jetson evidence from09fb3ea: observer0.68516CPU-s through final12s sample,
20.42MiB; aggregate peak63.12%; all42unit identities unchanged. New actor polling
and lazy target-membership overhead is not measured on Jetson; it remains covered
by unchanged safety rejection. Historical startup may still exceed75% and fail.

## Exact reviewed package

PC path:
C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/recovery-startup-diagnostic-reviewed-20261031
Earlier local preparation directories are superseded; use ONLY this manifest.
SHA256 of SHA256SUMS:
674b15132d1f1a6db7278957e0539f9815a37890e6a1ed652fe063b6f74a4f3c
Main supervisor SHA256:
c3b30b1566046202d0bd5cb327cd2c9d57afc023c8a2f5450ac3467d3c6e0451
Unit SHA256:
20e87bec7e1206e8e82c4e0585db440e3012c023b0439974f9899dc1058b92b1

Build using build_recovery_startup_package.py <NEW-directory>; nine files, exact
manifest required, LF normalized. All retained evidence/private process logs stay
out of Git. Hash the resulting evidence separately after the attempt and preserve
numbered snapshots, baseline, target identity, start intent, transaction, health,
service identities and journal. A missing result is NOT PASS.

## Future execution steps — NOT authorized now

1. Stage this package to a new
   /home/jetson/project-atlas-migration/recovery-startup-diagnostic-20261031.
2. Verify manifest hash above, `sha256sum -c SHA256SUMS`, old source/backup hashes,
   original unit config/policy, stopped/quiescent Recovery and rollback ownership.
   Reject any existing attempt, transaction, override or active supervisor.
3. Confirm local recovery terminal access, E-STOP latched, zero commands,
   stationary encoders, LIVE fresh telemetry, CPU/RAM/temp headroom, Astra OFF.
4. Only after separate approval install the reviewed supervisor unit in
   /run/user/1000/systemd/user/atlas-recovery-startup-diagnostic.service
   (fail if destination already exists), run `systemctl --user daemon-reload`,
   then ONE `systemctl --user start atlas-recovery-startup-diagnostic.service`.
   Do not enable it. Never run the Python actor directly: ExecStopPost is required.
5. Observe the bounded attempt; preserve result/journal. Check actual Recovery PID,
   readiness, snapshot disabled, original policy, protected services and safety.
   Stop after that one attempt regardless of outcome.

## Exact rollback / crash handling

To abort, stop ONLY the supervisor:
`systemctl --user stop atlas-recovery-startup-diagnostic.service`
Its ExecStopPost runs `recovery_startup_diagnostic.py --cleanup` independently of
Python finally, including timeout/SIGKILL. Cleanup issues only a Recovery STOP,
waits for MainPID0 AND no pending job, removes only its exact owned drop-in and
restores original Restart policy by user daemon-reload. No files were replaced and
no recovery start is included in cleanup. It is idempotent.

If stop cannot quiesce the service within the cleanup deadline, retain Restart=no,
report cleanup failure and obtain manual recovery instructions; NEVER remove the
bound or start another instance blindly. If policy ownership differs, stop and
report rather than deleting someone else's configuration. No automatic retry.

After supervisor is inactive and cleanup is verified, its exact runtime unit may
be removed and user daemon-reload performed. Retain staging/evidence/ATTEMPT_USED.
If independent cleanup itself failed, do not remove its unit or drop-in. A manually
invoked `python3 -B <stage>/recovery_startup_diagnostic.py --cleanup` is appropriate
only after confirming the supervisor is stopped and transaction ownership matches;
it never starts a service. On success, committed transaction cleanup intentionally
leaves the validated original Recovery service active.

## Remaining risk / next approval

The passive benchmark shows the collector is viable, not that Recovery startup is
safe below75%. Startup attribution may still be incomplete for very short-lived
processes. Current safety state is not newly checked here. Request approval for
ONE controlled diagnostic restoration with one start, no retry, failure leaves
Recovery stopped and exact original policy restored where safely possible.
No Astra, inference, backend, navigation, movement, firmware or controller changes.
