# Nav2 native capture: measured ROS/DDS work, no verified runtime fix

## Capture verified

Owner terminal run09:09:44 IST completed with NAV2_EXIT=0.
Evidence: `/home/jetson/project-atlas-migration/nav2-cpu-20261024/evidence-i2a4guhr/`.
perf.data187336bytes SHA256
2b3f614e9a74dc40e6c61ff4662c58555b6cc360dfe2de387e45c136870e54df,
verified against copied local bytes. No further profiling run initiated.
All11 protected service PIDs/restart counts match before/after. Recorder OFF,
E-STOP latched,manual-only,commands zero,fresh required sensors and mission READY
passed recorded checks. No production installation,restart,permission change,
camera start or movement. Voice and white glass UI unchanged.

Two other recent directories also exist: d759stoj has an aborted partial capture
with blank exception text; mv7er6m4 lacks a result and its root-owned perf.data
cannot be read by jetson. No permission change or retry attempted. These are not
counted as successful captures or silently pooled with the completed run.
Earlier sac7uvt5 remains the strict CPU admission abort. Keep all evidence.

## Resources (diagnostic CPU reporting exception only)

| Phase | Samples | Whole CPU mean | Peak |
|---|---:|---:|---:|
| Baseline |5|73.7892%|82.4532%|
| Profile |11|74.2837%|79.8986%|
| Postflight |5|73.3709%|76.8719%|

RAM maximum70.9093%;temperature maximum65.875C. Phase differences are not measured
CPU savings or isolated profiler overhead; background work is uncontrolled.
Production75% CPU,80% RAM,70C remain unchanged. This does not clear Astra admission.

## Actual native samples

perf reports15 user cpu-clock samples,zero lost,approximate sampled CPU789473670ns.
Six samples from BT navigator main TID8254; nine from navigation lifecycle manager
main TID8258. Their full proc user+system CPU over20.018745s is3.347% and4.945% of
one core respectively. All stable group threads total48.405% of one core (about
8.068% of six-core capacity). Native capture covers only the selected two threads,
not other threads,AMCL's call paths or kernel execution.

Inclusive path counts (overlap; do NOT sum as percentages):
-9/15 include Executor::wait_for_work.
-6/15 include FastDDS WaitSetImpl attach_condition/detach_condition.
-4/15 include subscription lookup/take/dispatch.
-2/15 include bond::Bond::publishStatus.

These are on-CPU samples, unlike earlier Python stack occupancy. They confirm
work in executor wait-set bookkeeping and lifecycle communication. They do NOT
prove a busy loop,duplicate subscriptions,bond storm or an avoidable algorithmic
defect. Several symbols are unresolved and15 samples cannot support precise
function cost estimates. No AMCL scan-matching hotspot is established by this
selection; it does not establish that AMCL is globally cheap either.

Process totals (%one core): lifecycle-navigation7.143,AMCL6.344,BT5.994,
behavior5.445,controller5.395,planner4.895,lifecycle-localization4.845,
waypoint4.246,map-server3.996,launcher0.100. Do not compare this group directly
with the historical Dashboard profile as a matched current ranking.

## Offline verification and fix decision

Added offline analyze_nav2_native.py: validates captured perf format,counts each
path at most once per sample,retains overlapping categories,separates sampled
periods from proc CPU,and excludes reused threads. Six new unit tests PASS:
overlap/deduplication,two-thread attribution,invalid/truncated samples,CPU units,
PID reuse,and counter/time/HZ rejection. Applied to the retained complete capture;
no ROS participant or hardware test. These are analysis tests,not proof of a
performance improvement. Existing29 profiler tests are prior evidence,not rerun.

**No runtime CPU fix is ready.** Increasing timer intervals or suppressing bonds
could weaken failure detection; removing DDS wait-set guards or caching dynamic
entities blindly could lose discovery/callbacks. Both are rejected without a
correctness-preserving native experiment. No tuning or library replacement made.

Next focused offline work: reproduce the measured wait-set/bond paths in a native
Humble fixture with realistic entity/message counts; evaluate equivalent
bookkeeping only,while testing dynamic entity creation/destruction,delivery and
bond failure timing. Actual production wakeup/entity rates are not contained in
this short capture,so a synthetic benchmark must state that limitation. Do not
request repeated drive tests or claim that saved CPU percentages prove a fix.
No further live profiling is authorized by the completed one-run exception.

Rollback: not applicable to production; changes are offline analyzer/tests/report
only. Raw stacks and telemetry remain private/untracked. No deployment package.
