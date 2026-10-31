# Passive Jetson attribution benchmark — 2026-10-31

Approved package/source: de22ab5. Exactly ONE attempt, PASS. No Recovery start,
ROS/DDS creation, service restart, camera/inference activation or production write.
No retry performed. Recovery incident remains OPEN.

## Integrity and execution

Manifest SHA256 fe5b945f6df055358a9ab5e05b1428b2559a175c1876f8bd408f179069a587a3
and all six package files verified on PC and Jetson before execution. Fresh
preflight required Recovery stopped, camera OFF, E-STOP, zero commands, stationary
encoders, fresh telemetry and CPU<75/RAM<80/temp<70. All three baseline checks passed.
The exact approved wrapper ran under timeout30s with2s TERM-to-KILL fallback.
12observer samples and3after samples completed; no timeout or threshold exception.
Observer baseline timestamp:2026-10-31T02:57:10.397558Z (08:27:10.397558 IST).
Observer elapsed12.010374s. First interval/startup CPU included, not discarded.

| Phase | Samples | CPU avg / peak % | RAM avg / peak % | Temperature peak C |
|---|---:|---:|---:|---:|
| Baseline |3|58.2188 /58.9347|59.6879 /59.7513|63.281|
| Observer |12|60.3196 /63.1218|59.8582 /59.9305|63.343|
| After |3|59.2552 /60.8844|59.7226 /59.7517|63.312|

Observed average whole-host increase during capture:+2.1009percentage points;
after baseline difference:+1.0364points. Not a causal isolated overhead estimate:
background processes remained active, baseline/after each cover only3samples and
the parent also monitors the child. No claim of CPU savings or sustained stability.

Observer cumulative CPU through first sample:0.1724928s (includes interpreter and
imports). Through final sample:0.685159776s, or5.7047% of ONE core over12.010374s;
on six online CPUs this corresponds to about0.9508whole-host percentage points.
Peak recorded RSS20908KiB=20.42MiB. Final-sample CPU is measured before that sample's
last validation/write/exit work, so not exact complete lifetime accounting. It
includes attribution and safety checks, not just /proc reads; parent cost is not
separately isolated. First aggregate CPU sample58.6325%.

Collection covered382visible PIDs and3selected cgroups. Per-snapshot collection
mean40.719ms, max60.479ms (<150ms budget). Observer intervals1.000252–1.001146s.
Two processes exited during scans; both gaps retained, no invented deltas.
Recovery ControlGroup was empty because it was stopped; explicit missing-group
record preserved. No Recovery CPU was manufactured or assumed to be zero usage
in a hypothetical future startup interval.

Measured cgroup mean/peak, ONE-core percent during observer window:
- Localization20.0208 /23.0102
- Dashboard49.1347 /53.0854
- Command mux19.8116 /22.2385
These are this passive test's values, not attribution for the historical93.624%
startup failure. Historical root cause remains UNKNOWN.

## Safety and cleanup

All18safety samples passed; maximum recorded telemetry packet age0.040s.
E-STOP latched, manual-only policy, zero commands and stationary encoder deltas
passed continuously. RAM and all required trusted thermal zones remained within
unchanged limits. No missing thermal readings were treated as zero.

Child PID362046/start_ticks5643586 was reaped; /proc/362046 absent at independent
postflight. All42recorded atlas/rover unit identities, states, restart counts and
cgroup paths matched before/after and an additional read-only postflight.
Recovery: MainPID0, NRestarts0, ActiveState failed (STOPPED), ControlGroup empty.
Astra OFF verified with two empty kernel driver inventories; the existing API
reported driver_stopped=false, so driver absence is based on the authoritative
OFF-plus-process checks, not that boolean alone.

Independent postflight measured CPU57.1675%, RAM59.7657%, temperature63.25C,
telemetry age0.005s, E-STOP latched and stationary. An earlier policy-only postflight
call used a placeholder CPU argument and is NOT CPU measurement evidence; the
subsequent real /proc one-second sample above provides resource verification.

All28saved JSON files passed SHA256 verification remotely and after copying to PC.
result.json: PASS, production_changed=false, recovery_started=false,
cleanup='owned child reaped; no production writes'. ATTEMPT_USED retained.
No rollback of production is necessary; only the new diagnostic staging package
and retained evidence exist. Do not delete its attempt marker or rerun it.

Private evidence (not committed):
Jetson /home/jetson/project-atlas-migration/recovery-attribution-isolated-20261031/evidence
PC C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/recovery-attribution-evidence-20261031
The PC analysis-summary.json is derived analysis, separate from the original
manifest. Raw process/service telemetry stays private.

## Suitability and next gate

PASS for the passive collector on actual Jetson under this workload. It is suitable
as the attribution component of a separately reviewed Recovery-start diagnosis.
This does NOT prove the next Recovery start will remain under75%CPU, and does NOT
restore the stopped service.

Before requesting that separate start: integrate the one-start fail-closed actor
with the verified observer, explicitly handle Recovery's initially absent cgroup
so its creation/cumulative counters are captured, retain full rejected endpoints,
and preserve original policy plus bounded failure handling. Dashboard must remain
available because this observer's independent safety source is Dashboard HTTP,
not the stopped Recovery node. No extra ROS observer is needed.

No further runtime operation is authorized by this result. Central sensor-recovery
coordination remains unavailable; E-STOP/zero/stationary safeguards are preserved.
