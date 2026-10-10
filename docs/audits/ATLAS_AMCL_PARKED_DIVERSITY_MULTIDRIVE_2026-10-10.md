# Parked pose diversity across six recordings

Follow-up to [parked-diversity experiment](ATLAS_AMCL_PARKED_DIVERSITY_EXPERIMENT_2026-10-10.md),
which used one drive. Same AMCL 1.1.20 core harness, same five policies,
seeds 1–30, now on every parked window (at least 30 s) in six recordings.
This is offline only. The Jetson was accessed read-only to copy recordings;
no service, parameter, calibration or rover movement was involved.

## Answer

The cross-drive result supports the single-drive finding.

- **Nudge 0.05 m / 2.5° never made the scan fit worse in 11 of 12 windows,
  on any of 30 seeds.** It improved the fit in 5 windows, by more than 0.05
  on 165 seed comparisons in total. The only regression was 2 of 30 seeds in
  the already-failed round-trip return window.
- **The parked-update gate made the fit worse in 5 of 12 windows, on all 30
  seeds each time (150 seed comparisons), and never better.** Every one of
  those is a window where the recorded parked updates had corrected the pose.
  The gate is rejected as a standalone repair.
- **Nudge 0.10 m / 5° is rejected.** It made the fit worse in 6 windows,
  including 30 of 30 seeds in the Hall-return window.
- **Nudge 0.02 m / 1° never made anything worse,** but in the failed window
  it recovered far less often (fit 0.91 against 1.00 for the 0.05 m nudge).

Two new issues need attention before any runtime design:

1. **The 0.05 m nudge adds jumps while correcting.** Maximum jumps rose from
   1 to 9 (return retry2, 151–247 s) and from 4 to 7 (Hall return 122252,
   221–295 s), though the final fit was unchanged or better. The mux already
   blocks autonomy on such jumps; a runtime version must not make jumps
   routine.
2. **Outbound 1636 shows a latent offset.** Its three parked windows held a
   pose that fit the held-out beams at only 0.61–0.63. All 30 nudged seeds
   moved about 0.42–0.52 m (heading 1–4°) to a pose fitting at 1.00. This
   matches the round-trip finding: AMCL can sit stably on a measurably
   worse pose. Stillness is not accuracy.

## Method

- **Recordings, copied read-only from the Jetson with checksums verified:**
  `amcl_hall_outbound_20261009_1636`, `amcl_hall_outbound_20261009_retry2`,
  `amcl_hall_return_20261009_retry2`, `hall_to_dhruv_20261009-20261009-122252`,
  `amcl_stationary_passive_20261009_2113`, and the earlier
  `amcl_roundtrip_20261009_final`.
  `hall_to_dhruv_amcl_d010_ab-20260825-084317` has no parked window of 30 s
  or more, so it was excluded. Mapping sessions were excluded because their
  map changes during the recording.
- **Windows:** exported with the logic of `atlas_extract_stationary_pf.py`
  (the ROS-free port described in the earlier report), using each
  recording's own map and the deployed AMCL parameters. That gives 12
  windows; each policy runs 30 seeds per window, for 1,800 runs in total.
- **Score, without a reference pose** (`atlas_amcl_diversity_multidrive.py`):
  - **Held-out scan fit:** the fraction of odd original-beam endpoints
    within 15 cm of a mapped wall at each seed's final pose, median over
    scans from the window's final 10 s. With 360 beams and `max_beams` 60,
    AMCL uses only every sixth beam (even indices), so odd beams never enter
    its update.
  - **Jumps** and maximum jump.
  - **Final-30 s pose span.**
  - **Outcome groups** across seeds.
  - **Per-seed comparison with the baseline**, with a 0.05 fit margin.

  The round-trip windows are re-scored with the same final-10 s rule, so all
  12 rows are comparable. The values differ slightly from the earlier fixed
  450–458 s scan set.

## Results

Fit = median held-out fit over 30 seeds.

