# Remaining CPU investigation: localization fit candidate rejected offline

Continued from deployed safety scan commit dcbc368. Owner authorized offline
investigation/testing only. No installation, restart, camera start, recording,
ROS participant, control call, movement or production safety change.

## Remaining load — verified scope

Read-only `ps` process-lifetime CPU (percent of ONE core):Dashboard43.2,
Pi Camera31.3,motor telemetry27.6,voice23.7,localization monitor16.5,
sensor recovery16.3,mux15.4,safety status12.8,mission11.0,RF2O10.7.
These are lifetime averages, NOT fresh synchronized whole-system CPU samples
or call-stack attribution. Existing source and profiles support distributed
load; no single dominant live cause was proven this turn. No new live stress
profile was run and the75/80/70 policies were not changed.

The exact live localization core was read and captured locally:
`artifacts/localization_core_live_20261024.py` (not committed raw).
SHA256 `d95828a09b174d109033c4af10fdf2f65599e1c7365ca669dff3428e6e723462`.
No changes to map, timing, steering, estimator parameters or localization authority.

## Candidate tested

`fit()` builds a full float distance vector, fills outside-map rays with99.0,
then computes the mean of threshold hits. Candidate counts inside hits directly
and includes outside rays only when99.0<=tolerance. Float64 conversion retained
to preserve original float32-map comparison behavior. Empty returns, NaN and
infinite tolerances preserved. All other top-level AST definitions identical.

Exact-hash transformer/benchmark:
`project_atlas/tools/diagnostics/benchmark_localization_fit.py`.
Candidate SHA256:
`add8c4ed754b03d0ee8055aab411b4cce735379b4f7a3d7b6379a503a0610f48`.
This candidate exists only in offline module memory; production source untouched.

## Tests

-216 exact score comparisons:empty/1/2/60/720 endpoints,float32/float64 distance
  fields,inside/outside bounds,NaN/Inf map values,negative/normal/99/100/NaN/Inf
  tolerances and cell/tolerance boundaries.
-10 existing `VerifyCoreTests` passed against candidate:room identification,
  wrong-room rejection,missing/ambiguous scan cases,map orientation,coarse score
  equivalence and median dropout behavior.
-2 focused unittest tests passed:wrong-baseline rejection and216 equivalence cases.
-Full search on synthetic room A and room B:identical complete hypothesis lists
  and confidence verdicts across all12 before/after pairs in two batches.
-No physical localization or historical five-jump resolution claim.

## CPU result — not deployment worthy

Native PC/WSL Python, no ROS. Two-room synthetic workload, two full global searches
per run;6 alternating-order pairs per batch. Warm search indexes. CPU measured
with process_time, outside the instrumented profile.

|Batch|Original mean CPU s|Candidate mean CPU s|Median paired saving|Positive pairs|
|---|---:|---:|---:|---:|
|Initial|0.396468|0.388800|2.403%|4/6|
|Detailed profile / repeat|0.403382|0.404987|-0.509%|3/6|

Second batch was run after adding detailed call-path evidence. Candidate did
not change between batches. Variation is larger than repeatable benefit.
**Rejected for deployment. Do not install this micro-optimization.**

Second cProfile workload wall0.389959s:

|Function|Self time s|Calls|
|---|---:|---:|
|_coarse_scores|0.218985|240|
|NumPy ufunc reduce (all callers)|0.099199|1507|
|NumPy argsort|0.030301|240|
|fit|0.017414|1267|
|global_search|0.008599|2|

`fit` cumulative0.027887s (7.15% of this profiled workload; first profile7.97%).
This explains the limited opportunity of the selected allocation change.
NumPy reduce totals include multiple callers; do not attribute all of it to
coarse scoring. cProfile timing includes profiler overhead and differs from
unprofiled process CPU. These are synthetic search costs, NOT measured live
monitor thread percentages or Jetson savings.

## Decision / next necessary evidence

Keep current deployments. Voice, white-glass UI and all useful features were
untouched. No rollback is needed because no production files changed.

The next meaningful investigation is coarse-search gather/reduction work **and
its actual live duty cycle**, rather than another small `fit` rewrite. Before
proposing a deployment, establish its share of the localization monitor's live
load versus ROS dispatch using bounded thread/function evidence. Any future
optimization must preserve full hypothesis ordering, ties, ambiguity refusal,
checkpoints, deadlines, confidence and search coverage. Do not substitute an
argpartition tie order or reduced search simply to obtain a benchmark saving.

No new admin command, deployment or camera test is requested based on this
rejected result. Overall CPU contention and Astra headroom remain unresolved.
