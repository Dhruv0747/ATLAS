# Dashboard CPU: retained administrator capture recovered and analyzed

23 October 2026; continuation after white-glass deployment e60eb0f.
**CPU defect unresolved. No runtime optimization or deployment claimed.**

## New evidence, not a repeated camera experiment

Recovered the previously completed administrator helper result from
`/home/jetson/project-atlas-migration/admin-diag-20261023/evidence-irp_fcmc/`.
It reports PASS, dashboard PID2013, CLK_TCK100 and unchanged protected services.
This is the earlier boot's capture, not a new live profiler run. The prior
documentation saying the helper had never executed is superseded by this evidence.
Raw stacks and telemetry remain private/untracked locally and on Jetson.

Input SHA256:

- stacks.json: `de5411197ab37ef211c6c46b9b688d9244869aed630eb0210bd2eef1921cac66`
- telemetry.jsonl: `40dda955a3b827233af4b761d517273c68400a72c3fc27d9c65da2324f74e6d9`

New offline analyzer excludes cross-phase intervals, exited/reused threads and
invalid data. It uses proc tick deltas for CPU, not stack observation counts.
Short same-phase windows contain4.006s baseline,10.005s profile,4.003s postflight.
These are descriptive measurements, not a statistically controlled savings trial.

| Measurement | Baseline | Profile | Postflight |
| --- | ---: | ---: | ---: |
| Whole CPU mean |70.81%|72.29%|71.39%|
| Whole CPU peak |72.09%|73.73%|72.85%|
| Linux TID5559 CPU, one-core scale |26.96%|25.89%|26.98%|
| Linux TID5716 CPU, one-core scale |13.98%|13.99%|14.49%|
| Observer CPU, one-core scale |2.35%|2.32%|2.29%|

The elevated whole-machine profile window cannot be assigned entirely to the
profiler: background workload is uncontrolled. The two hot threads did not show
a corresponding increase. Observer cost is measured separately, not subtracted
as though the remainder were an exact uninstrumented baseline.

Python profiles name `Thread-1 (_spin)` and `atlas-web-status-spin`, each199
observations. Respectively58.29% and78.89% of their weighted observations land at
the executor wait/return boundary. Current Jetson executor SHA256 remains
`e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010`;
line678 is the statement immediately after `wait_set.wait(timeout_nsec)`.
This confirms the source mapping, NOT time spent executing that statement.
Other observed paths include wait-set construction, context management,
subscription taking and readiness checks. HTTP thread has only5 observations;
it is not a representative HTTP-load benchmark.

**Important evidence gap:** py-spy thread labels are Python addresses, not Linux
TIDs. The capture does not map the named Python threads to5559/5716. It has no
native stacks, wait durations, wakeup reasons or callback execution-duration
counts. Therefore it cannot prove busy waiting, DDS event churn, duplicate
callbacks or which native function consumes the measured CPU. Glass rendering
is not part of these Python executor call paths, but client rendering cost is
not measured by this profile.

## Current read-only checks

Jetson reachable over existing Tailscale. Current dashboard hash remains
`98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79`.
White-glass CSS remains
`ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5`.
Fresh admission: CPU69.6817%, RAM66.9978%, maximum temperature59.656C;
manual-only true, commissioning false, E-STOP latched, STOPPED source,
commands zero and recorder off. Existing extra-safety sensor/access check passed.
One sample is not sustained Astra headroom qualification.

`perf` not found on current PATH; perf_event_paranoid2, ptrace_scope1;
`sudo -n true` requires a password. No privilege/sysctl change attempted.
No production file, UI, steering, safety limit, ROS configuration or service
changed; no restart, camera Start, motion or new ROS participant.

## Tested change and next necessary action

Added only offline `analyze_tagged_cpu_capture.py` and8 tests: tick-derived CPU,
exact-source line mapping, PID reuse, phase boundaries, bad time, invalid weights,
interleaved health records and invalid CPU. Existing collapsed-stack analyzer
tests remain applicable. No unsupported runtime fix has been packaged.

The next discriminating step is a bounded, single-dashboard-PID native CPU
profile with native TID attribution and matching passive proc/scheduler counters.
First locate a Jetson-kernel-compatible perf tool or equivalent native profiler;
review its sampling/overhead and fail-closed monitor before owner administrator
execution. Do not reuse the old combined ACL-recovery helper: USB access already
works and must not be changed for profiling. No global ptrace relaxation, ROS
participant creation, service restart or camera test is needed for this plan.
Administrator execution/setup is the remaining permission/tooling blocker.

No blanket executor sleeps, subscription removal, safety polling reductions or
threshold increases are justified. Compact JSON and role-cache candidates remain
too small to establish Astra headroom. No new CPU savings or reliable Preview
admission claimed. Production rollback is unnecessary because nothing deployed;
the white-glass backup and deployed theme remain intact.
