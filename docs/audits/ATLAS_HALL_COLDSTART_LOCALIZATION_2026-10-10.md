# Hall cold start localized as Dhruv Room: investigation, 2026-10-10

Operator test: ATLAS was restarted while parked in the Hall. The dashboard
showed MAP WAITING, then a pose in Dhruv Room (X 0.497, Y −1.183, ~84°)
labelled CONFIDENT. This report covers why, what was checked, an offline
and read-only live evaluation of a fix, and a controlled validation plan.
No motion was commanded. Production files are unchanged by this report;
deployment is a separate, explicit step (see "Deployment").

## Answer first

| # | Finding | Status |
| --- | --- | --- |
| 1 | **Every localization start seeds AMCL at the saved Dhruv Room pose without looking at the LiDAR.** `atlas-localization.service` runs `seed_atlas_localization.py` 10 s after launch. It reads `localization_seed_pose.json` (Dhruv Room, written 2026-10-09 12:10), else `home_pose.json`, and calls `/set_initial_pose`. Today it ran at 16:36:10 with x=0.254, y=−1.539. | **Confirmed** (journal, source, files) |
| 2 | **AMCL cannot escape a start 6 m wrong.** The seed spreads particles ±0.5 m / ±15° around Dhruv Room. With `recovery_alpha_slow/fast = 0` no random particles are ever injected. While parked, the 1 Hz forced updates kept resampling the best local fit near Dhruv Room. The cloud collapsed to **one unique pose duplicated 2,000 times**. | **Confirmed** (live `/particle_cloud`, params) |
| 3 | **"Extremely small, slightly negative covariance" is that collapse.** With every particle identical, the set covariance is floating-point round-off: xx −2.2e−14, yy −7.9e−14, yaw +5.4e−14 m²/rad². It measures nothing. Depending on the sign of that noise, the map page showed CONFIDENT (tiny positive) or invalid → UNCERTAIN (negative, as recorded at 16:55). Mission control and the mux clamp negative variance to 0 and so read it as **perfect** confidence. | **Confirmed** (live `/amcl_pose`, source) |
| 4 | **The LiDAR says Hall, unambiguously.** Searching the whole saved map with no prior: best pose (6.275, −2.115, −95.5°), held-out fit 0.976; next distinct place 0.789 (margin 0.187). The current AMCL pose fits 0.54; the Dhruv Room seed fits 0.37; the saved "hall" place fits 0.963. | **Confirmed** (live recording) |
| 5 | **Delayed start = LiDAR would not start for 11.5 min.** 25 failed starts (`Can not start scan: 80008002` / `SL_RESULT_OPERATION_TIMEOUT`) from 16:24:28 to 16:35:3x. Bounded recovery gave up at 16:31:28 ("HARDWARE ATTENTION"); systemd kept retrying and the scan started at 16:35:45. Localization start failed while `/scan` was absent and finally started at 16:36:13. Same signature 23 times on Oct 9 09:00–10:59 (ATLAS-015). | Confirmed timeline; cause (power/USB/motor spin-up) **hypothesis** |
| 6 | **SSD/reboots.** No NVMe PCIe AER errors since the 14:29 boot. The 16:24 restart was clean (shutdown recorded). The four earlier crash reboots (ATLAS-018) stand, and each of those also re-seeded Dhruv Room. | Confirmed |
| 7 | **The Oct 9 odometry scale (~0.6) played no part here.** The rover was stationary: `/odom` moved 0.000 m and all 146 `/cmd_vel` messages were zero. Both failures end the same way, AMCL confidently wrong, and the same LiDAR-to-map check exposes both. | Confirmed |

Autonomy is still blocked independently: live encoder health
`navigation_validated: false`, `autonomy_ready: false`. The deployed mission
scan-fit gate would also refuse this pose (fit 0.54 < 0.85).

## Startup pose sources traced

| Source | Used at start? | Evidence |
| --- | --- | --- |
| `atlas-localization.service` `ExecStartPost` → `seed_atlas_localization.py` | **Yes, always** | journal 16:36:10 "Seeded AMCL from saved pose x=0.254 y=−1.539 via service" |
| `~/.config/project_atlas/localization_seed_pose.json` | **Yes** (first choice) | Dhruv Room, 2026-10-09 12:10:07; same as named place "dhruv room" |
| `~/.config/project_atlas/home_pose.json` | Fallback only | (0.919, 0.026), 2026-10-08, older mapping session: stale |
| `named_places.json` "hall" (6.279, −2.199, −96.5°) | No (only `--place hall`) | — |
| Mode manager LOCALIZATION transition | Yes: saves the **live** map pose as the next seed, then reseeds | `atlas_mode_manager.py` `save_localization_seed`. A wrong live pose becomes the next boot's seed |
| Mission control `save_localization_seed` | After mapping only | writes the settled SLAM pose |
| Nav2 AMCL `set_initial_pose` / `always_reset_initial_pose` | No (both false) | AMCL waits for an initial pose; `save_pose_rate` only updates in-memory params |
| `/initialpose` publishers | None live | seeder uses the service, then exits |
| Dashboard | Display only | `/mapping` label from covariance thresholds only |

