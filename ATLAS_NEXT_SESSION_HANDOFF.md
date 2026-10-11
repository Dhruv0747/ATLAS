# ATLAS next-session handoff (written 2026-10-11 20:45 IST)

Read this first, then `AGENTS.md`, then `docs/audits/ATLAS_CURRENT_BLOCKERS.md`.
It replaces `docs/HANDOFF_2026-10-11.md` (15:10) as the current starting point; that file stays as
history.

**Status words used here:**
- BUILT: committed.
- TESTED: automated tests pass.
- DEPLOYED: installed on the Jetson.
- VERIFIED: checked live on the Jetson while parked.
- PHYSICALLY VALIDATED: proven in supervised motion or hands-on tests.

**Nothing below is PHYSICALLY VALIDATED unless it says so.**

## 1. Where everything is

| What | Value |
|---|---|
| Repository / branch | `github.com/Dhruv0747/ATLAS`, branch `agent/sync-developer-20261011` |
| Verified HEAD | `5eb0aad`. The remote equals the local HEAD and the working tree is clean. 310 commits ahead of `main`. **Not merged; do not merge without Dhruv's approval** |
| Jetson | Orin Nano, ROS 2 Humble, Tailscale `100.87.208.71`. The live tree `~/project_atlas` is **not a git checkout**: changes go in only as stage packages |
| Rollback packages | `~/project_atlas/data/backups/<stamp>-<stage>/ROLLBACK.sh`: 23 packages from today, all kept |
| End-of-day backup on the Jetson | `~/project_atlas/data/backups/eod-20261011-203508/` |
| End-of-day backup on Dhruv's PC | `~/Downloads/atlas_eod_20261011/` (see §8) |

## 2. Live state at hand-off (20:36 IST, read-only checks)

- **Safety:**
  - E-STOP **latched** (`stop_latched: true`).
  - Commissioning **not armed**.
  - Autonomy **disabled**; no goal active.
  - The monitor's relocalization mode is `suggest`: it never reseeds automatically.
- **Boot:** up 43 min, since 19:52:44. That restart came from the dashboard power action on the
  owner's PC, as did the one at 19:03:47.
- **Services:** all ATLAS user services active, none failed. Key PIDs:

  | Process | PID |
  |---|---|
  | AMCL | 4298 |
  | mux | 1890 |
  | base | 1893 |
  | `atlas-localization` | 4132 |
  | monitor | 15139 |
  | voice | 11857 |

- **Load:** load average about 13 on 6 cores (normal for this stack); RAM about 4.9 / 7.6 GB.
- **LiDAR:** `atlas-lidar` active, `/scan` about 5–8 Hz. It started cleanly this boot (scanning
  21.8 s after boot).
- **BMS:** fresh `/bms/status`: 100%, 14.1 V, 0.0 A. Earlier today it had no healthy samples, so
  BLE reliability is **not** established (ATLAS-007).
- **Network:**
  - Wi-Fi is the default route (metric 50); cellular `usb0` on standby (metric 600).
  - Gateway RTT 1.56 ms average.
  - Tailscale up.
  - The Wi-Fi → mobile data → ATLAS Rescue Hotspot order is unchanged. The hotspot fallback was
    not re-tested today.

## 3. Localization status (AMCL and LiDAR)

**Startup verifier (this boot):** VERIFIED (0.235, −1.535, 81°), fit 0.989, margin 0.111. It
seeded AMCL itself; Claude applied no pose.

**AMCL now:** (0.177, −1.473). That is 0.01 m from the operator-confirmed Dhruv Room pose
(0.187, −1.477).

**CHECK MY LOCATION:**
- Last live run: VERIFIED. LiDAR (0.235, −1.435, 75°), fit 0.994; AMCL agrees within 0.07 m and
  3–6°.
- The 72/75/78° spread between checks is the matcher's 3° heading grid, not motion.

**Weak point:**
- The margin over the known alias at (3.9, −0.7, 171°) is only about 0.09; the alias scores about
  0.90.
- Treat the pose as **parked-verified**, not navigation-validated.
- **Moving localization has never been shown to hold** (ATLAS-011).

**Open: the 0.90 startup score on the 19:06 boot.**
- Its evidence was overwritten.
- Stage 16 now keeps every boot's evidence (§5).
- **Do not create a failure to test it.** Wait for a normal start.

## 4. Deployed today (all with rollback packages; nothing physically validated)

