# Bounded pose diversity while parked: AMCL core experiment

Continuation of [weak-hypothesis trace](ATLAS_AMCL_WEAK_HYPOTHESIS_TRACE_2026-10-10.md)
and of the "next necessary action" in
[stationary-policy experiment](ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md):
test a bounded way to reintroduce credible pose alternatives while parked.
This is offline only. No ROS graph, Jetson service, deployed parameter,
calibration or rover movement was involved.

## Answer

Small bounded pose jitter after each parked resample (σ 0.05 m / 2.5°,
truncated at 2σ) was the only tested policy that recovered the failed return
window. It moved AMCL onto the refined Dhruv Room pose in **22 of 30 seeds**,
and it kept both previously correct parked windows correct in **30 of 30**
seeds each. It is **not reliable enough to deploy**: 8 of 30 failure-window
runs stayed wrong, and some of those wandered by up to 3 m in the final 30 s.

The repository's parked-update gate (no forced updates while parked) never
recovered the failed window. It also **blocked a correction that the recorded
behaviour achieved** in the outbound Hall window (0 of 30, against 30 of 30
for the baseline). This weakens the first implication in the
weak-hypothesis trace: stopping parked updates removes drift, but it also
freezes whatever pose AMCL had when the rover stopped. The earlier finding
is kept unchanged; this entry qualifies it with new evidence.

## Method and provenance

- **Harness:** `project_atlas/scripts/atlas_amcl_diversity_experiment.cpp`,
  a new file next to the unchanged `atlas_stationary_pf_experiment.cpp`. It
  links the actual nav2_amcl 1.1.20 particle-filter, map and laser
  libraries, restores the first published cloud in each parked window, and
  applies the same scans to every policy. Its jitter uses AMCL's own
  `pf_ran_gaussian`, so runs reproduce exactly from the seed.
- **Libraries:** built from nav2 tag `1.1.20` (commit `a097086`) with the
  same pf/map/sensors split and `HAVE_DRAND48` as nav2's CMake, in a
  ROS 2 Humble (jammy, g++ 11.4) container on x86_64. The Jetson uses the
  installed arm64 binaries instead.
- **Fidelity check:** before adding anything, the **unchanged** existing
  harness was run on the same bundles:
  - all 36 runs passed `validate_atlas_stationary_pf_results.py`;
  - window 2 baseline seed 1 reproduced the published 2.4442 → 5.3019
    last-scan scores exactly;
  - fixed-prior maximum displacements were 0.005, 0.029 and 0.040 m;
  - fixed-prior final poses were (3.221, −0.510) and (3.009, −0.316).

  The new harness differs only in the policies it runs.
- **Inputs:** the three parked windows of `amcl_roundtrip_20261009_final`,
  exported with the logic of `atlas_extract_stationary_pf.py`. A ROS-free
  port changed only message decoding and map-cell integer conversion. The
  windows match the earlier table: 1.673–120.946 s, 171.442–280.943 s
  (103 scans) and 351.239–464.442 s (106 scans).
- **Policies**, each run with seeds 1–30:
  - `baseline`: update and resample every scan, as recorded.
  - `parked_gate`: no forced updates, so the cloud is untouched.
  - `jitter_small`: baseline plus jitter of 0.02 m / 1.0°.
  - `jitter_medium`: baseline plus jitter of 0.05 m / 2.5°.
  - `jitter_large`: baseline plus jitter of 0.10 m / 5.0°.

  All jitter is truncated at 2σ. That makes 450 runs in total.
- **References.** None is surveyed ground truth.
  - Window 0: the initial room anchor (0.2070, −1.5454, 1.4080 rad).
  - Window 1: the late Hall anchor (6.4680, −2.7635, −1.6614 rad), which
    sits in the previously accepted Hall region.
  - Window 2: the refined room pose (0.3748, −1.1668, 1.3874 rad).

  Windows 0 and 1 use AMCL's own anchors, so "error" there partly measures
  departure from AMCL's previous answer.
- **Metrics:** the handoff list.
  - Recovery: the final winner pose is within 0.5 m and 20° of the reference.
  - Jumps: winner steps over 0.5 m, and the maximum jump.
  - Stopped-position stability: the largest winner-pose span in the final
    30 s.
  - Final heading error.
  - Held-out scan fit: the fraction of endpoints within 15 cm of a wall,
    using odd original beam indices on nine recorded scans. Window 0 uses
    110–118 s, window 1 uses 270–278 s and window 2 uses 450–458 s.

  `atlas_amcl_diversity_summary.py` computes these. It also checks equal
  initial states, finite poses, an RNG-independent and untouched gate, and
  exact same-seed reruns.

## Results (30 seeds per policy and window)

Failed return window (351.239–464.442 s); reference held-out fit is 1.000:

