# Voice CPU capture — verified result

The owner-supplied command succeeded. An earlier directory check found no voice
evidence directory; subsequent exact-path retrieval now confirms the saved
capture. No command failure is established and no replacement/retry is needed.
The reason for the earlier absence is not verified; do not call it a permissions
or profiler failure without evidence.

Evidence: `/home/jetson/project-atlas-migration/voice-cpu-20261023/evidence-g7twhac6/`.
Profile10937bytes, SHA256
`fa5e7039dc267ca7371fe26d3f8c7ab83eb2ee7c580f7a96128e5c1071f0fc3f`.
Remote checksum matches owner report and downloaded file. py-spy exit0,
65 samples,0 reported errors. Completed five baseline,ten profile,five postflight
guard samples. All protected PIDs/restart counts unchanged, including voice2021/0
and Dashboard94624/0. No production changes, camera start or movement.

## New observations

| Window | Whole-Jetson mean CPU % | Peak CPU % |
|---|---:|---:|
| Baseline,5 samples |70.683|73.456|
| Profile,10 samples |70.248|72.355|
| Postflight,5 samples |70.974|73.958|

The diagnostic-only CPU exception was authorized; even so these sampled values
remained below75%. This is not a camera admission or long-term resource pass.
Differences between short windows do not establish negative profiler overhead.

64 Python GIL samples belong to MainThread;1 to serial_loop.63 contain ROS spin,
54 contain wait_for_ready_callbacks. Leaf samples include QoS wait-set insertion,
entity counting, readiness, context-manager teardown and count addition. Native
main TID2021 consumed approximately21.98%,22.87%,23.48% of one core across the
first-to-last sample boundaries in each window. Thread tick counts support real
main-thread CPU activity, but a GIL stack at a wait call does not itself prove
busy waiting. Python thread addresses are not Linux TIDs; main-thread identity
is known, other thread address mappings are not inferred.

There is no evidence in this short parked capture that language inference or
audio processing dominates voice CPU. It cannot characterize active speech,
GIL-released native processing or all future conversational workloads.

## Next engineering action

Evaluate reuse of the already-tested private executor in the voice node OFFLINE,
against its actual subscription/timer workload, preserving wake-word, audio,
announcements, QoS, shutdown and motion safety. Existing Dashboard-only results
do not prove voice-process savings. Do not apply the rejected accumulator change,
disable QoS events, reduce voice functionality or deploy without approval.

No runtime fix implemented in this capture-review step; no new profiler run.
White-glass UI, production safety limits and existing services unchanged. Raw
profile and telemetry downloaded under `artifacts/voice_cpu_20261023/`; not
committed. No rollback needed because production files were not changed.
