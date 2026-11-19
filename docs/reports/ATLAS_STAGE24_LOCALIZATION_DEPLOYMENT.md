> **Erratum, 2026-10-15 20:40.** §6–§7 and §9 below describe ATLAS as *stationary* when A and B were produced.
> That inference (from `/odom` ≈ 0) was wrong: beam-by-beam scan comparison and the monitor's motion log show ATLAS
> was physically moved at ~19:46 and ~20:19. See `ATLAS_STAGE24_POST_DEPLOYMENT_LOCATION_RECOVERY.md`.
> **Owner confirmed 20:49:** the moves at ~19:46 and ~20:19 were deliberate localization tests.
> The original text is kept unchanged below.

# Stage 24: live deployment and startup localization recovery, 2026-10-15 20:05–20:12 IST

**Statuses: DEPLOYED. REGIONAL VERIFIED: NO (see §6). AMCL SEEDED: NO. PARKED VERIFIED: N/A (no seed).
BLOCKED on the seed (pose inconsistency). GLOBAL AMBIGUITY: not reproduced on this live scan, but unproven stable.
ROLLED BACK: no.**

Installed Stage 24 (3 files, no restart). Made **no seed**: two verified poses 1.2 m apart from a
stationary robot cannot both be right, and the seed condition "consistent with the independently
observed candidate" fails. Nothing was forced.

## 1. GitHub
Branch `agent/sync-developer-20261011`. Latest HEAD at preflight `32c61db`, no newer commits, no conflicts.
Source commit `cbf6dcc`; package source `d4614b1`; live-base seeder diff on `deploy/stage24-live-seeder` `e3a0ec1`.
This report's commit is recorded in the push (see the branch log).

## 2. Preflight (20:05–20:07)
- E-STOP: found **released**; owner pressed B. Rechecked 20:07: latched, manual-only true, commissioning disarmed,
  `/cmd_vel` zero, encoder counts unchanged, no Nav2 goal.
- Stage 21 `yahboom_base.py` `c551be00…`, `atlas_encoder_selection.py` `7d457c9f…`; Stage 22 recorder `7110961c…`
  intact after the reboot. Map `d957f0fe…`/`4beb26d5…`, EKF `69dd4479…` unchanged.
- LiDAR, IM10A and encoders publishing. CPU/RAM/thermals normal for this system (60–61 °C; load spikes noted).
- Backups complete (§5).

## 3. Tests and the three earlier errors
- Complete-tree run in the container: verify suite 35 tests OK; location suites OK.
- **Cause of the earlier errors (all explained, none from Stage 24):**
  - 2 errors: pre-existing at HEAD, from the undeployed Stage 20 seeder observer lines. Against the live
    (Stage 16) seeder with Stage 24 applied they pass.
  - 1 error class: 3 files missing from the Jetson scratch tree (environment, not code); passes in a full tree.
- Not caused by Stage 24. 9 new tests (region + seeder) pass.

## 4. Deployed files (MANIFEST MATCH, py_compile OK, config parses)
| File | Before | After |
|---|---|---|
| `scripts/seed_atlas_localization.py` | `db634ff0…` | `273989b23e9ee02342acbe23ba517f9a9be97124092b86ef94d0f6c9f6ebe883` |
| `scripts/atlas_localization_verify_core.py` | `abe5c2a3…` | `d95828a09b174d109033c4af10fdf2f65599e1c7365ca669dff3428e6e723462` |
| `config/place_regions.json` | absent | `325df94a7cade0cc7f02b424f0a2a097436c5f3df6ebecfa520e5e2a203cf775` |

Package `stage24-verify-place.tar.gz` sha256 `a4bb84f45359a185baecee0067fe911db8ebadaf40ea15078c93ad5ad25210d6`.
Hashes re-read at 20:10 and unchanged. Confirmed: `--verify-place` exists and is opt-in; boot path unchanged
(`ExecStartPost` runs `verify` without it); region bound to map sha `d957f0fe…`; thresholds still 0.93 / 0.06;
no restart; production service PIDs unchanged.

