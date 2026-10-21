# Stage 24: owner confirmation, AMCL seed and parked validation, 2026-10-15 20:49–21:06 IST

**OWNER MOVEMENT CONFIRMED · LIVE GLOBAL VERIFICATION PASSED · AMCL SEED SUCCESS · DASHBOARD LOCATION: backend feed
VERIFIED, rendered page not seen by me · 10-MINUTE PARKED STABILITY PASSED · MOVING VALIDATION PENDING.**
Global CHECK MY LOCATION ambiguity: not reproduced at this placement; not proven fixed elsewhere.

## 1. OWNER MOVEMENT CONFIRMED
The owner deliberately moved ATLAS forward and backward inside Dhruv Room as a localization test, around 19:46 and
20:19. Candidates A, B and C are different real placements; they are not a matcher regression. The earlier
"stationary rover, two poses" reading is withdrawn (see the erratum notes in the two earlier Stage 24 reports).
- **Odometry during those moves:** `/odom` and `/yahboom/odom` stayed at about (−0.025, 0). I do **not** know the
  mechanism (carried, slid, or rolled with a fault). Raw wheel counts changed only slightly between ~20:37 and 20:50
  (m4 −7206 → −7296, m1 4032 → 4037; CPR ≈ 2200), far too little for a ~1.7 m roll. That is consistent with the wheels
  not rolling, but it is not proof. Needs a controlled test (§8).

## 2. Pre-seed conditions (20:50–20:53)
| # | Condition | Result |
|---|---|---|
| 1 | ATLAS not moved since C | **Checked by scan, not by assumption.** Monitor logged MOVING at 20:37:14, 20:46:24 (after C). Fresh range image vs the C sample: 298 beams, median 4 mm, 98% within 5 cm, so the placement is unchanged |
| 2–5 | latched, manual-only, commands zero, disarmed | latched ("REMOTE STOP: joystick unavailable"), manual-only true, disarmed; 8/8 `/cmd_vel` samples 0.0 |
| 6 | no Nav2 goal | no goal status; navigation actions idle |
| 7 | sensors | `/scan` 7.7 Hz, IM10A 10.2 Hz, wheel odom 9.2 Hz, encoder update 7.5 Hz, `/odom` 8.7 Hz |
| 8 | hashes | Stage 21 `c551be00…`/`7d457c9f…`, recorder `7110961c…`, Stage 24 `273989b2…`/`d95828a0…`/`325df94a…`, EKF `69dd4479…`, map `d957f0fe…` all intact |
| 9–11 | fresh verification | see §3 |
| 12 | no newer motion invalidated C | see row 1. A guard re-checked for MOVING events since the fresh verification (none) and the latched policy immediately before the seed |

## 3. LIVE GLOBAL VERIFICATION (20:51:41–20:52:14, dry run, verdict file unchanged)
- Global: VERIFIED (0.235, −1.435, 78°), fit 0.981, margin 0.089. Next: (4.055, −0.735, 162.5°) 0.892.
- Dhruv Room: VERIFIED (0.235, −1.435, 75°), fit 0.981, margin 0.115. Next: (0.335, −1.235, −112°) 0.866.
- vs C: 0.0 m, 3° (global) / 0° (room). Thresholds unchanged (0.93 / 0.06).

## 4. AMCL SEED SUCCESS
- **One attempt**, 20:52:54 (`seed_atlas_localization.py --verify-place "dhruv room"`, no `--dry-run`).
- Seeded pose **(0.235, −1.435, 78.0°)**, fit 0.981, margin 0.105; σ 0.10 m / 8°. Log: "Seeded AMCL from LiDAR-verified pose x=0.235 y=-1.435 via service".
- Preserved: the pre-seed verdict and check files and "AMCL: no pose" in `data/diagnostics/stage24_recovery_20261015/pre_seed_205230/`
  (verdict sha `3e77b469136cae5b`); the old UNKNOWN verdicts remain in `localization_verdict_history.jsonl`.
