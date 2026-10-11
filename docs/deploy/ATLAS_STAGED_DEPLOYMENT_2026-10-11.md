# ATLAS staged deployment plan: four independent stages (2026-10-11)

Status: **all four stages prepared, tested offline and staged. Nothing is installed.** Each stage
needs your separate, explicit approval.
- **Staged at:** `~/project_atlas/data/staging/2026-10-11/` on the Jetson. These are inert
  tarballs with `SHA256SUMS`.
- **Production unchanged:** `rover-status-web` and the Visual Cloud services run the same files as
  before. The sha256 of `scripts/` + `config/` was identical before and after staging.

| Stage | What | Files | Restart | Measured effect | Approval |
|---|---|---|---|---|---|
| 1 safety | Web E-STOP latches the mux stop; drive refused while latched; stop/E-STOP accepted during shutdown; reboot action removed | `atlas_status_web.py` (2 ordered diffs) | `rover-status-web` | 13 offline safety tests + mux contract | **pending:** after you review `docs/security/ATLAS_ESTOP_SAFETY_REVIEW_2026-10-11.md` |
| 2 Glass UI V2 | `/v2/` pages, V2 E-STOP on pointerdown, 3-line static route | `web/v2/*` (19), `atlas_web_v2.py`, `atlas_status_web.py` (route only) | `rover-status-web` | Every V1 request contract identical; camera/radar requests 0 when off screen | **pending:** you asked to test on your phone after the safety review |
| 3 executor split | Hot/cold rclpy executors in `rover-status-web` | `atlas_status_web.py` | `rover-status-web` | Real module, isolated domain: 57% → 40.7% of one core | **pending** |
| 4 Visual Cloud | Local-only, viewer- and activity-activated monitoring; bounded history; no placeholder uploads | agent, core, server, `config/atlas_visual_cloud.json` | both Visual Cloud services | Live side by side: idle 11.5% → 1.4% of one core | **pending** |

**Recommended order:** 1 → 2 (then your phone test with the PC off) → 3 → 4.
- Each stage can also be installed alone or in any order. All 24 orders were rehearsed.
- Stages 1, 2 and 3 all restart `rover-status-web`. Installing them in one coordinated window
  means one ~5 s dashboard gap instead of three, but approve each one explicitly.

## How every package works

`install.sh`:
1. Checks that all patches apply, on a scratch copy of the live files, in order.
2. Backs up every file it will touch to `data/backups/<timestamp>-<stage>/`.
3. Writes `ROLLBACK.sh` there, with the install root **pinned**.
4. Applies the patches, byte-compiles, and reports a hash MATCH or DIFFER per file.
5. **Restarts nothing.** `README.txt` gives the single restart command. `verify.sh` runs GET-only
   checks, starting with `verify.sh capture` before installing.

## Rehearsals performed

**In the container:** `tools/deploy/check_packages.py` ran on an export of the deployed baseline
`aa93355`.
- **24/24 install orders of the four stages:** every resulting file equals the branch head.
- **Rollback:** every `ROLLBACK.sh` was run newest-first without `ATLAS_ROOT` set. Each restored
  the tree byte-for-byte.

**Stage-alone unit tests on the rehearsed trees:**
- stage 1: E-STOP 11/11 and no-reboot 2/2, plus the existing status-web tests;
- stage 2: route 6/6;
- stage 3: split 5/5 (the baseline comparison runs only in git);
- stage 4: Visual Cloud 27 tests.

**On the Jetson, on copies of the live files:** all four stages forward, all four reversed, and
each stage alone. Results:
- installs clean, byte-compile OK;
- rollback identical to live;
- live `scripts/` + `config/` hash unchanged.

### Incident during the first Jetson rehearsal (recorded, no effect)

The first rehearsal script ran each stage's `ROLLBACK.sh` without setting `ATLAS_ROOT`. The
rollback script then defaulted to the live tree, `~/project_atlas`. As a result it:
- copied its backups over the live files `scripts/atlas_status_web.py`,
  `atlas_visual_cloud_{agent,core,server}.py` and `config/atlas_visual_cloud.json`. Those backups
  were byte-identical copies of the same live files, preserved with `cp -a`;
- tried to remove `scripts/atlas_web_v2.py` and `web/v2/*`, which do not exist on the Jetson.

Afterwards, every live file had its original sha256 (`51f8e111…`, `a7d3fd22…`, `867a49e2…`,
`72022596…`, `cacccc5a…`) and its original mtime. No service was restarted, and all three
services stayed active.

The packager was then fixed:
- `ROLLBACK.sh` now has its install root pinned at install time and never reads the environment;
- the checker refuses any rollback whose root is not pinned and runs rollbacks with `ATLAS_ROOT`
  removed.

The staged packages were rebuilt after this fix, and the second rehearsal is the one reported
above.

## Not included in any stage

- The V1 one-line E-STOP `pointerdown` fix (V1 sends no `e_stop` during a two-finger touch). It
  awaits your decision.
- Same-origin enforcement on form POSTs, telemetry escaping and intercom auth (security items 3
  and 5).
- Rotating the Jetson password, and git-history handling.
- Any change to the mux, motors, Nav2, localization, maps or networking.

## Pre-existing test failures (not caused by these changes)

These fail identically at baseline `aa93355` in this container:
- `test_atlas_mobile_notifier_core`, `test_atlas_person_fusion_core`;
- `test_ultrasonic_validity`: `AtlasCmdVelMux` has no `navigation_localization_guard` in the
  extracted test scope;
- `test_opposite_steering_geometry`: no tests ran.