| Stage | What | Source | Record |
|---|---|---|---|
| 1, 1b, 2, 3, 4 | Web E-STOP latch / authenticated reset / Glass UI V2 / dashboard thread split / Visual Cloud local-only | see record | `docs/deploy/ATLAS_DEPLOYMENT_RECORD_2026-10-11.md` |
| 5 | V2 is the only dashboard (V1 kept, `ATLAS_CLASSIC_UI=1` restores) | `5b49f25` | `docs/deploy/ATLAS_V2_DEFAULT_2026-10-11.md` |
| 6b | Bounded motion recorder (opt-in CLI, **not running**) | `0c1d520` | `docs/ATLAS_MASTER_DEPLOYMENT_2026-10-11.md` |
| 8 | BMS: single retry owner, GATT reuse | `d5d1c59` | same |
| 9b, 9c | Operator views (surround LiDAR, full-size camera), view E-STOP | `bba0ad5`, `0ef0b9b` | same |
| 10 | LiDAR provenance | `1a9f077` | same |
| 11b, 12 | Navigation LiDAR-sector guard (mux, tight-space recovery), RPP inflation contract | `95add0c`, `6b0f462` | `docs/audits/ATLAS_NAVIGATION_GUARD_DEPLOYMENT_2026-10-11.md` |
| 11, 12 (location) | CHECK MY LOCATION lifecycle and snapshot | `92a3893` / `7f8ee2e` | `docs/audits/ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md` |
| 13 | CHECK MY LOCATION works without AMCL; precise codes | `2e10355` | `docs/deploy/ATLAS_LOCATION_CHECK_NO_AMCL_2026-10-11.md` |
| 14 | Voice announces latch **and** release | `27ccfcd` + `e2197f9` | `docs/deploy/ATLAS_LOCALIZATION_RECOVERY_2026-10-11_EVENING.md` |
| 15 | Location-check motion gate uses the EKF's IM10A gyro | `686fb03` | same |
| 16 | Startup evidence capture | `b81d7ac` | §5 below; `project_atlas/tools/deploy/readmes/stage16-startup-evidence.txt` |

**Rollback order if needed:** newest first. Each `ROLLBACK.sh` restores only its own files. Then
restart only that stage's service, with the rover latched.

## 5. Stage 16 result (startup evidence capture)

- **State:** BUILT `b81d7ac` → TESTED → DEPLOYED 20:23:50 IST → VERIFIED (file and hash). Not yet
  exercised by a real boot.
- **Tests:**
  - 26/26 seeder tests, including a replay of the stored evidence through the identical search;
  - 24/26 on the Jetson. The 2 errors are environmental: the
    `atlas_localization_verify_people_experiment` module is not installed there;
  - package rehearsal, rollback identity and tamper tests pass;
  - live dry run VERIFIED, fit 0.984, margin 0.093; it did not touch the verdict file or AMCL.
- **Live hash:** `db634ff08b6c…`, matching the package result and the GitHub HEAD.
- **Unchanged:** thresholds (0.93 / 0.06), seeding decisions, navigation authority and motor
  behaviour.
- **Nothing restarted.** AMCL PID 4298 kept.
- **Cost:** none while running; it executes only at `atlas-localization` start. Each boot adds a
  few KB to `~/.local/state/project_atlas/localization_verdict_history.jsonl` (4 MB cap plus one
  `.1` rotation). The file does not exist yet, as expected.
- **Rollback:**
  `~/project_atlas/data/backups/2026-10-11-202350-349365561-stage16-startup-evidence/ROLLBACK.sh`.
  No restart is needed.
- **First thing next session:** if ATLAS has been started since, read that history file. It holds
  per-attempt fits, margins, coverage, median ranges and the top five hypotheses.

## 6. Deployed files versus GitHub (checked 20:33)

**Today's evening stages (13–16):** all 6 live files are byte-identical to HEAD `5eb0aad`.

| File | Hash |
|---|---|
| `atlas_location_check_job.py` | `d3097fa0` |
| `atlas_location_check_ros.py` | `eec17779` |
| `atlas_voice_companion.py` | `37f275dd` |
| `atlas_voice_status.py` | `bc37eb3d` |
| `seed_atlas_localization.py` | `db634ff0` |
| `web/v2/location-check.js` | `4d4d32dc` |

