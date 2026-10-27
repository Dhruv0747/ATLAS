# Stage 28 bounded process/cgroup CPU profiler — prepared, not deployed

Continues06c0ca9. Historical98.84% source remains UNKNOWN. No new Jetson operations, restart, installation, camera or MCU access in this task.

## Implementation

`project_atlas/tools/diagnostics/bounded_process_cpu.py` reuses Stage31's first-eight /proc/stat counters and aggregate busy definition (idle and iowait excluded). Pure standard-library Linux reader: no ROS participant, subprocess, API request, control command or service management. This avoids creating DDS discovery load or repeatedly polling the Dashboard.

Adds raw aggregate counters, monotonic acquisition start/end and wall time, per-process user/system ticks and start identity, cgroup membership, v1 cpuacct.usage/v2 cpu.stat, cgroup inode/device identity, raw deltas and individual collection intervals. Captures every accessible PID rather than a top10 ranking. Process percentages are ONE-core percentages; aggregate is whole-system. Cgroup and process totals overlap and must NEVER be added. Snapshot acquisition is sequential, not an atomic kernel snapshot; acquisition spans explicitly expose skew.

PID reuse is excluded; exits/new PIDs are explicit and no unobserved lifetime is attributed to one interval. Missing/recreated cgroups and unavailable files cannot be treated as zero CPU. Partial observations are retained and stop a guarded run. Fast processes that start and exit between samples may be missing; retained cgroup totals can help but do not fully resolve this. No full command lines, environments or credentials are collected; process comm and cgroup paths remain local diagnostic metadata.

Bounded2..60s duration, one-second sleeps with measured actual intervals, hard alarm duration+5s (max65s),4096-PID/256-group caps,64KiB attribute reads and16MiB output cap. Exclusive-create private JSONL, per-row flush and final fsync; no overwrite of prior evidence. Completed output receives SHA256. Aborted output must also be hashed by the supervising capture procedure. Hard kill/power loss may truncate final line; preserve and classify it rather than silently accepting complete evidence.

CPU75%, RAM80%, temperature70C retained; uses existing Nano-aware read_thermal. Saves offending counters before abort. No CPU-report-only bypass. CPU overload stops profiler; it does not control services or relax production protections. Missing temperature, unavailable process baseline or integrity gaps stop collection. No guarantee of root-level visibility without validated permissions.

## Offline validation and overhead

24 tests PASS:20 profiler tests plus4 existing restart-analysis tests. Covers arithmetic, exact limits, invalid/reset counters, PID reuse/exit, cgroup recreation, v1/v2 resolution and path confinement, names with parentheses, missing thermal observations, invalid duration, no overwrite, preserved CPU rejection, synthetic /proc+cgroup snapshot, unavailable baseline, and no unsupported causal inference.

PC WSL benchmark: five collection calls,31 processes/20 groups; mean process CPU3.1427ms per call, maximum collection wall3.4411ms. Rough estimate at1Hz:0.314% of one PC core for collection alone. NOT a Jetson resource claim and excludes full JSON serialization, thermal reads and durability I/O. Three inaccessible reads were reported in each PC sample; these partial snapshots are not admission evidence. No production workload was simulated as measured Jetson overhead.

Each sample includes profiler CPU-seconds and elapsed time. Future validation must measure the complete process including resource reads and output I/O. Suggested acceptance target: <=1% of one core mean and collection span<=100ms, with all existing resource limits satisfied. A target is not a demonstrated result.

## Single controlled validation plan — future approval

1. Approve only ONE15-second passive stationary profiler validation, no restart or deployment. Verify E-STOP/manual-only/zero commands, recorder/camera OFF, LIVE telemetry and CPU/RAM/temperature admission before starting. Snapshot protected service identities using existing diagnostics.
2. Stage hash-verified profiler plus unchanged thermal helper in a NEW diagnostic directory. Confirm cgroup version/mount roots and read permissions. Do not change permissions automatically; any need for administrator access is a separate explicit action.
3. Run with --duration15 under an outer20-second timeout, preserve stdout/stderr and unique JSONL. Keep production75/80/70 safeguards. Stop on resource or evidence failure, no retry.
4. Verify complete/aborted status, raw/delta arithmetic, file SHA256, per-process/cgroup coverage, identity handling, profiler overhead and protected service states. Correlate monotonic intervals with retained journal events, without interpreting log counts as CPU time.
5. This baseline cannot reproduce restart causality. Only after its overhead/coverage pass should a separately reviewed instrumented recovery-only restart be considered. That would require separate owner approval and a safe rollback plan; no maintenance installation should be bundled into it. Do not request another deployment from baseline-only results.

Current verdict: GO for review of the passive profiler validation plan; NO-GO for maintenance deployment. No production optimization proposed without causal evidence. No automatic next operation.
