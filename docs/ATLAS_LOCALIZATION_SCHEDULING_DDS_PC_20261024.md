# Production scheduling/DDS differences: bounded PC experiment

## What changed in this investigation

Read saved production unit configuration and prior journal evidence; no Jetson
commands this turn. Monitor unit has CPUQuota60% (one core),Nice10,
FASTDDS_BUILTIN_TRANSPORTS=UDPv4 and ROS_LOCALHOST_ONLY=0. Repository mission unit
has CPUWeight1000. We did not newly verify the live effective mission weight.
Earlier isolated worker ran in an SSH session without the production quota.

Added a four-case native Humble PC experiment. Each process runs in a disposable
PC systemd unit with PrivateNetwork=yes,30s runtime bound,2s stop timeout and
control-group cleanup. ROS domain214 remains localhost-only. No existing service
restarted. Separate isolated HOME for diagnostic writes. Application never spun;
no control/service calls. Only synthetic1Hz heartbeat nodes spin.

## Results

| PC case | Constructor wall ms | Process CPU ms | Max receive gap s | Max delivery ms |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 122.627 | 24.896 | 1.000989 | 1.071 |
| CPU quota60% + Nice10 | 30.308 | 16.196 | 1.000531 | 0.716 |
| UDPv4 environment | 29.949 | 16.095 | 1.000199 | 0.437 |
| Quota + priority + UDPv4 environment | 33.916 | 19.229 | 1.000106 | 0.370 |

All20/20 messages arrived; no gap exceeded2s. Quota cases confirmed cpu.max
`60000 100000` and Nice10. Quota-only nr_throttled0. Combined nr_throttled3,
throttled_usec70068 across the entire child lifetime, not constructor attribution.
Unconstrained cases had no readable cpu.max, reported UNKNOWN, not guessed.
Synthetic publisher/receiver share the child cgroup; production owners do not.

This is one ordered four-case experiment, not a statistical performance study.
First-run/cache effects can explain timing differences; no speedup is claimed.
The UDPv4 environment was verified, not the vendor's actual selected transports;
transport sockets/packet paths were not captured. PrivateNetwork and localhost
intentionally omit the production network graph and cannot reproduce its
discovery/reconnection load. No artificial100% CPU saturation was introduced.

## Conclusion / safe fix decision

Original stale mission-status failure **not reproduced**. Measured cgroup
throttling occurred without stale synthetic status, so quota presence alone is
not a demonstrated cause. This does not exonerate quota under different load.
Production graph discovery, concurrent processes, scheduler pressure and actual
mission publisher/Dashboard callback timing remain unresolved.

No evidence-backed production fix is ready. Keep existing quota,priority,DDS,
safety75/80/70 policies,voice and white-glass UI. Do not remove throttling or
reduce sensor freshness checks merely because the isolated workload passes.
Prior failure-evidence logging correction remains offline, not installed.

Next useful evidence is correlated production publisher/receiver scheduling and
discovery during startup, or an offline synthetic graph with comparable entity
counts/load. Existing traces lack that timing; another identical startup retry
would not distinguish these hypotheses. Any live instrumentation or restart needs
separate approval. No driving or camera testing is needed for this issue.

## Tests and evidence

27 offline tests pass. No benchmark processes remained after completion.
Initial PC `systemd-run --user` capability probe failed because that shell lacked
a user bus; then PC system transient units were used under WSL root. No Jetson
service access or workaround occurred. All four workload runs completed once.

Private raw result: artifacts/startup_scheduling_pc_20261024.json
SHA256 `247a9af87deabeb61c702780eb6fb9cc2e987716b7468f92de90b7ed8b359b33`.
Includes per-stage timings,cgroup counters,heartbeat receipts and transient-unit
completion logs. Raw results not committed.

Files changed: benchmark_localization_ros_startup.py adds cgroup/nice/transport
metadata; benchmark_startup_scheduling_pc.py adds PC-only sandbox cases;
test_startup_scheduling_pc.py adds scope contracts; documentation/audit updates.
Previously approved Jetson package bytes are untouched; rebuilding would yield
a different worker hash and require review. No production installation or
rollback needed. Offline revert restores previous diagnostic tooling.
