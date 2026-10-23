# Offline executor count candidate — not deployed

## Scope and evidence

Continues the45-sample GIL investigation. All execution was on the Windows PC's
WSL Ubuntu22.04/Python3.10 ROS2 Humble, localhost-only domain213. No Jetson ROS
participant, camera session, movement, service change or production installation.
The owner's request to ignore CPU load did not alter any live safeguard.

Read-only capture of Jetson executor source:
`e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010`.
Its `NumberOfEntities.__add__` allocates a result and performs six dynamic
getattr/getattr/setattr operations on each waitable addition. The GIL profile
included this function; it is a confirmed operation, not proof of the whole
Jetson overload's root cause.

## Minimal candidate

`tools/diagnostics/benchmark_executor_counts.py` verifies the exact source hash
and replaces ONLY the single `entity_count += waitable.get_num_entities()` site.
It calls get_num_entities exactly once, then constructs the same count object
using six direct field sums. It does not eliminate the result allocation or
cache counts. No entity is removed, no QoS callback suppressed, no timeout,
polling rate, scheduling or message processing policy changed. Original operands
remain untouched; addition failures do not partially mutate the accumulator.

Generated candidate source SHA256:
`227ea71c4331281e198c28561c34e6707a6645c0b0b0deb5c0155977a0f32d72`.
Only generated in memory. Script contains the complete deterministic patch;
raw captured ROS sources remain local artifacts. No installer or autostart added.

## Measurements

Counting-only benchmark: eight alternating-order rounds,3000 passes/round,
21/82/107 synthetic waitables. Across three runs, count-addition CPU reduction
52.2–56.9%. These counts are representative workloads, not measured live QoS
waitable cardinalities. Native test uses107 real subscriptions in one node;
it does not reproduce the two-node Dashboard's exact traffic or entity mix.

Native exact-source executor (real local ROS handles), median of five batches
of300 idle spin_once(timeout=0) calls, CPU microseconds per call:

| Run | Original | Candidate | Reduction |
|---|---:|---:|---:|
| original first | 584.645 | 542.333 | 7.24% |
| original first repeat | 580.561 | 548.900 | 5.45% |
| candidate first | 570.983 | 524.988 | 8.06% |

This is an exploratory PC executor benchmark, not an ATLAS CPU baseline or
production workload. Zero-timeout spins deliberately measure repeated wait-set
construction; they are NOT a proposed runtime setting. Jetson ARM64 savings,
peak CPU, sensor/control deadlines and Astra headroom remain unmeasured.
No defensible whole-Jetson percentage or promise that this clears75% can be made.

## Tests and failures

39 unit tests passed:6 new candidate tests (including2000 randomized sums,
all six entity kinds, operand preservation, failure atomicity, exact-source and
ROS-isolation guards),11 profile-analysis and22 existing profiling-safety tests.

Both native variants passed ordered delivery of10 messages, subscription dynamic
add/remove with fresh delivery, callback-exception propagation, no execution of
a cancelled callback, and bounded executor shutdown. No physical safety or
deadline certification is implied.

Important unresolved native failure: task cancellation followed by spin raises
KeyError in ready-task lookup in BOTH original and candidate. The candidate did
not introduce it. Compared PC installed executor source: it contains a
`task.cancelled() or task.done()` skip immediately before the corresponding lookup;
the captured Jetson version does not. Do not bundle an unreviewed library update
into this CPU experiment or claim cancellation regression fully passed.

First isolated ROS attempt used domain241, which FastDDS rejected for invalid
port calculation. Corrected harness to localhost domain213; no ATLAS endpoint
was contacted. Repeated PC tests only, never another live profiling attempt.

## Deployment decision and rollback

Candidate prepared, NOT production-ready. It changes third-party executor code,
which would be broader than the previously approved Dashboard-only deployments.
Do not globally patch `/opt/ros` or monkeypatch all ROS processes. Preserve the
current runtime. No deployment approval requested at this stage.

Next necessary validation: isolate and resolve the cancelled-task baseline defect
as a separate reviewed change; extend native tests to concurrent dynamic entities,
QoS events, shutdown/cancellation races and representative loaded callbacks.
If those pass, prepare an opt-in Dashboard-only executor overlay, not a global
library replacement, with exact live-file hash protection and rollback. A later
approved parked comparison must establish actual Jetson resource/deadline impact.

Rollback now: none needed on ATLAS; this commit adds offline tooling/tests/docs
only. Future deployment must back up the exact live Dashboard/overlay files,
restore them on failure and restart only the explicitly approved web service.
White-glass UI, steering, safety,75/80/70 resource limits, camera and navigation
are untouched. Reliable live3D preview and whole-machine CPU relief are NOT proved.
