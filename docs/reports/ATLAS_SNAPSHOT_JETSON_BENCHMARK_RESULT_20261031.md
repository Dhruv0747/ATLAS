# One isolated Jetson snapshot benchmark — PASS — 2026-10-31

Owner-approved package def7b6c, manifest
`d0448da2029b04a6757317f2175f315291989b5ed493de845015ec29ec6236b8`.
Six package files hash-verified immediately before the single execution. No retry.
Fresh three-sample preflight passed, Astra OFF with empty kernel driver/worker
inventories (legacy driver_stopped field false retained, not treated as authority).
No service restart, ROS node, production producer, inference or motor activation.

## Measurements

| Phase | Samples | CPU average/peak % | RAM average/peak % | Temperature average/peak C |
|---|---:|---:|---:|---:|
| Baseline |3|61.970 /62.799|62.757 /62.803|63.093 /63.187|
| Benchmark window |13|61.239 /62.944|62.796 /62.842|63.089 /63.281|
| After |3|60.942 /62.245|62.737 /62.770|63.073 /63.156|

Same1s aggregate sampling methodology; actual intervals0.99992–1.00110s.
Benchmark work12.0008s, six2s ABBAAB phases, each20 iterations. Whole-device load
variation is not evidence of CPU savings; baseline/after are short3s windows.

Synthetic benchmark process:
- Baseline phases:0.004863904CPU-s over6.000431126wall-s (~0.081% of one core).
- Enabled phases:0.067235776CPU-s over6.000361909wall-s (~1.121% of one core).
- Incremental enabled cost approximately1.04 percentage points of ONE core at10Hz,
  for combined synthetic producer+consumer work. Not whole-Jetson percentage.
- Summed phaseCPU0.072099680s excludes interpreter initialization/other work outside
  phase timers. No claim this is complete process lifetime CPU.
- PeakRSS14064KiB (13.73MiB), unchanged high-water value across phases. This does
  not establish zero incremental allocation or live recovery-node memory cost.
- Wrapper sampledCPU increase0.10544544s across18.027s (~0.585% one core), excluding
  earlier initialization and final evidence/service checks; peakRSS19272KiB.

Old observer0.76CPU-s before first sample is a different startup workload. This
benchmark demonstrates low synthetic adapter cost, not a controlled proof that
removing the ROS observer resolves the original92.93% spike.

## Safety, service identity and cleanup

All19 observations passed latched E-STOP/manual-only, zero reported drive commands,
stationary encoder deltas and fresh LIVE packets. Packet age0.003–0.040s; effective
age checks include API observation age and request duration. No limit exemptions:
CPU75%, RAM80%, temperature<70C. Protected six-unit identities match in wrapper.
Additional before/after atlas-*/rover-* service-state comparison had no differences.
Recovery PID2005 and Dashboard PID182915 remain active, NRestarts0. Producer opt-in
absent. Production snapshot remains absent. No benchmark processes remain and
`/tmp/atlas-snapshot-benchmark-ha8mcs7o` is verified absent. Cleanup VERIFIED.

Evidence retained on Jetson:
`/home/jetson/project-atlas-migration/snapshot-benchmark-20261031/evidence/`
plus protected-before.txt/protected-after.txt in package directory.
Windows private copy:work/snapshot-benchmark-evidence-20261031/evidence.
Evidence SHA256SUMS digest:
`a80d8aa0f65c7d2fc8afcbf0f74614dbee82ae8a1aae355da2cd78749f3959bf`.
Both recorded files pass SHA256 verification. Raw telemetry is not committed.
ATTEMPT_USED retained; do not rerun this package.

## Decision

PASS for the one isolated Jetson benchmark. Adapter cost is suitable for preparing
separately reviewed production integration. NO-GO for immediate backend activation:
real recovery callback scheduling, producer lifecycle during HTTP downtime and
exact-live patch/rollback still require review and separately approved validation.
No production integration was performed or implicitly authorized by this result.