| Drive, window | Baseline fit | Gate fit | Nudge 0.02 m fit | Nudge 0.05 m fit | Nudge 0.10 m fit | 0.05 m worse / better seeds | Max jumps baseline → 0.05 m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Outbound 1636, 68–105 s | 0.62 | 0.61 | 0.72 | 1.00 | 1.00 | 0 / 30 | 0 → 0 |
| Outbound 1636, 182–212 s | 0.62 | 0.62 | 0.68 | 1.00 | 1.00 | 0 / 30 | 0 → 0 |
| Outbound 1636, 227–279 s | 0.63 | 0.63 | 0.86 | 1.00 | 1.00 | 0 / 30 | 0 → 0 |
| Outbound retry2, 1–97 s | 0.99 | 0.99 | 1.00 | 1.00 | 1.00 | 0 / 0 | 0 → 0 |
| Return retry2, 4–95 s | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0 / 0 | 0 → 0 |
| Return retry2, 151–247 s | 1.00 | 0.38 | 1.00 | 1.00 | 1.00 | 0 / 0 | 1 → 9 |
| Stationary capture 2113, 3–63 s | 0.76 | 0.76 | 0.80 | 0.82 | 0.77 | 0 / 22 | 0 → 0 |
| Hall return 122252, 4–163 s | 0.99 | 0.99 | 0.98 | 0.98 | 0.96 | 0 / 0 | 0 → 0 |
| Hall return 122252, 221–295 s | 0.95 | 0.45 | 1.00 | 1.00 | 0.79 | 0 / 0 | 4 → 7 |
| Round trip (final), 2–121 s | 0.97 | 0.82 | 1.00 | 1.00 | 1.00 | 0 / 0 | 0 → 0 |
| Round trip (final), 171–281 s | 0.84 | 0.49 | 1.00 | 1.00 | 0.99 | 0 / 30 | 2 → 1 |
| Round trip (final), 351–464 s | 0.80 | 0.28 | 0.91 | 1.00 | 0.74 | 2 / 23 | 22 → 11 |

Seed comparisons worse than baseline by more than 0.05, across all 12
windows:

| Policy | Worse | Windows affected |
| --- | ---: | ---: |
| Parked gate | 150 | 5 |
| Nudge 0.02 m / 1° | 0 | 0 |
| Nudge 0.05 m / 2.5° | 2 | 1 |
| Nudge 0.10 m / 5° | 60 | 6 |

Final-30 s pose span for the 0.05 m nudge stayed at or below 0.12 m in 8
windows. It reached 0.31–0.55 m in the outbound 1636 windows (the 0.5 m
correction itself) and 3.07 m in the failed round-trip window.

## Limits

- **Held-out fit is not ground truth.** A wrong pose in a repetitive space
  could also fit the map. This metric measures agreement with unused beams
  of the same scans, not surveyed position.
- **These are zero-motion core runs from published clouds,** not a full ROS
  replay, the live particle state, or localization while moving.
- **The Aug 25 run used an older map.** No usable window came from it, so
  every window here is from Oct 9.
- **Libraries were built on x86_64.** The earlier report verified exact
  agreement with published Jetson numbers on the unchanged harness.
- **No deployment or runtime change was made.**

## Next necessary action

1. **Investigate outbound 1636.** Find out why AMCL settled about 0.5 m from
   the best-fitting pose in all three parked windows: a map offset, a scan
   timing issue or a motion prior. Use the recordings already copied.
2. **Design a parked-only diversity candidate.** Use a σ between 0.02 and
   0.05 m. The candidate needs:
   - a guard that prevents nudging from producing repeated jumps;
   - an independent held-out scan-fit acceptance check;
   - no authority to grant autonomy by itself.

   Then validate it in full ROS replay on these 12 windows before any live
   trial.
3. **Keep the parked-update gate out of production** unless it is paired
   with a mechanism that can still correct a wrong parked pose.

## Validation

- 5 new unit tests pass in `test_atlas_amcl_diversity_multidrive.py`
  (27 tests across the three experiment suites).
- All 1,800 runs pass the summary invariant checks: equal initial state,
  finite poses, and an untouched, RNG-independent gate.
- Recording SHA-256 prefixes (copy matches Jetson):
  - outbound 1636: `99e1ed79`;
  - outbound retry2: `0ca64246`;
  - return retry2: `e34111bd`;
  - stationary capture 2113: `46016bbc`;
  - Hall return 122252: `c890f4d1`;
  - round trip: `5576d938`.

  Raw recordings and results remain outside Git.