- The new verdict file records mode `verify_in_place`, VERIFIED. No saved seed was overwritten, no value was forced, no retry.
- The seed lives in the running AMCL only. After a reboot the normal boot verification applies, unchanged.

## 5. AMCL after seeding
- First sample (30 s): (0.193, −1.387, 73.2°); settled to (0.158, −1.400, 74.3°), i.e. 0.08 m / 3.7° from the seed
  (inside its σ). Covariance: σxx 0.00102 → 0.00007, σyy 0.00066 → 0.00041, σyaw 0.0085 → 0.0006 (rad²/m²).
- Dashboard `amcl_quality`: xy std 0.022 m, yaw std 1.4°, uncertain false, large step false, last step 0.0.
- Frame `map`; AMCL message age ≤1.2 s, `/odom` age ≤0.2 s, scan age ≤0.31 s.

## 6. DASHBOARD LOCATION: backend verified, page not seen by me
Feed the chips use (`/api/map`, `/api/status`): `localization_check` VERIFIED (check age ≤21 s, limit 60 s),
`start_verdict` VERIFIED current boot, live map-frame pose (0.159, −1.399, 74.9°) from the authoritative
`map→base_link` TF. By the page's own code (`web/v2/shell.js`) that renders the chip "Localization verified" and
the motion chip "Stopped". `control_policy.source` is "STOPPED", motion state "quiet".
**I could not see the rendered page**: the browser pane loaded it without its scripts (every sub-request needs a fresh
approval). Please confirm the Live Mapping page shows the robot at the expected spot in the room.

## 7. 10-MINUTE PARKED STABILITY (20:53:24–21:03:39, 20 samples, read-only watcher)
- AMCL x 0.156–0.193, y −1.406…−1.387, yaw 73.2–75.5°; largest step between samples 0.015 m, 0.9°; no jump near 0.5 m.
- 21 LiDAR-vs-AMCL monitor checks, all VERIFIED, fit 0.981–0.985 (distance 0.037–0.084 m, heading 0.6–3.0°).
- `/odom` constant at (−0.0243, −0.0001), |v| and |ω| 0.0; 2838 `/cmd_vel` messages, **0 non-zero**.
- A single monitor MOVING/stopped blip at **21:03:43**, as the watch ended: I do not know the cause (not a measured
  displacement: `/odom`, AMCL step and jump indicators all stayed at zero afterwards, 21:05).
- Preserved at 21:05: latched, manual-only true, disarmed, all protected hashes unchanged, ekf 3242, localization 6019,
  monitor 1923, mux 1817, no restarts. **Stage 21 STOPPED indication intact** (policy source STOPPED, motion "quiet").

## 8. MOVING VALIDATION PENDING (prepared, NOT started; needs your separate approval)
Room limits: ~1.35 m wall to wall, so travel ≤0.5 m each way.
- **A0, optional, no motor power:** E-STOP latched, push ATLAS ~0.5 m forward and back by hand with all four wheels on the
  floor, recorder on. Answers the odometry question: do encoders count when wheels roll while latched?
- **A1–A2 (needs E-STOP release and manual driving by you):** ≤0.15 m/s forward and back ~0.5 m, then stop; tape-measure each leg.
- Recorder: installed profile `steering-validation` (≤600 s per run, `nice 10`; 41 topics incl. `/atlas/encoder_update`,
  `/particle_cloud`, `/amcl_pose`). Abort if `/yahboom/odom` <8 Hz.
- Pass criteria: wheel/EKF odometry ≈ tape distance when wheels roll; AMCL follows with no jump >0.5 m; Dashboard
  Moving while moving and Stopped within ~2 s of stopping; heading drift ≤ a few degrees; the monitor treats it as
  deliberate motion, not failure; LiDAR pose after each stop within 0.15 m of the tape.
- Candidate B stays undeployed until that baseline exists.

## 9. Source changes
None. No tests were needed. Nothing was deployed, restarted, moved or recorded.
