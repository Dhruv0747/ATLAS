# Outbound 1636: AMCL started 0.55 m ahead of the confirmed home spot

Follow-up to [multi-drive results](ATLAS_AMCL_PARKED_DIVERSITY_MULTIDRIVE_2026-10-10.md),
which found the three parked windows of `amcl_hall_outbound_20261009_1636`
sitting about 0.5 m from a much better-fitting pose. This is offline only,
on the recording copied read-only from the Jetson. No ROS graph, service,
parameter or rover movement was involved.

## Answer

During outbound 1636 the rover was very likely on the operator-confirmed
Dhruv Room spot. AMCL believed it was **0.55 m further forward**, along the
rover's own heading, with essentially no sideways or heading error.

- **The scans are not ambiguous.** On one scan from each parked window,
  AMCL's own likelihood-field score peaks at 0.55 m behind AMCL's pose and
  0.00 m sideways:

  | | AMCL likelihood | Held-out fit |
  | --- | ---: | ---: |
  | At the peak | 6.38–7.32 | 1.00 |
  | At AMCL's pose | 4.08–4.92 | 0.60–0.61 |

  The peak is about ±0.1 m wide.
- **The scan-best pose matches the confirmed spot.** That pose,
  (0.219–0.224, −1.543 to −1.556), lies **7.5–8.5 cm** from the reseeded pose
  recorded after the operator confirmed the exact Dhruv Room spot that
  morning: (0.187, −1.477, 1.330 rad), in
  [ATLAS_NAVIGATION_GATE_2026-10-09.md](ATLAS_NAVIGATION_GATE_2026-10-09.md).
  Every 30-seed nudged run in the multi-drive experiment converged to the
  same place.
- **The error was already present when recording began.** AMCL's first
  recorded pose, at 3.19 s, was (0.368, −0.975, 73.0°). Its cloud had 501
  particles and 53 distinct poses, with only 0.9 cm / 2.5 cm spread.
  Odometry did not move before 68 s. A cloud that tight, with zero motion
  and recovery disabled, cannot reach a peak 0.55 m away, which is why every
  parked update kept the error.

## What is not established (evidence gap)

How AMCL reached the offset pose happened **before the recording started**,
and the bag cannot show it. Candidates, none of them verified:

- an AMCL restart restoring an older saved pose;
- a seed from a stale file;
- convergence during earlier motion.

The earlier round-trip audit already records that `home_pose.json` and the
named `dhruv room` entry differed by about 1.70 m on Oct 9. Whether either
was used here is unknown.

Also unverified: whether this 0.55 m start error affected the subsequent
outbound drive and the Hall outcome. That needs the moving part of this
recording, analysed separately.

## Method

- **Script:** `project_atlas/scripts/atlas_amcl_axis_sweep.py`. It sweeps a
  pose along its own forward axis, then sideways at the forward peak,
  ±0.8 m in 0.05 m steps. At each offset it scores:
  - the nav2_amcl 1.1.20 likelihood-field factor, using the reimplementation
    from `atlas_amcl_weak_hypothesis_trace.py`, which matched the C++ AMCL
    harness within 0.4% on the same scan and pose (4.383 vs 4.366);
  - the held-out odd-beam fit, the fraction of endpoints within 15 cm of a
    mapped wall.

  It also reports the first recorded AMCL pose, the first clouds, and
  odometry movement before the first parked window.
- **Inputs:** the AMCL baseline pose from each window, with scans at 90,
  200 and 270 s. The map and laser transform are identical (hash
  `1262b7a9…`, laser (−0.05, 0, π)) across all six Oct 9 recordings, so
  this is not a map or laser-extrinsic difference between drives.

## Next necessary action

1. **Find the seeding event.** Read the Jetson's localization, mission and
   seed-script journal entries for Oct 9, 16:00–16:37, along with the
   `home_pose.json` and seed-file modification times.
2. **Analyse the moving part of outbound 1636** to see whether the 0.55 m
   start error carried into the Hall arrival.
3. **Gate mission start on a scan-fit check.** Any start-of-mission check
   should compare the current pose against a fresh held-out scan fit, not
   only stillness or covariance. Here AMCL was perfectly still and confident
   while 0.55 m wrong.

## Validation

- 4 new unit tests pass in `test_atlas_amcl_axis_sweep.py`.
- The sweep ran on all three parked windows with consistent results.
- Raw outputs remain outside Git.

## Update: journal and recording timeline (2026-10-10)

The operator ran the requested read-only checks on the Jetson.

- **No reset in the window.** `atlas-localization`, `atlas-mission-control`
  and `atlas-mode-manager` logged no initial-pose, seed, restart or start
  lines between 16:00 and 16:38 on Oct 9.
- **No new seed.** The newest seed file is `localization_seed_pose.json`,
  written Oct 9 at 12:10:07, which is the operator-confirmed reseed.
  `home_pose.json` was last written Oct 8 at 11:35.

So AMCL was not reseeded or restarted before outbound 1636. It carried its
pose over from earlier.

First and last AMCL pose of each Oct 9 recording (IST):

| Recording | Time | First AMCL pose | Last AMCL pose | Parked held-out fit |
| --- | --- | --- | --- | ---: |
| Hall return 122252 | 12:22:55–12:27:51 | (6.279, −2.200, −96.6°) | (0.314, −1.175, 62.4°) | 0.95 (end) |
| Outbound 1636 | 16:36:40–16:42:33 | (0.368, −0.975, 73.0°) | (0.354, −1.023, 75.8°) | 0.61 |
| Outbound retry2 | 16:47:31–16:50:25 | (0.381, −0.932, 68.9°) | (6.716, −2.374, −115.8°) | 0.99 (start) |
| Return retry2 | 16:51:50–16:55:57 | (6.716, −2.372, −114.9°) | (0.194, −1.298, 72.6°) | 1.00 |
| Round trip (final) | 17:45:51–17:53:36 | (0.206, −1.463, 81.3°) | (3.840, −0.482, 156.2°) | 0.97 (start) |

**Confirmed** from these rows:

- AMCL fitted the scans well at 12:27 (0.95).
- It did not fit at 16:36 (0.61).
- It fitted again at 16:47 (0.99), at almost the same estimate as 16:36.

Nothing was recorded between 12:28 and 16:36, or between 16:42 and 16:47.

**Suspected, not verified.** The pattern fits the rover being moved without
AMCL following, and then moved back:

1. Between 12:28 and 16:36, the rover may have been moved, for example
   placed back on the home spot or carried for charging, while AMCL stayed
   put with a 1–2.5 cm cloud and recovery disabled.
2. Between 16:42 and 16:47, the rover may have been moved forward about
   0.5 m, onto AMCL's estimate. That would explain why the 16:47 fit is
   0.99 with almost the same AMCL pose.

Only the operator can confirm or rule this out.

**If confirmed,** the failure class is moving the rover by hand while AMCL
cannot see it happen, the classic "kidnapped robot" case. The repairs follow
directly:

- reseed after any manual relocation;
- run a fresh scan-fit check before every mission start.

Neither involves AMCL tuning.
