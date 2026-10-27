# Stage 28 restart CPU investigation — cause unresolved, no retry

Reviewed65f4c4e and retained raw evidence. Read-only journal extraction and one existing10-second /proc sampler run; no service changes, deployment, ROS participant, camera session or MCU operation.

## Timestamped findings (same boot, monotonic seconds)

| Event | Time |
|---|---:|
| Baseline60.9215% sample completion |3672.005218|
| Before-write62.0805% sample completion |3673.081896|
| Old recovery stopping |3673.702118|
| New recovery started |3674.158367|
| New recovery PID33049 READY |3676.194329|
| Postflight safety fetch start/end |3677.160723 /3678.551843|
| Postflight98.8391% resource completion |3679.626406|
| Rollback recovery stop |3680.708770|
| Stopped, lifetime CPU3.040 seconds |3681.278143|
| Original recovery restarted |3681.281170|
| Restored PID33128 READY |3684.221371|

The API fetch took1.391s versus roughly0.04s preflight. This is correlated delay, not proof that the API caused CPU saturation. The wrapper does not save exact CPU-counter acquisition timestamps or raw deltas: reported completion includes RAM/thermal reads. Therefore do not label completion time as the exact CPU window boundary.

## Attribution and evidence limits

Systemd accounts3.040 CPU-seconds for the candidate recovery service's entire lifetime, including initialization and shutdown. It is NOT a per-window measurement. Six CPUs are currently online. If six were online during the at-least-one-second guard window, recovery alone could account for at most50.67 percentage points; it cannot explain98.84% alone. No recorded online-CPU history or synchronized process deltas exist for that window. Thus this is a conditional bound, not an exact attribution.

Normal ROS activity continued: rf2o PID2812 emitted953 journal entries and localization service4686 emitted139 in the40-second journal window. These are log counts, not CPU proportions. AMCL missing-map warnings and map-transform timeouts existed before and after restart. No basis to attribute the spike to them from journal volume.

Recovery initialization creates publishers/subscriptions and2s/5s timers. Its check() returns during30-second startup grace; no automatic recovery attempt is logged in this short lifetime. ROS import/discovery, callback startup and competing workloads remain hypotheses. The source contains no newly introduced tight startup polling loop; existing service queries are cached4s, recovery waits sleep1s. This source inspection cannot exclude expensive native DDS processing.

## Passive baseline, not a reproduction

Reused existing stage31_cpurec.py for10 seconds, without restarting anything. Whole-system CPU58.43..61.30%, mean60.175%. Current process averages (percent of ONE core; six-core equivalent is divided by6): dashboard43.61, python3 PID2837 35.45 (not resolved to function), base telemetry30.51, voice23.51, recovery18.84, mux16.16, safety12.91, rf2o11.84, localization monitor11.37. Sampler has a1.5%-one-core per-interval reporting threshold and does not provide complete exited-process accounting; these are approximate current baseline measurements, not historical attribution. It includes its own overhead.

Exactly one recovery process observed, PID33128; no deployment wrapper remained. Current baseline is lower than rejection, so high load was not continuous through this later window. Its duration immediately around restart is UNKNOWN: only one high sample was retained, and rollback changed conditions. Neither transient nor sustained classification is proven.

## Measurement review and proposed action

All deployment samples use the same first8 /proc/stat counters and (total-idle-iowait)/total, with a1s sleep. No changed denominator or different averaging was found. Existing passive sampler uses the same aggregate definition. Raw counter deltas and actual sample interval were not retained by the wrapper, limiting retrospective audit.

No production optimization is justified yet. Smallest proposed diagnostic improvement for a separately reviewed future observation is persistent one-second raw /proc/stat intervals plus process/cgroup CPU deltas and process start identities, started before any authorized restart and kept through abort. Include wrapper CPU, kernel irq/softirq, missing/exited counters and all processes, not only top10. This is NOT authorization to restart or repeat deployment, and must not replace or average the75% admission guard. Existing saved profiles from different sessions cannot supply missing counters for this event.

## Offline output and verdict

Added analyze_restart_cpu.py and four tests proving no transient/attribution inference from sparse samples, exact journal monotonic conversion, unchanged75% boundary, and no averaging of a rejection. Four tests PASS. No runtime fix, safety change or claimed CPU saving.

NO-GO for another maintenance deployment: exact CPU cause remains unverified. No retry approval requested. B1 remains blocked. Current read-only postcheck: base3333/NRestarts1, recovery33128/NRestarts0, both active; telemetry LIVE age0.037s; E-STOP latched, manual-only, commissioning false, zero commands.

Evidence kept outside Git in work/b1-maintenance-deploy-20261027/retry-d1d13a3: resources.json, safety snapshots, journal-window.jsonl, passive-baseline.jsonl, offline-cpu-analysis.json. No private raw logs committed.
