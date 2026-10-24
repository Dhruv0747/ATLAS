# Ranked CPU capture — Python workload and observer overhead

## Verified capture

Owner-run evidence-33p24t_m completed successfully. Copied existing evidence only;
perf.data5,599,080bytes SHA256
c20b5a7df7c0cc32ce3c64d2cf1a0b30430191bacd9e50374e334606fae10463 matches.
All11 protected identities unchanged,31 safety samples passed with CPU report-only.
RAM maximum66.4824%,temperature66.031C,maximum sample interval1.30974s.
No new recording/profile, production modification,restart,camera start or movement.
Offline perf report decoded the existing file on Jetson; no new perf record.
Existing Pi Camera continued running; Astra remained OFF in recorded checks.

## Ranking (percent of ONE core, not whole-machine percent)

30.324439s accounting interval; process totals and thread subsets kept separate.

| Service/process | One-core CPU |
|---|---:|
| Nav2/AMCL service group, multiple processes |47.09%|
| Dashboard, single process |41.75%|
| Pi Camera process |29.91%|
| Base telemetry |26.91%|
| Voice |21.93%|
| Sensor recovery |15.66%|
| Localization monitor |15.57%|
| Command mux |14.81%|

The observer is a separate, important load: its own `process_time` rose12.782318s,
equivalent to **42.1519% of one core**, approximately7.03percentage points of
six-core capacity. PID439351/session41 measured42.1442%, consistent with this.
Do not label that process as an unexplained permanent ATLAS service. Do not
subtract7.03 from total CPU and call the result a verified observer-free baseline;
induced Dashboard work, contention, scheduling and other workload changes remain.

Whole CPU baseline75.8648%mean/80.5324%peak; profile78.4954%/83.3893%;
postflight78.1890%/82.4415%. All phases have the observer active. These are NOT
clean before/after measurements of an optimization. The previous description
of this particular observer as low-overhead was not supported by this result.

Selected threads: Dashboard94660(25.00%) and94741(12.40%), telemetry3351(22.92%),
Pi Camera2586(20.68%), voice108742(19.98%), mux1852(13.88%). Their group totals
are not added again. Nav2 was not selected this time: its load is spread over
many processes/threads, rather than dominating the top individual threads.

## Native evidence

perf reports zero lost samples and approximately21.63265s sampled user CPU.
Leaf shared-object percentages of SELECTED samples:
Python3.10 60.38%,rclpy binding11.51%,libc9.25%,JPEG6.42%,FastDDS3.96%,
OpenCV core2.08%,libstdc++1.98%,rcl1.42%,RMW1.32%.
This is not a whole-system CPU breakdown. Interpreter symbols do not reveal
Python source functions. The profile therefore cannot justify another native
Nav2 wait-set rewrite or identify a specific Python hot line by itself.
JPEG work exists; redundancy is not proven. Camera source already gates payloads
on subscribers; do not disable useful consumers or reduce image quality blindly.

## Small safe offline correction

Diagnostic `snapshot` resolved executable paths for unrelated processes even
though their cgroup/owner already excluded them from stack profiling. Move that
exclusion before executable resolution. ALL readable process CPU totals remain
recorded. Eligible target validation, thread identity, safety polling, monitoring
cadence and all thresholds remain unchanged. This is a diagnostic optimization,
NOT a deployed robot CPU fix and NOT proof of the cause of all42% observer CPU.

PC /proc scanner AB/BA test:4pairs,20scans each,31process rows retained on every
scan. Original mean0.0326008CPU seconds; candidate0.0170871s, about47.6% lower
for this scanner workload. It excludes Jetson procfs behavior, active ATLAS thread
enumeration and safety HTTP checks. Do not extrapolate to the observer's full
CPU or whole robot. No live validation or automatic profiling retry occurred.

8profiler tests pass, including unrelated process totals retained without an
executable lookup.6new accounting tests pass: no PID/TID double counting, process
reuse, counter/time rejection, cgroup migration and preservation of earlier-group
accounting. New analyzer keys accounting by identity/service epoch.

## State and next necessary evidence

Permanent ATLAS high CPU remains unresolved. Standard executor, voice, white
glass UI, steering and production75/80/70 safeguards untouched. No safe
production patch is justified by interpreter-level stacks alone.

The next discriminating measurement is bounded Python-function attribution for
Dashboard and base telemetry, with reduced/measured observer overhead, separately
approved. Not another native Nav2 microbenchmark, drive, camera attempt or service
restart. Existing earlier Python profiles predate deployed optimizations and do
not prove current line costs. No new admin command or retry issued this turn.

Offline candidate wrapper SHA256
ef9f921590395ef969004a8ba7b731fb5fba39c765b3fc9a6ea6a225dad9c419.
Repository manifest updated for this candidate only. Jetson staged wrapper remains
the originally verified41ec29... version; it was NOT overwritten or executed again.
Generated/raw telemetry and profile remain private/untracked.

Rollback: no production changes to roll back. Revert offline diagnostic commit
if needed; preserve original capture and its historical manifest. No runtime
installation package is offered and no Astra headroom pass is claimed.