## AMCL checks (live recording, 16:55:20–16:55:54, parked in Hall)

- 31 `/amcl_pose` at 1 Hz (forced updates). Header stamp is 0.15–0.19 s
  before receipt, so there is no timestamp fault.
- `/particle_cloud`: 2,000 particles, 1 unique pose, unchanged for 30 s.
- Covariance as above; xy std is 0 to machine precision.
- `/scan` 7.1 Hz; `/odom` stationary; `/cmd_vel` all zero; encoder state
  READY, `navigation_validated` false, `autonomy_ready` false.

## Offline evaluation (recorded data, AMCL 1.1.20 core)

**Global scan search, no prior** (`atlas_scan_map_global_search.py`, same map
bytes as every bag): 11 parked windows. 10 are from the Oct 9 recordings
(Hall ×3, Dhruv Room ×7, including the hand-moved outbound 1636 start) and
1 is the live Hall recording. The verdict was VERIFIED at the expected room
in **11/11**:

| Window | Best pose | Held-out fit | Next distinct place | Margin |
| --- | --- | --- | --- | --- |
| live Hall | (6.28, −2.12, −95.5°) | 0.976 | (3.70, 0.41) 0.789 | 0.187 |
| 122252 start, Hall | (6.30, −2.08, −95°) | 0.996 | 0.799 | 0.197 |
| return start, Hall | (6.74, −2.34, −114°) | 1.000 | 0.874 | 0.126 |
| outbound end, Hall | (6.74, −2.34, −114°) | 1.000 | 0.867 | 0.133 |
| Dhruv Room ×7 | (0.14–0.34, −1.07…−1.64, 70–79°) | 0.975–1.000 | 0.826–0.897 | 0.082–0.149 |

The live AMCL pose offered as a "claimed" pose was rejected: 5.85 m / 180°
from the LiDAR answer → UNKNOWN. Dhruv Room has a near-180° symmetry: the
same spot rotated 184° scored 0.896 in the passive window (margin 0.082).
That is the tightest case and why a margin rule is needed.

**Cold-start replays** (8 seeds × 3 Hall windows, including the live one;
stationary; forced 1 Hz updates; production AMCL parameters):

| Start method | Correct place | Ended CONFIDENT at the wrong place | Ended CONFIDENT and right |
| --- | --- | --- | --- |
| Current: seed at saved Dhruv Room | **0/24** | 10/24 | 0/24 |
| Nav2 global localization (uniform particles) | 12/24 | 1/24 | 8/24 |
| Seed at the global-search result | **24/24** (median error 0.06–0.14 m, fit 0.98–1.00) | 0/24 | 24/24 |

Replays seeded at Dhruv Room ended at (0.14–1.55, −1.17…−1.38), the same
attractor as the live (0.497, −1.183). Nav2's own global localization is
not reliable from a parked start and is rejected as the startup mechanism.

## Live read-only check of the fix (dry run, nothing seeded or written)

`seed_atlas_localization.py --dry-run` on the Jetson with ATLAS parked in
the Hall, 17:05–17:20. Seven results were captured (an eighth run's output
was overwritten before it was read):

- Every captured run's best place was the Hall (6.24–6.30, −2.07…−2.26,
  −93…−97°). **No run picked any other place.**
- 3 runs: fit 0.95, 0.991, 0.991 → VERIFIED.
- 4 runs → UNKNOWN: fit 0.91, 0.916 and 0.926 (below 0.93), and one early
  run at fit 0.858, margin 0.004 (ambiguous).
- The fit at the same parked spot ranged 0.86–0.99 within minutes. Most
  likely people moved within LiDAR range; this is unconfirmed. The policy
  then reported UNKNOWN rather than guess.
- Time per run on the loaded Jetson: ~30 s, of which ~14 s is the search.

## Changes implemented (repository; not deployed)

All additive. With no configuration, startup behaves exactly as before.

1. `atlas_localization_verify_core.py` (new, pure): saved-map loader, global
   scan search, verdict policy. A pose is VERIFIED only if the best held-out
   fit is ≥ 0.93 **and** it beats every other place ≥ 1 m away or ≥ 30°
   rotated by ≥ 0.06, with ≥ 120 returns. Otherwise the verdict is UNKNOWN.
   A claimed pose must agree within 0.5 m / 20°.
