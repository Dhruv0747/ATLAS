# Observer startup CPU investigation — NO-GO

Review baseline: 5808376. No production changes, restarts, camera or inference
activation, new ROS participant, or deployment retry in this investigation.

## Evidence and attribution

Retained evidence: `/home/jetson/project-atlas-migration/web-activation-once-timing-20261030/`.
Manifest SHA256: `1203b2d8dfdea503343dd664dc0904da6858f1c25e4bca568e7751d184621a8d`.

Aggregate windows began at monotonic 25439.288693056 and 25440.288857235 seconds.
Their durations were 1.001133881 and 1.000164179 seconds; CPU was 70.6485% then
92.9293%. The unchanged CPU gate rejected the second sample before installation,
restart-policy changes or web restart. No timing exemption is justified.

| Measured contributor | Evidence |
| --- | --- |
| New observer PID205843 | First observation contains 54 user + 22 system ticks at 100Hz: 0.76 CPU-seconds since process birth. Next interval adds 15 ticks over 1.08546s: 13.82% of one core. |
| Supervisor PID205815 | 19.83%, then 20.25% of one core. Cumulative process CPU 0.5719 then 0.8124 seconds. |
| Full process/cgroup collection | Wall duration 0.2719 then 0.7221 seconds; wall time includes scheduling delay and is not all CPU work. |
| Localization cgroup | 24.27% then 81.52% of one core in overlapping windows. |
| Existing Pi Camera cgroup | 31.76% then 33.94% of one core; not Astra. |
| Dashboard process | 38.85% then 21.82% of one core. |

Process and cgroup windows differ from aggregate windows. New PIDs lack a prior
process sample; parent/child cgroups overlap. These numbers cannot be summed into
an exact attribution of the 92.93% whole-device sample. Python imports, ROS
initialization and DDS discovery are not separated by these counters. No saved
stack trace proves which operation dominated. Full causal root cause remains
UNKNOWN; observer startup and supervisor overhead are confirmed contributors,
with concurrent localization activity. Only two capture windows exist: one high
sample followed by cleanup and later roughly 61–64% postflight samples establishes
recovery, not the duration the overload would have had without abort.

## Existing monitoring is not a drop-in safety replacement

The monitoring watchdog reads port8088 `/api/status`; it cannot independently
verify safety while that web service is down. Read-only inspection also found
that watchdog failed with exit78 since 21:47:56 IST; it was not repaired or
restarted. Grafana samples cannot replace local fresh one-second safety gates.

Existing sensor recovery already subscribes to policy, command and encoder
health. However its summaries omit manual/commissioning policy fields and use
only three Twist components with a 0.01 motion tolerance. Those summaries are
NOT acceptable substitutes for exact-zero six-component checks.

A candidate local snapshot adapter is provided, NOT integrated or deployed:
`project_atlas/tools/vision3d/existing_safety_snapshot.py`. A future existing
subscriber integration must export original raw callback values and monotonic
receipt times, not those permissive summaries. Consumer reuses the current
strict Safety evaluator. No ROS imports, new node, subscriptions or loop are
introduced by this helper. Boot identity and producer age (0.75s) are checked;
source ages remain subject to the existing one-second limit. Republishing old
observations cannot make them fresh.

Integration contract: one trusted writer, private0700 runtime directory, atomic
0600 file replacement, same host monotonic clock/boot ID, and caller retaining
latched session failures. A producer crash or missed update rejects admission.
This ephemeral cache is not durable evidence. Resource guards remain independent
and unchanged: CPU75%, RAM80%, temperature rejection at70C.

## Focused offline validation

Ubuntu22.04 WSL PC: `python3 -B -m unittest -v test_existing_safety_snapshot`:
4 tests PASS. Cases include stale/future/wrong-boot producer, old source timestamps,
nonzero command, invalid policy/encoder data, missing/malformed file and encoder
motion. Native filesystem benchmark: 1000 publish+verify pairs used 0.08391056
CPU-seconds (about84 microseconds/pair). This is PC helper cost, not Jetson
measurement, ROS integration validation or proof of sufficient CPU headroom.

Collector path-resolution memoization was considered but is not implemented or
claimed as a saving. The current staged backend, observer and activation package
remain unchanged. Avoid introducing another unmeasured activation-package change.

## Decision

NO-GO for another activation. The helper demonstrates a low-cost offline path,
not a resolved hardware startup blocker. Remaining work is a separately reviewed
raw-observation export integration, fail-closed lifecycle/HTTP-outage tests and
measured Jetson overhead before any restart retry can be proposed. No retry
approval is requested. Preserve existing Dashboard, staged backend and evidence.
