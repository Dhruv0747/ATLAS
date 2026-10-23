# Offline interleaved loaded executor comparison

## Outcome

The combined cancellation/count candidate consumed less process CPU in9/10
paired PC runs: median paired saving6.2527%. One pair was4.6061% worse. This is
measured evidence for this synthetic PC workload, NOT a guarantee of Jetson-wide
CPU savings or enough Astra headroom. No installation or Jetson interaction.

## Method and scope

WSL Ubuntu22.04/Python3.10, native ROS2 Humble, ROS_LOCALHOST_ONLY=1 and domain213.
Load captured exact-source executors in memory. Both variants contain the tested
cancellation guard; only combined adds direct count-field sums. Hashes unchanged:

- Cancellation-only: `d005c1f91ab6e88e74c8f3f062ff5fc750264dff00a2f8217c81cbb7a44d247d`
- Combined: `543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1`

One PC process, alternating AB/BA order across10 pairs. Each variant creates its
own isolated context/node/executor,107 subscriptions and107 local publishers.
Wait for discovery, then1000 batches of107 Int32 messages, draining each batch
before the next. 107000 messages per measured run;20 runs total. A10ms timer,
200 task cancellations per run and a midpoint subscription add/remove exercise
executor behavior. Each executor/context is shut down before the next variant.

This is fixed MESSAGE work, not identical timer callback counts: faster runs
execute fewer timer callbacks. The timer handler is a simple counter; its cost
is not separately subtracted. Warmup is five untimed task spins, not a full
traffic warmup. Process CPU includes local publishing, receiving and DDS threads,
not executor Python alone. CPU seconds are compared for equal delivered messages;
one-core CPU% can exceed100 because DDS threads also run. Setup/discovery excluded.

The workload is saturated local batches in one node, not the live two-node
Dashboard's traffic rates, serialization/UI/TF/AI work, ARM64 environment or
production safety deadlines. No intentional CPU affinity/scheduling changes.
Uncontrolled PC background load and thermal/frequency variability remain.

## Results (all pairs, no favorable-run selection)

| Pair | Paired process CPU saving % |
|---|---:|
| 0 | 3.5085 |
| 1 | 10.6440 |
| 2 | 5.6420 |
| 3 | -4.6061 |
| 4 | 3.9878 |
| 5 | 10.8375 |
| 6 | 7.3867 |
| 7 | 13.0865 |
| 8 | 6.8635 |
| 9 | 4.0237 |

| Metric | Cancellation-only | Combined |
|---|---:|---:|
| Process CPU seconds,10 runs total | 34.647362 | 32.492977 |
| Delivered messages | 1070000 | 1070000 |
| Median of per-run p95 publish-to-callback latency,ms | 2.966258 | 2.702456 |
| Worst observed message latency,ms | 8.110136 | 9.193337 |
| Detected missing/duplicate/out-of-order messages | 0 | 0 |
| Cancelled callbacks executed | 0 | 0 |

All timer counters advanced; no cancellation exceptions or shutdown timeouts.
Combined worst-case latency is WORSE by1.083201ms in this sample. Therefore do
not claim improved worst-case deadlines or blanket no-regression certification.
No confidence interval or Jetson forecast is asserted from these pairs.

Pilot: six pairs of4280 messages/run, median saving1.6795%,5/6 positive; range
-0.2577% to6.7874%. It motivated the longer run and is not discarded as a failure.

Long-run generated evidence retained locally:
`artifacts/executor_benchmark_20261023/loaded-long-result.json`, SHA256
`a052d00e1de1b8c33cf4d3200cb777708c1e0de3b62036744a95429f90dedaeb`.
Raw generated evidence is not committed. Source, test code and these measured
summaries are versioned. Long-run total2.14million messages; pilot51360 additional.

## Reproduction and regression

```bash
source /opt/ros/humble/setup.bash
ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=213 timeout 180s python3 project_atlas/tools/diagnostics/benchmark_executor_loaded.py artifacts/executor_benchmark_20261023/executors.py --pairs 10 --rounds 1000 --output /tmp/atlas-loaded-new-result.json
```

Use a new output path; the report refuses overwrite. Exact captured source hash
required. No default production-domain connection permitted. Native runs assert
bounded shutdown; missing-message timeout fails rather than treating dropped work
as faster execution.

54 automated tests passed:6 new summary-validity tests,9 native cancellation,
6 count equivalence,11 profiler analysis and22 profiler safety tests. Summary
tests reject unequal work, dropped messages, incomplete/duplicate pairs and
invalid CPU; negative savings remain visible. No tests were skipped in the
explicit native run.

## Deployment/remaining work

Offline benefit demonstrated for this bounded workload; production readiness
NOT established. No live CPU/RAM/temperature measurements or resource-policy
changes. White glass, steering, controls, sensor services, cameras and safety
remain untouched. No camera session, motion, recorder or restart.

Before proposing deployment: complete loaded QoS and concurrent entity/shutdown
race coverage and prepare an exact-hash Dashboard-only opt-in overlay/rollback
package, not a global rclpy library replacement. Then request separate approval
for scoped installation and matched parked Jetson measurements. Preserve limits
75% CPU/80% RAM/70C. No approval for a camera test is implied.

Rollback now: no live change to undo; offline tooling is revertible by Git.