2. `seed_atlas_localization.py`: new `verify` mode, selected by `--mode`,
   `ATLAS_SEED_MODE`, or `~/.config/project_atlas/seed_mode`. In verify mode:
   - Needs ≥ 5 scans over 3 s with `/odom` still. If the rover moves, it is
     UNKNOWN.
   - Up to 3 checks, and all of them must agree on the place.
   - On VERIFIED, seeds the matched pose with 0.10 m / 8° spread.
   - On UNKNOWN, does **not** seed. AMCL then publishes no pose, and the
     seeder exits 0 so there is no restart loop.

   Every run writes `~/.local/state/project_atlas/localization_verdict.json`
   (including boot ID). `--dry-run` only prints the verdict. Default `saved`
   mode is unchanged apart from recording "UNVERIFIED".
3. `atlas_status_web.py`: `/api/map` adds `start_verdict` (same boot only).
4. `atlas_mapping.html`: green **LIVE / AMCL CONFIDENT (START VERIFIED)**
   needs low covariance **and** this boot's LiDAR verification. Otherwise:
   - **AMCL CONFIDENT - START POSE NOT VERIFIED** (amber);
   - **LOCALIZATION UNKNOWN - LIDAR DID NOT CONFIRM START POSE**;
   - a "Start pose check" row.
5. `atlas_mode_manager.py`: seeder timeout 30 → 150 s, and the status text
   reports UNKNOWN or verified instead of "seeded at …".

Tests: 17 new verify/seeder/status tests plus 9 dashboard tests (Node); the
44-test related set passes. Browser check with 5 verdict cases rendered the
expected labels.

## Not changed (needs a decision)

- **Mux and mission-control covariance clamp** (`max(0, var)`): a collapsed
  cloud reads as perfect confidence. Recommend treating total variance
  < 1e−9 as "no confidence measure". This is safety code, and autonomy is
  already blocked, so it is left for a separate reviewed change.
- **Mission scan-fit threshold 0.85**: wrong distinct places scored up to
  0.897 in this data. Recommend 0.93 plus the uniqueness check above before
  any autonomous start.
- **Mode manager persisting the live pose as the next seed**: in `saved`
  mode a wrong live pose propagates to the next boot. `verify` mode stops
  using it.
- **LiDAR start-up failures**: check the LiDAR USB power and cable, and test
  powering the LiDAR from a separate 5 V supply. Watch whether failures
  follow cold boots with the camera and cellular modem enumerating at the
  same time.
- Encoder calibration, EKF, AMCL parameters, map, network, motors: untouched.

## Controlled validation procedure

No motion is needed or allowed. Keep the remote stop in reach and leave
`navigation_validated: false`.

1. Deploy with backups (see below). Check that
   `seed_atlas_localization.py --dry-run` runs and writes nothing.
2. **Hall, parked on a marked spot**: run the dry run 3 times. Pass if each
   result is VERIFIED within 0.3 m / 10° of the marked pose or UNKNOWN, and
   never another place.
3. Enable `verify` (`echo verify > ~/.config/project_atlas/seed_mode`).
   **Reboot in the Hall** with nobody within 2 m of ATLAS. Pass if the
   dashboard shows START VERIFIED near the Hall, or LOCALIZATION UNKNOWN with
   AMCL unseeded. Save the verdict file and a 30 s bag.
4. **Reboot in Dhruv Room**: same pass rule.
5. **Negative**: reboot with ATLAS somewhere not uniquely in the map (box
   around the LiDAR, or a spot changed since mapping). Pass only if
   LOCALIZATION UNKNOWN, no seed, and a mission start is refused.
6. **People walking past during the check**: pass if VERIFIED is correct or
   the result is UNKNOWN, never a wrong place.
7. Repeat steps 3 and 4 five times each. Accept only with **zero wrong
   VERIFIED results**. Any wrong VERIFIED means rollback and an audit entry.
8. Rollback: `rm ~/.config/project_atlas/seed_mode` restores the old start;
   backed-up files restore everything else.

Passing this validates **startup** pose identification only. It does not
authorize navigation. Autonomy stays disabled until the odometry scale
(Oct 10 motion report), the LiDAR start fault and an independent route test
are resolved.

## Evidence files

- Live recording: Jetson `~/project_atlas/data/diagnostics/hall_coldstart_20261010/bag`
  (`/scan /scan_raw /odom /tf /tf_static /amcl_pose /particle_cloud /yahboom/odom /atlas/encoder_health /cmd_vel`).
- Map: `atlas_latest.yaml` (sha256 `d957f0fe…`), identical to every Oct 9 bag `/map`.
- Tools: `atlas_scan_map_global_search.py`, `atlas_localization_verify_core.py`,
  `atlas_amcl_motion_replay.cpp`.
