# Isolated snapshot benchmark safety wrapper — 2026-10-31

GO for ONE separately approved isolated benchmark, not producer activation or web
restart. No Jetson benchmark executed. Inert package staged under
/home/jetson/project-atlas-migration/snapshot-benchmark-20261031; six hashes checked
on Jetson, ATTEMPT_USED absent. No production files/environment/services changed.

## Bounds and independence

The child runs synthetic snapshot data in its own private temporary directory.
No ROS initialization, subscriber, camera, systemd mutation or production snapshot
path. Environment is minimal and excludes producer opt-in. Recovery is untouched.
Uses existing pure Safety validator, but synthetic results never count as real
rover safety. HTTP must remain UP throughout this test.

Three1s baseline samples, six2s ABBAAB benchmark phases (12s work,14s child deadline),
three1s after samples. External total timeout30s. Cadence rejects CPU intervals
outside0.9–1.1s; no averaging/exemption. Per-sample policy/manual/E-STOP, exact-zero
reported lin/ang commands, four exact-zero encoder deltas, LIVE packet freshness
and receipt age plus request elapsed checked. CPU>75%, RAM>80%, temperature>=70C,
missing/invalid data or delayed sampling abort. All six Orin thermal zones required.
HTTP total request deadline0.5s, socket timeout0.2s, response limit1MiB.
Safety is sampled, not hard real-time: nominal next-sample detection within1s plus
up to0.5s HTTP deadline and bounded termination; scheduling stalls reject when the
supervisor resumes. External timeout remains a backstop, not a safety exemption.

Child limits:3CPU-seconds,128MiB address space,1MiB per output file,32file descriptors;
wrapper256MiB address space and2MiB per file. Known fixed output count and bounded
HTTP/sample count bound disk usage; no unbounded logs. SIGTERM then SIGKILL with
0.5s waits terminates only owned child. Linux parent-death SIGKILL protects against
wrapper death. Temp directory cleaned after normal completion, guard failure,
handled timeout or interruption. SIGKILL/power loss cannot promise filesystem
cleanup; retained scratch path in result is available after handled failure.
An orphan private temp directory after hard death needs manual inspection, never
broad deletion. No automatic retry. ATTEMPT_USED is not removed on failure.

## Validation

Six focused tests PASS: CPU/RAM/temp boundaries including70C and NaN; missing/stale
telemetry; released E-STOP/nonzero command/encoder motion; real child termination
for timeout, guard failure and interruption; safe cadence; no activation paths.
One additional native end-to-end test PASS in19.116s on PC WSL: real bounded
benchmark child, simulated Jetson resources/HTTP/service identities; six benchmark
rows produced; private temp removed; evidence and attempt marker retained.
Seven tests total. Prior adapter tests reused. These do not measure Jetson cost.

Results include same-cadence aggregateCPU/RAM/temp baseline/active/after samples,
monotonic intervals, wrapperCPU and peakRSS, child per-phaseCPU/wall/peakRSS, and
protected service identities before/after. PeakRSS is a high-water mark, not proof
of incremental RAM. Actual Jetson overhead remains PENDING; old observer0.76CPU-s
is a different workload, not a valid direct savings comparison.

## Prepared command — DO NOT RUN until separate approval

Run as jetson, no sudo. Hash-verified manifest:
d0448da2029b04a6757317f2175f315291989b5ed493de845015ec29ec6236b8

```sh
cd /home/jetson/project-atlas-migration/snapshot-benchmark-20261031 && printf '%s\n' 'd0448da2029b04a6757317f2175f315291989b5ed493de845015ec29ec6236b8  SHA256SUMS' | sha256sum -c - && sha256sum -c SHA256SUMS && timeout --signal=TERM --kill-after=3s 30s /usr/bin/python3 -B snapshot_benchmark_once.py --approved-once
```

Result and evidence/SHA256SUMS remain in package. Review result.json and benchmark
output; FAIL means stop, no rerun/delete-marker workaround. No production rollback
needed: only inert package, private scratch and evidence created. Ctrl+C invokes
child termination and cleanup. Preserve evidence, verify child exited, then remove
only the exact owned scratch directory if hard interruption left it behind. Never
restart recovery/web or alter producer opt-in to clean this benchmark up.

Approval sought: ONE isolated benchmark using this exact package only. No service
restart, production producer activation, backend activation, camera or inference.
