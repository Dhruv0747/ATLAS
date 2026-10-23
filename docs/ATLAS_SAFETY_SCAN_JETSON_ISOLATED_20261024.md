# Isolated ARM64 scan callback comparison — complete, not installed

Owner approved isolated Jetson testing only. Continued from96d5010.
No production installation/restart, ROS participant, Astra start, recording,
movement, scheduling change or safety-policy change.

## Method / exact identity

Copied two diagnostic scripts to an isolated migration directory. Extracted only
the live `on_scan` method and executed original/candidate on synthetic720-ray
input in a separate Python process. No safety node or ROS node constructed.
Exact live hash checked by the transformer:
`57262f6e55aef3f28ba285805619a86f6131643e41cebf20dc49be86d3cf2e1e`.
Candidate hash:
`94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4`.

Three1-second baseline intervals;10 alternating-order pairs;10 callback calls
per measured block, then sleep to complete a1-second CPU window. Fresh resource,
E-STOP/manual-only/zero-command, recorder-OFF, sensor freshness, Astra-OFF and
access checks between blocks. Final postflight. Existing75%CPU/80%RAM/70C
guards unchanged; no failed admission bypassed. No high-load continuous loop.

The first wrapper invocation failed before preflight/work because its strict
service-ID parser expected `rover-status-web` instead of canonical
`rover-status-web.service`. Corrected this diagnostic identifier only after
read-only systemctl verification. No benchmark ran on that invocation. The
corrected attempt completed; no production service was changed to solve it.

## Actual Jetson measurements

|Metric|Original|Candidate|
|---|---:|---:|
|Mean process CPU ms per synthetic scan|4.570952|2.640188|
|Median paired callback CPU reduction|—|41.263%|
|Pairs with lower candidate cost|—|10/10|
|Whole-system CPU during corresponding intervals, mean|70.77%|71.17%|
|Whole-system CPU during corresponding intervals, peak|72.41%|73.23%|

All10 pair output dictionaries identical, including freshness timestamp using
the same fixed test clock. No outputs were published to production.
Baseline wholeCPU mean70.04%,peak71.57%;postflight68.47%. Overall peak73.23%.
MaximumRAM72.3031%,temperature59.718C; isolated process peakRSS21848KiB.
Three existing offline tests rerun passed (335 broader equivalence cases,
unchanged non-scan methods, exact-baseline rejection/source compilation).

**Confirmed: actual ARM64 callback savings. Not confirmed: whole-system CPU
savings or Astra readiness.** Original/candidate intervals run alongside unchanged
production and include background variation and diagnostic overhead. Candidate
wholeCPU mean was higher, so it is not evidence of an installed system benefit.
At a hypothetical10scans/s this synthetic result saves19.31ms CPU/s (~1.93% of
one core). Actual scan rate/ray mix and complete node benefit are unmeasured;
do not extrapolate41% to the node or whole Jetson. A live deployment comparison
is needed to prove its operational value, which may be small.

## Safety / preservation

All nine checked services remained active with identical PIDs/restart counts:
Pi Camera1858/0,motor3351/1,mux1852/0,EKF2982/0,AMCL8060/7,LiDAR7887/12,
Dashboard94624/0,voice108742/0,safety-status1889/0.
E-STOP latched,manual-only true,commissioning false,commands zero,recorder OFF,
Astra OFF passed all checks including postflight. White-glass/UI/voice source,
calibration and all production features untouched. No acoustic or UI interaction
test was performed; preservation here means no changes and stable service identity.

## Evidence and next approval

Jetson evidence:
`/home/jetson/project-atlas-migration/scan-cpu-isolated-20261024-zj0Z1d/result.json`
SHA256 `b1a45f0d0b2caebf7ce5279c928a8117fcf9710f58f4e92b7f807ffe8cdbb05a`.
Local retained copy:`artifacts/safety_scan_jetson_result_20261024.json` (not in git).
Runnable bounded wrapper:
`project_atlas/tools/diagnostics/safety_scan_isolated_jetson.py`.
No production rollback needed; candidate exists only in process memory.

Do not install automatically. Any deployment would require separate owner
approval for the exact-hash single safety-status file and ONLY its service
restart, fresh checks, verified original backup, matched before/after measurement
and rollback to the original hash on failed health checks. No camera start is
needed for that comparison. Astra headroom remains unresolved.
