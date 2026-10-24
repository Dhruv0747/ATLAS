# Native wait-set retention experiment — offline only

## Outcome

There is a measurable micro-optimization opportunity in repeated FastDDS
condition attachment/detachment. Retaining unchanged conditions is cheaper in
an isolated fixture. **Not a production-safe RMW patch, not a Jetson CPU fix.**
No installation,service restart,camera start,recording,movement,voice/UI or safety
limit change. No Jetson connection during this experiment. Owner's CPU exception
applies to offline work only here; production safeguards remain75%/80%/70C.

## Method

PC WSL Ubuntu22.04,x86_64,native FastDDS2.6.12; captured Jetson uses2.6.11/ARM64.
Fixture creates only WaitSet/GuardCondition objects: zero DDS participants,
publishers,subscribers,ROS nodes or network connections. No ROS domain joined.
This targets the attach/detach paths observed in6/15 prior native samples.
Does not reproduce the full rclcpp/RMW execution path or the real bond protocol.

Baseline attaches all conditions,waits for one rotating ready condition,then
detaches all. Candidate attaches once,performs identical triggers/waits,and
detaches at teardown. Both verify the same single ready condition every round.
Condition objects have explicit stable lifetimes,unlike general dynamic ROS
entities. Zero-timeout waits intentionally isolate operation cost; they are NOT
a proposed production polling loop. CPU measured with CLOCK_PROCESS_CPUTIME_ID.

An initial5000-round pilot was too short for robust timing. Superseding run:
500000 rounds/variant,6 alternating AB/BA pairs each at1/8/32 conditions.
18million verified waits total. Runtime bounded30seconds. All18 pairs improved.

| Conditions | Mean baseline CPU s | Mean retained CPU s | Median paired saving |
|---|---:|---:|---:|
|1|0.064475|0.033884|46.93%|
|8|0.285048|0.035418|87.58%|
|32|1.032547|0.048920|95.26%|

These percentages apply ONLY to this hot-loop fixture. At8 conditions the mean
absolute saving is about0.499 microseconds per wait on this PC. Actual Jetson
condition counts,wakeup rates,ARM performance and integration costs are unknown.
Do not claim87.58% less Nav2 CPU or that Astra now has enough headroom.
Raw local result: artifacts/native_waitset_20261024/result-long.json,not committed.

## Correctness checks

Passed native timeout with no trigger;single-ready identity;dynamic attachment;
removal of a triggered condition;no stale readiness after removal;trigger reset;
blocked wait awakened from a separate thread;detach before destruction;empty
condition set after teardown. The long run checks readiness on every iteration.
Separate AddressSanitizer/UndefinedBehaviorSanitizer fixture build passed
--check-only without diagnostics. Linked vendor library is not sanitizer-built,
so this is not full middleware memory-safety certification.

Initial compile caught misleading indentation under-Werror;fixed. Initial run
needed LD_LIBRARY_PATH for vendor dependencies;set only for the PC command.
No package install or system configuration changes needed.

## Why this cannot be installed yet

ROS wait sets can gain/lose subscriptions,services,guard conditions and timers,
and their lifetime/ownership can change across waits. Blind retention could use
destroyed entities or miss discovery/shutdown wakeups. The fixture avoids that
hazard by construction; it does NOT prove the same property in live RMW.
Bond publish/failure-detection behavior is untested: bondcpp is not available in
this PC fixture. No heartbeat periods,timeout thresholds or QoS are changed.

Next engineering step: inspect the exact2.6.11 RMW wait-set ownership path and
build a correctness-preserving invalidation strategy,then test real ROS dynamic
entities,discovery,delivery,shutdown and bond-failure timing in isolation. Reject
if lifecycle invariants cannot be preserved. No production deployment approval
requested now; no new physical test needed. Remaining blocker is integration
correctness and actual end-to-end saving,not permission to weaken CPU guards.

## Reproduction and rollback

Source: project_atlas/tools/diagnostics/benchmark_native_waitset.cpp.
Build on PC only with g++17,-O2,-Wall,-Wextra,-Werror,
-I/opt/ros/humble/include/fastrtps,-L/opt/ros/humble/lib,-lfastrtps,-lpthread.
Set LD_LIBRARY_PATH=/opt/ros/humble/lib for this command;bound run with timeout30s.
Sanitizer correctness build uses-O1,-g,-fsanitize=address,undefined and--check-only.
No production rollback needed: only offline benchmark/report added.
