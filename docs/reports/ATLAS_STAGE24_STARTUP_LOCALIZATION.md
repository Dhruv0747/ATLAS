# Stage 24: startup localization after the 19:15 reboot, 2026-10-15

**Status:**
- **Code committed:** `cbf6dcc`; package source `d4614b1`; live-base seeder diff on
  `deploy/stage24-live-seeder` `e3a0ec1`.
- **Offline tested.**
- **Jetson scratch rehearsal:** MATCH.
- **Live dry run:** VERIFIED in Dhruv Room.
- **NOT deployed. AMCL NOT seeded.** Both await approval.

## Live state (19:29–19:45, read-only)

- **Safety:** latched, manual-only.
- **Hashes:** Stage 21 driver (`c551be00`, `7d457c9f`) and Stage 22 recorder (`7110961c`) survived
  the reboot. EKF `69dd4479`, map `d957f0fe` / `4beb26d5`, Stage 16 seeder `db634ff0` unchanged.
- **Startup:**
  - `atlas-localization` needed 3 restarts while the LiDAR started;
  - LiDAR up at 19:28:51;
  - load average peaked at 61.9 during boot.
- **Startup verifier (19:29:46):** UNKNOWN, "ambiguous (0.98 vs 0.97)".
  - Best (0.115, −2.155, 71.5°) in Dhruv Room; runner-up (2.335, 0.665, 177°) north of the
    corridor; margin 0.011.
  - **AMCL was never seeded:** NOT_INITIALIZED.
- **CHECK MY LOCATION (19:33):** AMBIGUOUS, margin 0.007, the same two places. AMCL has no pose.
- **So:** this is a startup localization refusal, not a dashboard display fault. The dashboard
  correctly shows "unknown".

## Root cause

Since the 11:17 boot, the LiDAR has returned **nothing** on the front / front-right arcs.

| Sector, valid of 30 beams (robot frame) | 0° | 210° | 270° | 300° | 330° |
|---|---|---|---|---|---|
| Good boots | 23–30 | 18–23 | 21–29 | 25–30 | 19–25 |
| 11:19 and 19:29 boots | 2–7 | 5 | 5–6 | 9–13 | 0–1 |

**Effect:** with those arcs blank, a corridor-side pose fits almost as well as Dhruv Room.

**What it is not:** the map and laser TF (180°) are unchanged. No code or threshold changed, and
replay reproduces all 8 recorded verdicts.

**Likely physical cause** (not verified): an object or cover very close to the LiDAR's
front-right, a light-absorbing surface there, or open space in that direction. The arcs are
identical across boots 6 h apart.

## Fix (operator-confirmed place)

**Mode:** `seed_atlas_localization.py --verify-place "dhruv room"`.
- Runs the **same** startup LiDAR verification, with candidate positions limited to Dhruv Room's
  box: `config/place_regions.json`, x −0.7…0.7, y −2.8…−0.9, bound to the accepted map YAML sha256
  `d957f0fe…`.
- **Thresholds unchanged:** fit ≥ 0.93, margin ≥ 0.06.
- **Seeds only a VERIFIED LiDAR pose,** with σ 0.10 m / 8°.
- Never overwrites the saved seed.
- The boot check (`region=None`) is unchanged.

**Evidence:**

| Run | Result |
|---|---|
| Archived replay, 8 boots, unrestricted | 8/8 recorded verdicts reproduced |
| Archived replay, in-room, 4 good boots | Same pose, margins 0.17–0.24 |
| Archived replay, in-room, 19:29 | **VERIFIED (0.115, −2.155, 71°)**, fit 0.979, margin 0.113 |
| Archived replay, in-room, 11:19 | **Still UNKNOWN** (0.953 vs 0.948): it does not force a seed |
| **Live dry run (19:44)** | **VERIFIED (0.115, −2.155, 71.5°)**, fit 0.979, margin 0.109; next in-room candidate 0.870 |

The live dry run seeded nothing and wrote nothing (verdict file hash unchanged). A first dry run
returned UNKNOWN "no odometry while the startup scan was collected": `/odom` discovery took longer
than the seeder's 3 s window at load 30, and the second run succeeded.

**Tests:**
- 9 new (region and seeder);
- verify suite 35, with 2 pre-existing errors at HEAD from the undeployed Stage 20 seeder change.
  Against the patched **live** seeder those 2 pass; the only errors are 3 files missing from the
  scratch tree.

**Package `stage24-verify-place`** (sha256 `a4bb84f4…`):

| File | Live now | After install |
|---|---|---|
| `seed_atlas_localization.py` | `db634ff0…` | `273989b2…` |
| `atlas_localization_verify_core.py` | `abe5c2a3…` | `d95828a0…` |
| `config/place_regions.json` | absent | `325df94a…` (new) |

- No restart. Running processes keep their loaded core; the next boot check is unchanged.
- Rollback rehearsed in the container: it restores both hashes and removes the config.

## Approvals requested

1. **Physical check (no motion):** look at the LiDAR's front-right. Is anything within about 20 cm,
   covering it, or a black or shiny surface facing it? Remove it if so. Claude then re-runs the
   read-only check; restoring coverage should restore normal unique verification at boot.
2. **Install stage 24:** 3 files, no restart.
3. **Seed AMCL once:** `seed_atlas_localization.py --verify-place "dhruv room"`. It re-verifies live
   and seeds only if VERIFIED again, with the unchanged thresholds.

**Then validate:**
- AMCL pose and tracking fit (monitor);
- the dashboard location;
- 10 min parked stability.

**Expect CHECK MY LOCATION to keep reporting AMBIGUOUS** while the LiDAR arcs stay blind: its
search is whole-map by design.

## Not done

No seed, no install, no restart. Candidate B is not deployed (it addresses moving drift, not this).
Foxglove is unchanged.
