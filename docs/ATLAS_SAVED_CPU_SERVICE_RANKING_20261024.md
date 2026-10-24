# Saved CPU evidence: service-level ranking, 2026-10-24

## Result and scope

Offline continuation from 68ab788. No Jetson connection, production changes,
restart, camera start, recording or movement. Voice, white glass UI, steering
and the 75% CPU / 80% RAM / 70 C production limits remain untouched.

The largest **single process** in the retained all-PID capture is the Dashboard.
The largest **service group** is atlas-localization.service, which runs Nav2 and
AMCL. This is NOT atlas-localization-monitor.service, the Python process profiled
and tested in the recent startup/executor investigations. Repeating that monitor
test would not identify native Nav2 hot functions.

## Verified measurements

Input: private artifacts/astra_concurrent_20261021/cpu-all-processes.json,
SHA256 a824d638a4cf5d51417b06b2daec5d6114b059a74217aa770b575e374de459ad.
21 snapshots, 21.988519 s, six CPUs, HZ 100. Whole-machine tick-weighted CPU
71.39718%, interval peak 75.64688%. Historical October 21 capture, not a fresh
baseline: later dashboard/voice/safety changes prevent claiming current rankings.

| Group | One-core CPU % | Whole-machine tick share, percentage points |
|---|---:|---:|
| Nav2/AMCL atlas-localization.service | 51.345 | 8.554 |
| Dashboard | 44.842 | 7.471 |
| Pi Camera service | 30.470 | 5.077 |
| Base telemetry | 27.469 | 4.576 |
| Voice | 24.968 | 4.160 |
| Localization monitor | 18.419 | 3.069 |

Nav2 group's 1129 ticks comprise two lifecycle managers (164 and 111), AMCL149,
BT navigator143, controller129, behavior125, planner118, waypoint95, map server93
and launch process2. These are separate processes, not duplicate counts of their
threads. Grouping all similarly named python3 processes would be incorrect.
Both lifecycle managers are explicitly configured in atlas_localization.launch.py
for different node sets; their presence is not evidence of duplicate services.

About 5.016 whole-machine percentage points are unassigned by matched PID deltas.
Process enumeration is not atomic; short-lived processes and IRQ accounting limit
attribution. Do not allocate this remainder to DDS, the kernel or the profiler
without evidence. Do not add kernel thread usage again to PID totals.

## Saved profiles and fix decision

The saved native Dashboard profile has 75 user CPU samples for two Dashboard
threads. Voice and localization-monitor Python captures target their own PIDs,
not these Nav2 children. They cannot establish functions consuming the 1129 ticks.
The recently tested monitor constructor and synthetic heartbeat success do not
demonstrate a Nav2 optimization or explain production mission-status staleness.

Known Dashboard executor/snapshot changes were already tested; the additional
accumulator candidate was rejected by a longer interleaved comparison (median
0.02432% savings). Do not repeat it or relabel it as new headroom. Existing native
evidence does not justify disabling QoS events, reducing safety polling, changing
Nav2 rates, merging lifecycle managers, or stopping camera/voice/navigation.

**No new CPU-saving runtime patch is justified yet.** No new CPU savings measured.
The verified code correction here is diagnostic accounting, not CPU optimization:
sum child-process ticks by exact cgroup; retain PID birth identity and split
history on cgroup migration. Preserve original process output and units.

## Tests and reproduction

10 offline accounting tests passed (7 existing, 3 new): service children exceeding
the largest single process, equal executable names in different groups, no
double counting, cgroup migration, PID reuse, counter resets, invalid clocks,
kernel subset and nonuniform intervals. Reanalysis of the saved capture produced
the table above. git diff --check passed. No runtime workload benchmark was run:
without a supported runtime candidate it would not demonstrate a safe CPU fix.

Run locally:

    python -m unittest discover -s project_atlas/tools/vision3d -p test_cpu_accounting_report.py -v
    python project_atlas/tools/vision3d/cpu_accounting_report.py artifacts/astra_concurrent_20261021/cpu-all-processes.json

## Single next discriminating action

Prepare a bounded, receive-only/native on-CPU profile of the currently running
atlas-localization.service child processes, preceded by current all-process
ranking and PID/birth/cgroup verification. Collect native symbols, thread CPU,
lost samples and matched observer overhead; no ROS discovery participant or
control operation. This needs a separately approved live profiling run (and
administrator access if required), not a drive or service restart. It has NOT
been executed or authorized by this offline-only task. If current ranking differs,
target the current largest unexplained group instead. Preserve strict safeguards;
past one-run CPU exceptions are not reusable.

Native call paths are the missing evidence needed to choose a safe offline
optimization and matched regression workload. Astra headroom remains unresolved.
Rollback: no production rollback needed. Revert only this diagnostic commit if
desired; no installer, runtime package or service change accompanies it.