## 5. Backups and rollback
- Stage 24: `~/project_atlas/data/backups/2026-10-15-200802-082675749-stage24-verify-place/` → `bash …/ROLLBACK.sh`
  (restores both files, removes the config; no restart).
- Pre-seed localization state: `~/project_atlas/data/diagnostics/stage24_20261015/pre_seed_200743/`.
- Stage 22 / Stage 21 backups untouched.

## 6. Live verification (all read-only, `--dry-run`, verdict file hash unchanged each time)
| Time | Mode | Pose | Fit | Margin | Quadrants |
|---|---|---|---|---|---|
| 19:44 (before install, patched copy) | in-room | (0.115, −2.155, 71.5°) | 0.979 | 0.109 | [65, 19, 59, 89] |
| 20:08 | `--verify-place "dhruv room"` | (0.335, −0.935, 72.0°) | 1.000 | 0.116 | [62, 57, 76, 64] |
| 20:08 | unrestricted global (`verify`) | (0.335, −0.935, 72.0°) | 1.000 | 0.098 | [64, 56, 75, 65] |

Global runner-ups: (1.755, −0.135, 16°) 0.902; (3.295, 0.025, −102°) 0.898. Earlier real boots verified
(0.235, −1.735, 75°) and (0.275, −1.835, 69°).

**Findings**
- ATLAS did not move: `/odom` = (−0.012, 0.000) since boot; encoder counts unchanged; zero commands.
- The LiDAR scan changed between 19:44 and 20:08: the previously blind front arcs now return data
  (quadrant 2: 19 → 57). Cause **unknown**; nothing was changed by me. The owner states the arrangement is unchanged.
- The new pose is **1.2 m** from the 19:44 candidate, **0.8 m** from earlier good boots, and 0.035 m inside the
  region edge (y_max −0.9).

## 7. Seed decision: NOT SEEDED
Failed conditions: (a) proposed pose is **not consistent** with the independently observed Dhruv Room
candidate(s); (b) the owner confirmed only "Dhruv Room", not a spot, so placement cannot arbitrate; (c) the
region-edge position means the box may be clipping the true optimum. The fit 1.0 / margin 0.116 is the best
evidence yet, but a stationary robot gave two different "VERIFIED" answers within 25 minutes; that is a
reproducibility failure, not a pass. No `/set_initial_pose` call was made; AMCL remains NOT_INITIALIZED and
the saved state was not touched. Post-seed validation (§7 of the order) therefore **not applicable**.

## 8. Safety and Stage 21 (20:10)
Latched, manual-only true, commissioning disarmed, `/cmd_vel` zero, `/odom` static, protected hashes unchanged,
atlas-ekf / localization / monitor / mux active. Stage 21 not modified; STOPPED display not touched. Dashboard
location remains unknown (no pose).

## 9. Global ambiguity
The 19:33 CHECK MY LOCATION result was AMBIGUOUS (margin 0.007). The 20:08 global dry run was unique
(margin 0.098) on a scan with restored coverage. **One fresh sample is not a pass.** Boot-time ambiguity
cannot be called fixed or reproducible; the LiDAR coverage change is unexplained and could recur.

## 10. Needed to unblock (owner)
1. Repeat the read-only dry run 2–3× (no motion) and confirm the pose is stable; compare with a tape
   measure of ATLAS's actual spot in the room (distance to two walls) against (0.335, −0.935, 72°) and
   (0.115, −2.155, 71.5°).
2. Widen/redraw the Dhruv Room box only with evidence (the pose sits on its edge) — requires approval.
3. Then approve one seed, with the existing mechanism, if stable and consistent.
Candidate B, Foxglove, Stage 17B hold, E-STOP physical tests, and credential rotation remain as before.