**Whole-tree comparison:** 410 repo-tracked files under `scripts/`, `config/` and `web/`:
- **251 identical.**
- **137 absent on the Jetson:** offline diagnostics and tools that were never deployed; expected.
- **22 differ:**
  - **2 from today's afternoon stages** (`scripts/atlas_cmd_vel_mux.py`, `config/nav2_params.yaml`)
    match **exactly** the result hashes recorded in their stage 11b/12 MANIFESTs. Those stages were
    patch-mode installs onto older live files, so the difference is by design.
  - **20 were last modified on the Jetson between 21 Jul and 10 Oct.** This drift predates today's
    session and was not touched:

    | Area | Files |
    |---|---|
    | Config | `atlas_agent.yaml`, `atlas_house_semantic.json` |
    | Main scripts | `MIGRATION_NOTES.txt`, `amg8833_thermal_node.py`, `atlas_agent_core.py`, `atlas_agent_supervisor.py`, `atlas_fusion_bag_analyzer.py`, `atlas_mission_control.py`, `install_atlas_uno_r4_udev_root.sh`, `nav2_cmd_adapter.py`, `radar_avoidance.py`, `rd03d_node.py`, `rover_dashboard.py`, `tof_center_node.py` |
    | Test scripts | `test_closed_loop_control.py`, `test_commissioning_channel_source.py`, `test_im10a_bias.py`, `test_rear_ultrasonic_guard.py`, `test_straight_distance_core.py`, `test_voice_status.py` |

  - **Before deploying any of these 20**, diff the live file against the repo; never overwrite
    blind. `test_voice_status.py` is the known older live copy, with a pre-existing
    `test_low_battery_hysteresis` failure.
- Full lists: `~/Downloads/atlas_eod_20261011/drift.txt` and `differ.txt`.

## 7. Remaining problems, in the agreed priority order

**1. Moving localization (ATLAS-011): first.**
- VERIFIED → LOST after short manual drives, twice. No recording of a failure exists.
- Recorder stage 6b is installed but has never captured a supervised moving run.
- **Rejected, do not retry without new evidence:** lower AMCL alphas, the parked-update gate alone,
  a 0.10 m nudge, velocity-only EKF.

**2. Odometry and IMU accuracy (ATLAS-001, -010, -013).** Today's offline result is in
`docs/audits/ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11.md`:
- At 0.10–0.45 m/s, robust to binning: M1/M4 read **0.64–0.72×** of the LiDAR-ICP distance and M2
  **0.51–0.64×**. M3 contributes about 0.
- The consensus estimator removes only 1–3%.
- **Not separated:** constant CPR/scale error versus constant slip. M2 is different from M1/M4.
- **Retracted:** "speed-dependent count loss". That came from single binning, which was biased.
- **No CPR change** without the tape test (no arbitrary scale factors).

**IMUs:**
- The EKF fuses the IM10A (`/im10a/imu/bias_corrected_candidate`). It reads **exactly 0 when
  parked** because it zeroes on-sensor, so static qualification cannot measure its bias.
- One fast turn read 0.46× on the IM10A.
- The Yahboom board IMU `/imu/data` is uncalibrated, and its bias changes per boot: −1.71°/s this
  boot. Anything displaying its heading drifts about 100°/min.

**3. Map repair: Dhruv Room → corridor → Hall.**
- Accepted map unchanged:

  | File | sha256 |
  |---|---|
  | `atlas_latest.yaml` | `d957f0fe…` |
  | `atlas_latest.pgm` | `4beb26d5…` |

  The map server serves `6da76a70…`, matching the accepted map.
- Corridor candidate v1 is rejected; v3 brings no benefit. The alias at (3.9–4.1, −0.7) remains.
- Plan: `docs/audits/ATLAS_LOCAL_MAP_REPAIR_DHRUV_HALL_2026-10-10.md`. It needs fresh scans; the
  candidate gets validated with existing tools. No automatic overwrite, no continuous SLAM
  promotion.

**4. Supervised navigation validation (blocked by 1–3).**
- The Nav2 observation-coverage guard vetoes all directions with real scans (see the navigation
  guard record).
- The mission scan-fit gate (0.85) sits below the alias peak (0.872): needs Dhruv's decision.

**Other open items:**
- RPLIDAR start failures (ATLAS-015). The 19:06 boot had 15 failures (216 s to first scan). Supply
  measurement pending; StartLimitBurst step 3 **on hold**.
- BMS BLE reliability (ATLAS-007).
- NVMe AER / unclean power-off (ATLAS-018).
- Wi-Fi DHCP after roaming (ATLAS-019); proposals need approval.
- **Security:** rotate the Jetson password (it is in git history and 2 scripts). Remove the
  temporary access key used this session. Same-origin check on control POSTs.
- **Physical E-STOP tests A–E are NOT passed.** Do not mark them passed from logs.

## 8. Backups made tonight (verified)

**On the Jetson:** `~/project_atlas/data/backups/eod-20261011-203508/`, mode 700.