| Policy | Recovered | Median / max jumps | Max jump | Final-30 s span, median / max | Median final error | Held-out fit, median run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (recorded) | 0/30 | 4.5 / 22 | 1.47 m | 0.021 / 1.473 m | 3.44 m, 104.0° | 0.802 |
| parked_gate | 0/30 | 0 / 0 | 0 | 0 / 0 m | 2.78 m, 19.6° | 0.258 |
| jitter_small | 14/30 | 3.5 / 16 | 3.55 m | 0.046 / 1.388 m | 2.17 m, 15.4° | 0.904 |
| **jitter_medium** | **22/30** | 1 / 11 | 3.14 m | 0.057 / 3.075 m | **0.04 m, 2.2°** | **1.000** |
| jitter_large | 0/30 | 0 / 0 | 0.39 m | 0.066 / 0.098 m | 2.85 m, 49.0° | 0.751 |

Recovered runs fit the held-out scans at 1.000. Unrecovered `jitter_medium`
runs fit at 0.777. The jump counted in a recovered run is mainly the
correction itself, about 3 m from the wrong region to the room. The mux
correctly treats such a step as a localization jump and blocks autonomy.

Previously correct parked windows (control):

| Window | Policy | Recovered | Median / max jumps | Final-30 s span max | Median departure from AMCL anchor | Held-out fit |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0 room (anchor fit 0.969) | baseline | 30/30 | 0 / 0 | 0.012 m | 0.00 m, 0.0° | 0.969 |
| | parked_gate | 30/30 | 0 / 0 | 0 m | 0.09 m, 0.6° | 0.815 |
| | jitter_medium | 30/30 | 0 / 0 | 0.088 m | 0.12 m, 7.8° | 1.000 |
| 1 Hall (anchor fit 0.838) | baseline | 30/30 | 1 / 2 | 0.033 m | 0.00 m, 1.2° | 0.838 |
| | parked_gate | **0/30** | 0 / 0 | 0 m | 3.97 m, 50.5° | 0.494 |
| | jitter_medium | 30/30 | 1 / 1 | 0.107 m | 0.24 m, 8.2° | 1.000 |

In both control windows, every jitter size stayed within the reference
region in 30 of 30 seeds. `jitter_large` had up to 8 jumps in window 1. The
consistent 7–12° heading departure from AMCL's own anchors came with
*higher* held-out fit. Those anchors are themselves AMCL outputs, so this
does not show the jittered pose is wrong. It does show jitter moves the
estimate measurably while the rover stands still.

## Interpretation

- **Parked updates both help and hurt.** In window 1 the correct Hall
  hypothesis was already supported near its likelihood peak, and parked
  updates moved AMCL onto it. In window 2 the correct room hypothesis was
  weak and 0.2–0.3 m off its peak, and parked updates erased it. A gate
  that simply stops updates cannot tell these cases apart.
- **Small diversity lets the scan do the work.** Jitter of 0.05 m / 2.5°
  lets particles climb to a nearby likelihood peak, so the scans can pull
  the cloud to the better-fitting room pose. Too little jitter (0.02 m)
  does this less often. Too much (0.10 m) kept the cloud spread around the
  wrong region and never recovered.
- **It is not a guarantee.** About 1 run in 4 still ends wrong, and some
  failures oscillate. Any deployable version needs an independent
  wrong-match rejection, for example held-out scan-fit acceptance, before a
  pose can grant autonomy.

## Limits

- One drive with three parked windows. The windows come from the same
  recording as the references, and the room reference is a retrospective
  fit, so this is not independent validation.
- These are core-library runs from a published cloud with zero motion. They
  are not a full ROS/TF replay, the live particle state, or moving
  localization.
- Libraries were built on x86_64. The bitwise match to the published Jetson
  numbers on the unchanged harness supports, but does not prove, identical
  behaviour on arm64.
- No deployment, parameter change, runtime code change or driving followed.
  The production configuration is unchanged.

## Next necessary action

1. Repeat on other saved drives, using the Jetson's installed libraries,
   with seeds 1–30. Report the same table.
2. If recovery stays high and the control windows stay correct, design a
   bounded runtime form:
   - parked only;
   - the same σ and truncation;
   - never a source of autonomy permission by itself;
   - paired with an independent scan-fit acceptance check.

   Then test it in full ROS replay before any live trial.
3. Do not deploy the parked-update gate as a standalone repair. It froze a
   wrong pose in 30 of 30 runs here.

## Validation

- 9 new unit tests pass in `test_atlas_amcl_diversity_summary.py`; the
  earlier 13 weak-hypothesis tests also pass.
- Invariant checks pass for all 450 runs, and 10 same-seed reruns match
  exactly.
- Raw bundles and result JSON stay outside Git, as for the earlier
  experiment. Diversity-harness library SHA-256: pf
  `f5949ae8…`, map `d5b90805…`, sensors `65b176ec…` (x86_64 build).
