# Stage 32: all-process CPU accounting after 56346db

2026-10-21. Diagnostic progress, NOT a performance fix or camera acceptance.
No camera Start, production edit, restart, threshold change or movement.

## What the retained failure proves

The guardian rejected 76.6101695% before driver launch. The retained top-ten
sample used a different interval and cannot identify the exact cause of that
second. Zero frames means depth conversion was not executing. The previously
deployed conversion optimization cannot fix that pre-driver workload.

## New bounded passive measurement

21.9885 seconds, 21 samples, 391-393 processes, all accessible /proc/PID/stat
entries plus /proc/stat. PID birth times prevent reuse errors. No ROS discovery,
new subscriptions, service changes or camera activity. Five existing HTTP safety
snapshots were read. The first helper invocation stopped before sampling because
CPU PSI was unavailable; the corrected observer records that limitation explicitly.
This was not a camera retry. CPU PSI and scheduler latency are NOT measured.

Tick-weighted whole-machine results on six CPUs:

|Measure|Result|
|---|---:|
|Mean busy CPU|71.3972%|
|Individual interval range|68.0885-75.6469%|
|User/nice|55.4781%|
|System|12.4413%|
|Hard IRQ|1.8033%|
|Soft IRQ|1.6745%|
|All matched PID CPU|66.3813%|
|Top ten matched PID CPU|35.2175%|
|Other matched PID CPU|31.1638%|
|Kernel threads (subset of PID accounting)|1.7275%|
|Busy minus matched PID accounting|5.0159 percentage points|

IRQ/softIRQ account for much of the residual; remaining differences cannot be
attributed exactly because snapshots are sequential, exited PIDs can disappear,
and kernel/process accounting boundaries differ. Do not add kernel-thread CPU
to system CPU. Two new/reused PID intervals were excluded from delta accounting.

The observer consumed 1.4162 CPU-seconds: approximately 1.0734 percentage points
of six-core capacity over the sampled duration. Collection took up to 108.6 ms.
This observer is NOT a zero-overhead baseline. Subtracting its average does not
prove that any particular one-second guard window would pass without it.

Largest average processes, percent of ONE core (divide by six for approximate
whole-machine capacity):

|Service/process|One-core CPU|
|---|---:|
|rover-status-web|44.842%|
|Pi camera_node|30.470%|
|rover-base-telemetry|27.469%|
|atlas-voice-companion|24.968%|
|localization monitor|18.419%|
|sensor recovery|15.735%|
|command mux|14.689%|
|safety status|12.870%|
|mission control|11.461%|
|rf2o|10.460%|
|AI annotator|9.278%|
|agent team|9.187%|

NetworkManager, tailscaled, fallback and ModemManager together used about 0.819%
of ONE core (~0.1365% whole-machine). This sample does not implicate network
workloads as a dominant CPU consumer. It does not exclude an earlier burst.

Mean context switches ~26,684/s, interrupts ~15,693/s, runnable count ~10.35,
blocked count zero. These are contention indicators, not proof of deadline misses.

## Timing and protected state

Five HTTP reads took 18.1-62.9 ms. Reported policy ages 0-0.1 s, cmd_vel 0-0.2 s,
LiDAR 0.1-0.7 s, IMU 0-0.1 s, encoders 0.1 s, camera_info 0.3-1.0 s.
These rounded ages do NOT establish callback latency, E-STOP reaction time,
watchdog deadline compliance or worst-case scheduling latency.

Before/after: E-STOP latched (remote unavailable), manual-only, commissioning
disarmed, commands zero, recorder OFF. Protected service identities and restart
counts identical. RAM 67.926% -> 66.885%; maximum temperature 60.531 -> 60.593 C.
No claim of a fresh camera admission pass: the passive trace itself crossed 75%.

## Root cause versus hypotheses

Confirmed: insufficient aggregate headroom exists even without Astra, and
top-ten accounting substantially under-represents the running workload.
Not confirmed: which operation caused the historical 76.61% interval, whether
Python imports/hash/snapshot work supplied its final increment, or whether
interrupt/scheduler behavior caused an actual safety deadline miss.

Source review found existing hot/cold dashboard executors and raw voice
freshness subscriptions; do not repeat those completed optimizations. Dashboard
snapshot processing still computes history-derived rates and builds complete
responses. It is a candidate profiling target, NOT a verified expensive hotspot.
No evidence supports disabling safety, motor, sensor or network services.

## Changes and tests

Added OFFLINE cpu_accounting_report.py with all-PID, tick-weighted reporting,
one-core/aggregate distinction, kernel subset reporting, PID reuse handling and
explicit observer/residual accounting. Seven unit tests pass: units, PID reuse,
kernel subset, >10 processes, invalid clocks, reset counters, weighted windows.
Ran the analyzer against the retained new capture. No runtime code changed.

There is no new before/after production optimization comparison and no measured
production CPU saving to report. Preparing a deployment package now would imply
evidence we do not have. The next focused task is an offline dashboard snapshot
benchmark/profile using representative captured data, preserving identical
payloads, freshness, locking semantics and safety consumers. Only if a redundant
operation is measured should a candidate and rollback package be prepared.
If offline profiling is inconclusive, request a bounded low-overhead stack profile
of the existing web process, not another Astra Start or broad service shutdown.

## Separate 80% admission assessment (NOT implemented)

Changing 75 to 80% reduces nominal six-core reserve from 1.5 to 1.2 cores. That
does not guarantee any particular safety thread receives CPU. Aggregate load,
rounded message ages and a successful stationary camera session are insufficient
to approve it. Existing evidence cannot establish that 80% preserves deadlines.

Before such a policy experiment: enumerate actual mux/control/sensor/watchdog
deadlines; measure maximum and percentile scheduling/callback/stop-path latency
against them under representative bounded load; retain all freshness checks and
physical E-STOP; define automatic rollback and maximum duration. Separate owner
approval would be required for that instrumentation/experiment and any policy
deployment. This report does NOT recommend raising the guard to get a pass.

## Evidence and rollback

Raw private evidence retained, not committed:
`/home/jetson/project-atlas-migration/astra-20261021/cpu-all-processes.json`
and local `artifacts/astra_concurrent_20261021/cpu-all-processes.json`.
SHA256 a824d638a4cf5d51417b06b2daec5d6114b059a74217aa770b575e374de459ad.

No production rollback is necessary: no production file or service changed.
Offline analyzer can be reverted independently; existing deployment backups
remain preserved. Depth/IR settings, Domain 77, calibrated-cloud restrictions,
75/80/70 guards and preview behavior remain unchanged.

Next approval: none for continued offline benchmarking. No deployment candidate
is ready for approval. Any live profiling that alters process scheduling or any
camera Start requires a separately scoped request. Real usable full-session
3D Preview remains unverified; do not repeat a camera attempt on this evidence.