| File | Size | Contents |
|---|---|---|
| `atlas_runtime_20261011-203508.tar.gz` | 21.9 MB | `project_atlas/{scripts,config,web,maps,systemd,services,udev,CHANGELOG.md}`, `~/.local/state/project_atlas` (verdicts, location-check and monitor history), `~/.config/project_atlas` (named places, seeds, home pose, mode files) and `~/.config/systemd/user`. **Excludes** the 3 secret files |
| `atlas_rollback_stage13-16_20261011-203508.tar.gz` | 85.8 MB | the stage 13–16 rollback packages |
| `atlas_secrets_JETSON_ONLY_20261011-203508.tar.gz` | — | mode 600, **Jetson only**, never copied off: `estop_reset_pin.json`, `visual_cloud.token`, `visual_cloud.env` |
| `runtime_files.sha256` | — | 622 per-file hashes |
| `bags_inventory.sha256` | — | 12 bags, 380 MB, inventoried only (they stay on the Jetson; the Oct 9 bags also exist on the PC under `~/Downloads/atlas_bags/`) |
| `rollback_packages.txt` | — | the list of all rollback packages |
| `accepted_map.sha256` | — | accepted map hashes |
| `SHA256SUMS` | — | checksums of the above |

**On Dhruv's PC:** `~/Downloads/atlas_eod_20261011/`
- `jetson_backup_20261011-203508/`: the same files, minus the secrets archive;
- `head_hashes_5eb0aad.txt`, `drift.txt`, `differ.txt`;
- `analysis/encoder_scale_by_speed_20261011.json`.

**Verification:**
- **Transfer:** every PC copy matched `SHA256SUMS`.
- **Test restore** (extracted into a scratch directory):
  - **620/622 files byte-identical.** The 2 mismatches, `localization_check.json` and
    `manual_location_check.json`, are live status files the monitor rewrites every few seconds
    between archiving and hashing; expected.
  - Accepted map hashes OK.
  - All 4 rollback `ROLLBACK.sh` scripts parse, with their original files present.
- **Secret leak check:** none of the three secret files are in the runtime archive. Matches on
  "visual_cloud" are source and config file names only, with no keys inside.

**Not backed up off-device:**
- today's other 19 rollback packages and all older ones (today's 23 total 681 MB; they stay on the
  Jetson NVMe);
- the 380 MB of bags;
- the secrets.

There is no external drive on the Jetson: the on-Jetson copy shares the NVMe with the original.
**The PC copy is the only independent copy.**

**To restore** (only with approval, rover latched):
1. Verify `sha256sum -c SHA256SUMS`.
2. `tar -xzf atlas_runtime_*.tar.gz -C /home/jetson` restores into the same paths. Restore
   selectively, not the whole archive over a running system.
3. Restart only the affected services.

## 9. What not to repeat

- Stages 13–16 are deployed and verified; do not rebuild or redeploy them.
- Stage 14 and 15 redeploys are explicitly not wanted.
- The encoder-by-speed bag analysis is done (tool `project_atlas/tools/diagnostics/encoder_scale_by_speed.py`).
  Re-run it only on new bags.
- AMCL needs no reseed on the current boot; it is VERIFIED.
- Do not restart services or reboot to "create" startup evidence.

## 10. Exact next task (next session, about 2026-10-13)

**Step 0: check that nothing changed (read-only, about 10 min).**
- Check for a reboot (`uptime`; `localization_verdict_history.jsonl` exists?). If it exists, read
  and record the stage 16 evidence first.
- Confirm still latched, AMCL PID 4298 or the reason it changed, BMS, Wi-Fi.

**Step 1: moving localization, offline (no motion needed).** Use the existing Oct 9 bags (on the
PC under `~/Downloads/atlas_bags/` and `atlas_amcl_roundtrip_20261009_final`) and the existing
replay tools:
- **Heading:** compare the IM10A gyro yaw, wheel yaw, EKF yaw and LiDAR-ICP yaw per turn, using the
  same two-way binning to avoid bias.
- **TF timing:** check scan stamps against the `odom→base_link` TF, to measure the lag AMCL sees
  during motion.
- **AMCL particles:** trace AMCL particle spread and weight through each VERIFIED → LOST transition
  (`atlas_amcl_weak_hypothesis_trace.py`, `atlas_amcl_turn_divergence.py`).
- **Output:** a ranked cause list with measured evidence, appended to `ATLAS_CURRENT_BLOCKERS.md`
  and the ATLAS-011 registry entry.

**Step 2: one short supervised session, only after Dhruv approves the plan.** Group every physical
action into it:
- **E-STOP blocks A–E**, plus hearing the voice release announcement.
- **Tape-measured runs** with the 6b recorder: straight 2 m runs at about 0.15 m/s and about
  0.40 m/s with raw counts, plus ±90° turns. These separate CPR error from slip, isolate M2, and
  measure the gyro scale.
- **Corridor midpoint and Hall scans** for the map-repair candidate.

**Step 3, only after the session:**
- a measured (not arbitrary) calibration proposal;
- the corridor map candidate validated against the accepted map;
- then supervised navigation validation.

Every step above needs Dhruv's explicit approval for motion, reseeding, calibration, map
replacement, networking, reboots or deployments.
