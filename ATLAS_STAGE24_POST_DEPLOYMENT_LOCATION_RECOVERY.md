# Stage 24 post-deployment location recovery, 2026-10-15 20:22–20:40 IST

**Status:** Stage 24 DEPLOYED (unchanged). **AMCL NOT SEEDED: awaiting your explicit approval.**
Candidate **C = (0.235, −1.435, 75°)** is STABLE and GLOBALLY UNIQUE in 4 of 4 completed global samples
and 5 of 5 Dhruv Room samples. READY FOR SEED APPROVAL, with the conditions in §7. GLOBAL AMBIGUITY has not
recurred at this placement; it is not proven fixed for other placements (§8). No source change. Read-only throughout.

## 0. Correction to my earlier report
`ATLAS_STAGE24_LOCALIZATION_DEPLOYMENT.md` (7ecc03e) said a *stationary* ATLAS gave two different VERIFIED
poses. **That was wrong.** I treated `/odom` ≈ 0 as proof of no movement. ATLAS was physically repositioned
twice; A, B and C were each correct for where it stood at that moment (§4). Nothing was wrong with the matcher.

## 1. Five live samples (read-only `--dry-run`, ~20:23–20:29, one global + one Dhruv Room each)
Verdict-file sha256 `3e77b469136cae5b` before and after: nothing written. Scans were collected inside each run
(first scan 5–19 s after start, ~3.0–3.3 s span, 18–24 scans, 1.2–10 s old when the run ended): no cached data.

| # | Global pose | fit | margin | Dhruv Room pose | margin | union valid beams (of 360) | quadrants (global) |
|---|---|---|---|---|---|---|---|
| 1 | 0.235, −1.435, 75° | 1.0 | 0.106 | same | 0.123 | 305 / 302 | 76,76,84,69 |
| 2 | same | 1.0 | 0.113 | same | 0.125 | 307 / 305 | 78,76,82,71 |
| 3 | same | 1.0 | 0.105 | same | 0.111 | 305 / 302 | 79,75,83,68 |
| 4 | same | 1.0 | 0.106 | same | 0.125 | 305 / 306 | 78,76,82,69 |
| 5 | **UNKNOWN: "no odometry while the startup scan was collected"** (no scan evidence) | n/a | n/a | same | 0.118 | n/a / 305 | n/a |

- Runner-ups, global: (4.075, −0.735, 162.5°) 0.887–0.895; (0.315–0.335, −1.195, −111…−112.5°) 0.871–0.886.
  In room: the same reversed-heading alias 0.875–0.889, then (−0.525, −1.18, 132–136°) 0.77. Thresholds unchanged (0.93 / 0.06).
- Sample 5 global is a harness limit, not a different answer: the seeder's 3 s `/odom` discovery window lost to
  load 57.6. It happened once earlier today at load 30 (first 20:08 dry run). Not seen in any of the 8 recorded boots.
- Candidate covariance is not produced by the verifier. Spread across samples: identical to 0.005 m / 0.5° (grid resolution).

