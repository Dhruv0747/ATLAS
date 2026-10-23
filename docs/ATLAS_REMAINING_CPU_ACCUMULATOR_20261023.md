# Remaining CPU investigation — 2026-10-23

## Decision

No new production fix is ready. The next executor allocation candidate is
REJECTED FOR DEPLOYMENT because the longer matched-work experiment did not
confirm useful savings. Existing deployed three-file executor remains unchanged.
No services restarted/stopped, Astra started, movement, recording, steering or UI
changes. Production75% CPU/80% RAM/70C guards remain unchanged.

## New live observations (read-only)

The previous deployment's 20-sample comparison remains the baseline: whole Jetson
71.218 to71.100%, Dashboard46.869 to44.652% of one core. Do not reinterpret that
small whole-system difference as an Astra readiness pass.

A separate ten-interval procfs observation completed with existing admission,
safety, Astra-OFF and protected-service identity checks. Observer process CPU
was1.015 seconds total, including safety snapshot processing. Procfs intervals
were approximately1.05seconds; checks occur between intervals, not continuously.
No new ROS participant was created by this observer.

Illustrative first interval (not session averages):

| Process | PID | CPU, % of one core |
|---|---:|---:|
| Dashboard |94624|49.16|
| Existing Pi Camera node |2586|32.14|
| Yahboom telemetry |3351|27.42|
| Voice companion |2021|25.52|
| Localization monitor |1948|22.69|
| Sensor recovery |1905|17.02|
| Command mux |1852|14.18|
| Kernel kswapd0 |127|12.29|

Whole-Jetson CPU in that interval was71.677%. All numeric /proc PID entries were
considered, not just top10. Exited/reused PID identities are excluded; very short
processes can be missed. Raw stdout was truncated by the tool, so this report
does NOT claim an exact aggregate process ranking over all ten intervals. The
quoted first interval, completion flag and observer CPU are retained in tool
output. Do not infer hot functions solely from process CPU.

Follow-up read: swap usage0MiB, available memory2376MiB of7620MiB. Kernel PSI CPU
and memory files are unavailable. kswapd activity alone does not prove swap
thrashing or an actionable memory leak. No swap/governor/scheduling change made.
The distributed load includes useful functions; no service is designated
redundant merely because it consumes CPU. Voice already uses raw freshness-only
scan/IMU subscriptions; recovery already uses raw subscriptions where applicable.
Repeating that optimization or removing wake-word functionality is not justified.

## Offline candidate

Existing captured executor evidence identified wait-set processing as a hot
region. Source inspection confirms a new NumberOfEntities object is allocated
for each waitable addition on each wait-set construction. Experimental code
reuses the fresh local accumulator instead. Every RHS sum evaluates before
assignment, retaining failure atomicity; returned waitable counts are untouched.
No entity cache, QoS removal, timer change or scheduling change is introduced.
This confirms avoidable allocations, NOT that they dominate remaining CPU.

Only offline generator/benchmark/test files changed. The generator requires the
exact captured executor hash and builds on the already-deployed cancellation and
count corrections. Optional offline two-file package preparation has baseline
hash checks and original-byte backups; it is not a production installer. No
deployment package is recommended from this result.

## Tests and measurements

PC WSL Ubuntu22.04 native ROS2 Humble, localhost-only domain213. Never production
domain77. Four count/source checks, one package/rollback check and five inherited
QoS/concurrent-shutdown scenarios: **10 tests passed**, no skips. An initial test
harness assumed __dict__ on a slots object; corrected to inspect declared fields
before the passing run. No production defect was inferred from that harness error.

Pilot6 alternating pairs,300rounds:385200messages delivered,median paired saving
2.291%. The larger preplanned comparison supersedes that optimistic pilot:

| Long run metric | Deployed executor | Candidate |
|---|---:|---:|
| Process CPU total, seconds |32.59196|32.45659|
| Messages delivered |1070000|1070000|
| Worst observed latency, ms |7.35517|8.41751|

Ten AB/BA pairs,1000rounds,107publishers/subscriptions;2.14million total messages,
zero missing/ordering errors. Timers, dynamic entities and cancellation checks
remained exercised. Five pairs improved; five worsened. Paired savings percent:
0.879,1.203,2.023,2.311,5.928,-2.325,-0.831,-0.887,-2.079,-2.415.
Median **0.02432%**, pooled total reduction0.415%. This is not meaningful proven
headroom. Different timer counts and shared PC workload remain confounders;
latency numbers are observations, not safety deadline certification.

Local artifacts under `artifacts/executor_benchmark_20261023/`:
- accumulator-loaded-long.json SHA256 `dcfffb0f9db8c0a6be9e50508e4a9f882237e7f0f601d843177395e948542998`
- accumulator-loaded.json SHA256 `c8cb88c3b66245d40cb970a1147a4ffaf0bb7a4bdb2b5ba7ef8b34569b0caf34`

Raw generated results remain local; benchmark and tests are versioned.

## Remaining necessary work

Next useful measurement is bounded, thread-tagged on-CPU attribution of the
voice companion (PID2021 in this session), separating audio/wake processing,
ROS dispatch and inference. Existing Dashboard-only native/GIL profiles cannot
answer that question. Verify current PID/start-time and fresh safety first;
attaching a profiler may require owner administrator execution. Do not substitute
another general executor micro-optimization or stop useful services without
evidence. No new physical test is needed. Astra resource readiness is unresolved.

Rollback: none needed, no production file changed. Existing deployed package
and verified rollback from ATLAS_EXECUTOR_DEPLOYMENT_RETRY_20261023.md remain valid.
