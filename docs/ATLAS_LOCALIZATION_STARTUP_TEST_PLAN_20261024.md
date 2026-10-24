# Localization startup: offline findings and safe test design

## Completed offline investigation

Startup order from monitor source is: Python/scientific imports, ROS init,
Node construction, map load/distance transform, search index, TF listener,
publishers/client/subscriptions/timers, ManualLocationCheck imports/map identity,
additional subscriptions/services, initial diagnostic status write, then spin.
The retained rollback traceback stops in manual service construction, before
spin. The prior paced executor benchmark deliberately skipped construction,
map loading, search and status writes; it cannot qualify restart cost.

Added PC-only `benchmark_localization_startup_pure.py`. It executes only pure
imports/map operations, with per-stage monotonic wall and process CPU timing.
No ROS initialization, subscriptions, control, HTTP calls or production writes.
ARM64 execution is refused by this PC harness. Three fresh Python processes
ran in WSL Ubuntu22.04/x86_64. OS file cache was NOT flushed.

| Stage | Wall range, ms | Process CPU range, ms |
| --- | ---: | ---: |
| NumPy/SciPy/core import | 122.91–204.15 | 73.74–106.49 |
| Map load and distance transform | 5.95–18.19 | 2.84–3.78 |
| Search index construction | 0.55–0.64 | 0.57–0.67 |
| Cached index | 0.0035–0.0057 | 0.0036–0.0060 |
| Manual-check module import | 12.37–28.70 | 2.45–6.72 |
| Map identity hash | 2.91–4.15 | 0.37–0.58 |

Map218x187,8636 candidate cells. Local map identity:
`0c3da95dc4fc182864fc05a87dd5937a4a74624e7ce4de347f4f23a855053814`.
Repository core SHA256 `55cf27e7f1d11806abd0911f1738020eacfeb45e5e5981ce6d48a78a3ca135d0`;
normalized source matches previously captured live core (line endings differ).
This is a local saved map, not a newly verified production-map identity.
Results are retained in task tool output; not represented as Jetson measurements.

14 tests pass:3 new timing/error/scope tests plus11 existing installer/candidate
tests. Exact policy and sensor freshness limits unchanged. No optimization is
justified from PC timing alone. No CPU savings claimed.

## Important constraints on interpretation

Live service has Nice10 and CPUQuota60% of ONE core, not60% of the whole Jetson.
Its recorded2.937 CPU seconds over approximately14s includes construction and
shutdown, not stage attribution. Neither this quota nor the stopped process can
alone explain whole-system100% samples. DDS discovery work in other processes,
scheduling delays and publication/subscriber delays remain hypotheses.
Do not remove the quota or raise freshness/CPU limits as a workaround.

## Prepared staged diagnostic design (not deployed or run)

### 1. PC ROS construction experiment

Next implementation must use native Humble on PC, localhost-only private domain,
an isolated HOME and copies of the saved map/source; no production endpoints.
Construct original and candidate nodes WITHOUT spinning application timers or
invoking search, reseed, mission requests or motion callbacks. Explicitly block
service calls. Measure before/after ROS init, Node creation, each entity creation,
ManualLocationCheck and destruction. Use only a synthetic1Hz sequenced status
publisher and a separate private subscriber for delivery timing. Maximum30s per
arm, external watchdog terminates owned process group on timeout. Do not import
the executable main or silently execute production defaults.

Record monotonic time, process CPU, per-thread scheduler wait, RSS and cgroup
CPU-throttling counters where available. Mark unavailable counters unknown.
Use fixed source hashes, one original/candidate comparison, no automatic retry.
The full ROS construction harness is NOT implemented by this pure-stage tool.
This PC step needs no robot movement or production changes.

### 2. Conditional isolated Jetson experiment — separate approval

Only after PC isolation tests pass, propose one bounded construction-only run
on a private localhost domain, no production subscriptions or ROS controls.
Read-only existing Dashboard API observes mission receipt age, sample_time and
observed_hz at1Hz; persistent monitor measures system resources and protected
service identities before launch. Enforce CPU75%, RAM80%,70C, E-STOP, manual-only,
zero commands, recorder/Astra OFF and unchanged freshness limits throughout.
No implicit CPU exception inherited from earlier runs. Stop owned test on any
failed check, retain the failing sample, do not retry. No production restart.

Use10s baseline, at most20s construction, up to5s owned cleanup; preserve the
source package, timestamps, hashes, bounded logs and final health. No image/bag
recording. Cleanup must not delete historical evidence or affect other processes.

### Boundary interpretation and limits

- Synthetic publisher timer gaps: producer scheduling delay in the isolated test.
- Timely publish with late private receive: transport/receiver boundary delayed;
  requires additional scheduler evidence to discriminate those two.
- Private channel timely but production Dashboard age stale: production chain
  remains suspect, not proof of publisher or Dashboard fault.
- Timely Dashboard callback timestamps with delayed HTTP response: snapshot/API
  latency is implicated; retain request start/end separately.
- A complete test with no stale sample does NOT reproduce or fix the original fault.

Actual production publisher and subscriber timing cannot be conclusively
separated from existing Dashboard receipt age alone. If the isolated test leaves
that ambiguous, propose narrowly scoped instrumentation under separate approval,
not repeated reinstalls. No new production-domain participant is authorized here.

## Changes and rollback

Only PC diagnostic script, tests and documentation added. Voice, white-glass UI,
ROS/motor services, maps and safety settings unchanged. No SSH/Jetson commands
were run this turn. No installation, restart, camera start or movement.
Rollback is removal/reversion of offline files; no live rollback needed.
Remaining blocker is measured startup/transport attribution, not steering or
physical testing. Do not deploy the executor candidate from these PC results.
