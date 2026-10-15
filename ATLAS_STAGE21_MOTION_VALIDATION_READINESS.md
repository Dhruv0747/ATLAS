# Motion validation readiness (Stage 21 follow-up), 2026-10-15 13:45 IST

Branch `agent/sync-developer-20261011`. Nothing was restarted, deployed, recorded or moved for
this report.

**Verdict: READY TO RECORD a physical baseline, with one gap.** AMCL is not seeded on this boot, so
the AMCL parts of Test C, and Candidate B's AMCL criterion, need your seeding decision first (§8).

## 1. Stage 21 health (13:12–13:15, read-only)

**Installed files and backup:**
- `yahboom_base.py` `c551be0053a4…` and `atlas_encoder_selection.py` `7d457c9f9293…`: as deployed.
- Backup `…/2026-10-15-125345-601344477-stage21-driver-stop-anchor/` present, with both originals.

**Services:** base 45674, EKF 2802, mux 1788, localization 4521, IM10A 1802, LiDAR 1790. All
active, 0 restarts.

**Sensors and safety:**
- encoders fresh (18 ms), accepted [1, 2, 3, 4], source `stopped`;
- `/yahboom/odom`, `/atlas/encoder_update` and `/odom` at 10.0 Hz (after 2.4 s DDS discovery);
  `/odom` at (0.0, 0.0);
- IM10A 9.6 Hz; `/scan` 7 Hz;
- policy: latched, manual-only, commissioning disarmed; `/cmd_vel` zero;
- remote: `/dev/input/js0` present, `/joy` 8 Hz.

**Resources:** RAM 4.9/7.6 GB; thermal zones 58–59 °C; 369 GB free. Load average swings between
6.7 and 22.9 (1 min), recorded as a risk for recording.

**Configs:** accepted map `d957f0fe…` / `4beb26d5…` and EKF `69dd4479…` unchanged.

## 2. Recording method and topic completeness

**Use the installed Stage 6b recorder** (`atlas_motion_recorder.py`, live hash `02fcaed2…` = `0c1d520`).
- Opt-in `--record`, motion-triggered, with 10 s before and 10 s after each motion.
- 500 MB cap; no service, no publishers.
- It is not governed by the Stage 20 75% CPU admission rule; that rule belongs to the Stage 20
  recorder.

| Required evidence | 6b default profile | With optional stage 22 profile |
|---|---|---|
| LiDAR `/scan`, `/scan_raw` | yes | yes |
| Raw M1–M4 counts (`/yahboom/encoder/m1..m4`) | yes | yes |
| Wheel odometry, EKF `/odom`, TF | yes | yes |
| IM10A corrected gyro | yes | yes |
| IM10A raw (`/im10a/imu/unvalidated`) | **no** | yes |
| Accepted encoder increments, packet age (`/atlas/encoder_update`) | **no** (reconstructable offline from raw counts, approximately) | yes |
| AMCL pose + covariance | yes (only if AMCL is seeded) | yes |
| AMCL particles | no | yes |
| Commands (`/cmd_vel` and every source), steering commands, `traction` flag | yes | yes + `/joy` |
| Per-wheel applied PWM | **no topic exists** (only during the lifted test) | no |

**Optional stage 22** (`stage22-recorder-steering-profile`) adds the missing items through
`--profile steering-validation`.
- Recorder file only; default profile and helpers unchanged; capture limited to 30–600 s per run.
- Patches the live file → `7110961c…`. MATCH against the baseline; rollback restores `02fcaed2…`
  exactly (rehearsed); recorder tests pass.
- **Recommended**, because exact accepted increments are what separate the consensus estimator's
  losses from the encoders' own.

**During recording:** run the recorder at `nice 10`. Abort if `/yahboom/odom` drops below 8 Hz, the
control-policy age exceeds 0.5 s, or the operator sees anything unexpected.

## 3. Single-operator procedure (about 20 min, ATLAS latched between steps)

**Before starting:**
- clear 3 m of floor, away from walls, so LiDAR sees varied geometry;
- a tape line with marks at 0, 1 and 2 m; a measuring tape; tape for marking the end position;
- ATLAS's rear axle centre placed over 0 m, body aligned to the line by eye;
- steering centred (commanded 90/90);
- Claude starts the recorder (on approval) and confirms topic health.

**Remote:**
- left stick forward/back: up to 0.75 m/s at full deflection;
- right stick left/right: turning;
- **B** = E-STOP latch;
- **LB** held 2 s with sticks centred, then released = unlatch.
- Do not use RB (turbo).