## 2. Global vs Dhruv Room: they agree
Same pose in all 4 pairs. The region box did not clip C (it is 0.5 m inside the box's north edge). Region restriction
only removes the corridor alias (4.075, −0.735).

## 3. LiDAR coverage
- **Single scan:** 60 scans over 8.2 s at 7.17 Hz (not 4 Hz): **210 valid of 360 (205–218)**, 56 beams never valid,
  304 sometimes valid, 0 always valid. This is the Dashboard's 215. Stamp age at receipt 0.147 s mean, 0.271 max.
- `/scan_raw`: 209.2 valid per scan; `/scan`: 208.8. **The scan filter is not removing beams**; sparsity comes from the
  sensor/driver. (`/scan` carries `scan_time` 0.258 s against `/scan_raw` 0.134 s: a labelling difference worth a
  separate look, not a cause here.)
- **The archive's "valid" counts are a union over ~23 scans** (nanmedian), so they are not comparable to 215.
  Union coverage: good boots 294–315; 11:19 and 19:29 boots 230/234; 19:44 232; 20:08 259; **now 302–307**.
- **Coverage tracks placement, not time.** The 11:19 and 19:29 scans are the same range image across the 19:15
  reboot (median difference 3 mm); coverage only changed when ATLAS moved (§4). In the degraded scans the base-frame
  right and front-right sectors returned almost nothing (6/45 and 13/45 beams) where the map shows walls within 4 m;
  at C those sectors are 45/45 and 31/45. Quadrant-nearest values are not wall distances and were not used as such.
- Not proven: *what* at the old spot blocked the right side. The sensor itself looks healthy.
- Frames: `laser_in_base` = (−0.05, 0, π) in every sample and in live TF; unchanged. `map` frame does not exist yet (AMCL unseeded).

## 4. Why A and B differed: ATLAS was moved
Beam-by-beam range comparison (no map needed; common valid beams, median |Δrange|, share within 5 cm):

| Scan pair | Result |
|---|---|
| 11:19 boot vs 19:29 boot | 221 beams, 3 mm, 68%: same spot for 8 h |
| 19:29 vs 19:44 dry run | 232 beams, 0 mm, 100%: stationary |
| **19:44 vs 20:08** | 170 beams, **193 mm, 0%: moved** |
| 20:08 global vs 20:08 room | 255 beams, 1 mm, 98%: stationary |
| **20:08 vs 20:2x sample 1** | 238 beams, **343 mm, 39%: moved** |
| samples 1 vs 2 / 4 / 5 | 299–302 beams, 0–1 mm, 99–100%: stationary |
| 08:42 good boot vs 11:19 boot | 207 beams, 144 mm, 16%: moved earlier today |

Independent timing: the localization monitor logged MOVING bursts at **19:46:23–19:47:14** and **20:19:20–20:19:25**
(it flags motion when `/odom` twist exceeds its parked threshold). LiDAR displacement: A→B 1.24 m (+0.22, +1.22),
B→C 0.51 m (−0.10, −0.50). The owner's own CHECK MY LOCATION at ~20:17:45 returned B (LIDAR_ONLY_MATCH, fit 1.0,
margin 0.071), a different code path agreeing with my dry run.

**Odometry did not see the moves:** `/yahboom/odom` and `/odom` both sit at (−0.0255, −0.0001) since boot.
So ATLAS was lifted/carried or slid with the wheels not rolling; I cannot tell which. Consequence: odometry is blind to
hand moves, so after any hand move the LiDAR check must be redone before trusting AMCL.

## 5. Geometry causes ruled in/out
| Hypothesis | Verdict |
|---|---|
| Unstable/incomplete LiDAR returns | Partly: at the old spot the right side was blind (§3) and the 19:29 fit was ambiguous (margin 0.0–0.011), correctly refused |
| Duplicate wall geometry | Exists but is separated: reversed-heading alias 0.875–0.889, corridor alias 0.89; both below C by ≥0.106 |
| Region boundary clipping | No. C is inside; global and room agree |
| Frame/TF inconsistency | No (§3) |
| Wrong physical location assumed | **Yes. This was the main error: ATLAS had moved** |
| Matcher ranking instability | No: identical pose in 9 of 9 completed runs |
| Timing/cached data | No (§1) |

## 6. Evidence for C, and the physical check I need
- Fit 1.0, margin 0.105–0.125. The same C scan fits A at 0.62–0.63 and B at 0.59–0.60.
- Ray-cast of the accepted map from C: **284/302 and 287/306 (94%) of valid beams** land within 15 cm of the
  predicted range. Previous good boots: 73–77%. The same scan placed at A: 46%; at B: 48%.
- Matches earlier successful Dhruv Room boots: (0.235, −1.535, 74°) 0.10 m; (0.175, −1.735, 73°) 0.31 m;
  (0.235, −1.735, 75°) 0.30 m; (0.275, −1.835, 69°) 0.40 m / 6°.
- Not yet independent of the map and LiDAR: a tape measurement.

