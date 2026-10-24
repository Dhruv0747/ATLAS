# Native PC ROS startup experiment — 2026-10-24

## Result and scope

Completed one original/candidate-labeled construction-only pair in native
ROS2 Humble, WSL Ubuntu22.04/x86_64, localhost domain214. No Jetson connections,
production-domain participants, installations, restarts, camera starts or motion.
All production safety limits, voice and white-glass UI remain untouched.

The two labels execute the SAME constructor: the executor patch takes effect
only after construction and was deliberately NOT spun. Timing differences
are not optimization savings. This tests whether construction alone disrupts
a synthetic1Hz heartbeat under this PC environment, not deployed AMCL or Nav2.

| Measurement | Original label | Candidate label |
| --- | ---: | ---: |
| rclpy.init wall ms | 7.288 | 2.735 |
| Monitor import wall ms | 43.706 | 49.669 |
| Full constructor wall ms | 62.425 | 31.291 |
| Full constructor process CPU ms | 23.161 | 18.197 |
| App destruction wall ms | 3.654 | 1.961 |
| Maximum heartbeat delivery ms | 1.052 | 1.282 |
| Maximum receive gap seconds | 1.000165 | 1.001077 |
| Sent / received | 5 / 5 | 5 / 5 |
| Gaps above2s | 0 | 0 |
| Peak process RSS KiB | 76224 | 76244 |

Both manual ROS services constructed successfully. Application timers were
cancelled immediately and application node never added to an executor. All
Client.call/call_async operations blocked. Only synthetic publisher/subscriber
nodes spun; they are separate nodes in the same process/executor, not separate
production publisher processes. No search/reseed/control callbacks executed.

Constructor was shorter than the heartbeat period and fell between publishes;
there was no synthetic publish timestamp inside construction. This limits
coverage and must not be represented as stressed concurrent delivery proof.
No CPUQuota60%, Nice10, production discovery topology, sensor traffic or100%
whole-system load was reproduced. Scheduler wait and cgroup throttling are not
attributed by this harness. A clean PC result cannot verify Jetson safety deadlines.

## Isolation, evidence and tests

Captured monitor SHA256:
`cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b`.
AST extraction selects main's definitions/imports only; no main call or runtime
statements. Dependencies are repository versions; map is local saved copy.
Initial diagnostic writes redirected by isolated HOME, not production paths:
`/tmp/atlas-startup-pc-k7vkegmh` and `/tmp/atlas-startup-pc-_1vcle58`.
Temporary evidence retained. Full JSON stage timings are in task tool output.

Each child interpreter has30s external timeout; failure stops the pair without
retry. ROS entities/context and heartbeat thread cleaned up. Post-run process
check found no benchmark process remaining. No subprocesses launched by children.
External discovery-profile environment rejected; ARM64 and nonprivate domains
refused. This harness is PC-only and must not be run on ATLAS.

19 unit/contract tests pass, including5 new tests for exact-source rejection,
AST exclusion of main actions, private domain, ARM64 rejection and no application
spin/service calls; diff whitespace checks pass. Unit tests are not a simulated
production graph or exhaustive network-isolation proof.

Files added:
- project_atlas/tools/diagnostics/benchmark_localization_ros_startup.py
- project_atlas/tests/test_localization_ros_startup.py
- this report; changelog and audit registry entries.

## Root cause and next necessary action

Original stale mission-status failure **not reproduced; root cause unresolved**.
No deterministic constructor failure appeared on the PC. Do not deploy the
executor candidate or increase the2s freshness limit on this evidence.

The remaining discriminating test is separately approved, bounded, isolated
Jetson construction with startup stage CPU/wall timings and per-thread scheduler/
cgroup counters, while observing existing Dashboard receipt timestamps. It must
retain CPU75%,RAM80%,70C and all safety gates, stop on failure, never spin the
application node or alter services, and never retry automatically. A Jetson-ready
guarded package is not supplied by this PC-only harness; it must be prepared and
reviewed before requesting execution. If it fails to reproduce staleness, actual
publisher/subscriber timing instrumentation may still be needed under separate
approval. No manual drive or camera test is needed for this investigation.

Rollback: offline repository revert only; no production files were changed.
