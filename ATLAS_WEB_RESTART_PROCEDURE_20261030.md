# One web-only activation procedure — execution NO-GO

Preparation only. Existing staged backend/package is unchanged; no installation,
restart or activation occurred. CPU75%, RAM80%, temperature below70C unchanged.

## New verified restart-policy blocker

Read-only systemctl inspection: Restart=always, RestartSec=3s,
TimeoutStartSec=90s, TimeoutStopSec=10s, StartLimitIntervalSec=10s,
StartLimitBurst=5. A script with two restart calls does NOT bound systemd's automatic
restarts. Existing staged installer must not be executed as the final procedure.

Required future policy: temporary runtime drop-in affecting ONLY rover-status-web,
Restart=no, with effective property verification after user daemon-reload. This
requires explicit authorization in addition to a web restart. Do not change
production safety services or permanent unit files. Preserve original config/hash.
No override has been created. Restore the exact prior policy only once original or
candidate web service is healthy and stable. If rollback cannot recover, leave
automatic restart suppressed, report web unavailable and retain evidence; no third
start. This exception to automatic policy restoration must be explicitly approved.

## Exact bounded sequence for the eventual reviewed runner

1. Use a new single-use transaction directory. Verify the staged outer manifest
   a586c2d22276ef4f7385387a79cadd581b2c7a52567d89a8754ee051b9c99e68 and every entry.
   Preserve current three-file rollback originals and absence of seven additions.
   Verify inference enabled=false, existing hashes, service identities, no camera/
   AI processes, OFF API, material.css and24 disabled controls.
2. Begin1s aggregate/PID/starttime/cgroup counter collection15s before mutation.
   Use the existing bounded_process_cpu.snapshot/differences/resource_check code;
   do not run its HTTP-dependent CLI through a web outage or replace missing data
   with cached PASS. Keep raw counters, monotonic/wall times, interval/skew, PID
   exits/reuse, cgroup identities, monitor CPU time and collection errors. Record
   all processes, not only top10. Process percent is one-core; aggregate percent
   is whole-machine. Parent/child cgroup totals must not be summed as independent
   consumption. A disappearing PID is unattributed exit, not zero CPU.
3. Immediately before mutation/restart require fresh latched E-STOP, manual-only,
   zero linear/angular commands, fresh LIVE encoder telemetry and four zero deltas,
   recorder OFF, camera/AI absent, CPU<=75%, RAM<=80%, temperature<70C. Any missing,
   invalid/stale observation fails. Existing protected service identities must match.
4. Under separate approval install the runtime Restart=no override, daemon-reload,
   verify effective policy and unchanged protected services. If verification fails,
   restore the untouched policy and STOP before any restart.
5. Apply only the staged three replacements/seven additions (staging has NOT already
   activated these files). Keep configfalse. Verify installed bytes. No controls
   are enabled. No automatic API reload or additional ROS participant.
6. Persist activation-restart token BEFORE issuing exactly one
   `systemctl --user restart rover-status-web`. Bound job completion15s; record
   systemd job/PID identity. If job status is ambiguous, do not overlap another job.
   Resolve/cancel that job explicitly before rollback; unknown status is NO-GO.
7. Allow at most10s bounded HTTP readiness checks (2s/request), only connection
   refused categorized as startup unavailability. API errors/timeouts/malformed
   data reject. No resource rejection is waived during this interval. Full fresh
   safety check immediately after HTTP recovery; never relabel outage PASS.
8. Validate60s maximum with1s guards: read-only feature API, all starts false,
   six panels/24 disabled controls, desktop/mobile, original previews/navigation,
   white-glass styling and unchanged FlySky/Xbox policy/protected services. No
   Start POST, model load or camera request. Record CPU/process/cgroup baseline
   versus activation; no inference-performance claims.
9. On PASS retain candidate, restore original web restart policy, daemon-reload and
   verify without another restart. Preserve evidence/checksums. Stop monitoring.

## Abort and rollback

Abort on any CPU>75%, RAM>80%, temperature>=70C, safety loss/staleness, encoder
movement, camera/AI process, protected service change, bad hash, API/browser failure,
monitor failure or deadline. First failure stays latched; later lower values cannot
permit activation. Continue bounded diagnostics through rollback if safe/readable.

Before a restart has begun, restore only changed candidate files; no restart needed.
After activation restart, restore the three exact originals and remove only matching
seven additions. Refuse to overwrite concurrent changes. Persist rollback token
before ONE web recovery restart. Max15s job completion plus10s readiness and15s
fresh-health observation. Never repeat rollback restart. If CPU/safety is still
failed, mark recovery unverified; do not loop or claim PASS. On unresolved systemd
job/ownership, stop automated commands and request manual recovery, not parallel
restarts. Only original safety/controller services remain in charge.

Total observation budget:180s including15s baseline,15s activation job,10s readiness,
60s validation,40s rollback reserve and bounded evidence overhead. Completion may
be earlier; no extension/retry to obtain passing samples. Deadline must enter the
same single rollback state machine, not kill a shell and leave uncertain state.

## Offline validation and remaining approval gate

Nine existing focused simulated CPU-accounting tests PASS: aggregate/process/cgroup
deltas, PID reuse/exit, cgroup replacement and unchanged75/80/70 boundaries. Existing
13 verifier tests and2 import/staging tests reused. No live profiler was run.

This document is a precise procedure, NOT a newly validated executable orchestrator.
Execution remains NO-GO until two integration gaps are closed offline: independent
fresh E-STOP/zero/encoder observation through the HTTP outage; and transactional
systemd job/restart-budget enforcement including the runtime Restart=no override.
The existing profiler depends on the web API, so merely launching it beside the
restart does not close that safety gap. No claim of native crash recovery is made.

Separate execution approval must explicitly cover applying staged files, temporary
web-only restart-policy override/user daemon-reload, ONE activation restart and at
most ONE rollback restart, including leaving auto-restart suppressed if recovery
fails. It must not authorize camera/inference or a CPU transient exemption. Do not
request or execute this approval until the two integration gaps pass validation.