**Minimum physical input (from you, no approval needed, ATLAS stays untouched):**
1. Which way does ATLAS's front point: toward the corridor opening, or toward the back wall?
2. Tape from the **centre of the LiDAR head** straight to the **back wall** (far end, behind ATLAS). Predicted:

| Candidate | Back wall | East wall |
|---|---|---|
| **C now** | **1.38 m** | 0.39 m |
| reversed-heading alias | 1.72 m | 0.31 m |
| B | 1.88 m | 0.90 m |
| A | 0.61 m | 0.42 m |

3. Did you move, lift or nudge ATLAS near 19:46 and 20:19? (This only explains the data.)

## 7. Is seeding safe? Prepared, NOT run
Conditions met: stable, globally unique, agrees with map evidence and earlier good boots, inside the room,
latched, manual-only, no Nav2 goal, AMCL NOT_INITIALIZED, thresholds unchanged.
Not yet met: a tape confirmation (recommended, not mandatory) and ATLAS not moving again.

**Runbook (one attempt, existing mechanism):**
1. Re-check latched, manual-only, disarmed, zero commands, no monitor MOVING episode since 20:19:25.
2. Back up the verdict file, the check files and the AMCL status into `data/diagnostics/stage24_recovery_20261015/pre_seed_<time>/`.
3. `cd ~/project_atlas/scripts && python3 seed_atlas_localization.py --verify-place "dhruv room"`.
   It re-verifies the live scan and seeds only if VERIFIED at 0.93/0.06; σ 0.10 m / 8° via `/set_initial_pose`;
   no saved-seed overwrite.
4. **Abort without seeding** if the result differs from C by >0.15 m or >6°, the margin is <0.06, or any motion event appears.
5. After: AMCL pose and covariance, Dashboard location, no jump >0.5 m, 10 min parked sampling every 30 s,
   STOPPED display, sensors, zero commands. No second automatic attempt. Rollback: restore the backed-up verdict; AMCL
   state is cleared by the next boot, no file change to Stage 24.

## 8. Reboot reliability: honest status
Boot history: 4 VERIFIED, 4 UNKNOWN of 8. The UNKNOWN boots were all at placements with weaker coverage or fit
(10-11 20:59 fit 0.92; 10-13 21:23 margin 0.03; 10-15 11:19 and 19:29 the blind spot). None failed for "no odometry".
At C the union coverage and margins (0.105–0.125) match the VERIFIED boots, so a reboot **here** should verify
through the unchanged Stage 16 path. That is a forecast, not a test. I have not rebooted (not authorized).
The sample-5 odom-timeout is a latent risk under boot load; no change proposed without your approval.
Rule of thumb until a second placement is proven: do not hand-move ATLAS between sessions, and re-verify after any move.

## 9. Preservation (20:38)
Latched (reason "REMOTE STOP: joystick unavailable"), manual-only true, disarmed, `/cmd_vel` no messages,
AMCL no pose. Stage 21 `scripts/yahboom_base.py` `c551be00…` (PID 3521), `atlas_encoder_selection.py` `7d457c9f…`,
recorder `7110961c…`, Stage 24 `273989b2…` / `d95828a0…` / `325df94a…`, EKF `69dd4479…`, map `d957f0fe…`/`4beb26d5…`
all unchanged. Services ekf 3242, localization 6019, monitor 1923, mux 1817: same PIDs, no restarts. Load ~26,
RAM 4.7/7.6 GB. Evidence on the Jetson: `data/diagnostics/stage24_recovery_20261015/` (not committed).

## 10. Source changes and tests
None. No tests were needed. The sample runs used the deployed Stage 24 files.

## 11. The one next action requiring your approval
**Approve ONE seed of C via the runbook in §7**, ideally after you send the answers in §6. Reply "APPROVE ONE SEED"
and keep your hands off ATLAS until it is done.

Still open, unchanged: Candidate B (after the moving baseline), Stage 22 recorded driving, Foxglove, Stage 17B hold,
physical E-STOP tests, old `atlas_steering_calibrate.py`, Jetson password rotation and key removal.