| Step | Action | Measure (operator) |
|---|---|---|
| 0 | 30 s still (latched) | — |
| A1 | Unlatch, then about 20% left stick (~0.15 m/s), straight, to the 2 m mark. Stop. **B** | Distance travelled (centre of rear axle); sideways offset of the rear and front axle centres from the line; ATLAS heading vs the line (offset of front vs rear) |
| A2 | Same, in reverse, back towards 0 | Same three |
| B1 | Re-align at 0. About 55% stick (~0.4 m/s) forward to 2 m. **B** | Distance, sideways offset |
| B2 | ~0.4 m/s reverse to 0. **B** | Distance, sideways offset |
| C1 | Re-align. ~0.15 m/s forward with gentle left steer, about 90° arc. **B**. Wait 30 s | Final heading change (mark the floor) |
| C2 | Same, gentle right | Same |

**Rules:**
- After every step: latch B, wait 20 s motionless, then measure. A ruler or tape to 1 cm is enough;
  heading as a front-vs-rear sideways difference over the wheelbase.
- Stop on any unexpected motion, a stall, wheel scuffing, or a LiDAR/encoder warning on the
  dashboard.
- No autonomy, no Foxglove goals.

## 4. Tape measurements to record

For each step: start mark; end distance along the line (cm); rear-axle sideways offset (cm, + left);
front-axle sideways offset (cm); and for C, the final heading (°). Note anything abnormal.

## 5. Baseline metrics available now (offline, 9 Oct, production EKF A)

These are the comparison points. The physical baseline will replace them.

| Metric | Value |
|---|---|
| Heading drift per ~1.4 m (EKF vs LiDAR) | 5.1 / 7.4 / 23.6° (Humble replay) |
| Per-pair heading error, 90th percentile | 1.7–3.8° |
| EKF travel direction vs own heading, 90th percentile | 9–26° (LiDAR: about 9°) |
| Raw distance / LiDAR (0.1–0.45 m/s) | M1/M4 0.64–0.72; M2 0.51–0.64; M3 about 0 |
| Constant LiDAR travel-direction offset | +5.5° (4.5–6.5° per drive) |
| Real parked drift | ≤ 4.4 cm (A) |

## 6. Candidate B readiness (stage 23, not approved)

| Check | Status |
|---|---|
| Baseline recording with EKF A | **Pending:** this session |
| Map / EKF hashes | Verified 13:12 |
| Config diff | Semantic comparison: **only `odom0_config` indices 0 and 1** differ |
| Native Humble | robot_localization 3.5.4 (same as the Jetson), A/B reproduced |
| Stop anchor | Stage 21 live |
| Restart continuity | **New finding:** a plain `atlas-ekf` restart resets `/odom` to the origin (native Humble: **1.15 m / 34° jump**), which AMCL would treat as motion. Fixed procedure: `tools/deploy/ekf_continuity_config.py` sets `initial_state` to the parked `/odom` pose (read-only check; refuses unless latched, manual-only and still). Result: 0.0 m / 0.0° jump. Used for deployment **and** rollback (3 tests) |
| Backup / rollback | `tools/deploy/readmes/stage23-ekf-candidate-b.txt` |
| Same-boot restarts | Any later same-boot EKF restart must use the helper again; reboots are unaffected |

## 7. Risks and rollback

**Risks:**
- An operator speed that isn't constant: analysis uses LiDAR-measured speed per pair.
- High load spikes (to 22.9) during recording.
- Accidental motion during unlatch: mitigated by the LB rule (sticks centred, 2 s).
- The motion-trigger thresholds miss very slow creep (< 0.02 m/s).
- Candidate B: AMCL behaviour unproven.

**Rollback:**
- Stage 21: as in its report.
- Stage 22: `ROLLBACK.sh`, no restart.
- Stage 23: continuity-helper rollback.
- **Failure criteria for B:** any §7 criterion of the deployment plan.

## 8. Blockers and missing evidence

1. **AMCL not seeded on this boot.**
   - The startup verifier refused: exact tie, "1.00 vs 1.00". AMCL has requested an initial pose
     since 11:17.
   - Without a seed: no AMCL pose, covariance or post-stop stability in Test C, and B's
     "AMCL jump ≤ 0.5 m" criterion can't be evaluated.
   - Needs: you confirm where ATLAS physically is → run CHECK MY LOCATION (read-only) → approve a
     seed through the existing Set Location flow.
2. Raw IM10A and accepted increments need stage 22 (optional but recommended).
3. Per-wheel PWM is not observable without a code change. It is not needed for CPR vs slip; not
   pursued.
4. Foxglove exposure: open risk, deferred by you; unchanged and unused.

## 9. Commit

This report, `tools/deploy/ekf_continuity_config.py` with its tests, the stage 22/23 readmes and the
restart-continuity test are in the commit after `6acb0c0`.

## 10. Approvals needed before ATLAS moves

1. **AMCL seeding** (§8.1), after you confirm the physical location. Otherwise accept a baseline
   without AMCL metrics.
2. **Stage 22 recorder profile** install: no restart; optional but recommended.
3. **Recorder activation** for the session: about 20 min, bounded runs (≤ 600 s each with stage 22).
4. **E-STOP release and manual driving** by you, for Tests A–C exactly as in §3.

**Separately, later:** stage 23 (Candidate B), only after the baseline is recorded and analysed.
