# Remaining CPU: bounded scan-transform candidate (offline only)

## Verified evidence

Continued after voice deployment 1e02ca9, without repeating voice profiling.
Read-only SSH verified the live safety-status source SHA256:
`57262f6e55aef3f28ba285805619a86f6131643e41cebf20dc49be86d3cf2e1e`.
No live code, service, camera or motor change was made.

The process-lifetime `ps` snapshot reports Dashboard43.8%, Pi Camera31.7%,
motor telemetry27.5%, voice23.7%, sensor recovery/localization monitor16.2%
each, mux15.3%, safety status12.9%, mission10.8%, RF2O10.6% of ONE core.
These are lifetime averages, not a synchronized current whole-system measurement
and not function attribution. Do not add them to infer a current CPU guard value.
The previous matched voice deployment comparison did not prove system savings.

Exact live `on_scan` performs the same sensor-to-base rotation up to six times
for each valid ray. The candidate rotates once and preserves each subsequent
sector wrap, comparison, priority, minimum, range validation and timestamp update.
All other methods are AST-identical. No caching, rate reduction, stale-data
allowance, clearance interpretation or safety threshold is changed.

## Offline measurements

WSL PC Python; exact live method extracted without importing ROS or constructing
the node. Synthetic 720-valid-ray scans,300 scans per run,10 alternating-order
pairs. Process CPU time, not wall time:

|Metric|Original|Candidate|
|---|---:|---:|
|Mean callback ms/scan|0.971716|0.511628|
|Median paired CPU saving|—|47.177%|
|Pairs with lower candidate CPU|—|10/10|

All335 equivalence cases passed: randomized scan lengths, positive/negative angle
increments, varied origins, NaN/Inf/out-of-range returns, empty scans and sector
boundaries ±epsilon. Three unittest tests passed, including wrong-baseline
rejection, unchanged non-scan methods and complete-source compilation.

Candidate SHA256:
`94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4`.
The exact-hash transformer lives in
`project_atlas/tools/diagnostics/benchmark_safety_scan_transform.py`.
Tests: `project_atlas/tests/test_safety_scan_transform_candidate.py`.
It returns candidate bytes in memory; does not write/deploy to Jetson.

## Limits / decision

This is a confirmed redundant operation and an offline callback improvement,
NOT the verified dominant cause of remaining load. At a hypothetical10scans/s,
the PC result saves only4.6ms CPU/s, or0.46% of one PC core; actual Jetson scan
rate, per-callback cost and node share were not measured this turn. Thus do not
claim that this candidate enables Astra or reduces the entire12.9% node load
by47%. No new Jetson RAM/performance claim is made.

Existing no-valid-return behavior is intentionally preserved, not endorsed or
changed by this optimization. No production safety checks were bypassed.
Voice, white-glass UI, all service scheduling, Domain77 and75/80/70 guards remain
untouched. Astra was not started; no recording, restart or movement occurred.

## Next necessary step and rollback

Before requesting installation, measure this exact callback on isolated ARM64
execution and correlate its cost with the actual scan rate/function CPU share.
The callback benchmark does not require a ROS participant or camera. Current
approval does not install this candidate or restart the safety reporter.
Any future deployment needs fresh safety/hash checks, an exact-live backup,
explicit safety-reporter restart approval and matched live measurements. Rollback
would restore the hash-verified original file and restart only that reporter
under approval. No installed files currently require rollback.

Useful features must not be disabled to manufacture headroom. Remaining aggregate
CPU contention and live Astra readiness are still unresolved.
