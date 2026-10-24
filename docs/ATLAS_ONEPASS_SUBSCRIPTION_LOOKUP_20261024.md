# Standard-executor subscription lookup candidate

## New operation, not another static-cache attempt

Saved native evidence `evidence-i2a4guhr`, perf SHA256
2b3f614e9a74dc40e6c61ff4662c58555b6cc360dfe2de387e45c136870e54df,
contains two on-CPU samples through `MemoryStrategy::get_subscription_by_handle`
and `SubscriptionBase::get_subscription_handle`, one in each selected thread.
This establishes an active operation, NOT its exact CPU share or that it is the
largest hotspot. There are only15 total samples. The two bond publication samples
are in DDS publish/send paths, not evidence of expensive timer construction.
Do not tune bond timers based on those samples.

Reviewed matching PC Humble16.0.21 source:
https://github.com/ros2/rclcpp/blob/16.0.21/rclcpp/src/rclcpp/memory_strategy.cpp
https://github.com/ros2/rclcpp/blob/16.0.21/rclcpp/include/rclcpp/strategies/allocator_memory_strategy.hpp

`get_next_subscription` performs a handle-to-subscription search, then another
group/subscription traversal to recover the owning group. The candidate returns
both from the first search, still checking node liveness. There is NO cross-call
cache, static executor, changed polling interval or altered heartbeat deadline.
Existing eligibility checks, ready-list removal and node lookup remain intact.

## Implementation scope

- `onepass_lookup.hpp`: local paired lookup with weak-group/node validation.
- `prepare_strategy.py`: generates a privately namespaced variant of the exact
  installed header, changing only those two subscription lookup expressions.
  Source SHA256 must equal
  73504657a39bb47bcf08f2b763d7525d3f11505f54c93b7480b15300f8825e7b.
  Original license retained in generated header. No system header overwritten.
- Fixture `--onepass` passes that strategy to STANDARD SingleThreadedExecutor.
- `--lookup-only` validates edge cases and measures the operation separately.

Helper SHA256: 0ef5cdd6dbe53f0efbaf542f8f4cf0ac03d714d397c1dd722e1a71deb9c0b16d.
Generator SHA256: bf00ee535ffac99a2506dc8c0a2dc0223cc4d4becde9b6ceecc467cf9b023414.

This is a PC-only experimental strategy, not a Nav2 or RMW deployment package.
No live file, service, voice, white-glass UI, steering or safety setting changed.
No camera, recording, restart, Jetson connection or movement. Production limits
remain75% CPU/80% RAM/70C. Offline CPU was report-only as requested.

## Native tests

Private network namespace, Domain216, localhost only; same pinned PC dependencies
as the earlier fixture. C++17 -O2 -Wall -Wextra -Werror build passes.

Standard and candidate both pass21 ordered deliveries, subscription destruction
and recreation, dynamically created timer, cancelled-timer silence, healthy bond
and missing-heartbeat detection. Standard0.397603s; candidate0.397928s against the
same200ms..1500ms fixture acceptance. The standard executor is retained throughout.

Seven direct cases pass: matched subscription/group identity, unknown handle,
busy callback group not dispatched, available group dispatched, expired node
rejected as eligible owner, destroyed subscription absent, expired group absent.
All480,000 operation-benchmark calls verify the exact expected subscription/group.

## Measurements: do not confuse operation saving with robot saving

Operation benchmark: four alternating AB/BA pairs at each cardinality,20,000
lookups per variant per pair. Real ROS objects, synthetic group cardinality.
PROCESS_CPUTIME_ID, not wall time. One subscription per group; targets rotate.

| Groups | Original mean CPU seconds | Candidate mean | Operation reduction | Saved per lookup |
|---|---:|---:|---:|---:|
|1|0.00209230|0.00135872|35.06%|36.68ns|
|8|0.00868429|0.00450671|48.10%|208.88ns|
|32|0.03110263|0.01537418|50.57%|786.42ns|

Integrated standard-executor fixture: six alternating pairs, exactly100 messages
delivered in each variant, approximately100Hz. No missing messages. Process CPU:

| Pair | Original s | Candidate s |
|---|---:|---:|
|0|0.0536593|0.0543632|
|1|0.0533843|0.0394273|
|2|0.0568882|0.0599083|
|3|0.0464764|0.0443169|
|4|0.0452639|0.0477154|
|5|0.0551909|0.0458273|

Means0.0518105s versus0.0485931s, but THREE pairs regress and THREE improve,
with order/noise sensitivity. **No robust end-to-end CPU saving established.**
Mutation CPU separately ranged original0.000231678..0.000521482s and
candidate0.0002865..0.000977561s; excluded from steady-state numbers, not hidden.
The operation reduction is real in the fixture; aggregate Jetson headroom is
NOT demonstrated. Do not extrapolate35–51% to Nav2 or the whole Jetson. Synthetic
entity count and dispatch rate are not measurements of ATLAS's current graph.

## Readiness and next decision

Preserve this candidate as a small, correctness-passing offline experiment, not
a safety-certified production fix. Exact ARM64/version compatibility, production
graph cardinality/dispatch rate, concurrent entity teardown, broader QoS/services
and matched system measurements remain unvalidated. A full standard-executor
library change is not justified by these small absolute operation savings alone.
Do not install it merely to make progress or reopen static caching.

No new physical test or installation approval requested. The existing saved
profile is insufficient to identify a dominant avoidable cost beyond the tested
operations. To choose a high-impact production change, obtain separately approved
more representative attribution; don't repeatedly rerun this microbenchmark.

Reproduction from repository root with existing private build dependencies:
`bash project_atlas/tools/diagnostics/native_ros_entities/run_isolated.sh --onepass`
and `--lookup-only`. Generated strategy, builds and raw data stay untracked.
Rollback: no production rollback needed. Revert only the offline candidate commit
if desired; live executor remains unchanged. No deployment script is supplied.
