# One approved activation attempt — FAIL before production mutation

Approved controls0367c16911740ac7beb62b7d91652637343a3adf. Exactly one transient
supervisor launch; no retry. The independent observer started and was terminated
during cleanup. No policy override, backend installation or web restart occurred.

## Admission and timeline

Control manifest913afd64eb644d57a12d2b21aaaf9453244c0e9394dbd7006ca71062d805b69e and
all files verified. Reviewed backend20 manifest entries and exact live rollback
hashes matched. E-STOP latched, manual-only, zero commands, fresh LIVE stationary
encoders, recorder OFF, Astra OFF and no camera/AI process.

Preflight CPU59.73/64.00/60.59%, RAM63.0%, temperatures63.093/63.218/63.250C.
23:44:24 IST: single user transient supervisor started.
Initial aggregate counter monotonic25071.332245102; complete process snapshot
finished25071.518948531. Snapshot collection took0.186704s and included381 PIDs,
137 cgroups, no collection errors.
23:44:29: resource guard rejected CPU sample interval; observer ended at
monotonic25074.579155944. 23:44:30: transient unit finished failed, NRestarts0.
Systemd reports2.844s total CPU for the whole temporary unit, including shell,
observer and supervisor; this is not isolated profiler overhead or whole-Jetson CPU.

## Confirmed blocker and evidence limits

The monitor schedules its first next sample one second AFTER complete initial
snapshot collection and persistence, but checks elapsed time from the initial
aggregate-counter timestamp. The measured initial collection alone was186.7ms,
so nominal first spacing exceeds1.1867s before persistence overhead: outside the
unchanged0.9–1.1s measurement-window check. This scheduling mismatch explains the
interval rejection. It is not a measured CPU>75% rejection.

The invalid second snapshot/delta was rejected before being appended, so no valid
process-CPU interval row or actual new peak CPU was retained. The old79.15% cause
remains UNKNOWN. Do not infer low load or a harmless spike from missing evidence.
Fix scheduling relative to aggregate sample timestamps and preserve rejected raw
samples offline before proposing another attempt; do not widen the window or limit.
No such code change or retry was made during this authorized execution.

## Postflight / rollback evidence

All original atlas-/rover- service identities, restart counts and active states
matched. Web remains PID182915, active, NRestarts0, Restart=always. The temporary
override does not exist. Three original live files match exact backup hashes;
all seven backend additions remain absent. Thus rollback was unnecessary, not an
unperformed recovery claim. No production state requires manual recovery.

Fresh postflight CPU59.86/62.07/60.81%, RAM62%, temperature peak63.375C. Latched
E-STOP, zero commands, manual-only and fresh stationary encoders passed. Astra OFF;
no camera/AI worker. Existing Dashboard remains running; new APIs are not activated
and browser/API candidate checks were not reached. Independent observer operation
through actual Jetson HTTP downtime was not tested because no restart occurred.

Private evidence on Jetson:
`/home/jetson/project-atlas-migration/web-activation-once-20261030/`.
Control/service-before snapshot:
`/home/jetson/project-atlas-migration/web-restart-controls-20261030/`.
Windows copy: work/web-activation-once-evidence-20261030.
Evidence manifest SHA256:
`16de2e874781416642cb29c7e4339fc55d5e65bf1f29d96a52eaa600730f28ba`.
controller-result.json records the interval failure; restart-policy.json and
installer result.json are absent because those phases were never entered.

Outcome: FAIL / NO-GO for activation. Attempt consumed. No service recovery commands
are needed. Do not rerun this unit, reset the attempt marker or start an installer.
