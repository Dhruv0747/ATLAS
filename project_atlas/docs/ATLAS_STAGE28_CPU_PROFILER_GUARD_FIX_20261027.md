# Stage 28 CPU profiler safety guard correction — offline PASS

Continues fa01f45/b582cca. Existing counter collection, identity handling and cgroup arithmetic retained; no profiler rebuild, no live session or Jetson change.

## Changed code

- `project_atlas/tools/diagnostics/bounded_process_cpu.py`: fixed-loopback read-only status API with proxies disabled,250ms socket timeout,1MiB response cap; evaluate original stop/manual-only/commissioning/STOPPED/zero-command predicates using existing safety_evidence helper. Require fresh policy/command/API encoder age and LIVE packet age, finite numeric0..1s inclusive after request-duration adjustment. Missing/malformed/timeout data fails closed. Poll before and after each collection interval and final interval; safety checks also bracket baseline collection.
- Linux main-thread750ms SIGALRM cycle watchdog covers API body transfer/JSON parsing, collection, resource reading and normal evidence emission, independently of socket timeout. Missed polling deadlines abort. No retries, no threads left polling, no new ROS participant.
- Resources checked at every interval: CPU>75%, RAM>80%, temperature>=70C reject. No averaging across intervals. Source resource inputs and failed predicates retained. API error bodies/exception texts not logged. Metadata records comparisons and polling/watchdog settings.
- `test_bounded_process_cpu.py`: updated boundary expectations and mocked safety input.
- NEW `test_bounded_cpu_safety.py`: mid-capture injection, simulated full session and actual PC watchdog interruption tests.

## Timing contract

Safety polls begin on a nominal1s sampling schedule; each cycle checks before and after collection. Requests have250ms socket timeout, and the total cycle has750ms watchdog (also catches slow trickle responses). Configured on-schedule failure-detection budget is at most1.75s from a persistent change just after a poll:1s to next cycle plus0.75s deadline. Detected unsafe responses stop before further collection, not after another interval.

This is a userspace Linux bound, NOT a hard real-time maximum: scheduler starvation, delayed Python signal delivery or uninterruptible kernel I/O can extend wall time. Scheduling lateness>0.75s aborts when the process runs again. Abort evidence flushing/fsync is outside the collection decision bound and cannot have an absolute guarantee on broken storage. The profiler never controls E-STOP or motors; independent robot safety remains essential.

Fifteen scheduled intervals include final safety/resource verification; nominal15s capture may incur up to the final bounded cycle for verification. Retain an outer timeout for cleanup in the eventual separately reviewed live command. No live command executed or provided as permission to run.

## Tests

76 offline tests PASS on PC Ubuntu22.04: profiler/counter tests, new continuous guard tests, existing safety evidence tests and restart analyzer. Simulated full15-second run has16 counter snapshots,15 resource samples and32 safety polls. Covers E-STOP release, nonzero command, wrong mode, stale/non-LIVE telemetry, missing observations, invalid ages, API timeout/malformed JSON/oversize body, CPU75.001%, RAM81%, temperature70.0/70.01C, and abort evidence with no subsequent collection. PC tests demonstrate a blocked request interrupted by750ms watchdog; these are not Jetson latency/overhead measurements.

Dependencies for future isolated staging: profiler, unchanged offboard_bridge_preflight.py, and existing stm32_readback/safety_evidence.py under its package path. Keep original helpers hash-verified. No production service files changed.

## Verdict / next gate

Offline PASS; ready for separate approval of ONE guarded passive15-second Jetson validation after fresh safety/resources, source/package hashes and physical actuator isolation confirmation. No restart, deployment or camera start included. Jetson overhead now includes up to two read-only status requests per interval and must be measured; earlier3.14ms PC collection benchmark excludes these new checks. Process read permission failures remain fail-closed and may block validation.

Original98.84% source remains unknown. This correction does not justify a maintenance retry or B1/B2. Do not consume the previous hash-specific authorization for this changed candidate. No safety threshold raised or production setting changed.
