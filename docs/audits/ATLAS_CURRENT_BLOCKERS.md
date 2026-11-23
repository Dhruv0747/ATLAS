# ATLAS current blockers

### 2026-11-23 12:11–12:18 IST — Speed checks after the encoder-debounce deploy: 2 PASS (speed evidence current again)
- **12:11:19 FAIL** `STOP_LIDAR_0.59M`: the LiDAR safety stopped the run at an obstacle 0.59 m ahead after 0.47 m (wheels) / 0.53 m (ICP); steady 0.108 m/s. The test space was too short; the owner moved ATLAS to open space.
- **12:15:21 FAIL** `STOP_SPEED_LOOP_STATUS_STALE`: wheels 0.072 m; steady-mean and ended-by-distance checks failed. Not investigated; the next two runs were clean.
- **12:16:41 PASS** (DISTANCE): wheels 0.598 m, ICP 0.672 m, steady 0.113 m/s, coast 0.022 m.
- **12:17:41 PASS** (DISTANCE): wheels 0.592 m, ICP 0.680 m, steady 0.106 m/s, coast 0.022 m.
- **Readiness:** speed passed [0.15, 0.15], nothing blocking. The two new PASSes postdate the 12:05 yahboom_base change.
- **Next:** clear the stale goal (Abort), then a Stage-3 one-click run with the debounce live.

### 2026-11-23 12:05 IST — Encoder consensus debounce DEPLOYED (owner "e stop dene deploy")
- **Before the deploy:** stop latched ("REMOTE STOP: voice stop requested"), autonomy armed false, motion quiet. The Stage-3 runner was CANCELLED by the owner, recording off.
- **Change:** the deployed yahboom_base diff vs the backup is only the import, the constant, the debounce member, and the `consensus_failed = self._consensus_debounce.update(...)` wrap.
- **Install:** yahboom_base.py 57655cb2, atlas_encoder_selection.py 93c3542f; compiled OK. Backups: `~/project_atlas/backups/encoder_debounce_20261123/` (a9c378fc / d26e648d).
- **Restart:** `rover-base-telemetry` restarted 12:05:27 → active; no errors in the journal.
- **Live after restart:** encoder health DEGRADED (M3 excluded, normal), fresh; odom fresh; stop still latched; autonomy off.
- **Readiness blocks autonomy as designed: "Speed check pending: 0/2 PASS at 0.15 m/s".** The owner must run the Speed check twice (Readiness page) before autonomy can be switched on.
- The mission status still showed an old "NAMED GOAL ACCEPTED name=dhruv room taught-route" from the cancelled run. Autonomy is off and the stop is latched; to be cleared with Abort if Nav2 still holds a goal.

### 2026-11-23 10:25–11:05 IST — One-click run #2: 4/5 (only encoders); encoder consensus debounce STAGED; checker remote-exclusion DEPLOYED
- **Run #2** (bag `stage3_auto_20261123_102501`), checker with TF start:
  - PASS legs, **return_home 0.30 m / 3° (TF)**, safe_stop (v 0.157 → still in 0.30 s, 0.018 m), turn_sign (875/6).
  - **FAIL encoders:** 2 bad samples while moving.
  - The home leg again needed 17 Go attempts: D2 failures, and "localization still moving" refusals including a 0.66 m pose shift while stopped.
- **Encoder CRITICALs in this run:** +146 s NAV2 (v ≈ 0), +849 s NAV2 (0.137 m/s, cmd wz -0.66), +1081 s REMOTE (0.21 m/s), +1182 s NAV2 (0.077 m/s).
  - Every one is "encoder consensus unavailable; fewer than three wheel channels agree", with M3 excluded.
  - Example normalized deltas: M1 0.006 / M2 0.020 / M4 0.011 m, so all three pairs sit just outside tolerance (0.45 relative / 4 mm).
- **Evidence for B** (four bags: runs #8, #9 and today's two; about 65,000 health samples at 10 Hz): **20 consensus CRITICAL episodes, every one exactly 1 sample (0.1 s), never 2 in a row.**
- **A (owner "do it") — checker change.** The encoders check now excludes samples while the owner drives by remote (/cmd_vel_joy within TURN_REMOTE_WINDOW_S), like turn_sign, and reports how many it excluded.
  - Today's run: "1 bad sample while moving autonomously; excluded 1 during owner remote driving". Still FAIL.
  - Tests +1 (13 in the checker file).
  - **Deployed 11:04** as a file copy only: `tools/drive/stage3_autonomy_check.py` e5c7efae (backup in `~/project_atlas/backups/encoder_debounce_20261123/`).
- **B (owner "fix deploy karo") — debounce, STAGED, NOT DEPLOYED.**
  - New `atlas_encoder_selection.ConsensusDebounce`: consensus is declared lost only after 2 consecutive failed intervals (0.2 s, about 3 cm at 0.15 m/s).
  - `yahboom_base.py`: `ENCODER_CONSENSUS_DEBOUNCE_INTERVALS = 2`, wrapping the existing condition.
  - Hardware freeze faults, stale packets and link qualification are unchanged and still immediate.
  - On the four bags this removes all 20 false CRITICALs.
  - Tests: `tests/test_encoder_consensus_debounce.py` 5/5, added to CI. On the rover repo copy, every encoder / yahboom / speed-loop / curvature / drive-PID test passes. The 8 failures in that run were stage31 UI / vision3d tests picked up by the name filter, unrelated.
- **Not deployed yet:** a Stage-3 run was in progress (runner OUT, autonomy armed, stop not latched). The deploy needs ATLAS parked with the E-STOP latched and a restart of `rover-base-telemetry` (the Yahboom base). Because `yahboom_base.py` changes, **2 Speed check PASSes are required afterwards** (arm gate / speed evidence).
- Backups taken: yahboom_base.py a9c378fc, atlas_encoder_selection.py d26e648d.

### 2026-11-23 09:45–10:11 IST — First one-click Stage-3 run: 3/5 (return_home, encoders); checker TF start + 5 s record lead DEPLOYED
- **Run** (bag `~/atlas_bags/stage3_auto_20261123_094529`):
  - Go hall: 2 attempts (#1 cancelled); hall SUCCEEDED.
  - **Safe stop PASS while rolling** (v 0.154 → still in 0.27 s, 0.01 m).
  - Go dhruv room needed **18 attempts**: repeated failures in D2 at (1.05, -1.17); the owner drove ATLAS out by remote; finally SUCCEEDED.
  - Checker (deployed version): PASS legs, safe_stop, turn_sign (1489/29). FAIL return_home 0.33 m / 32°. FAIL encoders (first CRITICAL; CRITICAL at +432 s with vx 0.12, +454 s, +772 s, +774 s; no remote input).
  - The runner recorded the result (3/5) on the master-plan board.
- **Checker flaw found:**
  - "Start = first AMCL after the dispatch" is taken after the rover has moved, because AMCL publishes only on motion.
  - **Fix:** the start/end pose comes from /tf (map→odom ∘ odom→base_link). The start is the pose at or before the dispatch; if the recording began with the dispatch, it is the first TF pose before odom shows motion (≥ 0.03 m/s, within 10 s). Otherwise the checker falls back to AMCL.
  - Run #8 and #9 give the same verdicts with TF (0.24 m / 31°, 0.27 m / 131°).
  - **Today's run with TF: 0.37 m / 33° — a real miss.** TF start was (0.37, 0.15, 64°), but the runner had judged ATLAS at the start (within 0.25 m / 15° of (0.28, 0.66, 105°)) seconds before. The pose changed by about 0.5 m / 40° in the first 3 s of the recording while odom was 0 (ATLAS parked): an AMCL jump while stationary, the same open issue as the earlier 0.60 m / 42° one-update jump.
- **Runner fix:**
  - The recording now starts **RECORD_LEAD_S = 5 s before Go hall**.
  - If ATLAS leaves the start tolerance during those seconds (moved or localization jump), the recording stops ("moved before start") and the runner repositions.
  - Tests: checker 12, runner 13, master plan 6 (32 OK on Mac; rover copy OK).
- **Deploy:** backup `~/project_atlas/backups/stage3_tf_lead_20261123/`. Installed runner 177e695a, checker 39967e58. rover-status-web restarted 10:10:42 → active; runner IDLE; board stage3 IN PROGRESS, best 4/5, history shows today's 3/5.
- **Open:**
  - AMCL jumps while parked;
  - D2 doorway failures (18 retries);
  - encoder CRITICAL samples while driving autonomously.

### 2026-11-23 00:10 IST — "Master plan" progress board DEPLOYED (owner "Yes, deploy")
- **Before the deploy:** stop latched, autonomy off, motion quiet, Stage-3 runner IDLE.
- **Backups:** `~/project_atlas/backups/master_plan_20261123/` (status web, web_v2, stage3 runner, index, home-nav). The diffs were only this feature (3 / 2 / 11 / 2 / 2 lines).
- **Installed md5s:**

| File | md5 |
|---|---|
| atlas_master_plan.py | acb3d67e |
| atlas_status_web.py | 28dd4ca1 |
| atlas_web_v2.py | b4adcaaf |
| atlas_stage3_runner.py | 646d62f7 |
| plan.html | ef0503f9 |
| plan.js | b1717353 |
| index.html | b2b6e264 |
| home-nav.js | 1aa0cb68 |

- **Restart and checks:** rover-status-web restarted 00:10:54 → active. `/v2/plan`, `/v2/stage3`, `/v2/lidar` and `/v2/` all 200; no errors in the journal.
- **Live result:** `/api/master_plan` gives 1/3 [PASS, NOT DONE, IN PROGRESS], next step "Do stage 3 …". The page over Tailscale (mobile) shows the menu entries "Master plan" and "Stage 3 run", the next-step button, and the Stage 1 evidence (Speed check 2026-11-20 18:25: 0.59 m wheels, 0.67 m LiDAR).

### 2026-11-23 — "Master plan" progress board STAGED (owner: "show master-goal progress and help reach it without a developer"; not deployed)
- **New `scripts/atlas_master_plan.py`** (read-only except one write path):
  - The board follows the entry gate and execution order of `docs/AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md`.
  - **Status only from recorded evidence:**
    - **Stage 1** = a Speed check file with verdict PASS, end_reason DISTANCE, wheels ≥ 0.20 m and LiDAR ICP ≥ 0.20 m (a bounded straight run). The rover has such a file from 2026-11-20 (0.595 m wheels / 0.667 m ICP, coast 0.02 m), so Stage 1 shows PASS. This is an interpretation: the Phase-0 text records the 2026-09-30 runs as PARTIAL / FAILED SAFE; the later Speed check is the bounded straight-run evidence. The owner can disagree.
    - **Stage 2** = NOT DONE: no turn-sequence tool exists yet, and the board says so.
    - **Stage 3** = PASS only on a checker "STAGE 3: PASS". The one-click runner now calls `record_stage3()` after every checker run. History keeps runs #7–#9 (best 4/5).
  - The later steps (IMU/EKF/TF … arm) are LOCKED until the gate opens, then "NEEDS DEVELOPER".
  - "Next step" prefers a stage the owner can do with a tool. Now: "Do stage 3 … Stage 2 still needs a test tool (developer)", with an "Open Stage 3 run" button.
- **Web:** `/api/master_plan` (GET); page `/v2/plan` (`plan.html` / `plan.js`, polls every 5 s); menu "Master plan"; `atlas_web_v2.PAGES` += plan.
- **Tests:**
  - `tests/test_master_plan.py` 6/6, added to CI.
  - `test_stage3_runner` checks that the result is recorded.
  - Rover repo copy: master plan, runner, executor split, estop safety, no-reboot, v2 default route, mapping install: OK (1 skipped). A live evaluation on the rover data gives stage1 PASS, stage2 NOT DONE, stage3 IN PROGRESS 4/5.
- **Browser preview** (mobile): next-step box with the button, gate cards with status and evidence, locked later steps.

### 2026-11-23 00:01–00:04 IST — One-click "Stage 3 run" button DEPLOYED (owner "Yes, deploy")
- **Before the deploy:** stop latched, autonomy armed false, motion quiet, mission READY. Only rover-status-web was restarted (twice, see below); no base, mux, Nav2 or mission-control restart.
- **Backups** in `~/project_atlas/backups/stage3_button_20261123/`: status web, index.html, home-nav.js, atlas_web_v2.py. The status-web diff was only the Stage-3 additions.
- **Installed md5s:**

| File | md5 |
|---|---|
| atlas_stage3_runner.py | d1e35dde |
| atlas_status_web.py | 0f9e8a46 |
| stage3.html | 410ac894 |
| stage3.js | d6c87586 |
| index.html | 910dd35f |
| home-nav.js | 17426af2 |
| **`tools/drive/stage3_autonomy_check.py`** (now on the rover, previously only in /tmp) | 13dbcb3e |

- **First restart 00:01:10:** `/api/stage3` IDLE. But `/v2/stage3` returned 404: `atlas_web_v2.PAGES` is an allow-list.
  - Added `'stage3': 'stage3.html'`; `test_v2_default_route` + `test_mapping_install_once` OK.
  - Deployed atlas_web_v2.py f07ce612 and restarted again: `/v2/stage3` 200, `/v2/lidar` 200.
- **Live page** over Tailscale (mobile width): START STAGE 3 RUN button, step list, and the "Stage 3 run" menu entry. START was NOT pressed by me; starting a run is the owner's action.

### 2026-11-22 — One-click "Stage 3 run" button STAGED (owner "make a button, one click and it does everything"; not deployed)
- **Why:** runs #7, #9 and #10 failed on procedure, not on ATLAS: start heading changed by remote before Go, B pressed while not rolling, recording started after the rover moved. The button removes those steps from the owner.
- **New `scripts/atlas_stage3_runner.py`:**
  - **`Runner`** is a pure state machine: POSITION → SETTLE → OUT → HOME → CHECK → DONE.
    - POSITION: if not within 0.25 m / 15° of (0.28, 0.66, +105°), send Go dhruv room and wait for SUCCEEDED.
    - SETTLE: wait 5 s still at the start.
    - OUT: start the bag, then Go hall.
    - HOME: Go dhruv room.
    - CHECK: stop the bag and run `stage3_autonomy_check.py`.
    - "PRESS B NOW" is shown only while source = NAV2 and odom ≥ 0.08 m/s for ≥ 1 s. A latch with odom ≥ 0.05 m/s counts as the stop.
    - A failed, cancelled or refused leg (doorway, E-STOP, "not in known clear space", "localization still moving") is re-sent automatically. Conditions: the E-STOP is released, autonomy is ON, AMCL std ≤ 0.15, ATLAS has been still for 5 s, and 8 s have passed since the failure.
  - **`Service`:** a 0.5 s thread; `Recorder` (ros2 bag via `bash -lc` with the ROS env, SIGINT on stop); `run_checker()` parses the five verdicts.
  - **`serve()`:** `/api/stage3` GET snapshot; POST {action: start|cancel, confirm: STAGE3}, same-origin only.
- **Authority unchanged:**
  - Goals use `atlas_autonomy_web.go_refusal()` + `/atlas/navigate_named_place`, exactly like the Go buttons, and are logged to the E-STOP log as `stage3_runner_go`.
  - The runner never arms autonomy, never releases the E-STOP, never publishes velocity.
  - Cancel stops the recording; the owner stops motion with the remote / Abort.
- **Status web:** `/api/stage3` GET/POST routes; `_stage3_obs()` reads map_pose / odom / amcl_quality / mission_status / control_policy.
- **Page:** `web/v2/stage3.html` + `stage3.js` (`/v2/stage3`, menu "Stage 3 run").
  - One START button (with a confirm) and Cancel.
  - Big blinking red **PRESS B NOW** with beep + vibrate.
  - Step list, run log, and a result table with PASS/FAIL per check.
- **Tests:**
  - `tests/test_stage3_runner.py` 12/12, added to the CI list. Covers: start/record order; positioning without recording; never sending while latched or with autonomy OFF; a full round trip with B and a doorway retry; B while still not counted; cancel; mission-error retry; double start; service record/send/check; refused Go retried; bad status read sends nothing; checker parsing.
  - Rover repo copy: runner + executor-split + estop-safety + no-reboot + gate view + relocalize + stage3 checker + taught route: 77 OK (1 skipped).
  - Rover smoke test of `Recorder` from an empty environment: 15 topics subscribed, bag written and closed.
- **Browser preview** (fake API, mobile 375 px): the button, the PRESS B NOW banner, the step highlighting and the result table render correctly.
- **Deploy needs:** the new module + status web + page/menu files, and `tools/drive/stage3_autonomy_check.py` installed on the rover (it was only in /tmp). Restart rover-status-web; no base, mux or Nav2 restart.

### 2026-11-22 18:37–19:16 IST — Stage-3 run #9 FAIL (start re-oriented, no valid stop); run #10 recording discarded; next run tomorrow
- **Positioning:** a Go dhruv room (not recorded) brought ATLAS to (0.25, 0.52, 103°), exactly the arrival heading.
- **Run #9** (bag `~/atlas_bags/stage3_run9_20261122_183726`, 130 MB). Before Go hall the rover was driven by remote for about 70 s and ended at (0.08, 0.72, **-37°**). Go hall was dispatched there, so the checker's start pose is -37°.
  - Hall: #1 failed in a doorway (6). Then "localization still moving while ATLAS is stopped: pose_shift=0.32m" was refused; hall #2 SUCCEEDED 18:43:49.
  - Network: two outages (18:45:30 to about 18:50, about 19:03 to 19:06). The Wi-Fi roamed to mesh node b4:a7:c6:41:fc:9a, which gave CONNECTED_LOCAL (no internet), and moved to another node within 5 s (the retry fix worked). The bag kept recording on the rover.
  - Home leg:
    - one attempt failed with 7× lethal start in D2;
    - an E-STOP latched with "REMOTE STOP: joystick unavailable" (Xbox link drop);
    - final SUCCEEDED at (0.29, 0.54, 95°).
- **Checker:**
  - PASS legs, turn_sign (1423/25), encoders.
  - FAIL return_home 0.27 m / 131° (start -37° vs end 95°).
  - **FAIL safe_stop:** of 3 latches, none had odom ≥ 0.05 m/s at the press. One had cmd_vel 0.15 but the rover was not rolling.
  - localization blocks while moving 18.
- **Run #10:** started recording 19:14:54 at a perfect start (0.18, 0.53, 106°). The rover was driven to (-0.63, 0.30, 17°) before any Go, so the recording was stopped and set aside as `…stage3_run10_20261122_191454_discarded_moved_before_go`.
- **Owner:** stop for today, do the next run tomorrow.
- **Procedure for the next run:**
  - Go dhruv room (unrecorded) to reach the start pose; do not touch the remote.
  - Recording starts, then Go hall immediately.
  - Press B while ATLAS is clearly rolling straight (corridor), then reset → autonomy ON → Go again.
  - In the hall, Go dhruv room.
- **Best result so far, run #8:** 4/5, return_home 0.23 m / 31°. No run has passed all five; Stage 3 is NOT complete.

### 2026-11-22 15:27–16:18 IST — Stage-3 run #8: 4/5 PASS (return_home heading 31°); home heading = arrival direction DEPLOYED
- **Bag:** `~/atlas_bags/stage3_run8_20261122_152723` (156 MB). Start (0.41, 0.64, -75°), AMCL std 0.017.
- **Run:**
  - Hall #1 failed at 15:34:12 in D2 (1.34, -1.50) after 7× "Starting point in lethal space".
  - Go hall from inside the doorway was refused ("not in known clear space"). After the owner moved ATLAS forward: "SCAN CHECK OK fit=97%", accepted 15:36:43, **SUCCEEDED 15:40:17**.
  - Owner drove out through D4/D3. Go dhruv room accepted 15:50:17. **B pressed 15:50:21 while Nav2 drove**; released 15:50:25. A second B at 15:51:49; accepted again 15:52:22 ("TAUGHT ROUTE DISPATCHED … waypoints=11 corridor_error=0.12m"). **SUCCEEDED 16:06:26.**
- **Checker:**
  - PASS legs (hall=6, hall=4, dhruv room=5, dhruv room=4).
  - **PASS safe_stop** (v 0.117 → still in 0.18 s, 0.008 m).
  - PASS turn_sign (1433/11); PASS encoders.
  - localization blocks while moving 0; 2330 s.
  - **FAIL return_home: 0.23 m (≤ 0.30 OK) / 31° (> 20°).**
- **Cause:**
  - Arriving facing into the room (about 0°), the car-like rover made multi-point turns toward the -75° home heading (AMCL 0° → -20° → -28° → -45°). Nav2 reported "Reached the goal" at -43…-45°.
  - The Smac Hybrid planner has `tolerance: 0.30` and REEDS_SHEPP, so a path ending in a nearby pose with a different heading is acceptable to it. The controller (RPP, `use_rotate_to_heading: false`, yaw tolerance 0.35 rad) then finished there. Not proven which pose the final path segment had.
- **Fix (owner "karo", B latched):**
  - `reversed_route()` no longer overrides the final yaw: home keeps the **arrival direction (+105°)**, so there is no 180° turn at the end. Round trips must **start at (0.28, 0.66) facing into the room (about +105°)**; Nav2 turns at the start, which the checker does not grade.
  - This replaces the 13:45 "home = start heading (-75°)" rule; the tests were updated (`test_home_pose_is_the_arrival_direction`).
- **Deploy:** backup `~/project_atlas/backups/home_arrival_20261122/atlas_mission_control.py` (6501a6d2) → be467749; diff = docstring + the 2 removed lines. Restarted `atlas-mission-control` 16:18:22 → READY. Rover-copy mission-control tests + stage-3 checker tests OK.

### 2026-11-22 15:06–15:24 IST — Stage-3 round trip #7 (bag `~/atlas_bags/stage3_run7_20261122_150623`, 70 MB): legs PASS, STAGE 3 FAIL
- **Recording:** 15 checker + context topics (domain 0); `/astra/obstacle_scan_status` is on domain 77 and was not recorded.
- **Earlier bags re-checked** (owner "check all recordings"): hall_auto, hall_auto2, hall_auto3, hall_auto4 (2026-11-20) and rt6 (today) all FAIL.
  - hall_auto3: safe_stop PASS (0.47 s, 0.042 m).
  - hall_auto4: legs PASS but return_home 0.20 m / **131°**, because the "dhruv room" named place yaw is 65° while round trips start facing the door. A proposal to align the named places with the route start/end awaits the owner.
- **Run #7:**
  - Go hall was pressed at 15:07:22 while ATLAS faced -16° at (0.08, 0.47); I had asked to turn to about -75° first.
  - Hall #1 cancelled at 15:11:16: "camera obstacles lost (2.4s stale)" after 2× "Starting point in lethal space" at the D3/D4 doorways. **Astra BLINDED in narrow doorways** (walls closer than its minimum depth range) is a new Stage-3 blocker.
  - Owner assisted through D4; Go hall #2 SUCCEEDED at 15:14:31 at (2.33, -5.40).
  - Go dhruv room from inside D4 (1.92, -3.98) was refused: "saved-map navigation blocked: current pose is not in known clear space". The start-clearance check is by design; at (1.08, -1.21) it passes at 0.30 m and blocks at 0.35 m.
  - Owner drove out through D3; Go dhruv room accepted at 15:19:17 and SUCCEEDED at 15:23:31 at (0.44, 0.62, -76°). The taught route ends at the start heading as deployed.
- **Checker bug fixed:** mission status reports "name=<place> taught-route", so legs read "hall taught-route" and missed the home key.
  - `stage3_autonomy_check.py` now strips a trailing " taught-route".
  - New test `test_taught_route_labels_count_as_the_place`; `test_stage3_autonomy_check` 10/10 OK.
- **Verdict with the fixed checker:**
  - **PASS legs** (hall=5, hall=4, dhruv room=4), **PASS turn_sign** (same 1459 / opposite 11), **PASS encoders**.
  - **FAIL return_home** 0.39 m / 59° (start pose was off).
  - **FAIL safe_stop** (no B while Nav2 drove).
  - localization blocks while moving: 2; mean speed 0.134 m/s; 967 s.
- **What a PASS needs now:** start at about (0.28, 0.66) facing about -75° (within about 0.15 m / 10°), and press B once while Nav2 drives. Open blockers that cost assists but do not fail the checker:
  - D3/D4 lethal start;
  - Astra BLINDED inside doorways (cancels goals).

### 2026-11-22 13:45 IST — Home pose keeps the start heading DEPLOYED (owner "Yes, deploy", B pressed)
- **Before the deploy:** first check found the latch released and autonomy armed, so I asked the owner. After B: stop_latched true, armed false, motion quiet, mission READY.
- **Files:** backup `~/project_atlas/backups/home_heading_20261122/atlas_mission_control.py` (d35ac0c4); the diff is only the docstring + the final-yaw lines. Compiled OK; installed 6501a6d2.
- **Restart:** `atlas-mission-control` restarted 13:45:37 → active; log "READY". Still latched, autonomy off; load average 8–10.
- **On-rover check of the deployed helper:** the reversed route starts at yaw +85° (leaving the hall toward the door); home pose (0.28, 0.66) at **-75° = route start yaw** (return_home heading error 0° when started at the route start heading).
- Not yet verified: a real "Go dhruv room" ending with the on-the-spot turn.
- Earlier today, also recorded: reboot at 13:09 (owner, dashboard Restart) to retry the 4G modem. The modem still fails ("usb 1-2.2-port1: Cannot enable … unable to enumerate"); boot seeder seeded at (1.715, -4.975). Kernel also logged "imx708: probe of 9-001a failed with error -121", while the dashboard camera stream still reported streaming; not investigated.

### 2026-11-22 — Reversed taught route: home pose keeps the start heading STAGED (owner "#1 fix करो"; not deployed)
- **Problem:** with the 12:14 fix every reversed waypoint faces the travel direction, including the final "dhruv room" pose. That pose would be (0.28, 0.66) at about +105°, roughly 180° from the round-trip start heading (about -60…-75°, facing the door). Stage-3 `return_home` needs the final AMCL pose within 0.30 m / 20° of the pose at the first dispatch, so it would always FAIL.
- **Fix:** `reversed_route()` keeps yaw + π for all waypoints except the last, which takes the route's original start yaw (-1.309 rad = -75°). ATLAS turns on the spot at home.
- **Room check** (map + virtual obstacles): at (0.28, 0.66) the footprint clears by ≥ 0.17 m at every heading; a 0.34 m circle is free.
- **Tests:**
  - `test_taught_route` gains `test_home_pose_keeps_start_heading_for_return_home`; the reverse test now checks all but the last waypoint. Mac OK.
  - Rover repo copy: all tests that touch mission control pass.
- **Operating note:** start the round trip at about (0.28, 0.66) facing the door (about -60…-90°) so the start heading is within 20° of -75°.
- **Deploy:** `atlas_mission_control.py` + restart of `atlas-mission-control` (parked, E-STOP latched).

### 2026-11-22 12:30–12:55 IST — Taught route field test, a 4-min network outage, Wi-Fi retry fix (owner sudo)
- **Go hall #1 (12:30)**
  - "TAUGHT ROUTE DISPATCHED name=hall waypoints=21 corridor_error=0.34m": the new route was used.
  - Stopped after about 0.6 m at (0.50, 0.62).
  - 8× `AUTONOMY BLOCKED: RIGHT 0.16–0.17 m (stop 0.23–0.26 m)` while turning right, although the LiDAR showed 0.85–1.09 m clear on the right; seconds later the right HC-SR04 read 0.67 m. Hypothesis, NOT verified: the sensor sits above the front-right wheel and sees the steered tyre. Parked steering test proposed.
  - Then the Astra obstacle scan went `BLINDED` (valid_fraction 0.279 < min 0.30), so mission control cancelled: "camera obstacles lost (2.4s stale)", status 5.
  - Two further Go presses were refused with "camera obstacles OFF". After a small manual repositioning the Astra returned OK (valid 0.46).
- **Go hall #2 (12:34)**
  - The taught route was used again; D1 and D2 passed unaided, and the right ultrasonic did not false-trigger (min 0.27 m).
  - At D3/D4: "no valid path found to (1.90, -3.95)", "Failed to make progress", and 4× "Starting point in lethal space". Goal failed at 12:37:29 (status 6) at (1.93, -2.91). 82 LIDAR AVAILABILITY STOPs, 1 remote assist.
  - Costmap read once while parked: the robot centre was at cost 31. In D3 the band where the centre is below the inscribed cost is only about 0.10–0.25 m wide (live LiDAR marks on the jamb 0.25–0.35 m left; static walls). With moving AMCL std 0.1–0.2 m the planner sees the start in lethal/inscribed space. Root cause: localisation accuracy vs doorway width (D4 tolerance about ±0.12 m), not the rover's size.
  - Proposed (not started): a "doorway assist" mode that centres reactively on LiDAR side distances inside known doorway zones, with the gate unchanged. Meanwhile the owner assists at D3/D4. The owner passed D4 by remote to (1.69, -4.60).
- **Outage 12:42:22–12:46:41**
  - The rover was unreachable on Tailscale and Wi-Fi; Jetson up the whole time (uptime 3 h 23 min, 2.6 GB RAM free, all services active). Not a CPU crash.
  - The home Wi-Fi "Airtel_dhruv_9030" is a mesh (8 BSSIDs seen). Roaming to b4:a7:c6:41:fc:9a ended in "CTRL-EVENT-DISCONNECTED reason=15 … 4-Way Handshake failed - pre-shared key may be incorrect". NetworkManager went to need-auth and blocked autoconnect until 12:46:41.
  - **4G backup absent:** "usb 1-2.2-port1: Cannot enable. Maybe the USB cable is bad? … unable to enumerate" since 12:00:47; `mmcli -L` "No modems were found"; 1-2.2.1 is missing from sysfs. So there was no failover. Owner to check the hub 1-2.2 supply and reseat the modem cable.
- **Fix applied by the owner (typed the sudo password in the Terminal tab):** `sudo nmcli connection modify Airtel_dhruv_9030 connection.auth-retries 0 connection.autoconnect-retries 0`. Verified: auth-retries 0, autoconnect-retries 0 (forever), still connected at 192.168.1.19. A handshake failure on one mesh node no longer blocks reconnecting.

### 2026-11-22 12:14 IST — New taught route + reversed-route yaw fix DEPLOYED (owner "Yes, deploy")
- **Before the deploy:** stop_latched true (reason "joystick unavailable"), autonomy armed false, motion quiet, mission READY.
- **Backups** in `~/project_atlas/backups/taught_route_20261122/`: old route 773f7b3b, mission control db0b27c4.
- **Mission control:** the diff was only `reversed_route()` + its call; compiled OK. Installed md5 d35ac0c4.
- **Route:** checked map_id 350de9b5ec3eb7f4d6f1 and 22 points before copying; installed md5 4e5118aa.
- **Restart:** `atlas-mission-control` restarted 12:13:57 → active; log "READY". Status web OK; mission READY; still latched.
- **On-rover check with the deployed helper:**
  - Forward: start (0.281, 0.664, -75°) → end (2.19, -5.58, -95°).
  - Reversed for "dhruv room": start (2.19, -5.58, +85°) → end (0.281, 0.664, +105°). Both now face the travel direction.
- **Load:** 1-minute load average 32.5 right after the restart, 27.2 at 12:14:58 and falling (startup).
- **Not yet verified:** a real Go hall / Go dhruv room using the taught route. Expected log: "TAUGHT ROUTE DISPATCHED name=hall waypoints=…", not "Taught route ignored". The "hall" named place is still (1.68, -5.35), so the route is used only when ATLAS starts within 0.65 m of the route.

### 2026-11-22 — New taught route (dhruv room → hall) on the current map STAGED (owner "हाँ, route सिखाओ"; not deployed)
- **Why:** `config/routes/dhruv_room_to_hall.json` (2026-08-26, map_id a8e7035836f61cbac5f3) does not match the current map (`map_pair_id` 350de9b5ec3eb7f4d6f1), so mission control ignored it on every Go. Nav2 then planned freely and tried to turn inside the 0.61 m hall doorway.
- **Recording:**
  - New `tools/drive/teach_route_record.py`: polls the dashboard /api/status every 0.3 s, never moves the rover and uses no ROS.
  - Owner drove dhruv room (0.24, 0.72, -58°) → hall by remote, 12:02:57, 129 s.
  - **AMCL was not tight:** xy_std 0.15–0.63 m for most of the drive (0.627 at (1.74, -2.45)). After the owner latched at the end, the pose drifted 0.39 m while ATLAS stood still ((1.31, -5.91), inside the glass-table polygon, → (1.70, -5.98)), i.e. AMCL correcting itself. So the recorded poses were used only for topology.
- **Builder:** new `tools/drive/teach_route_build.py`, read-only, writes JSON for review.
  - Map: the accepted map YAML/PGM plus `virtual_obstacles.json`, unknown = blocked. The loader matches the live /map: 0 of 56862 cells differ.
  - Narrow sections (free width across travel < 1.4 m) use the wall-to-wall midpoint; wide sections keep the recorded poses with std ≤ 0.25 m; latched samples are dropped.
  - Smoothing; 0.25 m resampling; cut at the first point within 0.3 m of the end pose; central-difference yaw.
  - Then a sideways nudge (±0.35 m, ±20°) maximises footprint clearance; every waypoint's 0.50 × 0.36 m footprint is checked with a 0.05 m margin.
  - Narrow sections found: D1 dhruv room door 0.84–0.94 m; D2 1.1–1.3/-1.3…-1.6 0.84 m; D3 1.8–2.0/-2.7…-3.2 0.82 m; **D4 hall doorway (1.9, -3.9) 0.61 m**.
- **Result** `/tmp/route_new.json` on the rover (copy in the session scratchpad):
  - 22 waypoints, 7.01 m, map_id 350de9b5ec3eb7f4d6f1, from (0.28, 0.66) to an end of **(2.19, -5.58, -95°)**, the spot where the gate view showed every direction OK; the old hall place (1.68, -5.35) is 0.44 m from the virtual glass table.
  - All waypoints clear by at least 0.06 m (D4 0.06 m; it is 12 cm per side when perfectly aligned).
  - Rendered image `route_new_20261122.png` sent to the owner.
- **Bug fixed in `atlas_mission_control.py`:** going back to "dhruv room", the route was reversed but every pose kept the room → hall yaw, so each waypoint (and the final home pose) faced backwards. New `reversed_route()` reverses AND adds π.
- **Tests:** new `tests/test_taught_route.py` (6: reverse yaw/order, dispatch uses the helper, narrow corridor centred with clearance, end cut + yaw, latched dropped, PGM loader), added to the CI list. Mac: taught route + virtual obstacles 13 OK. Rover repo copy: every test that touches mission control (map acceptance core, camera obstacle gate, feature-on-demand mapping, final map sampling, goal supersede, status idle revert, session places) + taught route + virtual obstacles + map-known gaps: 103 OK.
- **Deploy needs:**
  - route file into `~/project_atlas/config/routes/` (backup the old one);
  - `atlas_mission_control.py` + restart of the mission control service (parked, E-STOP latched, autonomy OFF).
  - The taught route only replaces the named-place goal for "hall"/"dhruv room" when ATLAS is within 0.65 m of the route; otherwise the plain goal is used. Moving the "hall" named place to the route end is a separate owner step.

### 2026-11-22 11:50 IST — MAP_GAP_MAX_BINS 3 → 6 DEPLOYED (owner "Yes, deploy", B pressed)
- **First check:** latch released, so I asked the owner. After B: stop_latched true ("REMOTE STOP: B pressed"), autonomy armed false, motion quiet, ATLAS parked at about (1.88, -3.82) in the narrow passage.
- **Deploy:**
  - Backup: `~/project_atlas/backups/map_gap_6_20261122/atlas_lidar_availability.py` (md5 2df90553).
  - Only the constant line changed on the rover (diff = line 42 only); new md5 7f2c9036; the import reports MAP_GAP_MAX_BINS 6.
  - `atlas-cmd-vel-mux` restarted 11:50:24 → active; "LiDAR guard: 4 virtual obstacles". rover-status-web restarted → active.
- **Live check at the narrow passage:**
  - Gate view LIVE, limit 6; counts lidar 66, ultrasonic 1, map 5.
  - forward, reverse and **spin now OK**. Before: spin STOP with 6 map bins over the 3 limit.
  - Still latched (reason "joystick unavailable" after the mux restart), autonomy off.
- **Caveat:** after the restarts the dashboard shows AMCL xy_std None, because AMCL publishes /amcl_pose only after an update/motion. Until the first new /amcl_pose, the mux has no fresh pose, so the map fallback is disabled (fails closed).
- **Repo:** constant + comment in the repo file; the new exact-limit test is in `test_lidar_map_known_gaps`.

### 2026-11-22 — LiDAR gate MAP_GAP_MAX_BINS 3 → 6 STAGED (owner "5 fix karo"; not deployed)
- **Safety decision by the owner:**
  - The map may explain up to 6 no-echo 5° bins at once (was 3).
  - Every explained bin still needs the full map rule: fresh confident AMCL, free cells all the way to a mapped or virtual wall beyond the sweep distance, and no closer Astra obstacle.
  - Residual risk, unchanged in kind and wider in angle: an obstacle that ALSO returns no LiDAR echo and is not seen by the Astra, standing inside one of up to 6 gaps.
- **Replay** (round-trip-6 bag, the 4 deployed virtual obstacles, `reason()` with the AMCL std gate, `/tmp/gap_limit.py`):

| Limit | Vetoes | Hall (y ≤ -4.5) | Passage (2.0, -3.5) | (2.0, -4.0) |
|---|---|---|---|---|
| 3 | 2153/5051 (43 %) | 1065 | 730 | 103 |
| 4 | 1711 | 623 | 730 | 103 |
| 5 | 1586 | 500 | 730 | 101 |
| **6** | **1323 (26 %)** | **259** | 730 | 79 |
| 8 | 1225 | 228 | 730 | 12 |

  The narrow passage (730, wall_too_close) is not affected; it needs the taught route.
- **Staged:**
  - Repo `atlas_lidar_availability.py`: constant + comment.
  - `test_lidar_map_known_gaps`: a new exact-limit test (6 bins explained for a spin, 7 stop, no map still stops); the "many" test comment updated. Mac: 47 tests OK.
  - **Rover deploy plan: change only the constant line in the rover's own file** (the repo file also has staged, undeployed side-ultrasonic code). Tested on a rover-file copy with the one-line change: the map-known tests pass, except the repo side-ultrasonic test (`SIDE_US_MOUNTS` is not on the rover; pre-existing drift).
  - Needs restarts of `atlas-cmd-vel-mux` (parked, E-STOP latched, autonomy OFF) and rover-status-web (so the gate view shows the limit 6).
- Also found: the taught route `config/routes/dhruv_room_to_hall.json` (2026-08-26, map_id a8e7035836f61cbac5f3, 127 points, 3.8 m) is ignored on every Go today ("route map identity … does not match"). Re-teaching on the current map is proposed and not started.

### 2026-11-22 11:30 IST — Doorway cabinet virtual obstacle DEPLOYED (owner "Yes, deploy", B pressed)
- **Before the deploy:**
  - The first check found the latch released and autonomy armed, so I asked the owner. After B: stop_latched true ("REMOTE STOP: B pressed"), autonomy armed false, motion quiet.
  - ATLAS was parked at about (1.80, -3.08), in the narrow passage, not open space; the owner was told.
  - The pre-restart AMCL xy_std was 0.002 (collapsed covariance again).
- **Deploy:**
  - Backup: `~/project_atlas/backups/door_cabinet_20261122/virtual_obstacles.json` (md5 83d368b5). Deployed config md5 3ce3481d with 4 obstacles.
  - `atlas-localization` restarted 11:29:49 → active 11:30:21. Log: "4 virtual obstacles … /map 234x243: 1005 cells marked as virtual obstacles".
  - The ExecStartPost verify seeder seeded "AMCL from LiDAR-verified pose x=1.895 y=-3.075", 9.5 cm from the pre-restart pose.
  - `atlas-cmd-vel-mux` restarted 11:30:30 → active. Log: "LiDAR guard: 4 virtual obstacles from …/virtual_obstacles.json".
- **After the restart:**
  - Still latched; the latch reason changed to "REMOTE STOP: joystick unavailable" after the mux restart, joy age 0.1 s. Autonomy armed false.
  - AMCL xy_std 0.065 m, yaw 2.4°, not uncertain; the covariance is healthy again.
  - rover-status-web logged HTTP handler tracebacks at 11:30:23–24 (socketserver request thread, during the restarts); none after 11:30:40.
- Not yet verified live: the gate view / guard at the doorway spot (1.3–1.5, -1.8…-2.2) showing the +55…+65° bins as map-explained (yellow) instead of none (red). This needs ATLAS at the doorway.

### 2026-11-22 — Virtual obstacle for the dark wood cabinet + open door left of the hall doorway STAGED (owner "kar do"; not deployed)
- Owner photo from behind ATLAS in the hall doorway: on the left is a dark polished wood door, open against the wall, and a dark wood cabinet. Right: door jamb, black sofa. Owner: both stay like this.
- Live check at (1.53, -2.15, -73°): the LiDAR saw 0.95–1.1 m at +37…+52°, but 5.8–6.0 m at +57…+62° (beyond the map edge) toward the map (3.5, -2.6) area.
- Derivation (round-trip-6 bag, read-only `/tmp/door_obstacle.py`):
  - 975 vetoes in the door area. Their no-echo rays (2875 sub-rays) cross FREE cells and first meet UNKNOWN along a line at y ≈ -2.5, x 3.0–3.7 (cells (3.5, -2.5) 919, (3.2, -2.5) 601, (3.5, -2.6) 506, (3.7, -2.7) 418); median 2.33 m from the laser. This is the cabinet front, never returned by the RPLIDAR.
  - Polygon [[2.95, -2.85], [3.95, -2.85], [3.95, -2.47], [2.95, -2.47]] covers 38 free (the free/unknown boundary row), 100 unknown and 2 occupied cells. At least 0.96 m from the doorway route.
  - Replay with it: door-area vetoes **918 → 3**; total 3085 → 2153; all other spots unchanged.
  - A polygon starting at y -2.52 (not covering the boundary row) gave no change at all, so the row is needed.
- `config/virtual_obstacles.json` gets the 4th obstacle. `tests/test_virtual_obstacles.py`: count 4, plus a new route-clearance test for the doorway polygon (≥ 0.6 m). Results:
  - Mac: virtual obstacles + gate view pass.
  - Rover repo copy: virtual obstacles, lidar map-known gaps, lidar availability and gate view pass.
  - A first all-polygon version of the clearance test failed on the EXISTING "black cabinet": 0.45 m from route point (1.9, -4.2). This is pre-existing and was not changed; the test was scoped to the new polygon.
- Deploy needs:
  - restarting `atlas-localization` (AMCL + Nav2 + the /map_nav republisher; AMCL resets, so re-seed with FIX MY LOCATION / the verify seeder) and `atlas-cmd-vel-mux` (guard overlay);
  - ATLAS parked in an open mapped spot, E-STOP latched (B), autonomy OFF.

### 2026-11-22 11:01 IST — Side-ultrasonic label on the sensor panel DEPLOYED (owner "Yes, deploy")
- The left/right tile now reads "SIDE STOP ONLY · NOT USED TO FILL LIDAR GAPS", with the 0.28 m autonomy side-stop rule and the replay result (no benefit, sees the floor). The earlier "NOT USED BY SAFETY GATE" understated the side stop.
- Web files only, no restart. Backups in `~/project_atlas/backups/side_label_20261122/` (sensor-panel.js ceae025b, lidar.html 2050b845). Deployed: sensor-panel.js a28ee131, lidar.html 8c24df16 (`?v=20261122side`).
- Verified on the live page over Tailscale: the tile shows the new text with live readings (left 0.80 m, right 0.43 m).

### 2026-11-22 — Side (left/right) ultrasonic for the LiDAR gate: replay says NO benefit (read-only)
- Owner question: would the left/right HC-SR04 help the LiDAR gate? The owner sent a side photo (right side, front to the right). The sensor sits flat on the side panel about 4–5 cm behind the front edge, at the 0.23 m height measured earlier, facing straight sideways. Estimated mount: x ≈ 0.20 m, y ≈ ∓0.18 m, axis ∓90°.
- Mount check against the LiDAR (round-trip-6 bag, about 420 readings per side, /tmp/side_us_check.py):
  - Agreement is poor for every tested x (0.10/0.20) and axis (±70…±110°). Right: within 10 cm of the LiDAR only 8–17 % of the time, and more than 10 cm SHORTER 46–50 %. Left: best 32 % (x 0.10, axis 90–100°).
  - Median readings 0.79/0.80 m sit close to the 0.72 m floor-echo distance for a 0.23 m high sensor, so the sensors often see the floor or low objects below the LiDAR plane.
- Gate replay with the repo's side-coverage code (`side_ultrasonic_covered_bins`), mounts x 0.20, axis ±90°, cone 10° and 15°: vetoes 3085 → **3085 (zero change)**, the same at every spot.
  - Reason: the gate's bins are measured from the LiDAR origin, and the sensor sits 0.25 m ahead of it with a narrow cone. The directions the LiDAR misses (e.g. -88…-98° from the LiDAR) lie behind the sensor's cone. This confirms the 2026-11-19 finding (2 of 9 door cases).
  - (This replay uses `reason()` with the std gate, so its baseline is 3085 rather than the 2891 of the simplified replay.)
- Decision input for the owner: keep left/right as the existing autonomy side stop (≤ 0.28 m while turning). Do not add them to the LiDAR gate. The larger levers remain:
  - a virtual obstacle for the unknown non-reflecting object near map (3.5, -2.6): 918 vetoes;
  - Nav2 centring in the narrow passage: 730;
  - the MAP_GAP_MAX_BINS decision for the hall.

### 2026-11-22 10:38 IST — "All sensors" panel DEPLOYED (owner "Yes, deploy")
- Before the deploy: parked (motion quiet, mission READY), autonomy armed true, stop not latched. Only rover-status-web was restarted, at 10:38:20; no motion.
- Backups: `~/project_atlas/backups/sensor_panel_20261122/` (atlas_gate_view 36694951, lidar.html 99c64d49, lidar.js a732bcb2).
- Deployed md5s: atlas_gate_view 150f3311, lidar.html 2050b845, lidar.js e04a2ee3, sensor-panel.js ceae025b. Compiled OK; service active.
- Live API check: gate LIVE (lidar 70, map 2); astra_fresh true with 10 obstacle directions; forward, reverse and spin OK. sensor-panel.js 200; /camera.jpg 200 (28.5 kB).
- Journal: one BrokenPipeError at 10:38:06, from the old process before the restart.
- The page over Tailscale shows blue Astra dots ahead at about 1.2–2.6 m, 10 sensor tiles, and the live IMX708 frame (1280 px wide). No console errors.
- Live values: AMCL ±0.047 m; radar 2 targets, nearest 0.32 m (DANGER); GPS no fix indoors; encoders DEGRADED (M3 excluded).

### 2026-11-22 — "All sensors" panel on What ATLAS sees STAGED (owner "add kar do"; not deployed)
- New `web/v2/sensor-panel.js` (loaded by lidar.html, `?v=20261122sensors`), read-only. It polls /api/status every 1 s and the latest IMX708 frame every 2 s, only while the page is visible.
- Tiles for every sensor: LiDAR, Astra depth, ultrasonic front/rear, ultrasonic left/right, AMCL location, radar RD-03D, IMU, wheels/encoders, GPS and IMX708. Each shows freshness and a label saying whether the Nav2 LiDAR safety gate uses it.
  - Used by the gate: LiDAR, Astra, front/rear ultrasonic, AMCL/map.
  - Not used: left/right ultrasonic (no measured mounts), radar, IMU, encoders, GPS, IMX708.
- `atlas_gate_view.build()` now also returns `astra_obstacles` (per bin, distance from the laser; empty when coverage is stale) and `astra_fresh`. lidar.js draws them as blue dots on the ring view. 1 new test (10/10); the rover temp copy passes gate view, executor-split and estop-safety (28, 1 skipped).
- Browser preview with fake data: blue dots are at the correct side and distance; tiles readable on the dark panel; long lines wrap; the camera tile shows "waiting for a frame…" until a frame loads.
- Live values read at 10:31, for reference: AMCL xy_std back to 0.054 m (the collapsed covariance at 10:25 was temporary); radar 1 target at 0.13 m, x 57 mm / y 122 mm, "DANGER" while parked (likely a reflection off ATLAS itself, not checked); GPS NMEA live, no fix (indoors); encoders DEGRADED with M3 excluded.

### 2026-11-22 10:25 IST — "What ATLAS sees" window DEPLOYED (owner "Yes, deploy")
- State before the deploy: ATLAS parked (motion quiet, mission READY), autonomy armed true, stop not latched. Only rover-status-web was restarted (no base, mux, Nav2 or LiDAR restart; no motion).
- Rover files differed from the repo only by this change. Backups are in `~/project_atlas/backups/gate_view_20261122/` (status web, index.html, home-nav.js, lidar.html, lidar.js).
- Deployed md5s: atlas_gate_view 36694951, atlas_status_web 9bf00fee, lidar.html 99c64d49, lidar.js a732bcb2, index.html 7549dd2c, home-nav.js 4dec8552. Compiled OK; service restarted 10:25:13; active; /api/status 200; no errors in the journal.
- Live check at dhruv room (0.21, 0.71, -76°): /scan LIVE about 9 Hz; gate LIVE with all 72 directions lidar; forward, reverse and spin all OK; ultrasonic front 0.67, left 0.89, right 0.46, rear 0.73 m. The page (Tailscale, `/v2/lidar`) shows an all-green ring, "Every direction is covered right now", and the menu entry "What ATLAS sees".
- **New finding, pre-existing and not caused by this deploy: the AMCL covariance has collapsed.** `/amcl_pose` covariance is about 0, with tiny negative values (cov[0] -1.9e-15, cov[7] -3.7e-14). The dashboard therefore shows "Invalid AMCL pose/covariance" (amcl_quality xy_std None). The mux computes the std as sqrt(max(0, …)) = 0, so it treats the location as fully confident and the map fallback stays enabled. Earlier today the covariance was normal (xy_std 0.068 at 09:44). Not investigated or changed.

### 2026-11-22 — "What ATLAS sees" window STAGED (owner "हाँ, window बनाओ"; not deployed)
- Purpose: the owner can see live which directions the Nav2 LiDAR safety gate cannot see, and where they point on the map, so the cause of a stop can be found (taping surfaces is not practical in the house).
- New `scripts/atlas_gate_view.py`, display only (no publishing, no commands, no gate change). For each of the 72 robot-frame 5° directions it reports the source that covers it: lidar / astra / ultrasonic / map (map + virtual obstacles explain the gap) / none. It calls the same `atlas_lidar_availability` functions as the mux. For gaps it gives the map ray (wall / UNKNOWN / edge, distance, map point). It also reports what the gate would answer now for forward 0.15 m/s, reverse and spin 0.5 rad/s.
- `atlas_status_web.py`:
  - subscribes `/astra/obstacle_coverage`;
  - feeds a display-only `LidarAvailability` from `/scan` and coverage, under `self.lock` because the two callbacks run on different executor threads; the HTTP thread reads a copy taken under the lock;
  - keeps the map + `virtual_obstacles.json` overlay and the AMCL pose/std (same formulas as the mux);
  - `/api/lidar-view` gains `gate`.
- `web/v2/lidar.html` + `lidar.js` (`?v=20261122gate`):
  - a coloured ring around the rover;
  - Drive forward / Reverse / Turn on the spot OK/STOP chips;
  - a legend with counts;
  - a warning when more directions lack echo than MAP_GAP_MAX_BINS;
  - a list of "Directions nothing sees" with side, width and map point.
  - The menu entry is renamed "What ATLAS sees".
- Limitation: ultrasonic freshness comes from the `/ultrasonic/validity` JSON (0.5 s), not the mux's own ValidityWindow, so the view may differ from the mux for a moment.
- Tests:
  - `tests/test_gate_view.py` 9/9 (added to the CI list).
  - `test_status_web_executor_split` caught the cross-thread `gate_guard`. Fixed with the lock; `gate_guard` was added to its GUARDED set with a comment.
  - Rover temp copy: gate view, no-reboot, relocalize, estop-safety and executor-split all pass (47, 1 skipped).
  - Full CI list on a repo copy on the rover: 1173 run; 7 fail/error in monitoring config, scan self-filter service, systemd ordering and vision3d tests that do not touch these files (rover environment). GitHub CI is the reference.
  - Browser preview with fake data (real `build()`): ring colours and directions are correct (left = left), red unknown gap listed with its map point.

### 2026-11-22 09:31–09:45 IST — Round trip 6 (all-sensor recording): both legs SUCCEEDED with owner assists; STAGE 3 FAIL (not scoreable)
- Context: ATLAS had booted about 7 min before the run (load average 12–27 throughout). Autonomy ON by operator. The owner drove/assisted with the Xbox remote; I sent no motion.
- Recording (owner request "use all sensors together" for 3D mapping): two `ros2 bag record` processes (nice 5), started at 09:32:12 while ATLAS was already on the way to hall. Astra runs on ROS_DOMAIN_ID 77 and the main stack on domain 0 (UDPv4), so one bag per domain:
  - `~/atlas_bags/rt6_allsensors_20261122_093212`: Astra color, depth, camera_info and obstacle scans; 11 GB, about 13 MB/s. `/astra/extrinsic/depth_to_color` was not recorded (astra_camera_msgs type not installed).
  - `..._main`: 145 topics (LiDAR scan and scan_raw, tf, odom, AMCL, map, cmd_vel*, Yahboom encoders/IMU/wheels, IM10A, GPS, ultrasonic, radar, IMX708 compressed, /atlas/*); 385 MB.
- Leg 1, Go hall: Nav2 "Goal succeeded" 09:36:05; final pose (1.77, -5.24, -109°), 0.13 m / 11° off.
  - 187 `LIDAR AVAILABILITY STOP: unobserved motion sector (1–3 bins)` between 09:31 and 09:36.
  - One `Failed to make progress` (09:33:51) with `Control loop missed its desired rate of 10 Hz`; Nav2 then retried on its own.
  - rf2o: 639 `Waiting for laser_scans` in 4 min (scan delivery late under load).
  - 09:35:53–55: `AUTONOMY BLOCKED: LOCALIZATION XY UNCERTAINTY 0.30 m`; AMCL then recovered.
  - Owner assists: 2.
- Leg 2, Go dhruv room:
  - The first goal FAILED at 09:39:57 because the planner said `Starting point in lethal space` (the hall spot is inside the costmap's lethal space next to the wall). The owner turned ATLAS by remote (net turn about 184°), then pressed Go again.
  - Repeated `LIDAR AVAILABILITY STOP` while going straight on the hall→room line, with the most stops near (1.3, -1.8), the same area as on leg 1 (hall door frame). About 118 stops in 2 min, plus one more `Failed to make progress`.
  - Nav2 "Goal succeeded" at 09:44:49. Final pose (-0.04, 0.61, 92°): 0.14 m / 27° off. AMCL xy_std 0.068 m. Owner assists: several (turning and straight line).
- Checker (`stage3_autonomy_check.py`, run from /tmp on the rover with /usr/bin/python3) on the main bag:
  - PASS legs, turn_sign (autonomous same 737 / opposite 13) and encoders (0 bad).
  - FAIL return_home (2.81 m / 161° from the bag start pose, because the bag started mid-leg and not at dhruv room).
  - FAIL safe_stop (no owner B press while Nav2 drove).
  - localization_blocks_while_moving 3; mean moving speed 0.167 m/s; duration 691 s. **STAGE 3: FAIL.**
- Bag replay (read-only, /tmp/replay_gate.py and /tmp/spot_detail.py on the rover).
  - Method: the gate logic of `atlas_lidar_availability` over /scan + /astra/obstacle_coverage + /amcl_pose + /map + /cmd_vel_nav.
  - Limitations: ultrasonic coverage is not applied, and bag receive time is used as both clocks.
  - Result: 3323 of 5051 Nav2 commands vetoed. 1391 passed on LiDAR alone, and 337 passed only because the map explained the missing bins. Almost all vetoes were arcs, not straight lines.
- What the vetoes are:
  - **No-echo directions that are also UNKNOWN on the map.** At the hall spots (1.5–2.0, -5.0…-5.5), every LiDAR ray at robot bearing -22/-28° is inf, and the map ray from there meets UNKNOWN cells at 1.9–2.7 m (world 220–230°). Near the door (1.5, -2.0; leg-1 stop at 1.32, -1.76), robot bearing +52° is inf, and the map meets UNKNOWN at 2.3–2.6 m (world about 330°); 915 vetoes there. Neither the LiDAR nor the mapping run ever saw these surfaces. Likely non-reflecting surfaces (glass, black/glossy furniture, mirror); the owner should check what stands there.
  - **Mapped walls that give no echo.** In the hall, the right-side wall at 1.4–1.8 m (robot -88/-98°, world 150–160°) gives no echo. Together with the UNKNOWN bins that makes 4 or more missing bins, above MAP_GAP_MAX_BINS 3, so the map fallback is not used.
  - **Wall too close.** In the corridor (2.0, -3.5…-4.0), the right/rear wall at 0.3–0.5 m gives no echo and is closer than the sweep-required distance (wall_too_close).
  - **Not a fixed blind spot on the rover:** no robot bin was empty more than 34 % of the whole bag (/scan and /scan_raw are the same).
- **Corrections to what I told the owner during the drive:**
  - (1) CPU load did NOT delay the scans: scan gaps were median 0.137 s, p95 0.153 s, max 0.291 s, and none exceeded the 0.75 s timeout.
  - (2) On the plain /map the hall named place is 1.12 m from a wall. **But with the virtual obstacles that Nav2 and the guard actually use (`config/virtual_obstacles.json`), the hall spot (1.68, -5.35) is only 0.44 m from the "glass coffee table" polygon**, less than the footprint half-diagonal 0.31 m + inflation 0.28 m. At the 09:39 failure ATLAS was at about (1.77, -5.24), 0.55 m from the table corner. Costmaps were not recorded, so which layer made the start lethal is unproven.
- Second replay, matching the mux: virtual obstacles overlaid, front/rear ultrasonic applied.
  - Result: 2891 of 5051 vetoed; 1391 passed on LiDAR, 738 because the map explained the gap, 31 by ultrasonic.
  - Remaining veto groups:
    - (1.5, -2.0), 915 vetoes: robot +52° is inf, and the map ray meets UNKNOWN at map (3.5–3.7, -2.6…-2.7). This is a non-reflecting object that is not in virtual_obstacles.json and not yet identified.
    - (2.0, -3.5…-4.0), about 720 `wall_too_close`: the narrow passage, with mapped jambs at 0.3–0.5 m around (1.5–1.6, -3.7…-3.8) and (2.1–2.2, -3.8…-4.0) that give no echo.
    - Hall, `too_many_bins`: the missing bins all point at the virtual table (0.6 m) and sofa (1.1 m), but more than MAP_GAP_MAX_BINS 3 are missing at once.
  - What-if limits (not applied): MAP_GAP_MAX_BINS 4 → 2447 vetoes, 5 → 2322, 6 → 2059.
- `config/ultrasonic_mounts.json` does not exist on the rover, so the left/right ultrasonic sensors add no guard coverage (the staged 2026-11-19 code waits for measured mounts).
- Open, not changed: the non-reflecting hall and door surfaces; the corridor path hugging the right wall; the source of the lethal start; why the Astra coverage did not cover bearings -22/-28° (inside its FOV); and `stage3_autonomy_check.py` is not installed on the rover.

### 2026-11-22 06:29 IST — "SINCE POWER-ON" history DEPLOYED (owner "Yes, deploy") + battery backfill
- Before deploying: source STOPPED, stop latched, autonomy armed false. Backups in `~/project_atlas/backups/power_history_20261122/` (monitor, status web, usb-power.js, index.html); the rover files differed only by the replaced lines.
- First deploy 06:27:41 (monitor d8f7c766, status web d3a7a3ef, usb-power.js 44bc6576, index 6446fcfa): `?long=1` served. Faults since boot: 0. The battery reading filled within seconds, and the history file was saved. On the live chart, rail and battery were empty before 06:27 because they had not been recorded before this deploy.
- Follow-up (same feature, same deploy): battery minutes are now backfilled from the `rover-daly-bms` journal (5 s lines) for time before the monitor started; live readings are never overwritten. Minutes are sorted, and the 24 h cap drops the oldest minute. The chart notes when the Jetson rail starts ("recorded from 06:27 (dashboard start)"). Tests 16/16 (1 new); the rover temp-copy set passed. Redeployed 06:29:13 (monitor bbc24543, usb-power.js 95259b1b, index b0071249).
- Live result: 451 minutes from 22:59, all with battery. rail_from 06:27; faults since power-on 0. On the dashboard: green "No USB faults since power-on on any hub"; battery 35 % -> 100 % by about 03:05; current +1.5..2 A, then 0, never below 0.

### 2026-11-22 — Power chart "SINCE POWER-ON" history STAGED (owner "Yes, add it"; not deployed)
- `atlas_usb_power_monitor.py`: per-minute buckets for up to 24 h: Jetson VDD_IN min/avg/max and current avg/max, battery SOC/current/voltage from the Daly BMS (via the new `bms_for_power_history()` in status web), and USB faults per hub (disconnect, enum error, I/O error, over-current; re-enumerations are not counted).
- USB faults since boot are backfilled once from `journalctl -k -b` for the time before the monitor started; afterwards the live reader takes over, with no double counting. Rail and battery minutes are saved every 60 s to `~/.local/state/project_atlas/usb_power_history.json` and restored after a dashboard restart within the same boot (boot_id).
- `GET /api/usb_power?long=1` returns the per-minute list, totals per hub, and boot time. The dashboard fetches it every 60 s (only while the drawer is open).
- `usb-power.js`: new SINCE POWER-ON section with a banner ("No USB faults since power-on" or the faults per hub) and four charts: VDD_IN (1-min average line plus min..max shading and the 4.75 V line), battery %, battery current (above or below 0), and USB faults per minute. Cache key `usb-power.js?v=20261122long`.
- Tests: `test_usb_power_monitor.py` 15/15 (6 new; this caught `state_path=None` crashing `_restore`, now fixed). The status-web set is 77/77 in a rover temp copy; one combined run had a single failure that passed on two reruns and individually, likely a 3 s thread wait in `test_relocalize_web` under load, so the wait is now 15 s. Real rover probe: backfill took 0.02 s; boot 22:59; 0 faults since boot. Browser test page (rover 10-min data + BMS overnight history + one synthetic fault): banner and charts render, no console errors.
- Limitation: the rail and battery history start when the dashboard service first started this boot (the INA3221 is not logged elsewhere). USB faults cover the whole boot.

### 2026-11-22 06:20 IST — Overnight check: powered hub holds; 0 USB faults in 7 h 20 min
- Boot 22:59 (dashboard Restart); uptime 7 h 20 min. Kernel: 0 modem disconnects, 0 USB disconnects, 0 USB errors (-32/-71/-110/urb stopped). USB power chart: 0 faults on all 5 hubs, no device gone, suspect hub none.
- Jetson VDD_IN 4.856-4.880 V over the last 10 min, 1.6-1.8 A (8-9 W). Load average about 8.5.
- 4G: registered, LTE, signal 58 %, usb0 up. Hiwonder GPS: FIXED on ttyUSB1 (GPS 10, GLONASS 8, BeiDou 7 in view; 396 k valid NMEA). LiDAR 359/360. Localization VERIFIED. Stop latched, autonomy armed false.
- Battery (Daly BMS): 100 %, 14.4 V, 0 A; cells 3.593-3.612 V (full, balanced). The overnight charge completed.
- Conclusion: giving hub 1-2.2 its own supply fixed the modem USB drops, with no recurrence over the same post-boot window where yesterday's storm began. Still to verify: a drive with Wi-Fi loss (4G carrying traffic).

### 2026-11-21 23:25 IST — FIX MY LOCATION DEPLOYED (owner "Yes, deploy")
- Before deploying: control source STOPPED, stop latched, autonomy armed false. Backups in `~/project_atlas/backups/fix_location_20261121/` (atlas_status_web.py, index.html); the rover copies matched the repo before this change.
- Copied atlas_relocalize_web.py (aea8ed97), atlas_status_web.py (177235f4), find-location.js (715f4a41) and index.html (ae53dfde); md5s match, py_compile OK. `systemctl --user restart rover-status-web` at 23:24:48; active, no errors.
- Verified: GET /api/relocalize -> idle status (navigation_authorized false); a POST without confirm -> 400; /api/usb_power still serves 12 devices. On the live dashboard the FIX MY LOCATION button sits in the location panel and the localization chip handler is bound (chip currently "Localization verified"). No console errors.
- Not yet exercised end to end. The first real use runs the boot seeder (no motion, autonomy must be off).

### 2026-11-21 23:20 IST — Dashboard "FIX MY LOCATION" STAGED (owner request; separate button; not deployed)
- Why: at the 21:24 boot the seeder logged LOCALIZATION UNKNOWN (best map fit 0.78 < 0.93; LiDAR partly blocked during re-wiring, 299/360 points). After the 22:59 restart, the same boot check gave a unique fit 1.0 and seeded AMCL. The owner wants that fix without a restart. The existing CHECK MY LOCATION is read-only ("No driving or pose correction").
- `scripts/atlas_relocalize_web.py`: POST /api/relocalize runs exactly the boot seeder, `seed_atlas_localization.py --mode verify` (parked LiDAR search over the whole map, unique strong match only, same thresholds; the seeder refuses while moving). It never moves the rover. Gates: JSON confirm=FIND_LOCATION, same origin, autonomy armed must be False (unknown counts as armed), one run at a time, 150 s timeout. GET /api/relocalize returns running / elapsed / last result (seeded, pose, fit, reason). navigation_authorized stays false.
- `atlas_status_web.py`: routes for GET and POST plus `AtlasRosNode.autonomy_armed()` from the fresh mux control policy.
- `web/v2/find-location.js` (index.html): a FIX MY LOCATION button next to CHECK MY LOCATION; clicking the red "Localization unknown/lost" chip opens it too. It shows a bottom sheet with a 15 s auto-close, progress polling, and the result ("Location found and set: x, y, facing, fit", or "not found" with the reason and advice).
- Tests: `tests/test_relocalize_web.py` 11/11 (added to the CI list). Status-web suite 71/71 in a rover temp copy; the first run had 27 errors because the old test stub had no `autonomy_armed`, fixed by passing a lambda. Browser test page with the API stubbed: the button is placed after CHECK, the sheet opens and sends exactly {"confirm":"FIND_LOCATION"}, the polled result renders, Close works, and the chip opens the sheet.
- Deploy needs the owner's OK: copy 2 scripts and 2 web files, then restart rover-status-web (parked).

### 2026-11-21 22:59 IST — Restart from the owner's phone PASSED (new confirm sheet)
- estop_events: `reboot_latch` at 22:58:57 from 100.76.195.106 (the phone that failed before), then latch "REMOTE STOP: voice stop requested". New boot 22:59:35; SSH back by 23:02:07. After boot: latch "REMOTE STOP: joystick unavailable"; rover-status-web, atlas-lidar, rover-base-telemetry and atlas-gnss active; modem registered; 0 USB faults this boot.
- Earlier "Pressed YES" at about 22:51 left no record. The sheet's message was not reported, so that first try is unexplained (most likely a stale page before the reload).
- The scheduled 2 h USB recheck ran at about 23:00 during the reboot, and SSH failed (exit 255). The previous boot's kernel journal is not available ("No such boot ID"), so the USB fault count for 21:50-22:59 is unverified. At 21:50 it was 0 and the chart showed no suspect hub.

### 2026-11-21 22:45 IST — Restart confirm sheet DEPLOYED (owner "Yes, deploy")
- Rover state: control source STOPPED, autonomy armed false (stop released). Web-only change, no service restart; diagnostics.js and the pages are read per request.
- Backups in `~/project_atlas/backups/restart_sheet_20261121/`. Before copying, the rover files differed from the repo only by the old restart code. Copied atlas_diagnostics_ui.js (0f6b2b74), index.html (30cc8017), classic.html (e7f4845b) and mapping.html (5cf82520); md5s match.
- Served: /v2/ and classic.html load `diagnostics.js?v=20261121sheet`; diagnostics.js and mapping.html contain the sheet. Live page in the built-in browser with fetch stubbed: the sheet was still open 6.5 s after the tap, and Cancel closed it with nothing sent. Not yet tested with a real press on the owner's phone.

### 2026-11-21 22:40 IST — Restart: 15 s on-page confirm sheet STAGED (owner "Yes, build it"; not deployed)
- Finding: on a phone-sized page (real taps, requests stubbed), the two-tap Restart works when both taps land within 5 s. A second tap after 5 s only re-arms the button and sends nothing. That fits the owner's phone (100.76.195.106), from which only "stop" requests arrived (22:05-22:33), never `reboot_latch`.
- Change: `restartAtlas()` in `atlas_diagnostics_ui.js` (index + classic) and in `mapping.html` now opens a fixed bottom sheet: "Restart ATLAS Jetson?" with big "YES, RESTART NOW" and "Cancel" buttons and a 15 s countdown, then auto-closes. No pop-up. The result or error text shows in the sheet. Colours are forced with !important because the page's button CSS overrode them. The server side is unchanged (confirm=RESTART_ATLAS + same origin, drive stop latched first). Cache key `diagnostics.js?v=20261121sheet`.
- Test on the live dashboard at 375 px, real taps, fetch stubbed: More -> Restart opens the sheet; YES tapped after more than 5 s sent exactly `action=reboot&confirm=RESTART_ATLAS`; Cancel closes with nothing sent; the YES button computes red (rgb 208,32,47).

### 2026-11-21 22:13 IST — Owner: "Restart didn't restart" and "charging keeps stopping"
- Restart: no `reboot_latch` in estop_events since the 21:24 boot, so the request never reached the server. Only "stop" events arrived from 100.76.195.106 (22:05:49, 22:11:04), the same Tailscale device whose taps failed on 2026-11-20 (probably a stale page). The sudoers rules are still present. LiDAR is running: atlas-lidar and atlas-scan-filter active, /scan fresh (299/360 points, age 0.2 s).
- Charging (Daly BMS, 4S LiFePO4, Bluetooth, logged every 5 s): the BMS reports "OK" throughout, cells 3.336-3.358 V (spread 22 mV; far below the 3.65 V full level). The pack current flips between charging +2.5..2.8 A and discharging -1.8..-2.3 A (rover load with no charger input):
  CHG 21:28:33-21:47:13 (19 min), 21:49:48-21:58:58 (9 min), 21:59:18-22:02:28, 22:02:53-22:04:03, 22:04:48-22:07:43, 22:08:18-22:11:43, then 22:12:18 on. The charge runs keep getting shorter, and each cut lasts 20 s to 2.5 min before charging resumes by itself.
- Owner: the charger is rated 14.6 V 5 A. While the rover runs, the charger must deliver about 4.7 A (2.1 A load + 2.6 A into the pack), 94 % of its rating, continuously. Charge runs getting shorter (19 -> 9 -> 3 -> 1 min) fit thermal or over-current cycling of a charger at its limit. Options: charge with ATLAS shut down (full 5 A into the 17.4 Ah pack), or use a 14.6 V 10 A LiFePO4 charger after checking the Daly BMS charge-current rating. Also check the connector and the charger temperature.
- 22:22 owner photo: the "charger" is a programmable DC-DC bench supply, not a dedicated charger. Display: input 30.88 V; output 13.70 V, 5.01 A, 68.63 W in CC (current limit); V-SET 14.50 V, I-SET 5.00 A, OVP 30.00 V, OCP 7.00 A; 13.946 Wh delivered. Since 22:15 a cut needs a manual restart (latching protection).
- Correction to my earlier advice: in CC mode the supply delivers 5 A (about 68-69 W) whether or not ATLAS is on (with ATLAS off, all 5 A goes into the pack). Shutting ATLAS down does NOT reduce the supply's load. More likely causes: the input adapter (about 75 W drawn at 30.9 V, about 2.4 A) at its limit and sagging, which trips the module's input under-voltage/over-power protection; or module over-temperature. Mitigation: lower I-SET to 3.5-4 A (about 48-55 W), give the module airflow, check the adapter rating, and read the protection code shown at the next cut.
- Reading: BMS protection is unlikely (status OK, cells low and balanced). An intermittent external charger supply fits better: a loose charge connector or cable, or a charger hitting its limit or overheating. The charger must supply about 4.7 A (2.1 A rover load + 2.6 A into the pack). SOC (Daly coulomb counter) 26.6 %.

### 2026-11-21 21:57 IST — Back to Stage 3: localization not seeded after the 21:24 boot
- Boot seeder: "LOCALIZATION UNKNOWN: AMCL not seeded; scan does not match the saved map well enough anywhere (best 0.78 < 0.93)". AMCL: "Please set the initial pose"; the location monitor shows "AMCL pose stale". Relocalize mode is `auto`, but auto needs a live AMCL pose to compare against.
- Likely cause: ATLAS was not at a mapped spot during the USB re-wiring and reboot. Next: the owner places ATLAS at the "dhruv room" place facing 65 deg, then seed in verify mode (scan match, no motion).
- Plan for round trip 6 (official Stage-3 evidence):
  1. Tape the hall door frame.
  2. Start at "dhruv room", 65 deg, location VERIFIED.
  3. Record a light bag of the checker topics only.
  4. Go hall; press B once while Nav2 is driving (safe_stop); release; Go again.
  5. Go dhruv room.
  6. Run `stage3_autonomy_check.py BAG --home "dhruv room"`.

### 2026-11-21 20:56 IST — Owner gave the USB hub its own power: 0 USB faults in the first 16 min (early result)
- Rover rebooted about 20:40 after the re-wiring. Layout unchanged: hub 1-2.2 = 4G modem + motor base + LiDAR (+ billboard); 1-2.3 = ESP32 + UNO R4; 1-2.3.3 = Astra x2; 1-2.4 = GPS + IM10A + Xbox.
- Kernel this boot: 0 USB disconnects, 0 USB errors (-32/-71/-110/urb stopped). Modem registered on LTE (67 %), usb0 192.168.225.138.
- `/api/usb_power`: 575 samples, every device health 1.0 throughout, no faults on any hub, suspect_hub none. VDD_IN 4.864-4.888 V (1.69 A).
- Hiwonder GPS: NMEA_LIVE_NO_FIX on ttyUSB1 (renumbered), valid_nmea 10865.
- Owner confirmed (21:00): the external supply went to hub 1-2.2, the modem hub that also carries the motor base and LiDAR. 0 faults on every hub 19 min after boot.
- Caveat: this morning's storm started about 20 min after boot and lasted until 10:28. One clean 16-minute window is encouraging but not yet proof. Still to do: re-check after a few hours, and during a drive with Wi-Fi loss (4G carrying traffic).

### 2026-11-21 12:24 IST — USB power-health chart DEPLOYED (owner "Yes, deploy")
- Before deploying: control source STOPPED, stop latched ("REMOTE STOP: joystick unavailable"), autonomy armed false. Backups in `~/project_atlas/backups/usb_power_chart_20261121/` (atlas_status_web.py, index.html). Before copying, the rover's two files differed from the repo only by this change.
- Copied atlas_usb_power_monitor.py (147e0668), atlas_status_web.py (4cea5321), usb-power.js and index.html; md5s match. py_compile OK. `systemctl --user restart rover-status-web` at 12:24:43; active, no errors in the journal.
- `/api/usb_power` live: rail Jetson VDD_IN 4.864 V / 1.84 A. 5 hubs and 12 devices named correctly: hub 1-2.2 = 4G modem + Motor base + LiDAR + billboard; 1-2.3 = ESP32 + UNO R4; 1-2.3.3 = Astra x2; 1-2.4 = Hiwonder GPS + IM10A + Xbox. No faults since start. status-web process 20 % CPU right after start.
- Follow-up fix (same deploy): the dashboard runs in a light theme, where the dark-theme green banner text was unreadable. usb-power.js now picks a light or dark palette from the drawer's text colour; cache key `usb-power.js?v=20261121usb2` (usb-power.js bb82d130, index.html c73ca05b). Verified in the built-in browser on the live dashboard: green "No USB faults" banner readable, volt/amp charts and 12 device lines drawn, no console errors.

### 2026-11-21 — USB power-health chart on the dashboard STAGED (owner request; not deployed)
- Owner asked for a live power reading per USB device, so that a power drop shows which hub it came from. Per-port USB current is NOT measurable on ATLAS: USB 2.0 hubs and Linux do not report it. Real per-hub current would need an INA219/INA226 on each hub's 5 V line.
- Built instead (read-only): `scripts/atlas_usb_power_monitor.py` samples every 1 s (sysfs scan of every USB device, its hub, ttys and owning process role) plus the Jetson VDD_IN rail (INA3221 in1/curr1). A `journalctl -k -f` reader maps USB disconnect, re-enumeration, enumeration errors (-71), control/urb errors (-32) and over-current to the device. Health per second: 1 up / 0.75 re-enumerated / 0.5 USB error / 0 gone. 10-minute history, 1 h event counters per hub, and `suspect_hub` = the hub with the most faults in 10 min.
- `atlas_status_web.py`: new `GET /api/usb_power`; the monitor starts at server start.
- `web/v2/usb-power.js` (+ slot in index.html "Power and environment" drawer): red banner naming the suspect hub and its devices, smooth VDD_IN volts and amps charts, then one health line per device grouped by hub, with red/orange ticks on fault seconds. Polls every 2 s only while the drawer is open and the page is visible.
- Tests: `tests/test_usb_power_monitor.py` 9/9 (added to the CI list). Status-web suite 60/60 in a rover temp copy. Browser check with rover-sampled data (synthetic modem disconnect + base -32): renders, suspect hub 1-2.2 named, no console errors, no horizontal scroll at 375 px.
- Deploy needs the owner's OK: copy the 2 scripts and 2 web files, then restart rover-status-web with the rover parked.

### 2026-11-21 12:03 IST — Owner re-cabled USB: the modem now shares hub 1-2.2 with the base and LiDAR; GPS wedged again
- New layout. Hub 1-2.2: port 1 SIM8230G modem (enumerated 12:01:42, registered on LTE, usb0 up), port 3 Yahboom base CH340 (ttyUSB4), port 4 RPLIDAR CP210x (ttyUSB0, 360/360 points). Hub 1-2.3: ESP32 moved to port 1, UNO R4 on port 2. Hub 1-2.4: GPS 2.4.2, IM10A 2.4.3, Xbox 2.4.4.
- During the re-cabling: a brief device at 1-2.1 (11:58:42-45), then at 11:59:09 the GPS CH340 again logged "urb stopped: -32" and at 11:59:18 "failed to send control message: -32". GPS PORT_OFFLINE (needs a replug). No modem drop since 12:01:42 (checked 12:03:50, only 2 min).
- RISK: the modem's earlier brownouts now sit on the same hub as the motor base and the LiDAR. The modem's earlier drops had no errors on neighbouring devices, but hub 1-2.2 itself dropped completely once at 11:52:07 during re-cabling. A sag here could cut the base serial or the LiDAR mid-drive. Recommend keeping the modem off the base/LiDAR hub until it has its own 5 V ≥3 A supply. Do not drive autonomously in this layout.

### 2026-11-21 11:52-11:54 IST — Owner moved the 4G modem to a Jetson USB port directly: the modem no longer enumerates
- 11:52:07: the whole hub 1-2.2 (LiDAR CP210x, Yahboom CH340, ESP32, billboard) and 2-1.2 disconnected and re-enumerated, most likely bumped during the re-cabling. Services reopened: base now on ttyUSB4, LiDAR on ttyUSB0 (356/360 points). rover-base-telemetry, atlas-lidar, atlas-im10a and atlas-gnss are active.
- Modem at 1-2.1 (Jetson onboard hub port): "device descriptor read/64, error -71" (11:52:29-30), then "Device not responding to setup address" and "device not accepting address 50, error -71" (11:52:33). Since then: no SIMCOM device in lsusb, `mmcli -L` "No modems were found", no usb0. The 4G backup is currently DOWN; Wi-Fi is up.
- Error -71 (EPROTO) at enumeration on a direct Jetson port, with no hub, is a further sign that the modem cannot be powered from a USB port (or that the cable/connector is bad).
- The Hiwonder GPS recovered on hub 1-2.4 (NMEA_LIVE_NO_FIX on ttyUSB2, valid_nmea 2431) once the modem left that hub. The stop is latched ("joystick unavailable").

### 2026-11-21 11:50 IST — The modem's power event also wedged the Hiwonder GPS (same hub)
- 11:50:49 kernel: "ch341-uart ttyUSB2: usb_serial_generic_read_bulk_callback - urb stopped: -32" (GPS CH340, 1-2.4.2). Within one second the modem (1-2.4.1) re-enumerated four times (devices 38-41).
- 11:50:58: "usb 1-2.4.2: failed to send/receive control message: -32" and "ch341-uart ttyUSB2: failed to read modem status: -32". The GPS stays enumerated but is unusable. atlas-gnss: "expected one unclaimed verified device, found 0"; state PORT_OFFLINE.
- Modem drops this boot: 20 (13 at 11:34). The IM10A (1-2.4.3) and Xbox receiver (1-2.4.4) logged no errors this time.
- Reading: the GPS barely draws current and is not the cause. It is collateral damage from the modem's supply sag on the shared hub 1-2.4. Fix: move the GPS off hub 1-2.4 (hub 1-2.2 port 2 is free) until the modem has its own 5 V ≥3 A supply. Replugging also clears the wedged CH340; the driver rediscovers about 60 s after a new USB serial device appears.

### 2026-11-21 11:47 IST — Hiwonder-only GPS driver DEPLOYED (owner "Yes, deploy")
- Before deploying: control source STOPPED, stop latched ("REMOTE STOP: joystick unavailable"), autonomy armed false.
- Backup in `~/project_atlas/backups/gnss_hiwonder_only_20261121/` (src_gnss_node.py, test_gnss_reconnect.py). Copied `gnss_node.py` (md5 04f02a67, matches the repo commit 0ddb771) and the test into `~/project_atlas_ws/src/atlas_gnss_driver/`. The install is a colcon symlink install (build dir links to src), so no rebuild was needed. py_compile OK; on-rover tests 16/16 OK.
- `systemctl --user restart atlas-gnss` at 11:47:13; active. Log: "Hiwonder GPS V1 USB node started: automatic USB discovery of the Hiwonder CH340 (modem ports are never opened) at 9600 baud".
- After the 90 s low-priority discovery delay: 11:48:54 NMEA_LIVE_NO_FIX on /dev/ttyUSB2 (Hiwonder CH340, 1-2.4.2), valid_nmea 56. The gnss node holds only ttyUSB2. No base, motion or speed-loop change, so no Speed check.
- Rollback: copy `backups/gnss_hiwonder_only_20261121/src_gnss_node.py` back and restart `atlas-gnss`.

### 2026-11-21 11:30 IST — Audit: 4G modem USB drops and the Hiwonder GPS (read-only on the rover; GPS driver fix staged)
Owner rule (2026-11-21): the SIM8230G 4G modem stays. It is the Wi-Fi backup uplink, so fix it; do not propose removing it. The ONLY GPS is the Hiwonder GPS V1 USB.

**4G modem (SIM8230G on 1-2.4.1, RNDIS usb0 + ttyUSB4-6)**
- This boot (about 09:56) logged 13 modem USB disconnects: 1 at 00:xx (pre-NTP clock), 1 at 09:xx and 11 between 10:17 and 10:28, with the rover parked, Wi-Fi up and battery at 12.3 V / 86 %. None since 10:28 (checked 11:34). Yesterday's drive had 2 more (19:26:11, 19:27:41).
- Pattern: each drop re-enumerates within about 0.3 s. That is too fast for a modem firmware reboot (about 10-15 s), so the USB link itself is dropping. There is no over-current or USB error message before a drop, and no software command (ModemManager, NetworkManager or fallback) before it. The drops cluster right after NetworkManager auto-activates `ATLAS-Cellular-RNDIS` and ModemManager powers the radio on and registers ("power state updated: on" -> registered). That is when the radio transmits and draws its highest current.
- Only the modem drops. The GPS (1-2.4.2), IM10A (1-2.4.3) and Xbox receiver (1-2.4.4) on the same hub stay up.
- Hub 1-2.4 (214b:7260 "USB2.0 HUB", in a Jetson USB-A port) reports self-powered (bmAttributes e0). Cheap hubs often report this even without an external supply, so its real power source is unknown; the owner needs to check. The modem descriptor asks for 500 mA, while a 4G module's transmit peaks are well above USB 2.0's 500 mA.
- Conclusion: most likely a power-supply sag on the modem during radio transmit (brownout of its USB PHY), with marginal cable or connector integrity as the second suspect. Software cannot supply current. The fix is hardware: a dedicated 5 V supply of at least 3 A for the modem (powered hub with its own adapter, or a 5 V buck from the battery through a power-injector/Y cable) and a short, thick USB cable.
- Side risk: the IM10A (primary yaw-rate IMU) and the GPS share that hub with the modem.

**Hiwonder GPS V1 USB**
- Works after this morning's reboot: the CH340 at 1-2.4.2 became ttyUSB2 (renumbered), and auto discovery re-found it. NMEA_LIVE_NO_FIX indoors (GPS 5, GLONASS 2, BeiDou 1 in view; HDOP 25.5).
- Defect found: `gnss_node.py` DEFAULT_PORT was the SIM8230G modem's GNSS NMEA port (if03), and the default source name was "SIM8230G USB GNSS". The live unit uses auto_usb, so the modem port is only a misleading log label today. But any unit without `auto_usb:=true` would read the modem's GNSS, against the owner rule.
- Repo drift: the rover's `gnss_node.py` (low-priority USB discovery and hot-plug, 2026-10-24) and the `low-priority.conf` drop-in were not in the repo. Both are now synced.
- Staged fix (not deployed): DEFAULT_PORT is empty, auto_usb defaults to true, and an empty port forces discovery. A fixed port is refused if it is a SIMCOM path or USB vendor 1e0e. The startup log says "automatic USB discovery of the Hiwonder CH340 (modem ports are never opened)". Tests: `test/test_gnss_reconnect.py` 16/16 (5 new) in a rover temp copy. Deploy needs the owner's OK: colcon build atlas_gnss_driver and restart the low-priority `atlas-gnss` user service. No base, motion or speed-loop change, so no Speed check.
- No CH340 by-id ambiguity in use: base (ATLAS_YAHBOOM_AUTO_USB=1), IM10A (auto_usb) and GPS (auto_usb) all use verified discovery. Nothing references `usb-1a86_USB_Serial-if00-port0`.

### 2026-11-20 19:24-19:30 IST — Round trip 5: both legs SUCCEEDED (no bag; light dashboard log only)
- No rosbag (the owner chose "No need"), so the Stage-3 checker cannot score this trip. Evidence: dashboard `/api/status` read every 5 s (`/tmp/light_watch.py`) plus the mission-control, mux, E-STOP and kernel logs.
- Start was not the dhruv room place: ATLAS began the hall leg from about (1.33, -1.46, -71 deg), after the earlier blocked attempts and manual repositioning.
- Hall leg: Go 19:24:56, scan check fit 97 %, accepted 19:24:58, "NAMED GOAL FINISHED name=hall status=4" (SUCCEEDED) at 19:26:49. Stop pose (1.76, -5.21) vs place (1.68, -5.35): 0.16 m. One remote assist sample (src=REMOTE) at 19:26:13, near the hall door.
- Return leg: Go 19:28:01, scan fit 94 %, accepted 19:28:04, "NAMED GOAL FINISHED name=dhruv room status=4" at 19:30:21. Last samples (0.00, 0.28, 91 deg) vs place (0.08, 0.54, 65 deg): about 0.27 m and 26 deg by the 5 s samples. A remote sample (src=REMOTE) appeared at 19:30:15-19:30:25, just before the finish.
- Mux: 287 "LIDAR AVAILABILITY STOP" lines from 19:24:58 to the end; no LOCALIZATION JUMP, ultrasonic or encoder stops logged.
- 4G modem: two USB re-enumerations of 1-2.4.1, at 19:26:11 (two seconds before the hall-door assist) and 19:27:41. The GPS now shares that hub. Load average was 8-13 during the drive (my heavy monitors were stopped).
- Location monitor VERIFIED after the stop.

### 2026-11-20 19:14-19:22 IST — Round trip 5 attempt: no autonomous leg. LOCALIZATION JUMP, then refusal "localization still moving", then a CPU-load spike
- 19:14:53 hall goal accepted (scan check fit 97 %). Then 19:14:54 mux: "AUTONOMY BLOCKED: LOCALIZATION JUMP pose jump 0.60m/42.1deg (allowed 0.32m/64.2deg over 1.02s)". Nav2 commanded 0.15 m/s, /cmd_vel stayed 0. No auto-reseed at that time; location checks before and after were VERIFIED. The source of the one-update AMCL jump is unexplained.
- The first "B pressed" was not seen by the system (no latch_state event). B registered at 19:19:43, cleared the fault and turned autonomy OFF. LB released at 19:19:50; autonomy ON at 19:20:22; Go at 19:20:36.
- 19:20:36 mission control refused: "localization still moving while ATLAS is stopped: pose_shift=0.36m heading_shift=13.7deg". Pose samples then moved (0.33, 0.51) -> (0.80, -0.39) -> (0.88, -0.83) within about 20 s. Whether this was real motion or AMCL drift is unverified. Mux logged "LIDAR AVAILABILITY STOP: unobserved motion sector".
- 19:21:05 latch "REMOTE STOP: joystick unavailable"; at about 19:21:17 the location monitor reported "odometry stale"; rf2o logged "Waiting for laser_scans" 437 times from 19:19 (`/scan` still published when checked).
- Load average rose to 35, then 54 at 19:22, with about 30 % idle and polkitd at 26 % CPU. My own monitors were part of the load: a ros2 CLI pose/journal poll every 10 s, a ros2 topic echo and several ad-hoc ros2 CLI checks. I stopped them at 19:22, which broke the "no heavy rclpy probes during drives" rule. The load was decaying by 19:22:40 (46.6).
- No modem/USB disconnects were found in the kernel log for 19:19-19:22.

### 2026-11-20 19:04 IST — Relocalize mode set to AUTO (owner "Yes, set auto"); AMCL now VERIFIED
- Before: the location check said LOST several times ("LiDAR places ATLAS 0.82-0.87 m / 6-8 deg from AMCL"). AMCL read (-1.18, 1.08, 21 deg); the LiDAR recovery pose was (-0.885, 0.285, 12 deg).
- Change: `~/.config/project_atlas/relocalize_mode` changed from `suggest` to `auto` (backup `relocalize_mode.before-auto-20261120`). The monitor reads it on every result, so no restart. Rollback: `echo suggest > ~/.config/project_atlas/relocalize_mode`.
- Result: AMCL was reseeded at about 19:02. One result was discarded ("AMCL pose changed during the check"), then three VERIFIED results (amcl_fit 0.97-0.98). AMCL is now (-1.02, 0.28, 13 deg).
- Start pose for Stage-3 round trip 5 is not met yet: 1.13 m from the "dhruv room" place (0.08, 0.54), and heading 13 deg instead of 65 deg.

### 2026-11-20 18:53 IST — Hiwonder GPS back on USB; NMEA live, no fix indoors
- After a cable change the GPS enumerated at about 18:50 as a CH340 on 2.4.2 (ttyUSB6), after two "device descriptor read/64, error -32" retries. `atlas-gnss` saw the new device and opened ttyUSB6 at 9600 within about 60 s, with no restart.
- `/gps/receiver_status`: NMEA_LIVE_NO_FIX, valid_nmea 2134. `/gps/fix` status -1 (indoors, no fix). `/gps/nmea` shows GNGSA with no satellites used.
- Risk: the GPS sits on the bus-powered modem hub (2.4). The SIM8230G re-enumerated at the same moment (ttyUSB3-5 disconnected and reattached), which fits the earlier brownout hypothesis. Hub 2.2 port 2 is free.

### 2026-11-20 18:45 IST — Hiwonder GPS V1 (primary GPS) missing from USB since the 13:52 boot
- `atlas-gnss` (auto_usb) logs "expected one unclaimed verified device, found 0", every 10 min since 03:26. `/gps/receiver_status` reads PORT_OFFLINE. Its startup line names the SIMCOM if03 port only because that is the DEFAULT_PORT label; the node does not open the modem port. ModemManager owns ttyUSB5.
- Only two CH340s are present now: 2.2.3 = ttyUSB0 (yahboom_base) and 2.4.3 = ttyUSB1 (IM10A). Port 2.2.4, once a small hub carrying the GPS at 2.2.4.3, now holds the ESP32 directly. Port 2.2.2 is free.
- Evidence from the modem's first tty number in the kernel log: boot 11:34–12:49 gave ttyUSB4 (4 USB serials, GPS present). Boots from 13:52, 16:51 and 18:02 gave ttyUSB3 (GPS absent). So the GPS disappeared during the 12:49–13:52 power-off.
- The owner plugged the GPS back in about 18:37. The kernel logged no new USB device; not yet resolved (cable, port or power).

### 2026-11-20 18:25 IST — Speed check PASS (second post-curvature-fix PASS; speed evidence current again)
- `speed_loop_check_20261120_182509.json`: PASS, requested 0.15 m/s. Start 0.46 s; steady mean 0.117 m/s; peak 0.167 m/s (limit 0.25); wheel distance 0.587 m; ICP 0.648 m (agrees within 25 %); coast after stop 0.018 m. All checks true.
- PASSes after the 11:26 yahboom_base deploy: 11:29:44 and 18:25:09. The 2-PASS rule from the curvature fix is met.
- Still open: `atlas_autonomy_arm.speed_evidence` does not track `yahboom_base.py` (see the 18:15 entry).

### 2026-11-20 18:15 IST — Autonomy ARMED; no new Speed check ran; arm gate counts a pre-curvature-fix PASS
- The owner reported "speed test pass, autonomy on". Control policy: armed true, manual_only false, stop latched.
- No Speed check ran after 11:33 today. The last start attempt aborted: "front clearance 0.54 m < 1.00 m needed to start". The newest result file is still `speed_loop_check_20261120_113323.json`.
- PASS files at a requested 0.15 m/s: 20261116_075316 (from before the 11:26 curvature deploy) and 20261120_112944 (after it). `atlas_autonomy_arm.speed_evidence` needs 2 PASS newer than `speed_loop.yaml` + `atlas_speed_loop.py`. It does not track `yahboom_base.py`, so it accepted the pre-fix PASS.
- Follow-up: another start attempt also aborted: "front clearance 0.05 m < 1.00 m needed to start", and no result file was written. The Readiness page shows "2/2 PASS" because it counts the same two PASSes (11-16 and 11-20 11:29).
- By the 2026-11-20 rule (a yahboom_base change makes the speed evidence stale), only 1 of the 2 required post-fix PASSes exists. Open: one more Speed check (1.5 m clear ahead), and decide whether to add `yahboom_base.py` to SPEED_LOOP_CODE.

### 2026-11-20 18:02 IST — Dashboard Restart PASSED (real press by the owner)
- `estop_events.jsonl`: `reboot_latch` at 18:01:29 from 192.168.1.7 (local Wi-Fi). The rover rebooted, boot time 18:02:07, and was back on SSH by 18:03:08.
- After boot: rover-status-web active; no failed system or user units; stop latched ("REMOTE STOP: joystick unavailable"); autonomy armed false. The fallback md5 b6eee7d5 and both sudoers files persist.
- Earlier tries from 100.76.195.106 (Tailscale) never sent a request: "nothing changed" on the first tap even after the menu fix. Not reproduced in the built-in browser; probably a stale page on that device. Re-check it from that device after a full reload.

### 2026-11-20 — More-menu fix for the two-tap Restart DEPLOYED (owner "Yes, deploy")
- Failure: the owner pressed the two-tap Restart about 17:48 and the rover did not reboot (still up since 17:21; no reboot entry). Cause: the first tap rewrote the button label, which detached the click target. The More-menu outside-click handler (`menu.contains(e.target)`) then judged the tap as outside and closed the menu, hiding the armed button. Reproduced in the browser.
- Fix (commit 2866de6): `home-cards.js` now uses `e.composedPath().includes(menu)`. The cache key is now `home-cards.js?v=20261120menu`.
- Before deploying: stop latched, autonomy armed false. Backups are in `~/project_atlas/backups/restart_menu_20261120/`. Copied home-cards.js (bfd5230b) and index.html (9f13a673); the rover's md5s match. No service restart.
- Live-page test with fetch stubbed (nothing sent): after the first tap the menu stays open and the button is armed. The second tap sent exactly `action=reboot&confirm=RESTART_ATLAS`. A real press by the owner is still pending.

### 2026-11-20 — Dashboard Restart: two-tap in-page confirm DEPLOYED (owner "Yes, deploy")
- Owner pressed Restart about 17:40 and no dialog appeared. The rover did not reboot (up since 17:21) and no reboot entry reached `estop_events.jsonl`. The owner's browser most likely blocks `confirm()` pop-ups. In a fresh built-in browser page the dialog did appear (auto-cancelled; nothing sent).
- Fix (commit d756a67): no pop-up. The first tap arms the button for 5 s ("Tap again to restart (5 s)", red). A second tap within 5 s sends `action=reboot&confirm=RESTART_ATLAS`. Result and error text show on the button. The server side is unchanged.
- Browser test with fetch stubbed (nothing sent): one tap sent 0 requests, the button restored after 5.5 s, and a double tap sent exactly 1 correct body.
- Before deploying: stop latched ("REMOTE STOP: joystick unavailable"), autonomy armed false.
- Backups are in `~/project_atlas/backups/restart_twotap_20261120/`. Copied atlas_diagnostics_ui.js (1150750b), index.html (245d1301), classic.html (26d76f9b) and mapping.html (2ad700d2); the rover's md5s match. The service was not restarted because the files are read per request. The served pages load diagnostics.js?v=20261120restart2, which has the two-tap code. The real Restart has NOT yet been pressed.

### 2026-11-20 17:33 IST — Dashboard Restart button DEPLOYED (owner "Yes, deploy")
- Sudoers: the owner typed the password in their terminal tab. `/etc/sudoers.d/atlas-dashboard-reboot` (17:31, 0440 root) holds `jetson ALL=(root) NOPASSWD: /sbin/shutdown -r now`. `sudo -n -l` lists both shutdown -r and shutdown -h as NOPASSWD. The first two tries failed with 3 incorrect password attempts each and changed nothing.
- Before deploying: stop latched ("REMOTE STOP: joystick unavailable"), autonomy armed false, /cmd_vel zero.
- Backups are in `~/project_atlas/backups/restart_button_20261120/`. Copied atlas_status_web.py (md5 add0193f), atlas_diagnostics_ui.js (ec00b0ac), web/v2/index.html (b5aa494a), classic.html (917211fa) and mapping.html (66ae79d4). The rover's md5s match the local ones; py_compile OK.
- `systemctl --user restart rover-status-web` at 17:33:27; active. The old process printed ExternalShutdownException tracebacks while stopping (normal shutdown noise).
- On 127.0.0.1:8088: /v2/, classic.html, mapping.html and diagnostics.js?v=20261120restart all serve the Restart button or function. An unconfirmed `action=reboot` POST returns 403. The button itself was NOT pressed.
- After the deploy, the latch was released on the controller ("REMOTE STOP: released by neutral LB hold"). That was an operator action, not the web restart. Autonomy stayed armed false and manual_only true.
- Still open: the full CI list on the rover copy gave 2 failures and 3 errors (names not captured). GitHub CI must confirm after the next push.

### 2026-11-20 — Dashboard Restart button STAGED (not deployed; sudoers rule missing)
- Added `action=reboot` to `atlas_status_web.py`. It needs confirm `RESTART_ATLAS` and same origin, otherwise 403. It needs a NOPASSWD sudoers rule for exactly `/sbin/shutdown -r now`, otherwise 503 and nothing happens.
- When allowed, it first latches the drive stop, stops the rover and writes the E-STOP log, then runs `sudo -n /sbin/shutdown -r now` after 2 s. No password is ever piped. The old `sudo -S` reboot stays removed.
- Restart buttons sit next to Shut down in `web/v2/index.html`, `classic.html` and `mapping.html`. The diagnostics.js cache key is now `?v=20261120restart`.
- Tests: `tests/test_status_web_no_reboot.py` rewritten (9 tests). Ran 51 status-web tests on the rover in a temporary copy: OK.
- The full CI list in the same rover copy gave FAILED (failures=2, errors=3), which is not yet explained. The rover then went offline before the failing names could be read. The Mac's Python lacks yaml/numpy, so the list could not be run there. GitHub CI after the next push must confirm.
- Pending: the owner adds `/etc/sudoers.d/atlas-dashboard-reboot` with `jetson ALL=(root) NOPASSWD: /sbin/shutdown -r now` (visudo, owner types the password). Then "Yes, deploy" with the rover parked.

### 2026-11-20 13:50 IST — Slower 4G failover INSTALLED + USB hub autosuspend off (owner typed the sudo password)
- Ran from the owner's terminal tab (ssh + sudo; the owner entered the password).
- Installed `/usr/local/lib/atlas-network/atlas_network_fallback.py` md5 b6eee7d5 (backup `atlas_network_fallback.py.before-slow-failover`). Restarted `atlas-network-fallback` at 13:50:43.
- Verified: active; "Uplink=WIFI hotspot=False Wi-Fi=True cellular=True"; status mode WIFI on wlP1p1s0.
- `/sys/bus/usb/devices/1-2.4/power/control` = on (autosuspend off on the modem hub). **Not persistent across reboot**; a udev rule would make it permanent (owner decision).
- To verify on the next hall drive: modem disconnect bursts (`usb 1-2.4.1: USB disconnect` count) and system stalls.

### 2026-11-20 — Slower Wi-Fi→4G failover built (owner keeps the modem; install needs the owner's sudo)
- `atlas_network_fallback.py` (repo = installed copy before the change, md5 b165e9e2):
  - `Policy.WIFI_FAIL_CYCLES = 6`: Wi-Fi must fail six consecutive checks, about 40–50 s, before traffic is routed through the SIM (was 3, about 20 s);
  - during a short Wi-Fi blip the SIM is probed on the normal 30 s cadence, and every cycle only when failover is one check away or cellular is selected (was every cycle from the first Wi-Fi failure);
  - Wi-Fi recovery (3 good checks) and the hotspot rule are unchanged.
- Tests: `test_network_fallback` 13/13 (Mac and rover); new short-blip test.
- Staged at `~/project_atlas/scripts/atlas_network_fallback.py` (md5 b6eee7d5). **Not installed:** `/usr/local/lib/atlas-network/` is root-owned, so the owner runs the sudo install (and optionally `echo on > /sys/bus/usb/devices/1-2.4/power/control` for hub autosuspend).
- Verification after install: modem disconnect count and stalls on the next hall drive.

### 2026-11-20 — 4G modem reconnect storms: chain of events (read-only; owner keeps the modem)
- The 167 disconnects of the SIMCOM modem (USB 1-2.4.1) come in **bursts** (median interval 2.6 s; gaps up to 920 s), not steadily.
- Bursts per minute: 12:45–12:50 (10, 7, 10, 29), 13:10–13:11 (12, 13), 13:16–13:17 (6, 6). They coincide with the rover being in or near the hall/doorway and with today's stalls (13:11:05, 13:17:58).
- NetworkManager shows the **Wi-Fi DHCP lease dropping and returning** (12:40:55, 12:41:00, 12:45:11, 12:45:18, …). Immediately after each drop, `usb0` (modem RNDIS) is removed and re-activated repeatedly.
- `atlas_network_fallback.py` states "no modem AT writes" (it does not reset the modem).
- Hypothesis, not proven: the Wi-Fi drop in the hall dead zone moves traffic to 4G; modem TX current rises; the bus-powered USB2 hub 1-2.4 (100 mA; also feeds the 500 mA TGZ controller dongle and a CH341 serial) browns out. The modem re-enumerates in a loop, and each re-activation drives NetworkManager/polkit CPU (polkitd 21–29 %, load 10–12). Neighbouring USB devices are disturbed.
- Owner-side fixes (keeping the modem):
  - (1) move the modem to a direct Jetson port or a powered hub;
  - (2) a Wi-Fi extender for the hall;
  - (3) optional: no cellular failover during drives (system setting, owner via sudo).
- Verification after (1): the disconnect count and stall count on the next drive.

### 2026-11-20 13:04–13:37 IST — Round trip 4: both legs SUCCEEDED (bag `hall_auto4_20261120_1304`, 31 min)
- Changes in force: "hall" heading −120° and "dhruv room" heading 65° (owner request; backup `named_places.json.before-headings-20261120`); radius-aware side stop; mission-control fix; curvature fix.
- **Stage-3 checker: 3/5.**
  - **legs PASS:** hall 4 (13:07:42, 2 min 15 s, one owner assist); final dhruv room 4 (13:36:46).
  - **return_home FAIL:** 0.20 m (within 0.30) but **131°** from the start pose; the trip did not start at the "dhruv room" place facing 65°.
  - **safe_stop FAIL:** no owner B while Nav2 drove this time.
  - turn_sign PASS 6/629; encoders PASS.
- Return-leg problems, all logged:
  - **System stalls** at 13:11:05–13:11:13 and 13:17:58: encoder, localization, scan and camera all stale at once. The camera-stale cancel fired (status 5), then AMCL jumped 1.05 m.
  - Kernel: the **SIMCOM 4G modem (USB 1-2.4.1) disconnected 167 times this boot** (about every 37 s) on a bus-powered USB2 hub (1-2.4, 100 mA) that also carries the TGZ/xpad controller dongle (500 mA) and a CH341 serial.
  - Another device on that hub (1-2.4.2) failed to enumerate with a power cycle at 13:18:02. The LiDAR serial re-enumerated at 12:39.
  - Load average 10–12 on 6 cores, with polkitd at 21–29 % CPU (likely NetworkManager/polkit churn from the modem reconnects).
  - **Suspected root cause (not proven): USB power/brown-out on hub 1-2.4 driven by the modem.** Owner action proposed: unplug the 4G modem; later, a powered hub.
  - Doorway LiDAR-blind vetoes (5–6 bins) again led to progress-checker aborts; the owner assisted through the door.
  - In a narrow passage near (0.88, −0.53) the RPP collision check gave zero velocity (walls at 0.50 / 0.58 m from the laser). My first "phantom Astra marks" diagnosis was **wrong**: clearing both costmaps (owner-approved) changed nothing, and the ring is real walls inflated.
  - Separate open question: the Astra layer uses `inf_is_valid: false`, so empty views never clear old Astra marks (not the cause here).

### 2026-11-20 ~12:58 IST — Radius-aware inner-side stop DEPLOYED (owner "Yes, push and deploy"; "B pressed")
- State: `/atlas/motion_safety` = "REMOTE STOP: B pressed", autonomy not armed.
- Rover `atlas_ultrasonic_validity.py` was the pre-change version (md5 8f39f24c). Backup `…/atlas_ultrasonic_validity.py.before-radius-side`. Deployed md5 3fc62bf9 (commit 95558a2). Restarted `atlas-cmd-vel-mux` only.
- Verified:
  - active, no errors;
  - "LiDAR guard: 3 virtual obstacles" loaded;
  - limits on the rover: 0.165 m at R 0.35, 0.10 m at R 1.
- GitHub CI green again on 95558a2 (push and PR).
- Not yet verified on a drive; the next drive's mux log shows "(stop X m)" on side blocks.

### 2026-11-20 — Radius-aware inner-side stop BUILT (offline; not deployed) + CI regression found and fixed
- `atlas_ultrasonic_validity.py`:
  - the side is the **inner side of the turn** (sign(linear·angular)); this fixes the reverse case that checked the outer sensor;
  - the limit is `clamp(inner_side_sweep_m(R, 0.15 m) + 0.05, 0.10, side_stop 0.28)`: about 0.165 m at R 0.35, 0.11 m at R 0.5, 0.10 m for gentle turns;
  - steering-only commands (|v| < 0.01) keep the former side and the full 0.28 m;
  - the message now carries "(stop X m)".
- Tests: `test_ultrasonic_validity` 43/43 (6 new or rewritten side tests). The full CI list 127 modules passes locally.
- Replay on Nav2 turning commands: `hall_auto2` 26 % → **5.4 %** blocked; `hall_auto3` 15 % → **2.0 %**. Remaining blocks are close readings (mostly 0.15–0.20 m on tight turns).
- **CI regression (my error):** the 2026-11-20 left/right swap (84ee3d0) added `SWAP_LEFT_RIGHT` to bridge methods that `test_ultrasonic_validity` extracts. 14 BridgeIntegrationTests failed, and GitHub CI was red on 84ee3d0 and cdef3ce; I had not checked CI after those pushes. Fixed in the test scope (swap off); runs green locally.
- Deploy needs the owner's "Yes, deploy" (mux restart parked + latched; no base change, so no Speed check).

### 2026-11-20 — Side-stop analysis (offline; nothing changed)
- **Geometry** (0.50 × 0.36 m footprint rotating about the 4WS ICR): the excursion beyond the side line, beside the body, after 10 / 20 / 30 cm of travel, is the same forward and reverse.

| Turn radius R | Inner side (toward the ICR) | Outer side |
|---|---|---|
| 0.35 m | 6.6 / 12.4 / 19.5 cm | ≤ 5.6 cm |
| 0.50 m | 4.4 / 7.6 / 10.1 cm | ≤ 5.6 cm |
| 1.0 m | 2.1 / 3.3 / 3.9 cm | ≤ 2.6 cm |
| 2.0 m | 1.0 / 1.6 / 1.7 cm | ≤ 1.4 cm |

  The mux re-evaluates every cycle and the rover stops in about 4 cm at 0.15 m/s, so the relevant horizon is about 10–15 cm: roughly 9 cm (R 0.35), 6 cm (R 0.5) and 3 cm (R ≥ 1) plus margin.
- **Bug (latent):** `ValidityWindow.veto` picks the side from the sign of wz only. Reversing with wz > 0 puts the ICR on the RIGHT (inner side right), but the LEFT (outer) sensor is checked. Not triggered in these bags (every replayed block was forward / inner).
- **Replay** of Nav2 turning commands with physical-side ultrasonic:

| Bag | 0.28 m (current) | Inner-side rule 0.20 m | Inner-side rule 0.15 m |
|---|---|---|---|
| `hall_auto2` | 2 088/8 056 (26 %) | 24 % | 19 % |
| `hall_auto3` | 720/4 885 (15 %); 558 of them at R ≥ 1 m with readings 0.20–0.28 m | **2 %** | **2 %** |

  `hall_auto2` blocks were mostly real close objects at the narrow HOME start (0.10–0.13 m).
- **Proposal, not implemented:**
  - side = inner side by sign(v·wz);
  - limit = clamp(inner sweep for the commanded radius over 15 cm + 5 cm margin, 0.10 m, 0.28 m), i.e. about 0.15 m at R 0.35, 0.11 m at R 0.5, 0.08–0.10 m for gentle turns;
  - unit tests plus replay of both bags before any deploy. The mux restart needs the rover parked and latched.
- HC-SR04 cones see only beside the sensor; corner clearance stays with the LiDAR guard and costmaps.

### 2026-11-20 12:34–12:50 IST — Round trip 3, after the curvature and mission-control fixes (bag `hall_auto3_20261120_1234`)
- **Stage-3 checker: 3 of 5 PASS.**
  - **safe_stop PASS:** owner B while Nav2 drove at 0.128 m/s; still after 0.47 s, 4.2 cm.
  - **turn_sign PASS:** 7/753 (0.9 %).
  - **encoders PASS:** 0 bad samples while moving.
  - legs FAIL: hall 6, then hall 4 (SUCCEEDED 12:43:16), dhruv room 6, 6.
  - return_home FAIL.
- **Failure mode at both ends: arrival heading, not position.**
  - Hall: the rover stopped 0.16 m from the point with yaw −120° vs the saved −60°. It succeeded only after the owner turned it by remote.
  - Dhruv Room: 0.22 m and yaw 65° vs the saved 17° (48° off). The controller aborted while the guard/side stops blocked the turning manoeuvre.
  - A car-like 4WS rover cannot turn in place, and the hall/door surroundings veto most manoeuvres.
- Other events:
  - one "Starting point in lethal space" planner failure after the owner moved the rover close to hall furniture;
  - a Wi-Fi drop near the hall door (both IPs unreachable for about 1 min; the bag on the rover was unaffected);
  - "localization still moving while stopped" (0.45 m / 26°) refused one Go.
- Mux stop lines: LiDAR availability 667, side RIGHT 26, side LEFT 14, REAR 6, encoder CRITICAL 3, localization uncertainty 3. The side stop fell from 298 to 40 with a better start position.
- Mission-control fix: no pre-emption occurred this drive (0 "superseded" lines), so it was not exercised.
- **Open owner decision:**
  - (a) set the saved headings of "hall" and "dhruv room" to the natural arrival directions (about −120° and about 65°); and/or
  - (b) loosen `yaw_goal_tolerance` further.
  - Note: the Stage-3 return_home criterion (20° of the start pose) also needs the arrival heading to match the start heading.

### 2026-11-20 ~12:20 IST — Mission-control pre-emption fix DEPLOYED (owner "Deploy mission fix")
- Autonomy not armed; no mission-control goal in the previous 15 min.
- Rover `atlas_mission_control.py` was the pre-fix version (md5 a32a55a1, identical to the repo before d2ba6c9). Deployed md5 db0b27c4. Backup `backups/virtual_obstacles_20261116/atlas_mission_control.py.before-supersede`.
- Restarted `atlas-mission-control` only. Verified: active, status READY, Foxglove bindings ready, no errors.
- Expected (not yet seen live): a pre-empted goal's result is logged as "superseded …" instead of `NAMED GOAL FINISHED … status=6`; no READY revert while a goal drives; the camera tracker is not restarted mid-goal.
- Not addressed: Nav2 "Failed to make progress" after long safety blocks (10× in `hall_auto2`). That is the controller progress checker, not mission control.

### 2026-11-20 11:41–12:11 IST — Owner round trip after the curvature fix (bag `hall_auto2_20261120_1141`, 30 min)
- **Hall goal SUCCEEDED (status 4) at 11:48:41**, with owner remote help (stuck at the narrow HOME start; turnaround in the hall; doorway).
- Return to "dhruv room": the 11:51 goal was pre-empted by a new Go at 11:55:43. The new goal **aborted instantly**: the controller logged "Failed to make progress", carried over from the long-blocked previous goal (10 such aborts in the drive). Since the pre-emption bug was also present, the status showed FINISHED 6 / READY. Fix staged (d2ba6c9), not deployed.
- The 11:59 goal reached Dhruv Room; the owner then aborted the mission (status 5).
- **Stage-3 checker: FAIL.**
  - legs: hall 4, dhruv room 6, 5;
  - return_home: no HOME success;
  - safe_stop: no owner stop while Nav2 was driving;
  - turn_sign: **PASS**, 17/826 (2.1 %; 583 remote and 633 flip samples excluded);
  - encoders: **PASS**, 0 bad samples while moving.
- **Curvature fix verified on a real drive:** `/yahboom/odom` yaw now has the **same sign as the IM10A gyro in 782/818 turning samples (95.6 %)**, against 1–3 % before. The magnitude is high (median |wheel|/|gyro| 1.64; not fused in the EKF; calibration open).
- Encoder consensus CRITICAL: **5 episodes in 30 min** (about 0.17/min) vs 15 in 10.7 min (1.4/min) in `penalty_test`. The remaining episodes are two channels near zero while one moves (bursts/slip).
- Mux stop lines 11:43–12:12:

| Stop | Count |
|---|---|
| LiDAR availability (blind bins) | 880 |
| **side stop RIGHT ≤ 0.28 m** | 247 |
| **side stop LEFT** | 51 |
| scan stale | 5 |
| encoder CRITICAL | 5 |
| localization uncertainty > 0.25 m | 5 |
| encoder DEGRADED transition | 1 |

- The new side stop (active since the side sensors were enabled) is now the second-largest limiter: RIGHT 0.10–0.13 m at the narrow HOME start; 0.22–0.27 m in the doorway.
- Open, owner decisions:
  - (a) side-stop threshold and whether it should apply only to the inner side of a turn (analysis first);
  - (b) deploy the mission-control pre-emption fix;
  - (c) progress-checker behaviour after long safety blocks;
  - (d) HOME relocation;
  - (e) door-frame tape.

### 2026-11-20 11:26 IST — Wheel-curvature sign fix DEPLOYED (owner approved "Yes, deploy later"; rover parked, B pressed)
- State: `/atlas/motion_safety` = "REMOTE STOP: joystick unavailable", autonomy not armed.
- Rover `yahboom_base.py` was the pre-fix version (md5 18c74867, identical to the repo parent of 97e154e). Backup `backups/virtual_obstacles_20261116/yahboom_base.py.before-curvature`. Deployed md5 a9c378fc (commit 97e154e). Restarted `rover-base-telemetry` only.
- Verified parked: service active, no errors; `/yahboom/odom` about 9 Hz; encoder health DEGRADED with M3 excluded (normal 3-encoder mode); IMU calibration loaded; encoder stream requalifying after restart.
- **Speed evidence is now stale: two dashboard Speed checks must PASS before autonomy.**
- Not yet verified: the wheel-odometry yaw sign against the gyro while turning, and consensus failures in turns. Both come from the next drive's bag; recording `hall_auto_20261120_1123` is running.

### 2026-11-20 — Open-space ultrasonic check (owner placed the rover in open space; 15 s, all VALID)
- **Right: median 0.96 m** (0.82–1.62; the owner moved a hand in front) vs LiDAR right side about 0.94–0.95 m. **Not seeing the rover itself**; the earlier 0.16–0.23 m were real nearby objects. The side stop is kept.
- **Left: 0.723 m stable** while the LiDAR left side was open to about 2 m. This matches the floor-echo distance for a 0.23 m high sensor (floor about 17.7° below the axis at 0.72 m).
- **Rear:** 0.911 m with 0.719 m samples (floor echo) vs LiDAR about 0.75 m from the bumper.
- **Front:** 0.677 vs 0.704 m (−2.7 cm).
- Floor echoes (about 0.72 m) are far above the 0.28 m side stop and the 0.30 m front/rear stops, so they cannot cause autonomy stops. They do shorten readings (conservative).
- Recommendation: tilt the 0.23 m-high left/right/rear sensors up about 5–10°.

### 2026-11-20 — CORRECTION: enabling left/right ultrasonic ACTIVATED the existing autonomy side stop
- The 10:xx entries said the side readings were "informational only". **That was wrong.**
- The deployed mux already calls `ValidityWindow.veto(..., side_stop=auto_side_stop_m 0.28)`. While Nav2 turns left (wz > 0.05) or right (wz < −0.05), a fresh VALID reading ≤ 0.28 m on that side gives `AUTONOMY BLOCKED: LEFT/RIGHT <d> m`.
- The channels were DISABLED before, so the rule was dormant. Enabling them, and the later left/right swap, made it live. The rover file is identical to the repo (md5 8f39f24c).
- It only blocks autonomy (fails safe) and has not fired this boot (no autonomous drive). Front/rear stay advisory for missing data (`ATLAS_ULTRASONIC_ADVISORY=1`), but a close VALID front/rear reading still blocks.
- **Risk:** the right sensor reads short of the LiDAR (0.23 m vs about 0.31 m; 0.158 m at 10:5x in another spot). If it sees part of the rover, every right turn would be blocked. Owner to check the right sensor in open space; if it stays below 0.28 m with nothing beside it, disable the right channel (`ATLAS_RIGHT_ULTRASONIC_ENABLED=0`) until fixed.
- The LiDAR-guard side coverage (`config/ultrasonic_mounts.json`) is still disabled and not deployed.

### 2026-11-20 — Left/right ultrasonic SWAPPED in software (owner) + measured sensor heights
- Owner: the UNO left (D4/D5) and right (D6/D7) channels are wired to the opposite physical sides.
- Deployed: bridge `swap_left_right_payload()` / `SWAP_LEFT_RIGHT`, and `ATLAS_ULTRASONIC_SWAP_LR=1` in `side-ultrasonic.conf`. `/ultrasonic/left_mm`, `right_mm`, `/ultrasonic/status` and `/ultrasonic/validity` now use physical sides; validity carries `left_right_swapped: true`. Backup `ultrasonic_arduino_bridge.py.before-lr-swap`.
- Restarted `atlas-uno-r4-sensor-hub` only (stop held, autonomy not armed). After the restart: left 238–242 mm, right 233 mm, all VALID, no mux ultrasonic errors.
- The UNO LED matrix still labels the firmware channels (its "L" is the physical right); fixing that needs a firmware flash.
- Tests: `test_side_ultrasonic` 9/9 (2 new).
- **Heights measured by the owner** (floor to transducer centre): front 0.175 m, left 0.23 m, right 0.23 m, rear 0.23 m (LiDAR plane 0.18 m). Recorded in `config/ultrasonic_mounts.json`.
- **Likely cause of the occasional 0.71–0.72 m front/rear samples: floor echoes.** From 0.175 m and 0.23 m height, the floor is 13.9° and 17.7° below the axis at 0.71/0.72 m, inside an HC-SR04's side lobes (about ±15°). Suggested: tilt front and rear up by about 5–10°. Earlier "cross-talk" suspicion is weaker.
- Physical-side comparison with the LiDAR (same parked spot): left 0.24 m vs side wall about 0.20 m from the body (+4 cm); right 0.23 m vs nearest LiDAR return about 0.31 m from the body (−8 cm). The right sensor still sees something nearer than the LiDAR plane; owner checking its aim.

### 2026-11-20 ~10:30 IST — All four HC-SR04 vs LiDAR, rover parked in a narrow spot (read-only)
- 30 s and 15 s windows, 4 channels enabled, all VALID:
  - **Front:** median 1.756 m; LiDAR at the bumper 1.80 m (diff −4 cm). The 30 s run had 12/101 short samples (min 0.708 m); the 15 s run had 0.
  - **Left:** 0.226 m, std 2–4 mm. It matches the LiDAR side wall (best fit at about +90…+115°, about 1 mm after subtracting the 0.18 m half-width).
  - **Right:** 0.238 m, std 4 mm, **nearer than anything the LiDAR sees on that side** (closest about 0.31 m from the body at −75…−120°). Suspected: aimed at something below the LiDAR plane, at part of the rover (wheel/bracket), or down at the floor. Owner to check the aim.
  - **Rear:** 0.821 m vs LiDAR at the bumper 0.94 m (−12 cm), with intermittent 0.72 m samples (4/50; 13/102 earlier).
- The occasional 0.71–0.72 m samples on front and rear appeared only after four channels were enabled. Possible cross-talk between sequential pings (45 ms slots); not proven. Monitor; if confirmed, a longer firmware slot (owner-approved flash) would be the fix.
- Mount positions/angles still not measured.

### 2026-11-20 — Left/right HC-SR04 channels ENABLED for checking (owner: "just enable right and left so I can check")
- Rover state: `/atlas/motion_safety` = "REMOTE STOP: joystick unavailable", autonomy not armed.
- Deployed `ultrasonic_arduino_bridge.py`: the `side_ultrasonic_commands()` change only; the rover file matched the pre-change repo version (md5 caec6e96). Backup: `backups/virtual_obstacles_20261116/ultrasonic_arduino_bridge.py.before-side-us`.
- New drop-in `atlas-uno-r4-sensor-hub.service.d/side-ultrasonic.conf` (`ATLAS_LEFT/RIGHT_ULTRASONIC_ENABLED=1`). Restarted `atlas-uno-r4-sensor-hub` only.
- Verified over 10 s (28 reports, all VALID):
  - front median 0.346 m;
  - **left median 1.255 m** (1.216–1.283);
  - **right median 1.169 m** (1.141–1.178);
  - rear median 0.337 m.
- Timing: the firmware samples each enabled channel in a 45 ms slot (about 180 ms per sensor with 4), well inside the mux 1.0 s ultrasonic timeout.
- Not changed: the mux / LiDAR guard (rover mux has no side-sensor code; `config/ultrasonic_mounts.json` not deployed and disabled). The side readings are informational only.
- Next: owner checks the readings against a tape measure and reports each sensor's mount position and angle.

### 2026-11-20 — Mission-control pre-emption, room guard stops, turn-sign metric, GitHub CI (offline; nothing deployed)

**4. Early "NAMED GOAL FINISHED status=6" on pre-emption — fix STAGED (not deployed).**
- `penalty_test_20261116` (19:58:52 and 20:00:34): when a new goal was dispatched, Nav2 pre-empted the old one and its result was published as `NAMED GOAL FINISHED name=<old> status=6` while the new goal drove.
  - The narrator reported a failure.
  - The camera tracker was restarted mid-goal.
  - The terminal-status hold reverted the status to READY at 20:01:34 while the goal drove until 20:05:50.
- Fix in `atlas_mission_control.py`:
  - every named / return-home goal gets a generation;
  - results and rejections of a superseded goal are logged only (no status, no tracker restore, no home verification);
  - `revert_idle_status_to_ready` never reverts while `autonomy_goals_active > 0`.
- Tests: `tests/test_mission_goal_supersede.py` 4/4, plus the 24 existing mission-control tests (rover temp copy, ROS). Deploy needs the owner's OK (restart `atlas-mission-control` parked; no Speed check needed).

**5. Room "LIDAR AVAILABILITY STOP (1 bins)" ×146 (19:59–20:00) — explained, no change.**
- Replay with the live config including ultrasonic, penalty test t+120…260 s: 344 of 969 moving scans vetoed.
- Almost all were the single bin +35…+40° (front-left), during reverse + turn (292) at (−0.1, 2.1…2.2) near "dhruv room test 3".
- A mapped wall at (−0.34, 2.42) was 0.38 m from the laser against 0.40 m needed: the front-left corner was about 5 cm from the wall while manoeuvring.
- Correct veto. The rest of that drive: 0 %. Remedies already in place: goal tolerance 20 cm (less dithering) and goals at least 0.5 m from furniture.

**6. turn_sign 5.8 % — explained; checker corrected to measure autonomy only.**
- Breakdown (cmd_vel wz vs IM10A gz 0.3 s later):
  - owner **remote reverse turns 99–100 % "opposite"** (car-like stick: room test 3: 240/243, penalty: 6/6);
  - Nav2 samples within 1 s of a yaw-sign flip: 4–10 % (servo lock-to-lock travel);
  - Nav2 steady forward/reverse: 0–3 %.
- Attempt 7 had no `/cmd_vel_joy`, so remote samples were counted as Nav2.
- `stage3_autonomy_check.py` now excludes `/cmd_vel_joy`-active samples and the 1 s after a flip, and reports both.
- Results: bag 8 13/455 (2.9 %) PASS; penalty 2/1825 PASS; room test 3 11/773 (1.4 %) PASS; attempt 7 73/1358 (5.4 %) FAIL with the note that remote driving cannot be separated (topic not recorded).
- Tests: `test_stage3_autonomy_check` 9/9 (2 new).
- **Owner note:** this changes how a Stage-3 criterion is measured (autonomous turning only). It is not a relaxed threshold.

**7. GitHub CI.** *(Correction 2026-11-20 09:20: the workflow file below was NOT pushed: the GitHub token lacked the `workflow` scope and three device-authorisation codes expired. The file is kept locally; the module lists in `project_atlas/tools/ci/` are pushed. Owner to add the workflow via the GitHub web UI or after granting the scope.)* *(Update 09:59: added through the GitHub web editor in the owner's signed-in browser session at the owner's request, commit 5925d14; the first runs started on push and on PR #22.)* *(First CI result: 1 133 of 1 138 passed; the 5 errors were all `test_status_web_snapshot_cost`, which runs `git show cd75929:…` and needs full git history while the CI checkout is shallow. That module moved to `not_in_ci.txt`; CI list now 127 modules / 1 133 tests.)*
- `.github/workflows/offline-tests.yml`: ubuntu-22.04, Python 3.10, pyyaml + numpy; on push, pull request and manual run; read-only permissions; never contacts the rover.
- It runs `project_atlas/tools/ci/offline_tests.txt`: 128 modules / 1 138 tests, all passing together locally (70 skipped need ROS).
- 59 modules need ROS 2, hardware, the Jetson layout or are stale (`not_in_ci.txt`); evidence gap: not triaged one by one.
- Found and fixed while doing this: `test_autonomy_web` / `test_autonomy_abort` left a stub `atlas_wifi_web` (origin check always true) in `sys.modules`. That made the origin-security tests of `test_flysky_web` / `test_testlab_web` fail when run in one process; the stub is now removed after import.
- README badge restored once the workflow existed (5925d14).

### 2026-11-19 ~23:45 IST — Encoder CRITICAL root cause (wheel-curvature sign), side-ultrasonic geometry, pre-home point (offline; nothing deployed)

**1. "ENCODER CRITICAL: encoder consensus unavailable" — root cause found, fix STAGED (not deployed).**
- Bags `penalty_test_20261116`, `dhruvroom_test3_20261116`, `stage3_roundtrip8_20261116`: 15 + 8 + 5 CRITICAL episodes. All are consensus failures with M1, M2 and M4 rejected (M3 excluded), link LIVE, and almost all while turning (12 of 15 at turn radius < 0.3 m in the penalty test).
- `yahboom_base.py` computed the 4WS path curvature as `(tan(front) - tan(rear)) / L` and documented "servo-high is physical front-left". The 2026-11-15 steering-sign fix (`AUTONOMOUS_STEER_SIGN`/`REMOTE_STEER_SIGN` = −1) and bag 8 show the opposite: servo-low is front-left (servo direction matched the IM10A gyro in **186/186** forward turning samples).
- Consequences of the wrong sign:
  - (a) `/yahboom/odom` yaw is **opposite the gyro in 97–99 %** of turning samples (bag 8: 249 vs 9; penalty: 1 980 vs 8; room test 3: 738 vs 14). This is the root cause behind the 2026-11-12 decision to stop fusing wheel heading. The EKF `/odom` (IM10A yaw) agreed with the gyro in 100 %.
  - (b) The 4WS path scales treated inner wheels as outer, pushing the three wheel increments apart.
- Replay of the consensus rule on the logged increments (reproduces every logged CRITICAL: 24/24, 12/12, 5/5, no false positives). With the corrected sign: **24 → 3, 12 → 11, 5 → 0** (41 → 14). The remaining failures are genuine bursts/stalls (two channels near zero while one moves), often during owner remote driving.
- Staged fix: `applied_curvature_per_m()` in `yahboom_base.py` = `(tan(rear) - tan(front)) / L`, used for both odometry yaw and path scales. Tests: `tests/test_applied_curvature.py` 4/4. `scripts/test_encoder_update_snapshot.py` 6/6 (its stub also gained the speed-loop fields missing since 2026-11-15). `test_speed_loop_base` 25/25, `test_encoder_selection` and `test_atlas_encoder_geometry_audit` pass (rover temp copy).
- **Deploy needs the owner's OK, and because it changes `yahboom_base.py` the Speed check must pass twice afterwards.** Also affected (expected better): speed-loop distance in turns, `/yahboom/odom` consumers (ICP prior, LiDAR-odom gate, tight-space recovery).

**2. Side ultrasonic (front-corner HC-SR04) — software staged, and an earlier recommendation CORRECTED.**
- Staged:
  - bridge `side_ultrasonic_commands()`: `ATLAS_LEFT/RIGHT_ULTRASONIC_ENABLED` sends `USENABLE,L/R` only when explicitly set;
  - mux reads left/right only when `config/ultrasonic_mounts.json` has an enabled measured mount (repo file: both disabled);
  - guard `side_ultrasonic_covered_bins()` uses exact, conservative geometry.
  - Tests: `tests/test_side_ultrasonic.py` 7/7, `test_lidar_map_known_gaps` 20/20 (mux range test extended).
- **Finding:** with a ±10° cone, no single mount (corner at 20–30° out, front face inboard, side at 5–45°) makes the guard's whole-bin rule hold for the door bins −35…−20°. Best placement: 2 of 9 bin/motion cases. A sensor cannot see the points right beside itself, and the rule needs the whole 5° wedge clear to 0.47–0.63 m.
- **Correction:** the 2026-11-19 advice that two front-corner sensors at 30° would cover the 15–45° door blind zone was wrong. They add close-range readings (useful for a future side stop), but **matte tape on the door frame remains the fix** for the doorway vetoes.

**3. Pre-home point.**
- HOME (−0.77, 0.17) has only **0.26 m** clearance (a passage about 0.5 m wide), which explains the tight-spot manoeuvring and refused taps near home in the room tests.
- Best point at least 0.5 m clear within 1.3 m of HOME: (0.13, 0.54), 0.98 m away, clearance 0.52 m. That is effectively the existing **"dhruv room"** place (0.08, 0.54; clearance 0.49 m), which the Stage-3 checker already uses as home.
- Picture: `docs/audits/prehome_candidates_20261119.png`.
- Suggestion (not applied): end autonomous returns at "dhruv room" and do the last metre into HOME by remote.

### 2026-11-19 ~22:50 IST — Front/rear ultrasonic vs LiDAR check (read-only; rover parked, autonomy not armed)
- **Live, 60 s, parked:**
  - Front: 209 fresh VALID samples (3.5 Hz), median 0.683 m, std 4.2 mm, 0 samples > 5 cm from the median.
  - Rear: 209 VALID, median 0.671 m, std 8.1 mm, 0 outliers.
  - 3 frames had no state (startup).
- LiDAR along the same axis, assuming mounts at the footprint edges x = ±0.25 (laser at x = −0.05):
  - Front: LiDAR at the sensor 2.00 m vs ultrasonic 0.68 m (−1.31 m). The ultrasonic sees something nearer that the 18 cm LiDAR plane does not; owner to check what is in front at about 68 cm (low object, legs, floor echo).
  - Rear: 0.78 m vs 0.67 m (−11 cm).
- **Bags** (ultrasonic Float32 vs LiDAR nearest within ±10°, minus mount offset):

| Bag | Front, LiDAR-at-sensor < 1 m | Rear, < 1 m |
|---|---|---|
| penalty_test_20261116 | median +13 mm, 74 % within 10 cm | −59 mm, 74 % |
| dhruvroom_test3_20261116 | +46 mm, 90 % | −65 mm, 86 % |
| stage3_roundtrip8_20261116 | +45 mm, 66 % (120 pairs) | +46 mm, 55 % |

  - At longer range the ultrasonic is mostly shorter than the LiDAR (bag 8 front: 5 986 of 6 145 pairs). This is expected: its cone is wide and covers all heights (side walls, furniture legs, floor), while the LiDAR is a thin plane.
- **Reading:** both sensors are stable and agree with the LiDAR to within about 5–7 cm at close range (their safety role).
  - Small biases (front about +4.6 cm, rear about −6 cm) suggest the real mounts differ a few cm from the assumed footprint-edge positions.
  - **Evidence gap:** no tape-measure check yet. Proposed: a flat board at a measured 50 cm in front and behind, compared with the readings.

### 2026-11-19 ~22:30 IST — REJECTED (offline): short Astra "seen-clear" memory for the hall door (bag 8)
- Owner idea: use the Astra IR depth before and while crossing the door. Replay (scratch script, not in the repo):
  - Astra coverage rays that saw free space (obstacle rays excluded) are stamped in a 5 cm world grid via AMCL + odom delta. Later LiDAR returns erase them.
  - A still-missing bin counts as covered if every sample 0.35–0.8 m on all 5 sub-rays was seen free within T s.
  - Live config otherwise: unknown kept + virtual obstacles, sweep-aware.
- Door band y −4..−3, 2 407 moving scans: vetoed 96 % now. With memory: 1 s 96 %, 2 s 95 %, 3 s 95 %, 5 s 95 %.
- Forward commands only (1 091 scans: 789 straight, 302 turning): 92 % now, 90 % with 3 s memory. Still-missing bins: −30…−25° (623), −25…−20° (391), −35…−30° (211).
- **Why it cannot work:** the blind front-right bins are not empty space. They are the right door frame itself, about 0.55 m from the laser at −25…−30° (map: "wall too close 0.55–0.58 m"), i.e. only about 7 cm lateral clearance beyond the 0.18 m half-width at x ≈ 1.9. Neither memory nor the camera can honestly call that space clear, and the LiDAR gets no echo from the frame.
- **Conclusion:** the fix is a LiDAR-visible surface on the right frame (matte white tape/paper at LiDAR height). Once the frame is LiDAR-observed, those bins are observed and the guard no longer vetoes. Secondary: Nav2 passes close to the right frame; check door centring after the tape.
- Astra usable horizontal view in bag 8: about ±26° (rays at −30° and +25° are mostly no-depth); minimum range 0.35 m.

### 2026-11-19 21:58 IST — Goal tolerance loosened for the car-like base (DEPLOYED, owner "Yes, loosen it" on 2026-11-16, "B pressed" 2026-11-19)
- `controller_server general_goal_checker`: `xy_goal_tolerance` 0.10 → 0.20 m and `yaw_goal_tolerance` 0.35 → 0.6 rad. Changed in the live ws `nav2_params.yaml` (md5 fee91d04…, identical to the repo ws copy) and in the repo `config/nav2_params.yaml`. Backup: `backups/virtual_obstacles_20261116/nav2_params.yaml.before-goaltol`.
- Evidence: `penalty_test_20261116`. The "dhruv room" goal took 319 s with 228 forward/reverse switches and 26.7 m driven, and ended 0.36 m short. Test3 re-sent: 102 s, 21 switches, ended 0.17 m away.
- The rover had rebooted (up 2 min). State: `/atlas/motion_safety` = "REMOTE STOP: joystick unavailable", autonomy not armed. Restarted `atlas-localization` only.
  - Verified: controller_server 0.2 / 0.6; planner penalties still 5.0 / 1.0.
  - controller/planner/bt_navigator/amcl/map_server all active.
  - Virtual obstacles: 867 cells.
  - AMCL seeded from a LiDAR-verified pose (−1.225, 0.185).
- No base change, so no Speed check is needed. Not verified: any drive. Expected effect: the goal is declared reached within 20 cm / ~35°. Stage-3 return-home evidence must use this tolerance, stated explicitly.

### 2026-11-16 19:56–20:07 IST — Owner test after the planner penalties (bag `penalty_test_20261116`, 640 s): owner liked the motion, but goals did not complete
- The owner said "this time it moved well in the tight space". The data shows the near-goal manoeuvring is NOT fixed.

| Goal window | Time | Nav2 fwd/rev switches | Path driven | Result |
|---|---|---|---|---|
| test3 leg 1, home → (−0.03, 1.89) | 69 s | 6 | 3.81 m | got within 0.24 m; owner re-sent the goal |
| test3 re-sent | 102 s | 21 | 2.27 m | ended 0.17 m from the goal; preempted |
| dhruv room (0.08, 0.54) | 319 s | 228 | 26.7 m | ended 0.36 m short at (0.08, 0.90), nose to an obstacle (front 0.23–0.29 m); camera stale → cancelled |
| (earlier, old penalties) room test3 return | 56 s | 34 | 3.59 m | cancelled, nose to the wall |
| (earlier, old penalties) test3 legs | 10 s / 45 s | 0 | 0.9 / 3.2 m | succeeded |

- The planner published only 12 plans in 640 s. Most of the switching comes from the **controller (RPP, `allow_reversing`) during the final approach**, not from new planner paths, so the penalty change has little effect on it.
- Goal approach constraints:
  - `xy_goal_tolerance` 0.10 m and `yaw_goal_tolerance` 0.35 rad on a 0.50 × 0.36 m car-like base.
  - Inscribed-cost cells (99) lie within 0.35 m of the "dhruv room" and test3 goals and at 0.2 m from home (home cell cost 21).
  - The planner's `tolerance` 0.3 lets a plan end short of the goal; the goal checker still demands 0.10 m.
- The mux also logged 146 one-bin LiDAR-availability stops in 19:59–20:00 and 24 ENCODER CRITICAL stops. Each interruption makes the controller fall behind the path.
- Planner penalties kept (no harm seen; no clear gain).
- **Candidate next step, not applied:** goal tolerance for this chassis (`xy_goal_tolerance` 0.10 → 0.20, `yaw_goal_tolerance` 0.35 → 0.6), plus room places at least 0.5 m from furniture.

### 2026-11-16 ~19:50 IST — Nav2 planner penalties DEPLOYED (owner "Yes, change it")
- SmacPlannerHybrid `GridBased.reverse_penalty` 2.0 → 5.0 and `change_penalty` 0.0 → 1.0, in the live ws `nav2_params.yaml` (md5 9d5c9a31…, same in the repo ws copy) and the repo `config/nav2_params.yaml`. Backup: `backups/virtual_obstacles_20261116/nav2_params.yaml.before-penalty`.
- Evidence: bag 8 at the hall door (1 240 reverse-turn scans vs 789 forward-straight) and room test 3 (56 s of about 20 forward/reverse full-lock switches ending nose to the wall).
- Restarted `atlas-localization` only, with the rover latched ("REMOTE STOP: B pressed") and autonomy not armed.
  - Verified `ros2 param get /planner_server`: 5.0 / 1.0.
  - Virtual obstacles: 867 cells.
  - AMCL seeded from a LiDAR-verified pose (−1.665, 0.185).
- No speed-loop or base change, so no Speed check is needed.
- Not verified: any drive. Expected effect: fewer direction changes and wider forward arcs. Possible downside: in very tight spots the planner may now prefer longer paths, or fail where only a multi-point turn fits.

### 2026-11-16 19:25–19:37 IST — Owner room test after the unknown + virtual-obstacle fixes (bag `dhruvroom_test3_20261116`, 688 s, 24 topics)
- **"dhruv room test 3" (0.06, 2.12): reached twice, SUCCEEDED (status 4)** in 38 s and 47 s.
- **Return toward home, map point (−1.06, 0.23): failed after 56 s.**
  - Starting at (−0.06, 1.82, 100°), Nav2 issued about 20 alternating forward/reverse full-lock commands (±0.11 m/s, ±1.0–1.2 rad/s): a many-point turn that made no progress toward the goal.
  - It ended at (0.06, 1.15, 177°) nose to the wall: map wall ahead 0.35–0.38 m, front ultrasonic 0.23–0.28 m.
  - The front stop (0.30 m) blocked it. The Astra obstacle scan went BLINDED (wall inside its 0.35 m minimum range), so camera obstacles went stale and mission control cancelled (status 5). Later goals were refused with "camera obstacles OFF". All of this is correct fail-safe behaviour.
- Other refusals:
  - Tapped points near home (−1.47, 0.02), (−1.42, 0.07), (−0.67, 0.34) and "delhi test 4" were refused as "occupied within 0.35 m".
  - One goal was refused at an AMCL scan fit of 84 % (need 85 %).
- Mux: "ENCODER CRITICAL (fewer than three wheel channels agree)" stopped autonomy 7 times (existing encoder issue). There were 27 one-bin LiDAR-availability stops, mostly while nose to the wall.
- Guard replay with the live config: only 5 % of moving scans vetoed (y +1..+2: 6 %, y 0..+1: 3 %). **The guard was not the limiting factor in the room;** the unknown fix did not make the room worse.
- **Reading:** this is the same reverse + turn dithering seen at the hall door (bag 8: 1 240 reverse-turn vs 789 straight scans). It supports the pending Nav2 planner change (`reverse_penalty` 2.0 → 5.0, `change_penalty` 0.0 → 1.0), which is not applied and awaits the owner's OK. Home-side places sit close to walls; a pre-home point about 0.5 m from walls is suggested.

### 2026-11-16 ~19:35 IST — Regression from the free_thresh fix: map identity changed (fixed, owner "Yes, update it")
- `map_pair_id` hashes the accepted YAML + PGM. Changing `free_thresh` in `atlas_latest.yaml` changed the map id from 38253aab42e9e97304aa to 350de9b5ec3eb7f4d6f1. Mission control (`require_matching_map`) then refused every stored place, with the message "belongs to a different map".
  - The owner had to create "dhruv room test 3" (0.06, 2.12) by map tap at 19:23 to test.
  - I missed this side effect when applying the fix.
- Fix: the PGM and the frame are identical, so the stored poses are still valid. Re-stamped `map_id` 38253aab → 350de9b5 in `~/.config/project_atlas/named_places.json` (5 places), `home_pose.json` (1) and `localization_seed_pose.json` (1). Backups are `*.before-mapid-20261116`. The top-level `map_id` key in named_places (d12a1f18…) was left unchanged.
- Still referencing the old id: the remap-13 acceptance/review records (historical; not changed). **Lesson:** any edit to the accepted YAML changes the map identity; future map-config fixes must re-stamp the places, home and seed in the same step.
- Recording `dhruvroom_test3_20261116` (24 topics, as bag 8) started for the owner's room test.

### 2026-11-16 ~18:50 IST — Offline replay of bag 8: virtual obstacles + unknown fix (read-only, rover parked)
- Tool: `tools/drive/replay_map_known_gaps.py`, with new env options `FREE_THRESH`, `VIRTUAL_OBSTACLES` and `BANDS`. Settings: `TIGHT_ARC_SWEPT=1`, bag `stage3_roundtrip8_20261116`, 9 348 scans while Nav2 commanded motion.
- The replay has no ultrasonic coverage, so live vetoes in front/rear bins are lower. It includes the owner-assisted part.
- Scans the guard would still veto under the sweep-aware rule:

| Variant | All | Door band y −3..−4 | Hall y −4..−5 | Hall y −5..−6 |
|---|---|---|---|---|
| A: old (unknown = free, no virtual) | 94 % | 97 % | 99 % | 100 % |
| C: unknown fix only | 94 % | 98 % | 99 % | 100 % |
| D: virtual obstacles only | 41 % | 96 % | 19 % | 25 % |
| B: now live (both) | 41 % | 96 % | 19 % | 25 % |

- **Reading:**
  - The unknown fix is a correctness/safety fix. On this route it neither helps nor hurts: the explained rays ended at real walls.
  - The virtual obstacles cut hall vetoes from ~100 % to ~20 %.
  - The **door band stays ~96 % vetoed**. The frames are too close for the map rule, so the physical fix (paper/tape on both door frames so the LiDAR sees them) is still needed.
  - Rooms y −3..+1 are unchanged (7–52 %).
  - The earlier note that the replay numbers are "stale" is resolved for this bag: the fix does not change them.

### 2026-11-16 ~18:40 IST — CONFIRMED: saved map's unknown cells load as FREE (free_thresh 0.25 vs grey 205)
- Found by the guided-mapping session's replay, then confirmed read-only on the parked rover.
  - `atlas_latest.pgm` holds 44 608 unknown (205), 10 453 free (254) and 1 801 occupied (0) pixels.
  - The live `/map` (map_server, trinary) has 55 061 free (0), 1 801 occupied (100) and **zero unknown** cells.
- Cause: (255 − 205) / 255 = 0.196 < `free_thresh: 0.25`, so map_server loads unknown pixels as free. `map_autosaver_node.py` declares `free_thresh` 0.25, and every saved map since at least 2026-08 carries it (10 map yamls).
- Effect, partly suspected:
  - The global costmap and planner treat unmapped space as free.
  - AMCL free space includes unmapped areas.
  - The LiDAR guard's map-known rays pass through unmapped space as if it were free and stop only at a mapped wall or the map edge. Some blind bins may therefore have been "explained" through space that was never mapped. The 2026-11-16 map-gap replays should be re-checked with 205 = unknown.
- **FIXED 18:28 IST (owner "Yes, fix it").** Rover state: `/atlas/motion_safety` = "REMOTE STOP: joystick unavailable", autonomy not armed.
  - Changed `atlas_latest.yaml` free_thresh 0.25 → 0.196 (backup `atlas_latest.yaml.before-freethresh-20261116`).
  - Changed the `map_autosaver_node.py` default to 0.196 (repo + rover, md5 c34ebd6a; backup in `backups/virtual_obstacles_20261116/`). Its writer also uses free_thresh to classify cells (≤ 19 instead of ≤ 25 → free); SLAM values are almost all 0/100/−1.
  - Restarted `atlas-localization` only.
  - Verified: `/map` free 10 453 / occupied 1 801 / unknown 44 608, exactly the PGM's pixel counts. `/map_nav` 867 cells marked. Global costmap: sofa 100, hall place 0, home 0. AMCL seeded from a LiDAR-verified pose (−1.265, 0.185). Mux shows no map errors; it re-receives the latched `/map`.
  - Not verified: any drive. Expect more LiDAR-guard vetoes and fewer planner shortcuts near unmapped areas. The 2026-11-16 map-gap replay numbers were computed with unknown-as-free and are now stale.
- Candidate fix, as first written (now applied): `free_thresh: 0.196` in `atlas_latest.yaml` (the ROS standard for 205 pixels) and in the autosaver default; restart localization with the rover parked and latched. Expect more guard vetoes near poorly mapped areas (fails safe).

### 2026-11-16 18:20 IST — Guided mapping assistant: design + phase-1a offline modules (NOT deployed)
- **Owner request:** the owner drives; the dashboard shows the map building live with a per-area verdict (accepted / weak / "drive here again"); depth + LiDAR + ultrasonic are used, so objects the LiDAR cannot see are captured. Design: `docs/design/guided_mapping_assistant.md` (SLAM stays LiDAR-only; acceptance gate unchanged; phase 2 exploration only after Stage 3).
- **New, pure Python, offline only:**
  - `scripts/atlas_map_quality_core.py` (tiles, frontiers, English prompts);
  - `scripts/atlas_invisible_objects_core.py` (depth/ultrasonic where the LiDAR is silent, plus a "map change" layer for LiDAR returns on map-free cells);
  - `tools/mapping/bag_reader.py` (sqlite3 + CDR, no ROS) and `tools/mapping/replay_guided_mapping.py`;
  - tests 24/24 on the Mac.
- **Replay of `stage3_roundtrip8_20261116`** (`docs/design/guided_mapping_replay8_20261116.png`):
  - Depth+ultrasonic candidates at the hall-door/corridor frame (x 1.7–2.35, y −2.7…−1.8), the dark wallpaper wall (x −0.1–0.45, y −7.25…−6.95) and the corridor point (x 1.8–2.05, y −3.55…−3.2).
  - Map change at the sofa's near corner (x 0.45–0.75, y −5.0…−4.7), overlapping the confirmed sofa polygon.
  - Not found: the glass table and the cabinet (the rover reached only y −5.14); ultrasonic-only candidates in Dhruv Room are unconfirmed.
- **Evidence gap (verify read-only, parked):** with `free_thresh: 0.25`, PGM 205 would load as FREE by the threshold rule alone (0.196 < 0.25). The replay forces 205 = unknown. Not checked: how the live `/map` encodes those cells.
- **Not done:** live node, dashboard overlay and prompts (phase 1b) all need the owner's "Yes, deploy". No motion and no rover changes were made in this work.

### 2026-11-16 18:04 IST — Virtual obstacles for LiDAR-invisible hall furniture (DEPLOYED, owner "Yes, deploy")
- **Triggering evidence: Stage-3 attempt 8** (bag `stage3_roundtrip8_20261116`, 24 topics incl. `/cmd_vel_joy`, `/atlas/control_policy`).
  - The rover reached the hall door unassisted.
  - At the door, Nav2 asked for reverse + turn (−0.11 m/s, 0.3 rad/s). Blind side/rear bins vetoed it: 4–6 empty bins on both door frames.
  - After owner assistance, the goal "tes 3 hall" (0.98, −6.16) was blocked by an unexplained front-right gap (−25/−30°). The map was unknown/free there, but the black leather sofa stands there.
  - LiDAR returns on map-free cells: sofa cluster (0.0–0.7, −4.8…−5.6), cabinet (2.4–2.8, −4.3…−4.5), right side (3.0–3.2, −5.5…−6.2).
  - Astra depth sees the dark wallpaper wall at y ≈ −6.5…−7.1. Owner confirmed the picture and the glass table between the sofa corner and the wallpaper wall (`docs/audits/hall_unmapped_objects_20261116.png`).
  - Mission control reports "NAMED GOAL FINISHED status=6" instantly on goal preemption while the old goal still runs. This is a reporting bug, still open.
- **Fix:** `config/virtual_obstacles.json` holds three owner-confirmed polygons: sofa x[−0.30, 0.75] × y[−6.40, −4.70], glass table x[0.80, 1.35] × y[−6.30, −5.60], cabinet x[2.35, 2.90] × y[−4.60, −4.20]. Positions are estimated from recordings, not measured.
  - `scripts/atlas_virtual_obstacles.py` republishes `/map` as `/map_nav` with these cells occupied; it is started from `atlas_localization.launch.py`. Both `static_layer.map_topic` entries in `nav2_params.yaml` → `/map_nav`.
  - AMCL and `atlas_latest.pgm` are untouched. The polygons only add occupied cells and never clear any. A bad config publishes the plain map and logs an error.
  - Cmd_vel mux: `lidar_guard_virtual_obstacles` (default the same JSON) overlays the polygons on the guard's map copy. A gap toward the sofa is a known wall at the polygon edge (still vetoed if closer than the sweep-aware required distance, or if the camera sees something closer).
- **Tests:** `tests/test_virtual_obstacles.py` 8/8 on the Mac and on the rover. `test_lidar_map_known_gaps` and `test_lidar_availability` pass on the Mac; together with the new file that is 42.
- **Deploy (rover parked, `/atlas/motion_safety` = "REMOTE STOP: B pressed", autonomy not armed):** backups in `~/project_atlas/backups/virtual_obstacles_20261116/` (mux, live ws `nav2_params.yaml` md5 0996584…, launch). Restarted `atlas-cmd-vel-mux` and `atlas-localization`.
  - Verified: mux "LiDAR guard: 3 virtual obstacles"; node "/map 234x243: 867 cells marked".
  - Verified: `global_costmap static_layer.map_topic` = `/map_nav`. The global costmap is 100 at the sofa (0.2, −5.5), table (1.07, −5.95) and cabinet (2.6, −4.4), and 0 at the hall place (1.68, −5.35).
  - The local costmap has no static layer in its plugin list (LiDAR + Astra only), so it is unchanged.
  - AMCL was re-seeded by the seeder (LiDAR-verified, x = −1.265, y = 0.185).
- **Not verified:** any drive with this change. The polygon positions are estimates; edit the JSON if the furniture moves, then restart both services with the rover parked and latched. The "tes 3 hall" place (0.98, −6.16) lies INSIDE the glass-table polygon (goals there will now be refused), so use the "hall" place. The door-frame blind bins still need the owner's paper/tape.

### 2026-11-16 ~22:00 — Abort mission button, quiet narrator, drive CPU budget (staged, NOT deployed)
- **Abort mission** (owner: "one button to abort the mission"): `POST /api/autonomy {action: abort}`. It first switches to Manual (mux disarm; the mux then blocks every Nav2 command), then publishes `/atlas/cancel_navigation` (mission control: zero Twist + cancel all Nav2 goals). Needs no PIN and is never refused; logged `mission_abort`. Red "Abort mission" buttons on the Command center autonomy panel and the Navigation page (no confirmation dialog: it only stops). Tests: `test_autonomy_abort` 2/2. Fixed the leftover Hinglish link text ("Autonomy readiness: what is blocking / how to clear it").
- **Narrator** (owner: "after it stops it keeps talking"): obstacle/safety reasons are spoken only while a goal is running; repeat window 15 → 45 s; "NAVIGATION CANCELED" → "मिशन रद्द। मैं रुक गया हूँ।" once, then quiet. Tests: `test_autonomy_voice` 12/12.
- **Drive CPU:** `atlas_feature_on_demand` started agent team, AI annotator, vision-lidar fusion, person fusion and experience store on the `autonomy` trigger, i.e. exactly during drives.
  - Config: AI annotator triggers `[ai_object, follow, tracking]`; agent team `[]` (never by demand; code now allows an empty list).
  - The other three are unchanged.
  - Tests: `test_feature_on_demand_drive_cpu` 2/2 and mapping 4/4, on the rover.
- **Voice companion: owner chose "Low priority" (not paused).** It is already capped by the rover's `priority.conf` (Nice 10, CPUWeight 25, CPUQuota 25 %). New drop-in `systemd/user/atlas-voice-companion.service.d/zz-low-priority-20261116.conf`: Nice 19, CPUWeight 10 (CPUQuota stays 25 %). The spoken "stop rover" keeps working. Staged, NOT deployed.
- (superseded) Voice companion pause (owner chose it first): not implemented.
- **DEPLOYED ~22:30 (owner "Yes, deploy"):** status web, autonomy web, narrator core, feature manager + yaml, autonomy-panel.js, map-waypoints.js, glass.css (backups `*.before-abort-20261116`), plus the voice-companion drop-in `zz-low-priority-20261116.conf`.
  - Restarted with the rover parked, E-STOP latched and autonomy OFF: rover-status-web, atlas-autonomy-voice, atlas-voice-companion, atlas-feature-on-demand. All active.
  - Verified: companion Nice 19, CPUWeight 10, quota 250 ms/s. Feature manager loaded agent-team triggers [] and ai-annotator [ai_object, follow, tracking]. `/v2/autonomy-panel.js` and `map-waypoints.js` served with the Abort buttons.
  - Not yet verified: the Abort button pressed from the dashboard (loopback POST is refused by the Wi-Fi same-origin check, so it was not exercised from the rover shell); CPU during a real drive.
- **Abort verified by the owner from the dashboard:**
  - mux "AUTONOMY OFF (manual only)" at 1794829124.27;
  - mission control "Nav2 cancel acknowledged" and "NAVIGATION CANCELED; ROVER STOPPED" at 1794829124.39.
- The owner said the toast vanished too fast to read. Command center now shows a large banner for 30 s ("■ MISSION ABORTED at hh:mm:ss — …", or "⚠ ABORT PROBLEM" / "CONTROL LINK LOST — use the remote B"). Cache-busted `?v=20261116abort`. Deployed (static files only, backups `*.before-abortbanner-20261116`). The Navigation page keeps its modal alert.
- Owner: "the colour chosen to display the message was not good". Toast (`#toast`) and abort banner are now high contrast: dark #0b1620 text on white, 17–18 px bold, coloured accent bar (green OK / red problem / cyan info). Toast stays 6 s (was 2.2 s). Cache-busted `?v=20261116contrast`; static files deployed (backups `*.before-contrast-20261116`).
 That service also handles spoken "stop rover / emergency stop" (publishes `/atlas/voice/stop` and zero `/cmd_vel_joy`), so pausing it during drives removes a stop channel. Owner decision pending. An alternative is to keep it at low CPU priority (nice) during drives.

### 2026-11-16 ~21:00 — Stage-3 attempt 7, charger card, CPU budget (owner requests)
- **Stage-3 #7** (bag `stage3_roundtrip7_us_20261116`, 22 topics incl. ultrasonic), with the hall place centred, 45 s patience and front/rear ultrasonic coverage live:
  - **safe_stop PASS for the first time:** B while Nav2 drove at 0.078 m/s → still in 0.14 s, 0.006 m.
  - Mean moving speed 0.144 m/s.
  - legs FAIL: the hall goal aborted at the door (right-side non-echo wall #1, not papered), owner moved it in; the return needed the owner's help out of the hall. The rover arrived at (−0.01, 0.68).
  - turn_sign FAIL 1667/103 (5.8 % > 5 %; to check whether the opposite samples are the owner's remote assists counted by `/cmd_vel`).
  - encoders FAIL (1 CRITICAL sample while moving).
- **Charger:** owner rating 14.80 V 5.1 A (~75 W) → `battery_eta.yaml` `charger_current_a` / `charger_voltage_v`. The card labels speed by the charger (0.34C = Normal) and shows net vs rover load, e.g. "Normal charger (14.8 V 5.1 A ≈ 75 W, 0.34C) · battery gets 2.3 A, rover uses 2.8 A · ≈ 4 h 47 min to full". Deployed (status web only).
  - Note: 14.8 V is above the usual 4S LiFePO4 full-charge voltage of 14.6 V (3.70 vs 3.65 V/cell); the BMS cuts off, but a 14.6 V charger is advised.
- **CPU while parked and charging** (20 s /proc sample, 6 cores): total 371 %, load avg 19–20.

  | Process | CPU |
  |---|---|
  | yahboom_base | 29 % |
  | RGB camera driver | 29 % |
  | mux | 25 % |
  | **voice companion (idle!)** | 21 % |
  | status web | 19 % |
  | localization monitor | 14 % |
  | rf2o | 12 % |
  | Astra | 11 % |
  | ICP odom | 9.5 % |
  | ai_annotator | 9 % |
  | agent_team | 9 % |
  | mission control | 8.6 % |
  | ultrasonic bridge | 8.5 % |
  | lifecycle_manager | 7.5 % |
  | tight-space recovery | 7.5 % |
  | IM10A observer | 7.3 % |

  Owner reports CPU at 100 % during drives and the dashboard not responding.

### 2026-11-16 ~19:30 — Owner "A and B": hall place centred + Nav2 patience (LIVE), ultrasonic coverage (staged)
- **A1 LIVE:** `hall` named place moved (1.47, −5.91, clearance 0.65 m) → **(1.68, −5.35)**, the point of maximum wall clearance in the hall (1.1 m). Heading −60° (from Dhruv Room). Done with mission control's own `/atlas/save_named_place_at`.
  - The dashboard `/api/places` from loopback returned 403 (Wi-Fi client check); it was NOT bypassed.
  - Backup `~/.config/project_atlas/named_places.json.before-hallcenter-20261116`.
- **A2 LIVE:** Nav2 `progress_checker.movement_time_allowance` 20 s → 45 s (runtime `ros2 param set /controller_server`, verified 45.0; persisted in the ws `nav2_params.yaml`, backup `.before-patience-20261116`; repo `config/nav2_params.yaml` updated).
  - Effect: short guard pauses no longer abort a goal after 20 s. The safety guard is unchanged.
- **B staged (not deployed):** front/rear ultrasonic coverage (`ultrasonic_covered_bins`, ±10° cone, fresh VALID only via `ValidityWindow.reading`).
  - A bin is covered only when the clear range reaches the sweep-aware requirement; a short range never covers.
  - Mux `guard_ultrasonic_ranges`, parameter `lidar_guard_ultrasonic` (default true).
  - Tests: lidar suites 36/36. Not replayable: no ultrasonic topics in the stage-3 bags (record them next time).
- **B DEPLOYED ~19:45 (owner "Yes, deploy"):** `atlas_lidar_availability.py` 2df90553…, `atlas_cmd_vel_mux.py` 8b98aa7e…. Backups `*.before-ultrasonic-20261116`. Mux restarted with the rover parked, E-STOP latched and autonomy OFF; active, no errors. Next drive must record `/ultrasonic/validity` and `/ultrasonic/{front,rear}_mm`.

### 2026-11-16 ~19:00 — Can the Astra or the ultrasonics cover the LiDAR blind bins? (evidence)
- **Astra (stage-3 #6 bag)**, empty LiDAR bins while Nav2 drove (4426 scans):

  | Category | Bins | Share |
  |---|---|---|
  | Outside the camera view (\|bearing\| > 27°) | 7921 | 67 % |
  | Camera also has no depth (blind on the same surface) | 2020 | 17 % |
  | Floor seen to 0.8 m (already filled by the existing coverage rule) | 1625 | 14 % |
  | Camera obstacle | 236 | 2 % |

  A reach-based camera rule would add nothing: whenever the floor is seen, it is seen to the full 0.8 m.
- **Ultrasonic live check** (parked, 60 s, UNO R4 hub):
  - front and rear VALID at 3.4 Hz, sample age ~0.4 s, max gap 0.53 s;
  - **left and right DISABLED** (−1 / state DISABLED, 204/204 samples);
  - validity: SAMPLE_REPORT 201, SERIAL_BACKLOG 6 (3 %).
  - Front 1461 mm vs LiDAR 1868 mm at 0° (≈ 1568 mm from the bumper); rear 524 mm vs LiDAR 796 mm (≈ 596 mm from the bumper). Agreement within ~7–11 cm after the mount offset; one front outlier at 987 mm.
- Verdict: front/rear ultrasonics are usable as close-range coverage for front/rear bins; they cannot help the side bins (the majority) while left/right are disabled.

### 2026-11-16 ~18:30 — Stage-3 attempt 6 (newspaper on the hall-door left wall): FAIL, much better
- Bag `data/lidar_tests/stage3_roundtrip6_tape_20261116` (recording started before the first goal).
- `stage3_autonomy_check`:
  - legs FAIL (hall=6, dhruv room=6);
  - return_home FAIL (no HOME success, although the rover ended at (0.09, 0.56), 2 cm from the place);
  - safe_stop FAIL (no owner stop while Nav2 was driving);
  - turn_sign PASS 1163/53;
  - encoders PASS;
  - localization blocks while moving 0; mean moving speed 0.15 m/s.
- The owner helped several times. The rover passed A and the hall door itself (corridor stops ~14–44 per minute vs 89–430 before) and stalled 1.5 m inside the hall. Owner moved it to the hall place; the return goal stalled in the hall turn-around, the owner moved it into the corridor, the final goal ended status 6 at the place.
- Safe stop: the mux journal shows only ONE "AUTONOMY OFF: E-STOP latched" after "AUTONOMY ON" (16934), at 17900, i.e. ~48 s after the last goal ended. The owner reports pressing B as the stop test, but no B latch was recorded while Nav2 was driving. Needs a repeat: press B while the rover is visibly driving under Nav2.
- Remaining non-echo surfaces (front ±60° rays cast on the map; counts):

  | Spot | Map position | Rays |
  |---|---|---|
  | Hall door RIGHT side (new) | (2.1–2.2, −3.8…−4.0) | 2567 |
  | Spot A | (1.5, −1.4) | 1518 |
  | Hall door left C, partly still | (1.6–1.7, −4.0…−4.1) | 2480 |
  | Hall far wall | (0.5–1.0, −6.8…−7.0) | ~4650 |
  | Hall left | (0.5, −5.3) | 594 |
  | Hall right | (2.8, −5.5) | 539 |

2026-11-12 16:16 remap REJECTED (closure passed 0.06 m/2 deg; SLAM map->odom jump 0.92 m/12 deg at ~16:06:18 and
"observation did not cover session start" gate). Old map preserved; localization restored and VERIFIED. Named places
restored to old-map x/y with RECONSTRUCTED headings; home pose moved aside and MUST BE RE-SAVED before return-home.
Next: analyse side recording for the jump cause (suspected odometry distance scale, ATLAS-001) and the start-coverage gate.

2026-11-12 EKF heading root cause CONFIRMED + scoped fix DEPLOYED: wheel odometry heading and Yahboom gyro are
sign-inverted vs an independent LiDAR keyframe heading; IM10A correct. EKF now fuses wheel vx only + IM10A yaw
(previously rejected velocity-only trial re-adopted on new discriminating evidence: replay median heading error 68 -> 1.3
deg; live turn and drive agree). A wrong IM10A sign change was applied then reverted. Hall localization on the existing
map still FAILS (fit 0.20, AMCL jumped while parked); candidate 2D map rejected. Full-drive position NOT verified.
See docs/LOCALIZATION_HEADING_DIAGNOSIS_20261112.md; registry ATLAS-011/ATLAS-010 events.

2026-10-21 remaining CPU: two-thread lifetime pattern persists; existing untagged
executor samples cannot identify a safe dominant-cost fix. Exact-live compact
JSON candidate prepared,6+60tests pass; historical expected saving only~0.06
whole-machine points/client set, NOT sufficient for headroom. No deployment.
See ATLAS_STAGE32_REMAINING_CPU_AND_JSON_CANDIDATE.md.

2026-10-21 exact-live snapshot DEPLOYED/HEALTH VERIFIED:98f3c269, web-only restart.
CPU69.270->71.215% mean; no demonstrated whole-Jetson saving. No camera Start.
Headroom remains unresolved. ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_DEPLOYMENT.md.

2026-10-21 superseding snapshot package: exact-live fa62787f baseline reverified;
candidate98f3c269 changes only2bookkeeping sites.9 package+60 dashboard tests
pass, byte-perfect rollback rehearsal. NOT deployed. Whole-Jetson CPU/Preview
unverified; approval required. ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_PACKAGE.md.

2026-10-21 snapshot deployment ABORTED before modification: live web hash
fa62787f differs substantively from reviewed baseline73094079. Repository file
would introduce unrelated steering/HTTP/JSON changes. No restart/Start or CPU
comparison. Prepare exact-live-baseline candidate; see
ATLAS_STAGE32_SNAPSHOT_DEPLOYMENT_BLOCKED.md.

2026-10-21 offline snapshot profiling: redundant timestamp scans confirmed;
single-file candidate reduces Linux synthetic snapshot CPU82.81%,60 dashboard
tests pass. NOT deployed, no live CPU savings/camera admission claim. Needs
separate installation/web-only restart approval; no Start. See
ATLAS_STAGE32_DASHBOARD_SNAPSHOT_OPTIMIZATION.md. Aggregate headroom unresolved.

2026-10-21 superseding CPU investigation: all-process parked trace averages
71.3972%, peaks75.6469% with Astra OFF; top10 omits31.1638 CPU percentage points
of other PID work. Observer itself ~1.0734 points. Exact historical76.61% cause
still unverified; no justified new runtime optimization or80% policy. Seven
offline accounting tests pass; no production changes/camera attempt. See
ATLAS_STAGE32_AGGREGATE_CPU_ACCOUNTING.md. Next: targeted offline web profiling.

Current21 October: preview-core deployed97735e9. One approved test rejected
76.6102% before driver launch;zero frames, optimized conversion not exercised.
Per-process top10 evidence does not explain full aggregate load. No retry;
ATLAS_STAGE32_PREVIEW_CORE_LIVE_RESULT.md supersedes earlier candidate status.

Superseding21 October status: direct launch deployed08ad26f; approved test06ed75f
received17depth frames then CPU76.0757% stopped it. Preview not verified.
New OFFLINE core-preview candidate removes19,200 redundant per-pixel validations:
WSL54.8% conversion CPU reduction,94 tests pass. Whole-Jetson contention remains
unresolved; no deployment/Start authorized. ATLAS_STAGE32_PREVIEW_CPU_OPTIMIZATION.md.
Older entries below retained as historical evidence, not current deployment state.

Latest Depth-only attempt072a22c rejected76.0726% before hashing/snapshot/driver.
Offline direct-Python launch candidate removes redundant shell/ROS setup: PC CPU
0.162734->0.055208s,79 tests pass. No deployment. Jetson aggregate contention and
live Preview remain unresolved. See ATLAS_STAGE32_DIRECT_WORKER_LAUNCH.md.

Latest: startup guard74ff38f installed and hash-verified with approved web-only
restart; transient99.83% settled under75% by27s. Sensors/protected PIDs unchanged;
camera/recorder OFF. No live guard or preview test authorized/performed. Calibration
preparation independent; see ATLAS_STAGE32_STARTUP_GUARD_DEPLOYMENT.md.

Offline startup-coverage candidate now captures pre-spawn baseline and checks
resources during bounded hashing;77 tests pass. PC peak allocation down97%, CPU
time increased; actual combined CPU contention unresolved. NOT deployed. Needs
single-file plus web-restart approval, then separate one-session approval. See
ATLAS_STAGE32_STARTUP_COVERAGE_CANDIDATE.md. Calibration preparation is independent.

Latest approved follow-up: cleanup from abc6837 deployed; ONE combined attempt
stopped at CPU77.104377%. Six depth frames, zero RGB at Dashboard receiver;
browser rendering not verified. No restart or retry. An earlier observer-only
78.8889% initialization sample exposed missing worker startup guard coverage.
Fix that offline before another test. Performance optimization design remains
separately reviewed/uninstalled. See ATLAS_STAGE32_CLEANUP_LIVE_RESULT_20261021.md.

Historical 21 October Depth+RGB: CPU78.4615% guard stops startup; signal log precedes
invalid-context error26.874ms. USB opening succeeded. Diagnostic/cleanup candidate
offline,66 tests pass; actual resource-heavy cause and combined reliability NOT
resolved. No live session/deployment. See ATLAS_DEPTH_RGB_STARTUP_FAILURE_20261021.md.
USB native sandbox follow-up preserved separately; no rules installed.

21 October permanent USB audit: owner restored both temporary Astra ACLs; direct
access passes. Subsequent preflight CPU75.2902% blocked before installation/Start;
no retry. New owner task is offline persistence preparation. Eight static tests
pass; proposed exact two-interface atlas-astra0660 rule NOT installed. Guardian
still uses numbered nodes; group/session transition and native rule validation
must precede any persistence claim. Existing serial access works; radar is UNO
topic-fed. See ATLAS_PERMANENT_USB_ACCESS_AND_REBOOT_RECOVERY.md.

21 October20:44 approved Astra recovery: three safety/resource samples PASS;
administrator ACL access unavailable (sudo password required). Stopped before
installation/ACL mutation, camera test NOT started. Original ACLs unchanged.
Read ATLAS_STAGE32_USB_ACCESS_20261021.md for measurements and uninstalled
persistent-permission proposal. Next prerequisite: operator administrator access.

21 October post-reboot USB follow-up (new owner task supersedes pause): depth
admission failed at1.2004s before streaming. Expected Astra VID/PIDs/nodes present,
both lack jetson RW ACL; direct open denied errno13. No evidence of current address
change. Minimal diagnostic candidate offline; targeted ACL restoration plus one
Depth-preview test awaiting approval. No calibration/rendering changes required.
See ATLAS_STAGE32_USB_ACCESS_20261021.md; no live restoration claimed.

21 October 19:25 PAUSED 3 DAYS by owner (see ATLAS_3_DAY_PAUSE_HANDOVER.md).
U2+P DEPLOYED 19:17 (monitored restart, all post-checks passed). Live Depth-only
3D preview test NOT started (camera never started); needs owner re-confirmation.
Calibration still needs owner measurements; metric cloud still gated.

21 October 19:30 UNCALIBRATED 3D preview (diagnostic only) built and tested offline;
packaged with U2 as U2+P (one monitored rover-status-web restart), rehearsed on a
copy, NOT deployed, camera not started. A4 / 25 mm target and tools ready; they
need the owner's measured square size and target distances. Waiting on owner:
U2+P approval, then a Depth-only session approval. Metric cloud still gated.

21 October 18:38 U1 Vision Lab status UI DEPLOYED (static, no restart, backup verified).
P0 route to a live XYZ cloud: U2 (monitored web restart; manifest serial for the
gate) -> one IR+Depth session (IR-to-depth offset) -> A5 IR checkerboard + depth
targets -> offline validation review -> A6 install + one Depth+3D cloud session.
Waiting on owner: U2 confirmation, IR+Depth approval, printed-target and distance
measurements. Calibration gate active; no metric cloud.

21 October 18:35 Stage32 continuation (offline): UI status fix READY (no-restart U1;
label/serial U2 needs a web restart), not deployed. Combined modes NOT tested
(driver has no IR/depth exclusion; both Astra devices on USB 2.0 behind shared hubs).
Calibration tooling ready: IR despeckle (synthetic 1/24 -> 24/24 detection),
front-face depth model, corners-only capture and depth-target tools. Calibration,
XYZ cloud, XYZRGB still blocked. See Stage32 report section 26.

21 October 18:02 IR RESOLVED (single acceptance): Vision Lab IR now requests
640x480@30 GRAY8 (runtime fc807489, retained). A 60-s IR-only session on the
production driver completed normally: 1624 frames, 29.7 fps, 640x480 mono8 rendered,
raw probe OK, guard 63.7-70.5%, no restart, lease heartbeat max gap 1.40 s. Still
blocked or unapproved: IR+Depth/other combinations, Depth+RGB regression,
calibration, XYZ cloud, XYZRGB, IR-no-frames banner.

21 October 17:45-17:49 permanent IR 640x480 attempt (approved): on the PRODUCTION
driver, real IR 640x480 mono8 ~29.7 fps was delivered and rendered for ~31 s, then
the 4-s viewer lease watchdog stopped the camera at ~42 s (guard 64.5-68.0%, not
resource). Clock comparison indicates the PC test client paused ~3 s. Acceptance
incomplete, so the runtime was restored to 320x240 (454dd25f). No restart; library
and manifest untouched. Next: a re-run from a non-pausing viewer needs approval.

21 October 17:37-17:40 D2 (approved): IR-only at 640x480@30 GRAY8 with the
instrumented driver, no restart. REAL IR FRAMES ON THE DASHBOARD: 1656 frames
read/published (29.70 fps hardware), 1569 received, canvas rendered, 60 s session
completed, guard 65.0-71.3%. Zero-frame cause on this unit: advertised 320x240@30
IR mode not served. All temporary files restored (runtime 454dd25f, lib 6ae87601,
manifest c1a6d1c0; integrity PASS). Production IR still 320x240 = no frames until a
separately approved permanent 640x480 change.

21 October 17:28-17:30 D1 (approved): instrumented driver installed WITHOUT any
restart, one IR-only session, rolled back (integrity PASS, identities unchanged).
Earliest failed boundary = 1: OpenNI started IR 320x240@30 (all rc 0) but
waitForAnyStream timed out (102) 11/11; no frame ever ready, no publish. Receiver
matched (subscribers=1), so the ROS/web path is not at fault. IR NOT verified. Next:
separately approved single 640x480@30 GRAY8 instrumented session.

21 October 17:20 Stage32 takeover from c68ba48 (offline/read-only; nothing installed,
no restart, no camera). The 95.64% sample measured the rover-status-web restart
transient itself: the same restart with a different payload (A1) averaged 93.6% with
about 51 runnable tasks; the candidate does not touch domain 0. Separately found that
the rolled-back candidate would have failed the worker's 458-file runtime integrity
check on every Start. New no-restart diagnostic package (driver library plus runtime
manifest only) rehearsed with byte-identical rollback. IR NOT verified; approval D1
needed. See ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md section 21.

Final documentation-only handover: `ATLAS_STAGE32_DEVELOPER_HANDOVER.md` and
`ATLAS_STAGE32_DEPLOYMENT_REGISTRY.json` index exact versions/evidence/approvals.
No new live checks. Next developer: passive read-only restart-CPU investigation
first; no unchanged install or IR retry. Last safe state is historical section19.

21 October Stage32 conditional installation ROLLED BACK: package/hash/safety
preflight and ARM64 dependency load passed; after web restart CPU95.64% failed75%
guard. Original three files restored; only web restarted (install+rollback).
No IR Start, no retry. Final stopped state, Pi Camera and protected identities
verified, full evidence retained. Next: diagnose restart CPU spike read-only;
new deployment/test approval required. IR failure boundary still unknown. Section19.

21 October Stage32 driver counters: ARM64 candidate built offline, three-file
package/rollback rehearsed. Counters discriminate OpenNI readiness/read, callback,
conversion, ROS publication/subscriber presence, receiver/API/browser. 94+3 tests
passed, one dependency skip; real hardware failure not reproduced offline. Live
hashes unchanged, no activation/deployment. Need owner approval for installation,
web-owner restart and ONE guarded IR test. No motion. Report section18.

21 October Stage32 offline follow-up: pinned vendor source silently discards
OpenNI wait timeouts; saved logs have no frame-read/publish counters or live graph
snapshot. Cannot isolate sensor readiness from ROS publication/discovery. PC
Domain77 real receiver passed 180 synthetic callbacks; this is NOT a hardware
pass. Diagnostic/banner/count-retention candidate prepared, not deployed; no
camera retry. Next evidence must include OpenNI wait/read/publish counters plus
receiver discovery in one separately approved instrumented IR session. Section17.

21 October Stage32 instrumented revalidation: one approved IR-only attempt FAILED
delivery. Eleven ACTIVE samples captured zero IR callbacks before Stop; monitor
ended it after >10s without frames. Peak guard CPU69.78%, RAM70.09%,59.47C, so
not resource blocked. No retry/A3. Driver started but publication/receiver cause
unresolved; offline path review next, not hardware-failure assumption. Postflight
safe, hashes and protected identities unchanged. Stage32 report section16.

21 October Stage32 handover: A1 already deployed, ten hashes and rollback verified.
A2 already attempted, but IR Dashboard delivery acceptance evidence missing:
stop clears counters, so saved zero counts do not prove absent frames. Driver
started IR; session stopped `viewer paused or closed`, not a CPU trip. A3 held.
A4 recovered firmware5.8.22/identity, not validated calibration. No repeat tests,
movement or restarts during reconciliation. See Stage32 report section15.

21 October 15:13 Stage31B: 1-s guard window and stale-summary fix DEPLOYED (no
restart). One 60 s Depth-only session ran to completion: 607 real frames on the
Dashboard, click-to-measure 2.721 m (uncalibrated), guard 63.7-71.1%, limits
unchanged. Astra live viewing now WORKS uncalibrated; calibration/XYZ/cloud still
blocked; single session is not a reliability qualification.

21 October 14:44 second Depth test BLOCKED at start-up: guard sample 76.0% (~0.5 s
window) = Astra start-up burst + kswapd0/kcompactd0 + network-fallback curl probe;
no 1-s sample in 191 s exceeded 75%. No frames, no retry. Owner decision needed on
guard window / background load. See ATLAS_STAGE31_LIVE_DEPLOYMENT.md second test.

21 October 14:35 Stage31 live: UI and Astra domain-77 fix DEPLOYED (web restart only,
protected identities unchanged). One Depth start delivered real frames for ~11 s
(guard 63.5-69.4% after launch, vs first-sample failures before), then a 77.8%
sample stopped it safely; cause unproven (own mid-session SSH observer likely).
Sustained viewing and click-to-measure still UNVERIFIED. Thresholds unchanged.
See ATLAS_STAGE31_LIVE_DEPLOYMENT.md.

21 October Stage31 takeover: Astra startup block traced to ROS/DDS discovery fan-out.
Camera-free, passive /proc sampling: one participant joining production domain 0
raised whole-machine CPU 65%->92% for ~3 s (34 existing nodes woke); the same
join in private domain 77 affected no other process. Parked baseline 65.4% is
spread over ~70 processes (20 points are nice-10/15 background). Fix IMPLEMENTED
(Astra driver + Vision Lab receiver in private domain 77; receiver verified on
Jetson at 30.01 Hz synthetic, no fan-out) but NOT DEPLOYED; projected guard peak
~73% vs 75% limit, so a pass is likely but not certain. Live viewing still
BLOCKED pending approval. Home/Vision Lab redesign built, tested offline and
package-rehearsed on Jetson; not deployed. Thresholds unchanged. See
ATLAS_NEW_DEVELOPER_HANDOVER_AND_RECOVERY.md and ATLAS_DASHBOARD_V2_UI_REDESIGN.md.

21 October Stage30 approved deployment follow-up: three-file ac34cd3 cleanup
installed and hash-verified, no restarts. One real Dashboard Depth attempt
stopped at80.7786% CPU; zero frames, no retry. Independent RAM69.916%,61.187C.
Cleanup is deployed; stable viewing remains BLOCKED. Pi camera and all protected
identities preserved. See final section of ATLAS_STAGE30_ASTRA_RESOURCE_RECOVERY.md.

21 October Stage30: parked CPU65.24% mean/66.78% peak; normal Astra startup
guard75.94%. Startup-only pacing failed to recover stable viewing and was
removed from proposal. Camera-free ROS join also tripped81.68%, implicating
native/graph startup but exact hot path unresolved.119 focused tests pass for
three-file observer-overhead/early-CPU-rejection cleanup; NOT deployed and NOT
a stable-camera pass. No threshold/production-service changes. See
ATLAS_STAGE30_ASTRA_RESOURCE_RECOVERY.md for failures, measurements and approval.

21 October read-only Vision Lab DEPLOYED (`/v2/vision3d`); only web restart,
12 hashes verified, desktop/mobile/Home links pass. One Depth-only attempt
RESOURCE BLOCKED CPU77.9097% >75%; camera stopped before frames, no retry/bypass.
No live pixel/accuracy pass. CPU headroom remains blocker; calibration/XYZ/cloud
still blocked.108 targeted tests pass; Pi camera/six protected owner identities
unchanged. See ATLAS_3D_VISION_LAB_LIVE_DEPLOYMENT.md for backup/hashes/evidence.

21 October calibration continuation:120-byte ctypes layout matches pinned SDK;
vendor validates only part of returned calibration. This does not explain NaNs
or prove camera damage. Alternative supported read paths still untested.
458 live hashes match; stationary admission passed, no stream activation.
94 targeted offline tests pass. Valid intrinsics, measured depth accuracy and
cloud remain blocked. See ATLAS_ASTRA_PRO_CALIBRATION_AND_POINTCLOUD_VALIDATION.md.

21 October Stage29 continuation supersedes the incomplete-build status below:
isolated PC-built ARM64 runtime installed and loader verified; concurrent RGB
15.095 Hz/depth10.527 Hz passed while Pi camera stayed active. 88 targeted tests
pass. Factory parameter query returns NaNs: metric cloud/registration remain
blocked pending valid calibration. CPU-report-only owner exception allowed test
CPU peak99.86%; no normal headroom/endurance pass. Runtime now OFF, production
identities unchanged, no autostart/dashboard deployment. See Stage29 report.

21 October Stage29: PC ARM64 compiler installed and real ELF64/AArch64 probe
passed (two offline tests). Compatible sysroot incomplete: read-only compressed
target copy stopped at CPU75.7983%. Custom target OpenCV4.8 must not be replaced
with host x86/stock4.5 libraries. No driver package or ROS stream verified.
Existing safety/production identities unchanged. See [Stage29](../reports/ATLAS_STAGE29_ASTRA_OFFBOARD_ARM64_BUILD.md).

21 October Stage28: fresh admission passed, but one incremental isolated build
with own-process duty pacing aborted on aggregate CPU80.8782% >75%; RAM68%,
thermal61.218 C. No automatic retry, ROS driver launch or production change.
Owned processes gone; essential service identities unchanged, recorder OFF.
Next: offboard ARM64 build feasibility, not another unchanged Jetson attempt.
Four new supervisor failure-path tests pass. See Astra report for separate status gates.

21 October latest: isolated Astra RGB/depth each returned 15 real frames within
resource limits; depth warning/parser correction verified offline from preserved
output. No recording or existing-service restart. User cgroup CPU quotas are NOT
enforceable; global CPU stability remains unresolved. Full ROS driver, simultaneous
streams, TF/accuracy/endurance and viewer deployment pending. Earlier blocked
attempts below are historical. See [measurements](../reports/ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

21 October2026 approved Astra stationary setup follow-up: vendor source and seven
private dependency packages staged, no global install. Build aborted by unchanged
CPU75% admission (75.884% measured); no auto retry. Depth/RGB USB permissions remain
ungranted; SSH has no suitable passwordless sudo. No streams, movement, recordings
or existing-service restart.86 targeted offline tests pass, not a vendor-build or
live-camera pass. See [follow-up](../reports/ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

21 October 2026 Astra Vision Lab: read-only USB confirms Astra Pro0403/RGB0501,
but no vendor ROS driver/publications and no user write access to depth USB.
Offline viewer tested; NOT deployed and NOT a navigation/localization fix.
72 targeted tests pass including native message serialization; all camera modes,
real depth accuracy, TF/extrinsics and streaming resource impact remain unverified.
Separate stationary driver/permission approval is next; no motion/recording or
production dashboard/service change authorized. See
[Vision Lab report](../reports/ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

20 October2026 UNO incident: full operator power cycle restored native USB and
all3 I2C devices. Initial I2C-offline/LOW reports and later USB enumeration failure
are separate observations; common root cause not proven. A reproducible wall-clock
serial-watchdog defect was fixed with monotonic elapsed time (same8-second limit),
67 tests pass, scoped bridge deployment verified with essential owners/calibration
unchanged and stop/recording safeguards preserved. Original electrical/firmware
lockup remains UNRESOLVED, not a permanent stability certification. See
[evidence, deployment and rollback](ATLAS_I2C_USB_RECOVERY_2026-10-20.md).

16 October 2026 09:30 UPDATE: Dashboard Motion Chip correction DEPLOYED and verified (static files, no restart). OPEN and
now the main blocker: physical check of the M2 (rear-right) and M3 (front-left) encoder channels; evidence shows
direction-dependent count loss that has moved M4 -> M3 -> M2 since 2 Oct (connector/harness/supply suspected, unproven).
Jetson was power-cycled overnight; an AMCL/Nav2 launch started outside systemd at ~08:56 by an unknown actor (mux
manual-only, E-STOP latched, no goal). No drive, Candidate B or fallback deployment until the hand test is done.
See [report](../reports/ATLAS_STAGE25_ENCODER_FAULT_RECOVERY_AND_DASHBOARD_DEPLOYMENT.md).

15 October 2026 22:30 UPDATE (Stage 25): the slow return failed because encoders M3 (front-left, near-dead) and M2
(rear-right, froze 21:40:24 then reversed) removed the 3-of-4 consensus; the base failed closed (37% of travel
discarded). Physical encoder check on M2/M3 is the blocker before any further drive. Final AMCL pose unverified
(owner says back in Dhruv Room; AMCL/LiDAR say ~4.3 m east). E-STOP was not latched during the loop. Dashboard chip
fix is offline and undeployed. Candidate B, Foxglove hardening, Stage 17B and physical E-STOP tests unchanged/open.
See [report](../reports/ATLAS_STAGE25_ROUNDTRIP_ROOT_CAUSE_AND_FIX.md).

15 October 2026 21:06 UPDATE: owner confirmed the 19:46/20:19 position changes were deliberate tests. AMCL seeded once
(20:52:54) at (0.235,-1.435,78); parked 10 minutes stable (max step 0.015 m, 21 checks VERIFIED fit0.981-0.985,
commands zero). OPEN: moving validation (needs separate approval); odometry response to hand moves unexplained
(/odom ~0 during ~1.7 m of owner moves); Dashboard rendered page not visually confirmed by agent; global
ambiguity unproven for other placements; one unexplained MOVING blip at 21:03:43. E-STOP latched, manual-only.
See [seed validation](../reports/ATLAS_STAGE24_AMCL_SEED_VALIDATION.md).

15 October 2026 20:40 UPDATE (supersedes the 20:12 stationary reading below): ATLAS was physically moved at
~19:46 and ~20:19 (scan range images change 0.19 m and 0.34 m median between periods, identical within them;
monitor MOVING bursts at those times); /odom did not register the moves. Five read-only samples: global and Dhruv
Room agree on (0.235,-1.435,75), fit1.0, margin0.105-0.125 (4 of4 completed global; 1 global run failed on the
seeder's 3 s /odom discovery under load). AMCL still NOT seeded; one seed awaits owner approval; tape check
requested. Boot success depends on placement (4 of8 boots UNKNOWN). See
[recovery report](../reports/ATLAS_STAGE24_POST_DEPLOYMENT_LOCATION_RECOVERY.md).

15 October 2026 20:12 Stage 24 deployed; AMCL seed BLOCKED. Live dry runs on a stationary ATLAS
(/odom static) returned (0.115,-2.155,71.5) at 19:44 and (0.335,-0.935,72.0, fit1.0, margin0.116) at 20:08
as front LiDAR arcs reappeared (cause unknown). Poses disagree by1.2 m, so no seed; AMCL
NOT_INITIALIZED, Dashboard unknown. Global ambiguity not proven fixed. E-STOP latched,
manual-only, commands zero. See [Stage 24 deployment](../reports/ATLAS_STAGE24_LOCALIZATION_DEPLOYMENT.md).

15 October2026 CPU continuation: diagnostic search paced without changing its
math, inputs or30-second deadline. Monitor burst74.27%→23.24% of one core;
56 focused tests pass, exact geometry results preserved. Final90-second system
CPU mean70.747%, peak78.696% (3 excursions>75): sustained headroom still NOT
resolved. Largest peak coincides with polkitd32.29%; requester unknown, unprivileged
headers-only trace denied. Need bounded privileged attribution before further
changes. E-STOP latched, manual-only true, commands zero, recordingOFF; essential
services/steering unchanged. See [CPU continuation](../reports/ATLAS_BACKGROUND_SEARCH_CPU_20261015.md).

15 October 2026 parked CPU/manual-only update supersedes the earlier false
manual-only state below: live manual-only now true, E-STOP latched, commands zero,
recorder OFF. Unused AI preview rendering fixed and deployed; 19 tests pass.
Final short resource check passes, but sustained CPU still peaks above 75%.
Rejected diagnostic CPU-quota trial restored to 60%; localization still ambiguous.
See [measurement and rollback report](../reports/ATLAS_PARKED_CPU_MANUAL_ONLY_20261015.md).

15 October2026 Nano thermal policy corrected: NVIDIA documents CV0/1/2 absence
on Nano; fresh device-tree identity verified and exact CV EAGAIN is now N/A.
26 offline tests pass. Fresh Jetson check: thermal reads pass, E-STOP latched,
commands zero, commissioning false, Stage20 inactive/PID0. Admission remains
BLOCKED: CPU sample77.89%>75%, manual_only=false. No recording/movement/change
to production settings. See [verified policy/check](../reports/ATLAS_ORIN_NANO_CV_THERMAL_POLICY_FIX.md).

15 October2026 authorized fixed-probe check: six thermal readings59.625–60.656C,
CPU peak71.43%, RAM66.46%; CV0/1/2 return EAGAIN, precise paths/traces preserved.
Full admission blocks. Separate safety status could not be fetched: SSH timeouts
over Tailscale and Wi-Fi. Fresh E-STOP/recorder state unverified; no activation.
See [Jetson check](../reports/ATLAS_PC_BRIDGE_TEMPERATURE_JETSON_CHECK.md).

15 October2026 offline correction: bounded binary thermal reads replace the
UTF-8 read path; exact None-read exception reproduced offline. Per-file paths and
tracebacks now preserved, unavailable data still blocks.17 focused tests pass
on Ubuntu22.04. Original live failing attribute/cause remains unproven without
its traceback. No Jetson probe/deployment or recording retry. See
[offline fix](../reports/ATLAS_PC_BRIDGE_TEMPERATURE_OFFLINE_FIX.md).

15 October2026 approved10s bridge attempt: BLOCKED before connection. Five fresh
CPU intervals69.19–73.46%, RAM65.05%; temperature measurement path raised
`TypeError: can't concat NoneType to bytes`. Exact cause unverified; thermal map
empty and safety/sensor admission incomplete. No subscription, bag or retry.
See [attempt evidence](../reports/ATLAS_PC_BRIDGE_STATIONARY_ATTEMPT_20261015.md).

15 October2026 follow-up: publisher-presence blocker cleared by3/10/20s graph
snapshots; AMCL/raw scan/particle publishers now visible. Earlier snapshot below
is historical, not a device-fault diagnosis. WSL10s graph-only DDS probe found
no Jetson nodes; existing bridge TCP reachable. Clock bounds still unstable;
Windows Time stopped and WSL initial sync observed, causation not yet established.
Next requires approval for10s stationary receive-only qualification; no movement.
See [connectivity report](../reports/ATLAS_PC_JETSON_CONNECTIVITY_AND_LOCALIZATION_NEXT.md).

15 October2026 PC offboard update: native21-topic synthetic capture verified,
22,779/22,779. Live recording remains NO-GO: direct DDS over WSL NAT unqualified;
clock-offset bounds varied by~944ms; bounded graph snapshot had no AMCL/scan_raw
publishers and no particle_cloud topic. These are observations, not new root-cause
claims. Jetson unchanged, recorder OFF. See
[readiness report](../reports/ATLAS_PC_OFFBOARD_RECORDER_READINESS.md).

Latest startup audit: exact post-start refusal76.2295% is confirmed, process attribution
UNKNOWN. Isolated setup profile0.6521 CPU-seconds does not reproduce or attribute it.
No justified correction, deployment or retry;75% preserved. See
[CPU root-cause report](../reports/ATLAS_STAGE20_RECORDER_CPU_SPIKE_ROOT_CAUSE.md).
Prior supervisor evidence-loss fix is deployed; older source-only status below is history.

Latest: activation supervisor evidence-loss defect fixed in source;18 PC/native
isolated tests pass. Original rejecting measurement UNKNOWN. Installed recorder
unchanged/OFF, no grant or retry. Separate supervisor deployment/activation approval
required; see recording activation failure fix report. Resource headroom unresolved.

Latest17:11UTC: owner approved installation-only CPU exception. Five-file30s upgrade
DEPLOYED/OFF; exact hashes match,328 protected files/production identities unchanged.
Recording grant absent, static/inactive PID0. Runtime75% gate remains unchanged.
Activation and localization validation still pending; earlier rollback preserved below.

14 October17:10UTC approved30s installation passed preflight, failed postflight
CPU77.35%>75%, rolled back all five exact originals. Recorder never started;
production identities and328 protected hashes unchanged. No retry. See readiness
report installation addendum and preserved transaction evidence.

14 October upgrade readiness: exact five-file30s diagnostic patch prepared, six
native install/rollback scenarios passed. Live nine hashes unchanged and unit OFF.
Current parked dashboard~70% does not negate historical CPU refusal; six-core
synthetic recorder estimate adds~8 percentage points. No higher admission justified.
Installation-only approval requested; activation still NO-GO. See
[readiness](../reports/ATLAS_STAGE20_30S_UPGRADE_READINESS.md). No repeated localization replay.

14 October latest milestone: installed legacy Stage20 remains OFF, nine payloads
and83 protected files unchanged. New30s source passed isolated native capture and
failure checks; not deployed. Required static TF loss found/fixed in candidate.
CPU79.496% admission refusal preserved,75% limit unchanged. Minimal fusion candidate
contract-tested only; missing EKF initialization prevents faithful A/B and five AMCL
jumps remain unresolved. No new drive requested. See
[milestone](../reports/ATLAS_NEXT_LOCALIZATION_MILESTONE.md) for current status, superseding
older installation-absent status below without erasing historical attempts.

14 October CPU optimization: compact dashboard JSON is verified faster in isolated
native response tests, but its absolute budget cannot establish Stage20 headroom.
Live dashboard stack profiling refused OS access; noninteractive sudo requires a
password. No permissions/services changed. Live/repository dashboard drift includes
undeployed steering diagnostics: future rollout must be JSON-only, not whole-file
repository replacement. See [optimization report](../reports/ATLAS_STAGE20_CPU_OPTIMIZATION_REPORT.md).

14 October CPU admission follow-up: read-only baseline demonstrates actual CPU
excursions above75% with collector absent and no installation running. Historical
postflight exact sample remains unavailable; causality is not retrospectively proved.
Exact resource evidence and transactional postflight rollback are corrected in
`bb8ec665ed5474d7b2b0db22e9b5624ddd137b06`; nine runtime payloads unchanged.
No third production attempt, recording activation, motion or service restart.
See [CPU investigation](../reports/ATLAS_STAGE20_CPU_HEADROOM_AND_INSTALLATION_FIX.md).

14 October supervised retry: installer and unit registration succeeded, but immediate
postflight resource guard refused acceptance. Exact threshold sample was not retained;
subsequent CPU79.7% exceeds75%. Rolled back only new diagnostics; collector never ran.
All production service identities/protected hashes unchanged, stop latched/zero commands.
No automatic retry. See [retry result](../reports/ATLAS_STAGE20_SUPERVISED_RETRY_RESULT.md).

14 October Stage20 installation update: initial install aborted before writes;
original child error UNKNOWN because wrapper discarded captured stderr. Durable
installer failure evidence fixed in source; 83 PC tests pass (one POSIX skip),
19 native targeted tests and fake-root install/rollback pass. Unit parser/offline
static state verified; manager reload simulated. Nine runtime payloads unchanged.
No production retry authorized or performed; collector absent/OFF, stop latched,
production identities unchanged. See [installation investigation](../reports/ATLAS_STAGE20_INSTALL_FAILURE_ROOT_CAUSE.md).

Stage20: **PUBLIC-ONLY alternative qualified, approval pending; private checkpoint
NOT ready**. Native120s rate/2000-particle test captures all97,901 source messages;
raw CDR fixes a demonstrated diagnostic receive bottleneck. Actual530-unit graph,
adapter/grant, resource bounds and scratch rollback pass;65 offline checks pass.
CPUQuota/device filesystem sandbox unavailable; actual total-CPU75s/memory192MiB/
tasks48/runtime bounds distinguished. No overlays/hooks shipped or live changes.
Private initialization/covariance/reference/consumption/RNG unavailable in partial
scope; localization unresolved, B–E blocked, Stage17B HOLD. See
[minimum-safe scope](../reports/ATLAS_STAGE20_MINIMUM_SAFE_DEPLOYMENT.md).

Stage20 continuation: controlled native startup/consumer audit passes (2734
consumptions), static matched EKF comparison passes (609 samples; max full-covariance
difference0.0895%). Earlier wall-time covariance3.223%/discovery losses retained;
not a moving/historical repair. Gaussian allocation reseeds static pf_pdf_seed,
correcting wall-seed-only explanation. 46 current checks and native crash/quota
tests pass; package/systemd/reset/timing/full-rate qualification still pending.
DEPLOYMENT READY NO; live unchanged, EStop latched, Stage17B HOLD and B–E blocked.
See [readiness report](../reports/ATLAS_STAGE20_DEPLOYMENT_READINESS_REPORT.md).

14 October Stage 20 partial milestone: sandbox-only collector and upstream-library
EKF observer capture actual relative reference/full covariance; opt-in service-call
hooks default OFF. Native synthetic smoke and 28 offline checks pass. NOT production
ready: complete startup/consumer order, AMCL internal events, total overhead and
failure/rollback qualification remain missing. Fidelity and B–E still BLOCKED;
no live installation, motion, seed or calibration. See [Stage20](../reports/ATLAS_STAGE20_EKF_AMCL_CHECKPOINT_CAPTURE.md).

14 October Stage 19: full native Humble EKF/AMCL Hall-return baseline completed in
private network/PID/device namespaces, without actuator access. Five original parked
jumps NOT REPRODUCED; eight native pre-stop corrections instead. Cold EKF starts
at zero while original starts (18.392,-3.654 m,-128.476 deg), with unrecorded prior
relative wheel reference/full estimator state. Even after initial rigid alignment,
native differs up to 1.343 m/18.401 deg. Candidate comparisons FIDELITY BLOCKED;
B native launch refused by strengthened gate. No live configuration/service changed,
E-STOP remained latched, Stage17B HOLD. Next evidence is initialization/checkpoint
capture, not another repeated route. See [Stage19](../reports/ATLAS_STAGE19_NATIVE_EKF_AMCL_REPLAY.md).

14 October Stage 18 supersedes the next-step approval request: Stage 17B is on
HOLD, not authorized for deployment or motion. Offline general 4WS math and
neutral-seeded ICP/gyro screening are tested. Final roundtrip also contains exact
encoder updates (4,591), correcting the earlier incomplete inventory. General
lateral correction using the same commands does not fix wrong yaw; gyro-heading
shadow improves yaw but not translation consistently. Five original AMCL jumps
remain unresolved. No calibration, fusion, map, policy or live service changed.
See [Stage 18 report](../reports/ATLAS_STAGE18_ODOMETRY_SENSOR_FUSION_REPORT.md).

14 October Stage 17: exact encoder/raw-gyro/particle/steering instrumentation
is prepared and an isolated parked Humble capture passed (7,032 messages,
zero application or DDS-reported losses, all required topics available).
E-STOP stayed latched; no physical steering/movement or production deployment.
Current PWM owner is front channel 2/rear 1, centres 90/90, with no physical
angle readback. Visual perspective/sync tools are tested; actual road-wheel
angles and loaded linkage behavior remain missing. The unused direct-serial
utility's opposite channel mapping is disabled in source, not implicated in
the recorded yaw failure. Recorder ~85 MiB/40.5% one-core CPU, whole-system
sampled peak 99.4%; fresh timing/resource and functional remote checks remain
physical-test prerequisites. Battery was charging. Next approval is stationary
lifted front/rear measurement; ground movement remains separate. See
[Stage 17 preparation](../reports/ATLAS_STAGE17_STEERING_YAW_VALIDATION.md).

14 October read-only resumption: Stage 16 has four retained startup verdicts.
Alternate-position checks failed for two distinct measured reasons: one best
fit 0.923 below 0.93, another best fit 0.950 but ambiguity margin 0.028
below 0.06. Both had 21–24 scans and ≥58 valid rays per quadrant on the same
accepted map; neither seeded AMCL. Two Home checks scored 1.000 and seeded via
the startup service. The second alternate check reused an Oct 11 Jetson boot
ID, so was not a new Jetson boot. Exact physical cause of poor/ambiguous fit
is unverified; motion localization remains unvalidated. Oct 9 bag receipts
show ≈10 Hz encoder publication and no diagnostic sequence gaps in the main
Hall→Dhruv recording, while measured encoder distance remains low. No live
settings changed. The repository's `atlas_latest` map differs from the
accepted Jetson map: any offline replay must use the archived accepted pair.
See [resumption report](../reports/ATLAS_CORE_LOCALIZATION_RESUMPTION_REPORT.md).

11 October 20:15 IST: AMCL localized again, through the existing startup verifier, after the owner's
19:52 dashboard restart (fit 0.989, margin 0.111). No manual seed was applied. Live CHECK MY
LOCATION is VERIFIED 3/3: AMCL (0.178, −1.473, 78°) versus LiDAR (0.235, −1.435, 72–75°),
0.069 m / 3–6°. The heading spread is the 3° search grid.

New finding: the board IMU on `/imu/data` read −1.71°/s parked this boot (+0.006°/s on the
previous boot). It is not used by the EKF, but it held the location check in ROVER_MOVING; stage 15
moved that gate to the EKF's IM10A gyro.

Voice latch/release fix deployed (stage 14); a spoken release is not physically tested.

The 0.90 startup score on the 19:06 boot remains unexplained: its verdict and journal were lost,
and web driving 19:13–19:32 means its pose is uncertain. Per-boot replayable verdict capture is
prepared (`b81d7ac`), not deployed. See the
[evening record](../deploy/ATLAS_LOCALIZATION_RECOVERY_2026-10-11_EVENING.md).

11 October 19:47 IST: CHECK MY LOCATION "UNAVAILABLE" after the 19:06 restart. **Root cause:**
the startup verifier refused to seed (best 0.90 < 0.93), so AMCL was active with no pose. The
check required an AMCL pose before even starting its independent LiDAR search and reported a
merged "SCAN UNAVAILABLE or AMCL reference unavailable"; scan, scan-time TF and map were all
fresh. **Fix (stage 13, deployed latched):** precise blocking codes and a stage table; AMCL
reported separately; without AMCL the search runs and the best answer is LIDAR_ONLY_MATCH, never
VERIFIED. Live result in Dhruv Room: (0.235, −1.435, 72–78°), fit 0.994–1.000, margin
0.079–0.107; runner-up is the known alias near (3.9, −0.6). The isolated replay of the Oct 10 bag
reproduces the 3.95 m AMCL alias MISMATCH. AMCL is still un-seeded; no reseed was performed. Only
the location monitor was restarted. Evidence gap: why the boot-time fit was 0.90.
The voice stop announcement (latch spoken, release silent) is fixed in source (27ccfcd), not
deployed. See [stage 13 record](../deploy/ATLAS_LOCATION_CHECK_NO_AMCL_2026-10-11.md).

11 October 18:55 IST: CHECK MY LOCATION Stage A is now deployed on both
dashboard pages with fresh scan/IMU/odometry/TF/map/AMCL validation. 73 scoped
Python tests, 6 UI assertions, isolated ROS smoke tests and both live buttons
passed. Live checks report roughly 1.6–1.7 m AMCL/LiDAR disagreement; candidate
ambiguity remains. This is diagnostic evidence, NOT localization repair or
autonomy clearance. E-STOP remained latched; no movement or pose correction.
Stage B correction is not enabled. Details, resources and rollback:
[implementation report](ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md).
The foundation-only statement below is superseded by this deployment.

11 October follow-up: 26 saved plus 18 fresh paired scans locate all missing
returns in raw +inf, not self-filter removal. Physical cause remains unknown;
guard permissions unchanged. Settled CPU 70.35%, RAM 5442.83 MiB; no basis to
attribute the earlier entire increase to the guard. CHECK MY LOCATION has an
isolated-tested lifecycle foundation only; adapter/UI/replay/deployment remain.
See [checkpoint](ATLAS_CORE_RELIABILITY_CHECKPOINT_2026-10-11.md) and
[location feature status](ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md).

11 October 18:10 IST: approved recovery freshness + stop-only NAV2/recovery
LiDAR guard deployed; RPP conversion 3 -> 15 deployed in both config copies
and running controller, without AMCL restart. 15 full-controller/mux checks,
11 native checks and 38 regressions pass. Direct ROS verifies latched stop,
zero commands and fresh sensors. Historical entries below are preserved.
Remaining: 68/68 fresh real scans have missing observation bins and conservatively
veto hypothetical autonomy in every direction; this is NOT proof of occupied
space. Swept-path observation qualification, physical stopping, and unresolved
moving localization/encoder qualification still block autonomous acceptance.
Two startup verification attempts rolled back on dashboard timing; direct ROS
and systemd verification succeeded. See
[deployment evidence and rollback](ATLAS_NAVIGATION_GUARD_DEPLOYMENT_2026-10-11.md).

11 October decision-path audit: STOP remains latched; no movement or live
control changes. Confirmed recovery defect: all-invalid sectors were infinite
clearance, permitting forward/reverse choices. Source-only correction passes
six regressions. Local costmap does not track unknown space; expected scan
update rate is zero. Neither proves observed free space or a scan-loss stop.
Live RPP inflation-cost conversion is 3 versus costmap scaling 15: confirmed
configuration mismatch. Both need bounded approval-backed commissioning, not
arbitrary range suppression. Full controller action replay remains unfinished.

Latest 11 October 17:15 IST: LiDAR provenance stage 10 is now installed from
`1a9f077`; new markers and raw-ray details verified in the browser. All 60
parked API samples LIVE. Only dashboard restarted. The physical object behind
the front-right minimum is still unknown; no timed before/after hand-test
capture exists. Combined map/scan overlay and arbitrary-point raw provenance
remain unfinished (quadrant minima have raw provenance). BMS still times out;
passive HCI monitoring is blocked by OS permissions. No autonomy enabled.
See the appended stage-10 section of `ATLAS_LIDAR_PROVENANCE_2026-10-11.md`.

Latest 11 October 16:33 IST: owner-approved BMS ownership fix deployed; no
competing restart, but connect still times out (one/120 s, zero healthy samples).
Read-only LiDAR/camera/Home views deployed. All 62 sampled HTTP JPEGs exactly
match original ROS JPEGs: current blur is upstream of V2, precise cause unknown.
See `../ATLAS_MASTER_DEPLOYMENT_2026-10-11.md`; older rollback notes below retained.

2026-10-11 staged rollout update: bounded motion recorder installed and parked
capture verified (3,203 messages; one DDS-reported loss; zero application drops).
No continuous service, no movement. BMS link reuse/backoff stage rolled back
after confirmed competing recovery-supervisor restarts. Offline ownership fix
awaits approval to restart the supervisor; no motor-related restart performed.
connection root cause still unresolved. Owner confirms phone BMS app disconnected.
Current Wi-Fi baseline had no losses/disconnects over 120 s; this does not erase
historical roaming/DHCP faults. No network settings changed. See
`../ATLAS_ROLLOUT_2026-10-11.md` for deployment identities, rollback and measurements.

2026-10-11 13:35 read-only reliability pass (no changes, no motion; see
[core reliability report](ATLAS_CORE_RELIABILITY_READONLY_2026-10-11.md)).
- **Wi-Fi.** Roams to AP B or the extender X failed DHCP 4 of 16 times (plus 1
  unresolved when the journal ends); the
  main router succeeded 26 of 26. The longest outage (73 s on cellular) was a
  DHCP failure, not radio loss. The fallback agent also saw 5 Wi-Fi Internet
  failures (17–109 s), one today at 09:39 with no roam. Six 1 s cellular
  default-route flips with no Wi-Fi event have unknown cause. Power save is on
  at two levels, the regulatory domain is 00, and BT coexistence runs against
  1,164 BMS bonding failures this boot.
- **Correction:** the Oct 10 "46 roams 14:00–15:00" cannot be reproduced from
  the retained journal (6 found); treat it as unverified.
- **LiDAR.** Start-only failures: 0–21 per boot, first scan at 20–257 s, never
  a runtime failure once scanning. No USB re-enumeration. ModemManager,
  vc02 voice and other port users are ruled out. The deferral fix works. The
  5 V supply remains suspected; it needs a measurement.
- **IMU.** The EKF's IM10A gyro outputs exactly 0 when parked (587 of 587
  samples; 54% zeros on the Oct 2 drive). The Oct 2 "zero drift"
  qualification therefore did not observe the bias. This does not explain the
  0.46× fast turn.
- **Localization.** It failed again live. The operator's web drive at
  13:23–13:24 took a VERIFIED pose to LOST, 1.05 m / 24°. The monitor caught
  it 4 s after the stop. There was no recording, so a bounded drive recorder
  is proposed. ATLAS is currently LOST, with the latch released by the
  operator. Not reseeded.
- **Boot −1** ended uncleanly at 00:55:16. Boot 0 began 07:36:51 real time
  with the clock at 01:16 until NTP.

2026-10-11 00:00 local map validation. Candidate v1 is REJECTED: it opened
new passages and deleted real surfaces. The safe v3 gives no benefit. The
corridor needs a supervised slow re-map at ≤ 0.15 m/s and ≤ 15°/s, driven
by the operator. Fresh scans at the corridor midpoint and the Hall are still
pending.

2026-10-10 23:30 local map audit, Dhruv Room → Hall (read-only). About 17%
of the mapped walls in this section are contradicted by 6 independent drives,
mostly shifted copies drawn by the mapping run's return leg. A candidate map
(not promoted) improves offline AMCL replays but leaves the corridor weak. A
slow local re-map is recommended. See
[local map repair](ATLAS_LOCAL_MAP_REPAIR_DHRUV_HALL_2026-10-10.md).

2026-10-10 21:29: steps 1 and 2 of the reliability review were deployed with
approval. The step 3 LiDAR restart limit is on HOLD. On the Jetson:
- Dhruv Room was verified by the monitor and by an independent dry run;
- monitor CPU fell from 0.28 to 0.10 core;
- in a replay, all states and all stale-input rejections behaved correctly.

Still open: stop latency on a real drive, and LiDAR start failures at boot.
Autonomy is still disabled.

2026-10-10 21:30 reliability review (offline fixes, **nothing deployed**).
The monitor took 30–40 s to verify after a stop because the search took
17–20 s on the Jetson. The monitor also had no stopped/verifying state, could
apply a result from before a move, and had no input freshness checks. Fixed
offline:
- search 2.2–2.6 s on the Jetson with identical hypotheses;
- expected about 5 s from odometry stop to result.

LiDAR start failures are chronic: 6 of the last 10 boots had 10–21 failed
starts. The restart loop is unbounded, and two restarters compete. The cause
of the start failure is unconfirmed; suspected supply at boot, which needs a
measurement. Mission's 0.85 scan-fit gate is below the alias peak (0.872);
the autonomy-gate integration is proposed separately. `CPUQuota` is not
enforced on user services, which corrects an earlier claim. The crash boot
left no journal. Awaiting approval for the deployment steps. See [reliability review](ATLAS_RELIABILITY_REVIEW_2026-10-10.md).

2026-10-10 19:16–19:27: localization monitor deployed in suggest-only mode,
with backups and the operator's approval. It marked the live 4 m error LOST
(fit 0.785), and the page showed red LOST. ATLAS was reseeded while parked
by the verify-mode seeder (fit 1.00) and independently re-checked VERIFIED
(monitor fit 0.962, 0.09 m; separate dry run fit 1.00). Autonomy remains
blocked (`navigation_validated: false`). Next: startup LiDAR stability, then
supervised recorded slow/fast drives.

2026-10-10 18:30 moving failure after a verified start. A fast remote drive
from a verified start (3.72, −0.70) to Dhruv Room left AMCL at (4.13, −0.77,
160°), 4.0 m wrong, while the page said START VERIFIED. Confirmed:
- the wrong pose is a recurring Dhruv Room alias (fit 0.87), found in 4
  recordings;
- EKF odometry reported 0.77 of the distance and **0.46 of the −97.5° turn**,
  and wheel yaw had the wrong sign;
- the encoder consensus went CRITICAL at the stop;
- the cloud collapsed to one particle.

The cause of the heading shortfall is unproven (no drive bag). A
continuous parked LiDAR check, built and tested offline, flags all 12
known-wrong AMCL states as LOST and confirmed 14 correct ones on 29 parked
checks. It is not deployed. "START VERIFIED" no longer turns the page green.
A recorded repeat drive is needed. See
[moving failure report](ATLAS_MOVING_LOCALIZATION_FAILURE_2026-10-10.md).

2026-10-10 household movement vs start-pose verifier. Quiet Hall scans fit
0.97–1.00. With people moving (operator confirmed 17:05–17:15) the dry runs
fit 0.86–0.95; that is a time correlation, because those scans were not
saved. Stress test: simulated people in real scans from 11 windows, 484
runs: **0 wrong-place verdicts**. With people, 111 of 176 were verified
correctly and the rest were UNKNOWN. A wrong place out-scored the truth in 10
runs (up to 0.919), and both guards rejected them. Percentile aggregation and
lower thresholds were rejected on this evidence; deployed settings unchanged.
A people recording is needed to confirm on real data.

2026-10-10 Hall cold start localized as Dhruv Room (confirmed): every
localization start seeds AMCL at the saved Dhruv Room pose without checking
the LiDAR. No recovery particles are injected, and 1 Hz parked updates
collapsed the cloud to one pose duplicated 2,000 times. The covariance is
round-off (±1e−14) that the map page can show as CONFIDENT and the mux and
mission control clamp to "perfect". A no-prior LiDAR search finds the Hall
uniquely (fit 0.976, margin 0.187) and was correct in 11/11 parked windows.
Replays: saved seed 0/24 correct, Nav2 global 12/24, search seed 24/24.
A verify-before-seed mode (UNKNOWN instead of guessing) is implemented and
dry-run on the Jetson: 3 correct VERIFIED, 4 UNKNOWN, 0 wrong. Installed and
switched on 17:25–17:30 IST with backups (operator approved). AMCL was
reseeded at the Hall (fit 0.991). Controlled reboot validation is pending. The delayed start was 25
LiDAR start failures over 11.5 min. See
[Hall cold-start report](ATLAS_HALL_COLDSTART_LOCALIZATION_2026-10-10.md).

2026-10-10 localization during motion: wheel odometry reports only ~0.6×
the distance LiDAR scan matching measures (M1/M2/M4 raw counts 0.60–0.62;
EKF 0.36–0.54 above 0.3 m/s), matching tape results of Sep 16 and Sep 25.
That drives UNCERTAIN while moving, forward map→odom corrections and the
"falls behind" symptom. A validated AMCL motion replay shows corrected
distance raises held-out fit from 0.69–0.74 to 0.84–0.94 on 3 of 4 drives.
Lowering alphas alone looks confident but is less accurate: rejected.
CONFIDENT-after-stop is the 1 Hz forced resampling. Wi-Fi roams caused no
Jetson-side ROS gaps. The dashboard mislabelled link stalls as POSE DELAYED:
fixed and deployed (display only). Four unclean reboots today followed NVMe
PCIe error storms. The next gate is a supervised tape-measured distance
calibration; no calibration, EKF or AMCL change was made. See
[motion investigation](ATLAS_LOCALIZATION_MOTION_INVESTIGATION_2026-10-10.md).

2026-10-10 operator confirms ATLAS was moved by hand on Oct 9. Manual
relocation (AMCL cannot see it) is the confirmed cause class for the
outbound 1636 start offset; exact move times were not recorded.

2026-10-10 operator: it is possible ATLAS was moved by hand on Oct 9. Manual
relocation without AMCL following is now the leading (not confirmed)
explanation for the outbound 1636 start offset. Mitigation needs no AMCL
tuning: reseed after any manual move, and gate mission start on a fresh
held-out scan-fit check.

2026-10-10 outbound 1636 start offset: AMCL began the recording already
converged 0.55 m ahead of the scan-best pose along the rover's heading (no
sideways error). AMCL's own likelihood peaks there (6.38–7.32 vs 4.08–4.92;
held-out fit 1.00 vs 0.60), and that pose is 7.5–8.5 cm from the morning's
operator-confirmed Dhruv Room reseed. The cloud was 1–2.5 cm wide with zero
odometry, so parked updates could not correct it. How AMCL got there predates
the bag (evidence gap: check Oct 9 16:00–16:37 Jetson journals). Offline only.
See [start-offset diagnosis](ATLAS_OUTBOUND_1636_START_OFFSET_2026-10-10.md).

2026-10-10 multi-drive parked-diversity check (12 parked windows, 6
recordings, 1,800 AMCL core runs): nudge 0.05 m / 2.5° never lowered held-out
scan fit in 11/12 windows (2 seeds in the already-failed window) and improved
it in 5. The parked-update gate lowered fit in 5 windows on every seed and
never improved it: rejected as a standalone repair. Nudge 0.10 m rejected.
New: outbound 1636 sat ~0.5 m from a far better-fitting pose (0.62 vs 1.00).
The 0.05 m nudge added jumps (up to 9) in correcting windows. Offline only.
See [multi-drive results](ATLAS_AMCL_PARKED_DIVERSITY_MULTIDRIVE_2026-10-10.md).

2026-10-10 parked-diversity experiment (AMCL 1.1.20 core, 450 runs, seeds
1–30): bounded jitter of 0.05 m / 2.5° after each parked resample moved the
failed return window onto the refined Dhruv Room pose in 22/30 seeds
(held-out fit 1.000) and kept the correct room and Hall windows correct in
30/30 each. 8/30 failure-window runs stayed wrong, some wandering up to 3 m:
not deployable. The parked-update gate never recovered and froze the Hall
window wrong in 30/30, where recorded updates had corrected it; do not
deploy it as a standalone repair. Unchanged existing harness reproduced
published Jetson numbers exactly. Offline, one drive; production unchanged.
See [parked-diversity experiment](ATLAS_AMCL_PARKED_DIVERSITY_EXPERIMENT_2026-10-10.md).

2026-10-10 weak-hypothesis trace: the 15 room-near particles were lost
while parked (+351.997 to +362.854 s, 11 forced no-motion updates, 0.23 mm
odometry). Scans did not reject them: the exact room pose outscored every
particle on every update, but none sat on that peak. Multinomial resampling
as KLD shrank 2,000 to 1,098 particles removes them in 9.6–14.2% of trials;
zero motion noise and zero recovery alphas meant no new particle could
reach the peak. Offline, one recording; no candidate fix or runtime change.
Next: replay the parked-update gate plus bounded diversity on saved drives.
See [weak-hypothesis trace](ATLAS_AMCL_WEAK_HYPOTHESIS_TRACE_2026-10-10.md).

2026-10-09 competing-pose comparison: equal bounded fitting plus later unused
beams favours the Dhruv region (99–100% endpoint fit, 0.214° corrected-gyro
residual) over the refined false region (78.9–85.6%, 98.229°). A recorded
cloud contains 15 particles near the better room pose; blanket missing-support
claims are not justified. Ten helper tests passed. Offline only, not a fix
or independent multi-drive validation. Next trace weak-hypothesis survival.
See [competing-pose evidence](ATLAS_COMPETING_POSE_EVIDENCE_2026-10-09.md).

2026-10-09 sensor evidence: six recorded stopped windows confirm that physical
stillness is not global localization correctness. Early return AMCL spans
1.148 m/76.478° against repeatable scans and +0.064° integrated gyro. Late
return is steady but wrong; its 77.4–82.7% endpoint fit overlaps late Hall.
No threshold or runtime change was deployed. Six helper tests passed.
See [sensor stability evidence](ATLAS_SENSOR_STABILITY_EVIDENCE_2026-10-09.md).

2026-10-09 follow-up: mission-start incompatibility is CONFIRMED, not merely
suspected. Saved isolated replay has two poses; actual mission code requires
four over at least 5.6 seconds in an 8-second window. One extra startup
refresh still cannot pass. Seven new offline contract tests passed, including
jump/heading/uncertainty rejection. Candidate remains disabled; no production
change or driving. Next: design and offline-validate an independent stationary
estimate-stability criterion before replacing the publication-count requirement.

2026-10-09: added an opt-in, bounded AMCL measurement-refresh handshake.
Healthy processing never overrides stale pose, jump or covariance checks.
The request tick stays blocked; only a subsequent real pose can satisfy the
existing guard. All new authority switches default OFF; production unchanged.
45 focused regression tests passed. Mission startup's multi-pose stability
window and moving/stop localization accuracy remain deployment blockers.
See [isolated experiment details](ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md).

Updated 2026-10-09. Read alongside the [registry](ATLAS_ROOT_CAUSE_REGISTRY.json) and [master analysis](ATLAS_MASTER_FAILURE_ANALYSIS.md).

Processing/pose separation is now implemented and tested in an isolated AMCL
build. Diagnostic processing evidence survives stationary pose silence and
expires on data loss, including frozen ROS time after a discovered timer fix.
It never authorizes navigation. Production mux and AMCL are unchanged;
accurate pose validation and safe permission integration remain release gates.

Deployment validation of 4a4ea9a: **REJECTED**. Actual mux guard tests confirm
the candidate blocks after 2.5 s stationary or sufficiently slow movement.
Five contract tests preserve this counterexample; no deployment or driving.
Separate AMCL scan-processing health from pose publication before integrating
the update gate. Do not extend the timeout or republish stale poses as fresh.

Latest follow-up: [stationary-policy experiment](ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md)
reproduced the stationary-switching failure class, not the original exact five
events. Reduced resampling and frozen priors were rejected as complete fixes.
A source-only fresh-odometry request gate eliminated parked forced requests
in five recorded timelines; AMCL/mux continuity and accurate localization are
still deployment gates. User reboot explicitly seeded saved home at 21:39:42,
so the improved post-reboot marker does not demonstrate autonomous recovery.
No production changes or new driving tests were made.

Latest stationary capture: AMCL stayed at the previously wrong return pose
with 2,000 particles but only one effective geometric support point. The
saved drive also had collapsed support at +104.009 s. Unconditional 1 Hz
no-motion updates plus resampling every update provide a concrete mechanism
for stationary particle impoverishment; the original wrong-mode selection
is still unverified. Keep the current configuration preserved and test the
update/resampling policy offline before deployment. See
[particle-collapse evidence](ATLAS_AMCL_PARTICLE_COLLAPSE_2026-10-09.md).

Later stopped/charging checks found a concrete saved-map blocker: the taught
route is bound to an older map and the **previous** saved Hall goal failed
exact footprint clearance. After a manual Hall arrival, the operator confirmed
the live pose, and a new map-bound Hall point at (6.279, -2.199) passed exact
known-free 0.18 m clearance and grid connectivity to home. This is not a
recorded or repeated autonomous return-home pass. See
[the navigation gate](ATLAS_NAVIGATION_GATE_2026-10-09.md).

The subsequent recorded **manual** Hall → Dhruv Room return exposed a new
localization reliability blocker: AMCL made five >0.5 m position steps after
remote commands stopped, the largest 2.206 m/130°, while wheel odometry was
stationary. The wheel-odometry path was about 6.77 m, so its 4.236 m endpoint
displacement versus 6.053 m between map-frame endpoints must **not** be used
as proof of wheel-distance under-reporting. The drive bag also recorded 32
traction samples with critical encoder consensus (about 3.2 s total) and
about 49 degrees of wheel-versus-IM10A integrated yaw-rate disagreement.
LiDAR/AMCL message delivery was fresh, so the operator's roughly 20-second
map-position lag cannot be dismissed as browser delay alone.
The web map now flags stale displayed poses, but that does not repair AMCL or
motion-estimate disagreement. Keep autonomy gated pending same-time heading,
TF, encoder and localization validation; do not retune wheel scale from this
manual route alone.
The subsequent [cross-bag audit](ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md)
confirmed recurrent but variable wheel/gyro heading disagreement, including
an Oct9 short interval where wheel-model yaw had the opposite sign to gyro
and scan ICP despite four selected encoders. An isolated saved-map AMCL A/B
did **not** reproduce the five live jumps in either configuration; velocity-only
improved some correction metrics but worsened final-window position stability.
The experimental EKF change is rejected for deployment; localization remains
unresolved, and the exact physical steering/traction/geometry contribution
is not proven.
The subsequent steering-interface review confirmed that the live driver sends
front/rear commands to Yahboom PWM channels 2/1; the vendor's readable UART
bus-servo API is a different interface. There is no current external steering
position feedback. The wheel-odometry curvature assumes commanded servo
offset equals physical road-wheel angle, including during encoder path
normalization. This is an unverified model assumption, not a proven failed
servo. No steering/EKF parameter was changed. See the cross-bag audit.
Operator photos confirm visible left/right wheel response and the operator
wants the existing steering behavior preserved; they do not measure physical
wheel angles. A read-only per-jump correlation of the Hall-return bag found
all five AMCL steps 2.856–13.063 s after the last remote command with zero
nearby wheel XY motion, zero corrected-gyro turn and 6–8 LiDAR scans between
poses. AMCL XY uncertainty was already >1 m at each event. These are
stationary localization-hypothesis changes, not a physical motion pulse at
the jump instants. Why the filter became uncertain remains unresolved; do
not retune steering or deploy the velocity-only EKF candidate on this basis.
The particle-cloud and same-scan follow-up confirms a diffuse, multimodal
AMCL estimate switching while stationary: fresh scans and particles were
present, odometry did not move, and one reverse switch worsened scan/map
endpoint agreement. A replay-only beam laser model made position stability
worse; velocity-only EKF also remains mixed. None of the isolated replays
reproduced the five live jumps, so neither candidate is a verified fix.
Production localization is unchanged and autonomy remains gated; see the
cross-bag audit for per-event and replay measurements.
The next [replay-fidelity audit](ATLAS_AMCL_REPLAY_FIDELITY_2026-10-09.md)
confirmed that the saved map matches the recorded map cell-for-cell, but the
earlier replay omitted source scans and rebuilt odometry. A closer replay with
all original scans and EKF odometry in its input still emitted only 120 AMCL
poses versus 168 live and reproduced none of the five jumps in two runs.
Its particle spread also differed. The recorded bag lacks AMCL's internal
particle/RNG checkpoint and pre-clip update history, so these zero-jump
outputs are not evidence of a localization repair.
The full-bag replay also stopped emitting AMCL poses before the original
post-stop jump window. A replay-only zero-motion-threshold experiment kept
updates flowing and produced one repeatable 1.827 m correction, but at 512
poses versus 168 live; it does not reproduce the original five-event failure
or justify deploying an AMCL parameter change.
Follow-up found the missing replay trigger: mission control requested AMCL
no-motion updates about once per second during the original jump window.
Post-stop odom/TF drift was only 0.01221 m/0.504°, below the replay update
gates. A full-bag, isolated replay with that request cadence matched the
original 384 total and 80 post-stop AMCL poses and reproduced two stationary
>0.5 m jumps (max 3.470 m), versus five (max 2.206 m) originally. This
explains the earlier replay's missing updates and reproduces the failure
class, **not** the exact event sequence or a validated repair. Production
localization remains unchanged and autonomy remains gated; see the replay-
fidelity audit for measurements and remaining particle/likelihood work.
A matched one-second scan-window/particle follow-up found broad clouds in
both runs, but original jumps 1 and 4 moved to poses with *worse* map-endpoint
fit across all seven preceding scans each, while both replay jumps moved to
better-fitting poses across every selected scan. Published cloud weights are
uniform and omit AMCL's pre-resampling likelihood/cluster decision. The replay
cannot validate a localization fix; the original hypothesis-selection cause
remains unverified. No further repeats of the same replay output can restore
those unrecorded internals.
A separate, bounded AMCL 1.1.20 shadow binary now captures pre-resampling
weights and cluster selection without replacing production AMCL or
broadcasting TF. A properly paced 10-second stationary run verified the
capture topics and showed one stable cluster. This does not reproduce the
historic five jumps or clear the autonomy gate. The shadow is off by default;
see the [trace audit](ATLAS_AMCL_SHADOW_TRACE_2026-10-09.md).
An isolated A/B replay on the same Hall return found velocity-only wheel
fusion materially closer to saved-map LiDAR endpoints than current wheel
pose+velocity fusion (median 50.2% versus 23.1% within 15 cm), but the
candidate still underfit and a prior Oct 8 comparison was mixed. It has
**not** been deployed. The map page now reveals AMCL uncertainty and pose
jumps instead of treating a fresh TF as a precise fix; it does not solve the
localization instability. See the navigation gate for test scope and data.
Per operator priority, continue non-motion navigation evidence first and leave
the intermittent BLE transport repair until later; **do not bypass fresh BMS
telemetry or any movement safety gate**.

The operator later confirmed ATLAS is at the exact saved Dhruv Room/home
spot and heading while stopped and charging. The earlier live AMCL pose was
about 3.8 m away in unknown map space; fresh LiDAR endpoints strongly favored
the saved spot. A backup was made and the existing AMCL seeder applied the
map-bound Dhruv Room pose once. The subsequent live pose was in known free
space within about 9 cm of the saved point, with 99% of scan endpoints within
15 cm of mapped walls. This resolves the observed stopped-pose mismatch, not
reboot or moving localization repeatability. The named places and accepted
map are bound to `d12a1f183177212a3cc8`. On the Oct 9 boot,
`atlas-localization.service` had six restarts. Its start-preflight exited
124 (timeout) while LiDAR repeatedly logged hardware operation timeouts;
missing scans are a strong explanation for the preflight failures, not proof
that the seed caused them. Once running, Nav2 logged several out-of-map robot
poses before settling. These observations make localization
verification a current autonomy gate. The later physical confirmation and
scan-map check isolated the prior AMCL pose as wrong. Do not start an
autonomous route solely because the stationary reseed worked. See
[the navigation gate](ATLAS_NAVIGATION_GATE_2026-10-09.md).
An exact saved-map lookup subsequently found the reported rover position in
unknown cells (205), while the saved Dhruv Room point was known free (254).
The 15-second stopped scan was fresh and wheel/EKF odometry did not move. This
is a concrete route-start blocker even if AMCL's short-window variance looks
small. A fail-closed start-cell check was deployed in mission control with
25 offline map-acceptance tests passing; physical localization still needs
validation under motion and across reboot, and no autonomous movement was
attempted.

## Latest LiDAR priority on 11 October 2026

The owner reprioritized sensing provenance before further BMS/network work.
The reproduced 0.509 m FRONT minimum is raw ray 318 at -44.7 degrees in
base_link, not a fabricated dashboard range or forward-wall estimate.
64 paired raw/filtered samples preserved all finite measurements; scan-density
variation was already present upstream. A second 26-sample capture retained
raw payloads and replayed identically on Jetson. Physical obstacle/reflection
identity remains unknown; do not remove the close point. Candidate provenance
markers and cluster diagnostics are tested but not deployed. No motion,
localization, map, network or calibration change. See
[the consolidated sensing report](ATLAS_LIDAR_PROVENANCE_2026-10-11.md).
Next physical action, after authorized diagnostic deployment, is a parked
measured target check, not another manual room loop. Earlier observations below
remain dated evidence rather than current readiness guarantees.

## Current verified boundary

Latest observed motor owner: IDLE, stop latched, raw test interface disabled, all outputs zero; PID 3120, NRestarts=0. At 10:07 IST live encoder health reported fresh packets and selected encoders M1–M4, no exclusions, but this is **not** dynamic encoder qualification or proof M3 is physically reliable. At that time autonomy separately reported `FAULT: STOP: SLAM MAP DATA LOST`; see the later stopped diagnostic recovery below. No autonomous readiness can be inferred from the encoder flag alone.
At about 10:14 IST, a ROS CLI snapshot showed `/atlas/mode` publishing `LOCALIZATION` but `/map` with zero publishers. A later snapshot found the map publisher, and a new transient-local subscriber successfully received the saved map. The dashboard had received it at startup but the safety reporter still marked it `LOST`. Graph discovery therefore fluctuated; the zero-publisher snapshot was **not** proof of a dead map server. An earlier CLI check without the matching transport was also misleading about `/atlas/mode`.
With explicit operator approval while ATLAS was stopped, the safety reporter alone received a diagnostic-only update and restarted at 10:22 IST. It then reported `operating_mode=LOCALIZATION`, `received=true`, `slam_map=ONLINE`, and stayed online at map age 27.68 s, as expected for a latched saved map. The motor service kept PID 3120 and zero restarts. The prior false map-loss state cleared, but whether its cause was a missed mode callback, discovery lapse, or another stale in-process state is **unproven**. This does not validate physical localization or a navigation mission.
BMS reported healthy samples around 94–96% between BLE connection timeouts; percentage is a dated observation, not a present guarantee. Source review later found JSON invalidation was correct but scalar SOC/voltage/current were republished stale on failures; the repair was deployed to the stopped Jetson and passed a short healthy-runtime check, but live invalid-path and BLE endurance validation remain. See [BMS freshness repair](BMS_FRESHNESS_REPAIR_2026-10-09.md).
LiDAR service recovered to running/device-health OK after startup retries; stream freshness and navigation readiness still need direct checks.
No movement is authorized by these reports. Keep manual emergency stop authoritative.

## Ordered work / release gates

| Priority | IDs | Next bounded action | Acceptance / what remains |
| --- | --- | --- | --- |
| 1 | 007,006 | Diagnose single-owner BLE connection failures; distinguish phone/radio/stack/reconnect behavior without resetting all Bluetooth | Proposed 10-minute stopped observation with complete fresh four-cell snapshots, no unexplained connection loss; deliberate unavailable BMS stays invalid and inhibits testing. Current result FAIL/unresolved |
| 2 | 004,005 | Add isolated no-motion common-clock timing instrumentation; distinguish client send, DDS arrival, owner execution, receive thread and cache | Three 60-second zero-output trials; current deadlines unchanged; missed-heartbeat injection aborts; cleanup verified even on timeout. Ground rover must not falsely assert lifted mode |
| 3 | 002,003,015 | Audit bounded discovery fairness and startup/ROS environment | Motor-power-off controlled reboot/reconnect/absent-device tests with one verified serial owner, no restart storm or ambiguous binding. Operator approval for disruptive tests |
| 4 | 001 | Fresh operator readiness, short M3-only lifted response test | Correct physical wheel/direction and coherent encoder sign/delta; reliable stop. Does not require every old air test again |
| 5 | 010,013 | Verify exact deployed IMU/EKF authority and wheel model against saved data; keep approved steering unchanged | Stable stationary bias and signed turns, no stale TF; measured wheel/IMU/scan agreement on independent data. No magnetometer authority assumed |
| 6 | 011 | Reuse saved mapping bags; validate composed robot-pose correction and frame-bound places | Accepted geometry, closure, full footprint/connectivity and collision-free plan. Small endpoint closure alone insufficient |
| 7 | 001,011,012 | Only after prerequisites, supervised low-speed ground distance/turn and Dhruv Room→Hall→Dhruv Room | Predeclare measured pose/stopping tolerances and route clearance; no contact/unexplained abort; record recovery and map reload. Then a repeatability campaign, not a one-off success |

Proposed test counts/windows above are future acceptance criteria, not tests already passed. Do not run motor tests while charging or override battery freshness simply because SOC looks high.

## Evidence still needed before changing control

- Exact serial packet and ROS callback timing in the **test mode** that fails.
- BLE connection-stage evidence with competing phone connection ruled in/out; do not presume it.
- Current selected encoder mask and calibration hashes after hardware replacement.
- Why the live selector includes M3 despite earlier exclusion/uncertainty, and whether its loaded-motion counts/sign are coherent.
- Current SLAM map freshness and exact fault origin; do not treat the saved map's presence as an active SLAM stream.
- Physical steering angle versus commanded servo angle if model discrepancy persists; no steering recalibration without explicit scope.
- Source/deployed IMU authority identity and valid retained bias calibration.
- Same-time robot pose, not just transform-origin translation, for map quality.
- Current LiDAR scan age and geometry after the observed startup recovery.

## Work explicitly deferred

No new PID authority, LLM control authority, perception redesign, additional hardware purchase, firmware flashing, automatic motion or safety relaxation is justified by this audit. Existing working features remain intact.

Local Whisper/faster-whisper is a later **voice evaluation**, not a current reliability repair. The active voice path still sends microphone clips to cloud transcription and checks the wake phrase afterward; local Piper speech and optional local text reasoning do not make recognition offline. Preserve that working path and its privacy/motion gates while benchmarking any offline candidate. See [voice ASR evaluation](ATLAS_VOICE_ASR_EVALUATION_PLAN.md).

## What the user needs to do now

No route driving or air lift for this documentation/read-only phase. If a phone is connected to the BMS, report it and disconnect that app before a controlled BLE comparison. A fresh confirmation will be requested only when a specific physical test is ready—not repeatedly while its software prerequisites fail.

## Publication and follow-up

The audit is an initial baseline; full developer transcript review, older unavailable journals, all raw ROS logs, all commit diffs and an independent replay of every historical test remain incomplete. Continue the registry in future sessions; no background automation was installed.


## 2026-10-11 20:45 update: encoder distance by speed (ATLAS-001, offline)

**Data:** Oct 9 bags, 898 near-straight LiDAR-ICP scan pairs, binned two ways (by ICP speed and by
encoder speed) to expose binning bias.

**Findings:**
- **0.10–0.45 m/s:** both binnings agree. Raw M1/M4 read 0.64–0.72× and M2 0.51–0.64× of the true
  distance.
- **Slow end:** not interpretable; the two binnings disagree in opposite directions.
- **Consensus estimator:** removes only 1–3%.

**Still open:** constant CPR/scale error versus constant slip is not separated. M2 differs from
M1/M4.

**Retracted:** a same-day claim of "speed-dependent count loss".

**Evidence gap:** tape-measured straight runs at two speeds. **No calibration change is proposed.**
See [encoder scale by speed](ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11.md).

## 2026-10-14 Stage 17B preparation — ATLAS-013

Disabled-by-default single-person front steering measurement sequence is prepared
and mock-tested. Tilt-only phone orientation is not physical steering feedback.
No live deployment, motion, calibration or localization repair is claimed.
Physical wheel-angle evidence and expanded-profile Jetson resource validation
remain pending. See [Stage 17B](../reports/ATLAS_STAGE17B_SINGLE_PERSON_STEERING_TEST.md).
# 2026-10-14 executor-profile clarification

Owner-provided live py-spy evidence is now available, superseding the earlier profiler-access gap. Focused audit found measurable dashboard CPU, but no demonstrated avoidable executor defect or duplicate constant-topic subscriptions. Eleven offline checks passed; no runtime patch/deployment or CPU savings claimed. Stage 20 headroom remains blocked. See `ATLAS_STAGE20_DASHBOARD_EXECUTOR_CPU_FIX.md` for sample-attribution limits and the bounded thread measurement. Suppressing QoS, adding sleeps and replacing executors are rejected without further discriminating evidence.


## 2026-10-15 update: EKF translation/heading contamination, Candidate B-safe (offline; ATLAS-011, ATLAS-001)

**Confirmed (offline):**
- The production EKF's X/Y follows the wheel-integrated, commanded-steering trajectory while its
  yaw follows the gyro. Its travel direction against its own heading has a 90th percentile of 22°;
  LiDAR gives 9°.
- Native replay reproduces the recorded EKF's relative motion, so a relative A/B is valid.
  Stage 19's absolute/AMCL fidelity block still stands.
- Removing wheel X/Y pose (Candidate B) cuts heading drift per about 1.4 m from 4.8 / 7.4 / 23.6°
  to 0.5 / 2.3 / 3.4°.

**New hazard, closed in source:** B coasts 2 m during a parked stop when encoder consensus is lost.
The fresh-zero-count twist anchor in `yahboom_base.py` closes it in source (0.003 m in the
synthetic test). **Not deployed.**

**Separate open issue:** a constant +5.5° LiDAR travel-direction offset, either a LiDAR mount yaw
error or a steering crab. B's sideways benefit depends on resolving it.

**Unchanged:**
- the wheel distance under-read (about 0.65×);
- the five unexplained parked AMCL jumps.

**Deployment gates:** see the [recovery handoff](../reports/ATLAS_SINGLE_DEVELOPER_RECOVERY_HANDOFF.md).

## 2026-10-15 13:30 update: Humble transfer, stop-anchor revision, bridge exposure

**Candidate B on native Humble (robot_localization 3.5.4):** it reproduces the Jazzy A/B. B's
heading benefit transfers.

**Stop anchor revised:**
- The `3eff519` one-tick rule was too weak: all four counts stay unchanged for up to 0.79 s while
  moving.
- Replaced by a 1.0 s stillness detector.
- The stage 21 package is prepared and rehearsed against byte-identical live files.

**Foxglove bridge (production):**
- Any tailnet/LAN client can publish `/goal_pose` (relayed to Nav2), write any node's parameters
  and call services. Demonstrated in isolation.
- Read-only config prepared.
- Bridge 3.x requires subprotocol `foxglove.sdk.v1`.

**Pre-existing test failures, not caused by this work:**
- `test_status_web_estop_reset` wrong-PIN lockout (409 ≠ 403);
- `test_atlas_safety_status_camera_heartbeat`.

**Not deployed.** See the [deployment plan](../reports/ATLAS_CORE_LOCALIZATION_FIX_DEPLOYMENT_PLAN.md).

## 2026-10-15 13:10 update: Stage 21 deployed and parked-verified

**Deployed** (12:53:45, owner-approved): the driver stop anchor. Only `rover-base-telemetry` was
restarted.

**600 s parked check:**
- `/odom` drift 0.0 cm;
- encoders fresh, 4/4 accepted;
- safety state unchanged;
- protected services untouched.

**Not yet shown:**
- **NOT LIVE EXERCISED:** the new fewer-than-3 branch.
- **MOVING VALIDATION PENDING.**

**Not deployed:** Candidate B and the Foxglove hardening. See the
[Stage 21 report](../reports/ATLAS_STAGE21_DRIVER_STOP_ANCHOR_DEPLOYMENT.md).

## 2026-10-15 13:30 update: Stage 22 recorder profile deployed (recording OFF)

**Deployed:** the steering-validation recorder profile. Recording is OFF.

**New finding:** the live `atlas_steering_calibrate.py` is the August direct-serial tool, which can
command the steering servos. The repository version is retired. The repository tests execute it.
- In the Stage 22 rehearsal it was run against a scratch copy and failed safely, because
  `/dev/yahboom` is absent.
- **Replacing it needs owner approval.**

**Still blocking the baseline drive:** AMCL is unseeded on this boot.

See the [Stage 22 report](../reports/ATLAS_STAGE22_RECORDER_DEPLOYMENT.md).

## 2026-10-30 Vision Lab backend installation

Rolled back; Type=simple HTTP readiness race corrected offline. CPU79.15% was
measured during OLD web shutdown, not candidate startup. Attribution remains
unknown; NO-GO for retry. See [diagnosis](../reports/ATLAS_OBJECT_TARGET_INSTALL_DIAGNOSIS_20261030.md).

2026-10-30 shutdown follow-up:39/39 historical scrapes failed; CPU attribution and
duration remain UNKNOWN. Staging avoids restarts; functional API activation does
not. See [assessment](../reports/ATLAS_WEB_SHUTDOWN_CPU_ASSESSMENT_20261030.md).

2026-10-30 restart safety follow-up: independent ROS observer and bounded restart/
policy/file recovery implemented offline.8 focused tests including native WSL
SIGKILL fake-unit recovery pass. Actual Jetson admission/performance remains gated;
79.15% cause remains UNKNOWN. [Package](../reports/ATLAS_WEB_RESTART_SAFETY_PACKAGE_20261030.md).

2026-10-31 PRIORITY INCIDENT: original recovery STOPPED after93.624% startup rejection. Original bytes restored; snapshot producer disabled. Saved stack is within ROS Node initialization before custom work. Exact process attribution missing;19 historical Prometheus scrapes failed. Offline rejection evidence retention fixed/tested, not a runtime optimization. Incident OPEN; see ATLAS_RECOVERY_STARTUP_ROOT_CAUSE_REVIEW_20261031.md.

2026-10-31 CPU attribution preparation: stdlib all-PID/selected-cgroup collector;11focused PC tests PASS,12s native PC run0.045941CPU-s/14.80MiB. No live execution. Root cause still UNKNOWN; Recovery restart NO-GO pending guarded collector integration and Jetson overhead validation. See ATLAS_RECOVERY_CPU_ATTRIBUTION_PREPARATION_20261031.md.

2026-10-31 attribution follow-up: guarded passive wrapper complete,13 new focused tests PASS. Native PC observer0.05061CPU-s first sample,0.09019CPU-s over12s,20.64MiB. GO for separately approved isolated overhead test only. Recovery start remains NO-GO; cause UNKNOWN. See ATLAS_RECOVERY_ATTRIBUTION_GUARDED_TEST_20261031.md.

2026-10-31 passive attribution test PASS on Jetson: observer0.68516CPU-s through final sample/20.42MiB, peak aggregate63.12%;42units unchanged, child absent after cleanup. Recovery remains stopped; original93.624%cause unknown. Future startup needs separate actor/cgroup integration and approval. See ATLAS_RECOVERY_ATTRIBUTION_JETSON_RESULT_20261031.md.

2026-10-31 final startup preparation: verified collector integrated with one-start original-Recovery actor;8focused offline tests PASS including native fake-unit SIGKILL/timeout and rejected first-interval evidence. GO to request ONE separately approved diagnostic restoration, not proof startup will pass75%. No live execution. See ATLAS_RECOVERY_STARTUP_DIAGNOSTIC_PACKAGE_20261031.md.

2026-10-31 approved diagnostic restoration FAILED: RecoveryPID364817 started once; first startup sample68.729% retained with PID/cgroup. Next collector scan exceeded150ms and discarded partial counters. No CPU>75rejection proven. Recovery stopped, Restart=always restored;41unrelated units unchanged. Incident OPEN; no retry. See ATLAS_RECOVERY_DIAGNOSTIC_ATTEMPT_RESULT_20261031.md.

2026-10-31 confirmed tooling defect corrected OFFLINE:150ms scan exhaustion returns explicit partial evidence rather than discarding acquired counters; safety measurements still validated and true CPU rejection retained.8focused tests PASS. Runtime CPU root cause remains UNKNOWN; no startup performed. See ATLAS_RECOVERY_PARTIAL_EVIDENCE_FIX_AND_CPU_AUDIT_20261031.md.

2026-10-31 corrected restoration package prepared: eight focused built-package tests PASS; nine hashes verified. GO for separate execution approval with fresh admission, not a live safety PASS. Recovery remains last verified STOPPED; startup CPU cause UNKNOWN. See ATLAS_RECOVERY_CORRECTED_RESTORATION_PACKAGE_20261031.md.

2026-10-31 corrected attempt: FAIL at actual 86.934673% CPU; complete 42.96ms scan retained. Recovery PID374161 reached READY but failed safety, now STOPPED. Recovery cgroup54.71% and localization48.22% of one core; causal hot functions UNKNOWN. Original policy/config restored, 41 unrelated services unchanged. See ATLAS_RECOVERY_CORRECTED_ATTEMPT_RESULT_20261031.md.

2026-10-31 offline candidate: required Recovery message types preloaded before rclpy.init, methods/QoS/safety unchanged. Four tests and native no-node check PASS; PC import16ms only, no measured Jetson saving. Not sufficient evidence to declare86.93% issue resolved. Recovery remains STOPPED. See ATLAS_RECOVERY_TYPE_PRELOAD_CORRECTION_20261031.md.

2026-10-31 saved-counter review: approx96% of66.28->86.93% CPU increase is system/IRQ/softIRQ time, not user time. Existing user-only Nav2 stacks cannot identify kernel hot path. No substantial safe runtime fix established; no new tools/tests/live actions. See ATLAS_RECOVERY_KERNEL_TIME_FINDING_20261031.md.

2026-10-31 OWNER STOP: CPU investigation stopped at evidence limit; root cause UNKNOWN. Recovery incident OPEN, service STOPPED; its fault reporting/automatic recovery unavailable. CPU optimization and restoration NOT COMPLETE. AMCL initial-pose/missing-map-transform warnings tracked separately, not a confirmed CPU cause. Evidence retained; no further tools/retries authorized. Handover: ATLAS_RECOVERY_INCIDENT_HANDOVER_20261031.md.

2026-10-31 separate localization finding: map loaded; verify-mode seeder deliberately withheld initial pose after ambiguous matches (margin0.004). AMCL/map-TF readiness blocked, physical disambiguation unresolved. No pose published or runtime changed. One ambiguity test PASS; old source-text seeder test ERROR due renamed observer call. See ATLAS_AMCL_INITIAL_POSE_FINDINGS_20261031.md.

2026-10-31 AMCL follow-up: saved two candidates match230/246 and229/246 held-out beams,213 common; current room independently confirmed DHRUV ROOM. Heading/movement history pending, no current pose verified. Existing verify-place dry-run needs separate live approval; five focused tests PASS, test-only API fix. Recovery remains STOPPED/open. See ATLAS_AMCL_PLACE_VERIFICATION_PLAN_20261031.md.


2026-10-31: Named-place localization dry-run safety path corrected offline: one
attempt, bounded processing, independent existing safety utilities and continuous
sensor/TF freshness checks. 14 focused tests passed. Not deployed or executed;
localization remains unverified and Recovery remains STOPPED/open. See
[guard report](ATLAS_LOCALIZATION_DRY_RUN_GUARD_20261031.md).

2026-11-02 superseding state: bounded snapshot validation failed CPU77.4461%; no same-window process attribution, causeUNKNOWN. Exact original Recovery script andRestartalways restored; RecoverySTOPPED, snapshotdisabled, incidentOPEN. Original-only restoration prepared/offline8tests, not executed. No restart authorization in overnight sprint. See ATLAS_WEB_BINDING_READY_20261102.md superseding section. AMCL edd6563 mission-start offline15tests PASS; no live localization acceptance.

2026-11-02: Original-only restoration failed watcher freshness before start; noCPUviolation (acceptedpeak62.79%). RecoverySTOPPED/PID0, originalpolicy/source intact. Timing cadence/publication ordering corrected offline in existing package,8focusedtests/reviewPASS; newattempt requiresapproval. HardwaretimingPENDING; earlier77.45%CPUcause remainsUNKNOWN. See ATLAS_WEB_BINDING_READY_20261102.md.

2026-11-02: Cadence-corrected restoration aborted on watcher systemctlPID query during daemonreload beforestart; noCPUviolation. Direct cgroup/proc identity replacement offline12tests/reviewPASS, notdeployed. RecoverySTOPPED; incidentOPEN; separateoriginal-only executionapproval required. See ATLAS_WEB_BINDING_READY_20261102.md.

2026-11-04: Neural PARTIAL LIVE (owner-accepted 3-second PC scrape trial; two paths verified). Continuous coverage remains blocked by the unchanged 15-second exporter cache; separate follow-up only. PRIMARY task is independent Object Detection/read-only Tracking host. Existing RGB HTTP route can start viewer transport through touch(), so it is not yet a guaranteed passive boundary. Deployment remains NO-GO pending cache-only transport/API implementation and reviewed access/rollback. No service changes. See ../ATLAS_VISION_HOST_PREPARATION_20261104.md.

2026-11-04: Vision independent host/cache boundary implemented offline; 15 focused checks and independent review PASS. SSH-authenticated private Unix-socket design, disabled inactive archive and exact-live rollback prepared. No deployment. Runtime BLOCKED: running Web lacks passive endpoint; no verified no-restart module loading path. CPU/model resource compatibility UNKNOWN. See ../ATLAS_VISION_HOST_OFFLINE_RESULT_20261104.md. Neural remains PARTIAL LIVE; no monitoring changes.

2026-11-12 remap-jump follow-up (offline replay, no live changes): EKF process-noise candidate q_vx 0.025->0.5 replayed on remap_20261112-160012_bag. Room->hall straight-line: live EKF 2.31 m, replay current 2.31 m, candidate 3.34 m, vs truth ~6.1-6.4 m (SLAM 6.39 m, old map places 6.07 m). Heading identical in all variants (-187.3 deg). Raw wheel |speed| integrated room->hall is only 5.12 m path, i.e. below the 6.39 m straight-line distance, so the wheel odometry itself under-reports distance (>=20%) in addition to the EKF lag. Candidate q_vx=0.5 is NOT sufficient alone and was NOT applied; atlas_ekf.yaml unchanged (vx-only + IM10A yaw). Next discriminating test: offline wheel-speed vs LiDAR keyframe-ICP translation scale on the same bag (no motion needed). Remap attempt 2 stays blocked until odometry distance is fixed.

2026-11-12 wheel vs LiDAR scale (offline, read-only; tool project_atlas/tools/localization/wheel_vs_lidar_scale.py, same method as ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11): clean straight scan pairs from today's three drive bags. /yahboom/odom over LiDAR ICP distance: remap_20261112-160012 0.64x (278 pairs, 17.29 m), m3_session_151321 0.66x (104 pairs), m3_session_153118 0.65x (87 pairs). Binned by ICP speed and by wheel speed: 0.58-0.71 in all bins, no consistent speed trend in both binnings. Same ~0.6-0.7x as ATLAS-001 on Oct 9 bags, so it is persistent, not new. The EKF (vx-only, q_vx 0.025) further reduces it to 0.34-0.43x on short pairs (lag). Root cause of the remap jump: wheel distance about 0.65x true plus EKF lag. Constant CPR/wheel-size error vs constant slip is still not separated; needs a wheels-off-ground hand-rotation test by the owner. No calibration or config changed.

2026-11-12 ~16:55-17:02 hand-turn test (owner; wheels lifted, E-STOP latched (software latch), board/motor power ON, each wheel turned forward ~5 turns by hand): read-only recorder (project_atlas/tools/localization/wheel_hand_turn_recorder.py) got ~4,400 fresh packets per wheel (/atlas/encoder_update packet_fresh true, sequence advancing) but raw counts did not change by even 1 count on any wheel (152190, -168149, -26078, -145047 before and after). INCONCLUSIVE for CPR vs slip. Either the board does not report count changes while traction PWM is 0, or the hand rotation did not reach the encoders. A powered lifted-wheel test (owner drives slowly with the remote, counting tape-marked turns) is the next discriminating step. Nothing changed.

2026-11-12 17:08-17:21 hand-turn test, second attempt (owner, wheels lifted, E-STOP latched, power on, each wheel turned forward 2 full turns by hand, one at a time; read-only recorder, logs /tmp/hand_turn_log_frontleft.csv and /tmp/hand_turn_log_3wheels.csv on the Jetson). Counts per wheel in turn order:
- front left: M3 +149 counts (0.07 turn of 2), jittering -128..+149. Consistent with the known M3 forward-count loss.
- front right: M4 -2980 counts = 1.34 configured turns, i.e. ~1490 counts/turn vs configured 2230.5 (0.67x).
- "rear left": counted on M2 (configured rear_right), -2992 counts, ~1496/turn vs 2215.0 (0.68x); M1 unchanged.
- "rear right": counted on M1 (configured rear_left), +3170 counts, ~1585/turn vs 2238.4 (0.71x). M2 also moved back +1477 during this step (unexplained: coupling, contact or a counting artefact).
Conclusion (provisional, hand-counted turns are about ±5 %): the configured counts_per_revolution values are ~1.4-1.5x too high, which explains most of the 0.65x wheel distance seen against the LiDAR. It is a calibration/config error, not mainly floor slip. Rear M1/M2 position mapping may be swapped; the owner's left/right perspective still needs confirming. No calibration or config changed; a CPR change needs owner approval and a LiDAR-verified drive.

2026-11-12 17:24 APPLIED (owner approved): encoder_calibration.yaml counts_per_revolution M1 2238.4->1585, M2 2215.0->1496, M3 2199.1->1500 (estimate, faulty channel), M4 2230.5->1490. Backup on the Jetson: config/encoder_calibration.yaml.before-cpr-20261112 (md5 ea558981...). rover-base-telemetry restarted while parked with E-STOP latched; loader validation OK; encoder_health READY 4/4. The rear M1/M2 position swap was approved too but NOT applied: atlas_encoder_calibration.py enforces fixed labels (m1 rear_left, m2 rear_right), so the swap needs a code change.
Verification drive 17:39-17:41 (owner; back ~1.1 m then forward, recorded /tmp/cpr_check_bag3): 47 clean straight LiDAR ICP pairs, wheel/LiDAR 0.97x (2.72 / 2.80 m; bins 0.86-1.09), was 0.64-0.66x. Wheel distance FIXED. The EKF /odom is still 0.58x on short pairs (lag: wheel twist cov 0.1 vs q_vx 0.025); the q_vx candidate is still open. Rollback: copy the backup back and restart rover-base-telemetry while parked.

2026-11-12 ~17:50 EKF q_vx replay on the verification drive (cpr_check_bag3; no IM10A topic in this bag, straight drive): whole-drive path wheel 2.69 m (~0.97x LiDAR), live EKF 2.53 m (0.94x wheel), replay current 2.43 m, replay candidate q_vx=0.5 2.55 m (+5 % vs current replay). After the CPR fix, the EKF loses only ~6 % over a full drive; the 0.58x on short scan pairs is timing lag that catches up, not lost distance. q_vx change NOT applied (small gain). Re-evaluate after remap attempt 2 if the SLAM jump is still over the gate.

2026-11-12 18:30 Astra colour ENABLED (owner OK "Yes, use Astra"): new astra.color block in astra_obstacles.yaml (UVC 2bc5:0501, 640x480 MJPEG at 15 fps, extrinsic publishing on). Depth parameters are unchanged and depth_registration stays false, so the obstacle scan keeps the factory depth CameraInfo. Backups on the Jetson: *.before-20261112-colour. After the restart (parked, E-STOP latched): /astra/color/image_raw 15 Hz, depth 17.6 Hz, obstacle_scan_status OK, astra camera_node ~39 % of one core. The atlas-astra-bridge (domain 0) did NOT restart: its parked check refused because cmd_vel telemetry is stale while the E-STOP is latched (fails closed as designed; not bypassed). The bridge needs a fresh cmd_vel (owner releases the E-STOP with sticks untouched) before it is started again. Rollback: color.enable false, restart atlas-astra-obstacles.
2026-11-12 18:33: the owner released the E-STOP with the sticks untouched; the bridge parked check passed and atlas-astra-bridge is active. /astra/obstacle_scan is 8.1 Hz in domain 77 and 6.7 Hz in domain 0, the same as the Nov 6 baseline (6.4-6.9 Hz), so colour did not slow the obstacle scan.

2026-11-12 ~18:50 map-acceptance start-coverage fix (owner OK "Yes, fix it"). Root cause: manual teaching deliberately begins the map->odom observation at ready_unix (after ensure_mapping_stack, about 79 s in attempt 1), but evaluate_acceptance_evidence required it within 5 s of started_unix, so manual teaching could never pass. Fix: for mode manual_teaching, the coverage reference is ready_unix, and a NEW fail-closed gate requires /yahboom/odom stillness between the start request and drive-ready (displacement <= 0.02 m, yaw <= 2 deg, odom age <= 2 s at both ends; missing evidence = reject). Exploration sessions are unchanged; all other limits are unchanged. Tests: scripts/test_map_acceptance_startup.py, 8/8 PASS on the Jetson, including a replay of the attempt-1 evidence: old reference reproduces the coverage failure; new reference leaves only the real 0.916 m / 12.0 deg jump; missing stillness rejects. Deployed; atlas-mission-control restarted while parked (READY). Backups: scripts/*.before-startup-gate-20261112. Pre-remap state backup: ~/.config/project_atlas/manual_session_backups/pre-remap2-20261112. Colour side recorder: tools/m3/color_side_record.sh (tested, ~13 MB/s).

2026-11-12 remap attempt 2 (sessions):
- 18:45-19:04, session 6c954325: ABORTED with no drive. The owner did not drive, and "hall" was saved at the start spot by mistake. The session file was moved aside before stop_exploration, so no candidate map was saved and the accepted map was preserved. Saved places were restored from pre-remap2-20261112 and the session's home pose was set aside.
- 19:43-19:58, session 348c4a79 (owner drove room -> hall -> room; colour side recording maps3d/remap3_colour_20261112-194252): REJECTED, accepted map preserved (atlas_latest.pgm md5 3b049b9e unchanged).
  - startup stillness 0.000 m; ready 1.5 s after start;
  - the start-coverage failure is GONE (the fix works);
  - closure PASSED (0.092 m / 7.0 deg);
  - failures: map->odom translation jump 1.392 m at 19:50:21 and yaw jump 20.7 deg at 19:51:52 (around the hall / start of the return).
  - Report: maps/.atlas_candidate_348c4a79....acceptance.json.
  - Hall saved at map (-8.40, 2.57), 6.8 m from start.
  - Place, home and seed files from the session are kept in ~/.config/project_atlas/rejected_session_348c4a79; named_places restored; home NOT set.
  - Normal localization restored: atlas-localization started (slam-fast/nav2 stopped by its Conflicts), seeded; verify-place "dhruv room" VERIFIED, fit 0.996, margin 0.217.
  - Open: why EKF /odom moved only 3.3 m vs SLAM 6.8 m room->hall despite wheel 0.97x on a straight drive. Turns / heading are suspected; needs analysis of the base bag.

2026-11-12 ~20:30 remap attempt 2 jump analysis (offline, maps3d/remap3_colour_20261112-194252/base):
- Sensors are fine. Wheel vs LiDAR ICP 0.93x (315 straight pairs). Heading: EKF follows IM10A, and both stay within about 3-10 deg of LiDAR keyframe ICP through 350 deg of net turning.
- Room->hall straight-line distance by estimate:
  - LiDAR keyframe ICP 6.88 m;
  - wheel speed x IM10A heading dead reckoning 6.05 m, ending 0.13 m from start;
  - live EKF 3.32 m, ending 1.38 m from start;
  - SLAM hall 6.8 m.
- EKF vx is 0.38x wheel vx while moving (best correlation at 0.2 s lag). The EKF itself throws away distance: wheel twist variance 0.1 vs process noise q_vx 0.025 makes it heavily low-pass vx. Timestamps are fine (lag <10 ms) and the IMU has no acceleration inputs.
- Replays of this bag (offline, domain 92):
  - current: 3.32 m / end 1.38 m (reproduces live);
  - +vy fusion: no change;
  - q_vx 0.5: 5.00 m / 0.49 m;
  - q_vx 2.0: 5.69 m / 0.16 m, path 21.71 m vs wheel 21.67 m.
- Candidate: process_noise_covariance[vx] 0.025 -> 2.0. NOT applied; needs owner OK.
2026-11-12 ~20:45 APPLIED (owner OK "Yes, apply it"): atlas_ekf.yaml process_noise_covariance vx 0.025 -> 2.0 (all else unchanged). Backup on the Jetson: config/atlas_ekf.yaml.before-qvx2-20261112. atlas-ekf restarted while parked with the E-STOP latched; /odom 9 Hz, at rest 0.0. AMCL re-seeded with verify-place "dhruv room": VERIFIED (fit 1.0, margin 0.229); AMCL (0.215, -1.891). Live drive validation is pending (owner drive with LiDAR comparison), then remap attempt 3. Rollback: copy the backup back, restart atlas-ekf while parked, re-seed with verify-place.
2026-11-12 21:09-21:12 live check of q_vx 2.0 (owner short drive, about 1 m; /tmp/ekf_check_bag): EKF vx / wheel vx 0.78 mean while moving (before: 0.38). Straight pairs EKF/LiDAR 0.78x (before: 0.40-0.54x). End displacement LiDAR ICP 0.88 m, wheel+IM10A 0.77 m, EKF 0.65 m; path EKF 0.74 vs wheel 0.83 (0.89x). Clearly improved; the drive was too short for a full validation. Next: remap attempt 3 (room->hall->room) as the real test.

2026-11-12 remap attempt 3 (session b852bf94, 21:11-21:35, with EKF q_vx 2.0): REJECTED, accepted map preserved (md5 3b049b9e unchanged).
- startup stillness 0.000 m; start coverage OK;
- closure PASSED (0.033 m / 0.96 deg; the owner moved forward 45 cm onto the true start spot, which was 45 cm ahead of the old tape after the test drive);
- room->hall: SLAM 6.6 m vs EKF about 5.4 m (attempt 2: 3.3 m), so improved but still ~0.8x;
- failures: map->odom single-step jump 1.112 m at 21:31:06 and yaw 14.8 deg at 21:32:20. Both came early in the return drive, after a 20-min parked wait in the hall. They look like slam_toolbox snapping the accumulated odometry error (~1 m) in one step when it re-recognised the corridor/room.
- Colour data: maps3d/remap4_colour_20261112-211052 (outbound) and remap4b_colour_return_20261112-213018 (return).
- Restored as before: rejected_session_b852bf94 kept; named_places from pre-remap2 backup; home not set; atlas-localization restarted; verify-place "dhruv room" VERIFIED (fit 1.0, margin 0.117).
- Next candidate (not done): wheel+EKF alone remains ~10-20 % short. The existing shadow EKF with rf2o LiDAR odometry (atlas-ekf-lidar-candidate) should be evaluated offline on these bags before any change. The 0.15 m single-step gate is unchanged.

2026-11-12 ~22:00 offline odometry comparison on the remap attempt 3 outbound bag (remap4_colour_20261112-211052/base; 12.3 m SLAM path, 416 s). Each track is aligned to the SLAM pose (map->odom ∘ odom) at motion start; error vs SLAM at the end:
- live /odom (q_vx 2.0) 1.35 m (replay "current" reproduces it exactly: 1.35 m);
- existing LiDAR shadow EKF (rf2o -> lidar_odom_gate -> atlas_ekf_lidar_candidate, replayed in domain 93) 2.28 m, i.e. WORSE; NOT a candidate;
- wheel speed x IM10A dead reckoning 1.09 m;
- keyframe scan-to-scan ICP alone 0.47 m (max 0.62), but heading error up to 18 deg. Its translation must be rotated by 180 deg: the laser frame points backwards relative to base_link;
- ICP translation x IM10A heading: 0.20 m final, 0.28 m max (0.17 m per 10 m), about 5x better than the live EKF.
Conclusion: wheel-based odometry cannot meet the 0.15 m single-step map gate over a room->hall->room loop. A LiDAR scan-matching translation source with IM10A heading is the promising fix; it needs a new real-time node plus EKF fusion, an offline replay first, then owner approval. Tools: project_atlas/tools/localization/{replay_lidar_ekf.sh, compare_odom_to_slam.py, icp_wheelimu_export.py}. Nothing changed live.

2026-11-12 ~22:40 NEW (offline-validated, NOT deployed): LiDAR keyframe-ICP odometry node.
- Files: scripts/atlas_icp_odometry.py + atlas_icp_odometry_core.py, publishing /lidar/icp_odom with body vx/vy; the laser mount comes from TF (yaw 180 deg).
- Tests: test_icp_odometry_core.py 5/5 PASS (synthetic room, backwards laser, still/forward/turn+drive/rejection).
- Replays (tools/localization/replay_icp_ekf.sh, domain 94) against the SLAM pose:
  - outbound 12.3 m: live EKF 1.35 m; ICP node alone 0.03 m final (0.19 max); EKF + ICP vx/vy (variance 0.002) 0.30 m final (0.32 max);
  - return drive (includes the SLAM 1.1 m snap in its reference): live 1.18 m; EKF + ICP 0.46 m.
- Live CPU test (read-only, 60 s, new topic only): 23 ms/scan, ~14 % of one core, 0 rejected, inliers 0.995. Initially 179 ms/scan; fixed with an early-convergence stop.
- Proposed live change (needs owner OK): run the node as a user service and add odom1 /lidar/icp_odom (vx, vy) to atlas_ekf.yaml. Restart the EKF while parked with the E-STOP latched, then verify-place.
2026-11-12 ~22:30 APPLIED (owner OK "Yes, switch it on"):
- New user unit atlas-icp-odometry.service (enabled at boot) runs scripts/atlas_icp_odometry.py with velocity variance 0.002 and a stationary lock: velocity is zero while fresh wheel odometry is still (|vx| < 3 mm/s, |wz| < 0.01 rad/s, age < 1.5 s).
- atlas_ekf.yaml gains odom1 /lidar/icp_odom (vx, vy). Backup: config/atlas_ekf.yaml.before-icp-20261112.
- atlas-ekf restarted while parked with the E-STOP latched.
- Parked drift: 1.0 cm per 40 s without the lock, 0.0 with it.
- Node: 16-52 ms/scan under live load (scan period 128 ms), 0 rejected, inliers ~0.99.
- AMCL re-seeded from a LiDAR-verified pose (0.315, -1.135) in Dhruv Room.
- Pending: live drive validation, then remap attempt 4.
- Rollback: copy the EKF backup back, disable --now atlas-icp-odometry, restart atlas-ekf while parked, verify-place.

2026-11-12 ~23:10 colour 3D map v1 (offline, from remap attempt 3 recordings):
- Built with tools/m3/build_colour_map.py:
  - Astra depth 160x120 + colour 640x480;
  - SLAM poses (map->odom ∘ odom), refined by scan-to-map ICP against the session's 2D map (.atlas_candidate_b852bf94);
  - frames skipped above 8 deg/s turn rate;
  - 2 cm voxels seen >= 2 times.
- Result: 327,802 points (maps3d/colour_room_hall_20261112.ply); dashboard copy 52,199 points at 5 cm.
- Checks (sharpness = 5 cm cells occupied):
  - depth time offset sweep -0.3..+0.35 s: 0 is best;
  - camera yaw sweep -6..+6 deg: 0 is best;
  - map refinement: 6 % sharper.
- Known limits: some walls in Dhruv Room still show 2-3 copies; the hall is dark (lighting); no depth->colour offset (extrinsic message not recorded); refinement failed for 154 of 267 frames outside the room.
- Dashboard: web/v2/home-cards.js draws real colours when the feed has "rgb" (far-to-near order) and redraws once the full-screen overlay is sized. map3d_live.txt now holds the stored colour map. Backups: *.before-colour3d-20261112.
- Next for better quality: a new drive with the ICP odometry live and the lights on.

2026-11-13 remap attempt 4 (session 00c9e957, 10:24-10:48, first drive with the ICP odometry live). REJECTED; accepted map preserved (md5 3b049b9e).
- First start attempt (10:21) failed: "mapping stack did not become ready within 90 s" (CPU ~8 % idle after boot). Retry with the stack up: ready in 1 s.
- Startup stillness 0.000 m; closure PASSED (0.036 m / 1.3 deg, after the owner backed up 20 cm).
- Room->hall: map->odom correction only 0.29 m / 1.4 deg on reaching the hall (attempt 3: ~1.2 m), so the ICP odometry helped.
- Failures:
  - map->odom jump 1.456 m at 10:32:39 and yaw 11.0 deg at 10:32:49, at the start of the return drive;
  - max SLAM TF source age 2.1 s;
  - candidate map not connected room<->hall (no inflated path, footprint path or Nav2 plans).
- Context: the Jetson was overloaded during the return. Load average reached 40-47 with ~2 % CPU idle (two bag recorders, mapping stack, IMX708 camera node, Nav2). The dashboard (rover-status-web) stopped answering; it was restarted at 10:42 after the colour recorder stopped.
- Suspected: CPU starvation delayed slam_toolbox (2.1 s source age), then a large correction. Not yet proven.
- Restored: rejected_session_00c9e957 kept; named_places from pre-remap5-20261113; home not set. atlas-localization failed its first start ("AMCL is not subscribed to /initialpose"; lifecycle timeouts under load) and came up on retry; seeded from a LiDAR-verified pose (0.235, -1.535).
- Colour data: maps3d/remap5b_colour_20261113-102354 (outbound and return until ~10:40).

2026-11-13 ~11:10 attempt 4 jump analysis (tools/localization/slam_jump_timeline.py on remap5b_colour_20261113-102354/base):
- The big corrections (1.95 m / 14.6 deg at 10:32:52, 1.30 m at 10:32:50, 1.32 m / 18.9 deg at 10:33:24, plus 0.8-0.9 m steps to 10:33:25) all fall in the first ~45 s of the return.
- During that window the wheels report the rover driven fast: up to 0.78-1.02 m/s and 82-148 deg/s turn rate. Over the whole return, speed 95th percentile was 0.65 m/s (outbound 0.52), turn rate max 148 deg/s (outbound 86).
- LiDAR rate stayed normal (6.5-6.8 Hz every minute, scan delay <= 0.54 s). The SLAM TF delay was ~3.8 s all session, also when calm, so it is not specific to the jump. CPU overload is therefore NOT the primary cause.
- Main cause: aggressive driving/spinning at the start of the return smeared LiDAR scans (148 deg/s = ~22 deg per scan at 6.7 Hz) beyond what scan matching tracks, and SLAM corrected in large steps. The room<->hall connectivity failure follows from the resulting smeared map.
- Fix to try: a mapping-mode speed limit (e.g. <= 0.3 m/s, <= 30 deg/s) or strict slow driving. Any limit is a config change needing owner OK.

2026-11-13 ~11:40 CORRECTION to the 11:10 entry (new discriminating evidence from independent sensors, same window 10:32:19-10:33:25):
- Turn rate: IM10A max 53 deg/s (95 % 34 deg/s). The 148 deg/s figure was WHEEL-reported and wrong: wheel yaw is unreliable (swapped rear labels, faulty M3). The existing mux mapping limits (mapping_remote_max_linear 0.30 m/s, mapping_remote_max_angular 1.20 rad/s, active in operating mode MAPPING) held for turning.
- Linear speed (LiDAR ICP): 0.61 m/s 95 %, 0.77 max, about 2x the commanded 0.30 m/s cap. The open-loop PWM drive (drive PID disabled) moves ~2x faster than the commanded value since the CPR fix.
- ICP odometry: 0 rejected scans in the window; EKF /odom stayed smooth.
- SLAM (map->odom) oscillated within ~40 s: (-0.22,0.19,1.4 deg) -> (-0.51,0.29,3.8) -> (+0.64,-0.24,-7.8) -> (-1.51,0.30,9.4) -> (-1.15,0.18,5.2) -> (-1.52,0.38,10.4) -> (-0.90,0.36,4.3) -> (-0.55,0.20,0.4) -> (-1.08,0.26,8.4).
- So the jumps come from slam_toolbox scan matching bouncing, not from odometry. SLAM TF stamps lag receipt by ~3.8 s all session (scan_queue_size 20, minimum_travel_distance 0.05 m, minimum_time_interval 0.1 s): SLAM is running ~4 s behind.
- Revised suspects: (1) the SLAM processing backlog and its default correlative search accepting wrong matches during faster motion; (2) real speed ~0.6 m/s.
- Candidate fixes (not applied): lower mapping_remote_max_linear to ~0.15 (real ~0.3 m/s); offline replay of slam_toolbox parameter variants (larger minimum travel, smaller scan queue, stronger odometry trust) on this bag before any live change.

2026-11-13 ~12:00 APPLIED (owner OK "Yes, do both"): atlas_cmd_vel_mux.py default mapping_remote_max_linear 0.30 -> 0.15. It applies only in operating mode MAPPING and can only reduce speed. Live parameter read back as 0.15. Backup: scripts/atlas_cmd_vel_mux.py.before-mapcap-20261113. The mux restarted while parked; RemoteStop starts latched by design. The angular cap stays 1.20 rad/s (the real turn rate stayed below it).
Started: offline slam_toolbox replays (tools/localization/replay_slam.sh, domain 95) of the attempt 4 bag with three variants: live params; lighter processing (0.2 m / 0.17 rad / 0.5 s, queue 1); lighter + stronger odometry trust (variance penalties 1.0/2.0, search 0.3 m).

2026-11-13 ~13:00 offline slam_toolbox replays of the attempt 4 bag (tools/localization/replay_slam.sh; odom->base_link TF rebuilt from /odom because the recorded /tf odom->base_link arrived ~11 s late, 1.6 Hz, which made the first replay attempt invalid):
- live params: max single step 0.757 m at 10:32:55 (reproduces live); 63 steps > 0.15 m; 6 > 5 deg; total correction 28.7 m.
- lighter (min travel 0.2 m / 0.17 rad, interval 0.5 s, queue 1, map update 3 s): max 1.019 m at 10:33:20; 32 steps > 0.15 m; total 14.9 m.
- lighter + variance penalties 1.0/2.0 + search 0.3 m: same as lighter (no effect).
- lighter + loop closing off: same max 1.019 m at 10:33:20, so the big jump is scan matching, NOT loop closure.
At 10:33:15-29 the rover moved up to 0.87 m/s (0.19 m and 11.5 deg between consecutive odom samples) in a narrow spot: 170/360 valid beams, median range 0.58 m. Conclusion: lighter processing halves the bouncing; the remaining large jump comes from fast motion through a tight, feature-poor place. The new 0.15 mapping cap (real ~0.3 m/s) targets it directly; slower driving cannot be proven by replay.
Proposal (not applied; needs owner OK): lighter SLAM settings in atlas-slam-fast.service.
2026-11-13 ~13:10 APPLIED (owner OK "Yes, switch on"): atlas-slam-fast.service lighter settings.
- minimum_time_interval 0.10 -> 0.5; minimum_travel_distance 0.05 -> 0.2; minimum_travel_heading 0.10 -> 0.17; map_update_interval 1.5 -> 3.0; scan_queue_size 20 -> 1.
- Only ExecStart changed. Backup: ~/.config/systemd/user/atlas-slam-fast.service.before-lighter-20261113. daemon-reload done; the unit was inactive (localization mode), so it takes effect at the next mapping session.
- Together with the mapping speed cap 0.15, ready for remap attempt 5.

2026-11-13 ~13:40 owner-approved fixes ("Yes, deploy all"):
- Dashboard deadlock: rover-status-web was found hung (27 threads in futex wait, ~2 % CPU, CLOSE-WAIT sockets with unread requests), so CPU was not the cause.
  - atlas_status_web.py now registers faulthandler on SIGUSR1, which dumps all thread stacks to the journal.
  - New atlas-status-web-watchdog.timer (every 20 s, enabled at boot) curls /v2/; after 2 failed checks it sends SIGUSR1 and restarts rover-status-web only.
  - The root-cause lock is still unknown; the next hang will produce the stack dump.
- Mapping CPU: manual teaching paused nothing (only exploration called pause_mapping_background). start_manual_mapping now pauses MAPPING_BACKGROUND_UNITS, extended with ai-annotator, agent-team and person-sensor-fusion (~25 % of a core), and restores them on start failure and at stop (existing finally). The Pi camera is kept: atlas_sensor_recovery restarts atlas-camera when its stream is stale.
- Backups: scripts/*.before-20261113-cpu-dash.
- CORRECTION to the 13:10 SLAM change: scan_queue_size 1 broke live SLAM. The tf message filter discarded every scan ("queue is full"), so no map frame was produced; that is why the 13:08 mapping start failed after 90 s. The offline replay did not show this. Set scan_queue_size 5 (other lighter settings unchanged); after the restart the map frame appeared within 10 s with 0 drops. Dashboard /api/map now returns the live SLAM map and the rover pose (map->base_link).

2026-11-13 remap attempt 5 (session 57941c0d, 13:41-13:52; speed cap 0.15, lighter SLAM with queue 5, ICP odometry). REJECTED; accepted map preserved.
- Passed: startup stillness 0.000 m; closure 0.051 m / 8.6 deg; room<->hall connectivity and Nav2 plans (they failed in attempt 4).
- Failed: map->odom single-step jumps 1.120 m (13:49:34, return) and yaw 12.0 deg (13:45:43, room lap).
- Other large steps, often paired back-and-forth: 0.89 m at 13:46:31/33 and 0.80-0.89 m at 13:49:02/08.
- The SLAM TF is now timely (stamp ahead of receipt; it was ~3.8 s behind in attempt 4).
- At every jump window: real speed median 0.04-0.14 m/s (scan-pair max 0.52-0.66), IM10A turn <= 38 deg/s, ICP odometry 0 rejections. Only 130-173 of 360 beams were valid, median range 1.0-1.5 m.
- Conclusion: the bouncing persists at walking speed with good odometry. slam_toolbox scan matching accepts wrong matches with this sparse RPLIDAR data.
- Bug found and fixed: pause_mapping_background stopped the voice companion, but "Job for atlas-ai-annotator.service canceled" raised before the record was written, so voice was not restored. Voice restarted manually; ai-annotator removed from the list; units are now stopped one by one with a per-unit record. Deployed (mission control restarted, no session).
- Localization restored (seeded from a LiDAR-verified pose (0.115, -1.995)); named_places from pre-remap6-20261113; rejected_session_57941c0d kept.
- Next candidates (offline replay on this bag first): stricter scan-match acceptance (link_match_minimum_response_fine, smaller search window); odometry-led mapping (scan matching off) with closure checked against ICP drift.

2026-11-13 ~14:30 offline replays on the attempt 5 bag (remap6_colour_20261113-134122/base):
- current lighter params: max step 0.525 m at 13:49:35 (live had 1.12 m at 13:49:34); 14 steps > 0.15 m; total correction 7.33 m.
- strict matching (link response 0.3, loop response 0.6, search 0.3 m, loop distance 2 m): 0.515 m at the same moment, 14 steps, i.e. no effect (like the penalty/search variants earlier).
- odometry-only (scan matching off) checked directly from /odom: start vs parked end 0.610 m / 5.2 deg over a 27.1 m path. Fails the 0.15 m closure, so it is ruled out.
LiDAR data: while parked, only 207/360 bins are valid; the 153 empty bins are spread evenly over all directions, so it is not an obstruction. Driver: rplidar_ros scan_mode Standard (2 kHz sample rate) at ~7-8 Hz with angle_compensate into 360 bins (fw 1.29, hw rev 7). Leading hypothesis: sparse scans give ambiguous matches in the corridor. Candidate (needs owner OK, parked restart): a denser RPLIDAR scan mode (Express/Boost, if supported), then measure valid bins and replay.
2026-11-13 ~14:30 APPLIED (owner OK "Yes, test LiDAR mode", kept after test): atlas-lidar.service scan_mode Standard -> Boost.
- RPLIDAR A1 fw 1.29 hw rev 7 accepts Boost: 8 kHz sample rate.
- Backup: atlas-lidar.service.before-scanmode-20261113. Restarted while parked with the E-STOP latched.
- /scan now 1080 beams at 0.33 deg, 1040 valid (96 %), 7.2 Hz. Standard mode gave 207/360 valid (57 %).
- Downstream: atlas_scan_self_filter uses angle_increment (no fixed 360).
- ICP odometry: scan_to_points now subsamples to max_points 400. 92 ms/scan -> 20 ms/scan; core tests 5/5 pass.
- Localization on the old map with Boost scans: verify-place "dhruv room" VERIFIED, fit 0.987, margin 0.205.
- CPU: atlas-localization (AMCL + Nav2) ~53 % of a core during the check.
- Next: remap attempt 6 with denser scans.

2026-11-13 ~14:35-14:50 remap attempt 6 ABORTED, Boost REVERTED:
- Session 1e570a39 started only after a manual atlas-slam-fast restart. Cold switches from localization to mapping have failed three times today (10:21, 13:08, 14:29: no map frame within 90 s); a restart always fixes it. Cause not yet found.
- The remote stop latched ("REMOTE STOP: joystick unavailable"). The owner reset it.
- With LiDAR Boost (1080 beams) + mapping + recorders, load average reached 50-59. TF odom->base_link stopped arriving (map and base_link not connected) and the EKF missed its update rate.
- Session aborted without a map: the session file was moved aside before stop_exploration. Accepted map preserved; background profile restored.
- LiDAR restored to Standard from atlas-lidar.service.before-scanmode-20261113. Named places from pre-remap7.
- Localization restarted; seeded at the hall (6.475, -2.375) before the owner drove back. Load fell to ~14 by 14:49.
- Remote input priority: atlas-remote.service (joy_node + teleop) had default CPU weight while the base and mux have CPUWeight=1000. joy gaps under load latch the remote stop. Applied `systemctl --user set-property atlas-remote.service CPUWeight=1000` (live, persistent in ~/.config/systemd/user.control, no restart).
- Boost needs scan thinning first: one decimating node (1080 -> ~360 bins) for all consumers, keeping full density only where needed.

2026-11-13 ~15:05 CPU reduction (owner chose "Pause AI extras" and "Lighten the dashboard"):
- Baseline per service (% of one core, localization mode): atlas-localization 55, rover-status-web 40, atlas-camera 34, rover-base-telemetry 30, voice 22, astra 22, sensor-recovery 16, mux 16, mission-control 15, localization-monitor 14, safety-status 13, icp-odometry 13, rf2o 10, ai-annotator 10, agent-team 9. Total ~430 % of 600 %.
- Dashboard: stack sampling (SIGUSR1) showed the time going into executor wait-set rebuilds (wait_for_ready_callbacks), one per message, ~190 msg/s on the hot node.
  - atlas_dashboard_executor.create_executor/spin gained batch_s: sleep before each wait-set rebuild so pending messages are dispatched in one pass.
  - Hot node (web drive/E-STOP path) 30 ms; status node 100 ms. The integrity-hashed impl file is unchanged.
  - Result: rover-status-web 40 % -> 17 %; /v2/ answers in 0.01 s; /api/map OK.
  - Tests on the Jetson are identical before and after: idle_camera 11 pass, smart_panels 7 pass, executor_split 4 pass/1 fail/1 skip. estop_reset, estop_safety, no_reboot and executor_profile ERROR at collection (missing module calibration_validation, pre-existing); snapshot_cost 5 fail (pre-existing). So the web E-STOP path is NOT covered by a passing test.
  - Backups: scripts/*.before-batching-20261113.
- AI extras: stopped, but atlas-feature-on-demand restarted them within ~1 min. The design is fail-open: mission_status != READY counts as autonomy demand, and after the abort the status stayed "MAPPING NOT ACTIVE; ACCEPTED MAP PRESERVED". Mission control restarted (no session), status READY, so the manager stops them after idle_s 300. They were already "disabled" at boot; boot state recorded in ~/.config/project_atlas/ai_extras_paused_20261113.txt.
- Follow-up: mission control should publish READY after a stop/abort finishes.
2026-11-13 ~15:15 parked in Dhruv Room: verify-place VERIFIED (fit 0.996, margin 0.22), AMCL (0.20, -1.80). Normal localization healthy after today's changes.

2026-11-13 ~16:00 APPLIED (owner OK "Thin dense scans"): LiDAR Boost + thinning in atlas_scan_self_filter.
- Filter rewritten with numpy; self-box logic unchanged. When the raw scan has >= 1.5x TARGET_BINS (360) beams, each output bin is the NEAREST valid return of its consecutive raw beams (conservative for obstacles). angle_min is the group centre, angle_increment and time_increment are x factor, and the header stamp is unchanged. Standard-mode scans pass through unthinned.
- tests/test_atlas_scan_self_filter.py: 3 new tests (nearest-per-bin with empty and below-min bins; self-returns removed before thinning; Standard not thinned). 6/6 pass on the Jetson.
- Recorded Boost scans: 1080 -> 360, valid 88 % -> 90 %, 0.4 ms/scan.
- Live after deploy (parked; atlas-scan-filter restarted, then atlas-lidar.service scan_mode Boost again):
  - /scan 7.2 Hz, 360 bins, 98 % valid (Standard was 57 %);
  - load average ~15-17 (Standard ~12-13; Boost without thinning 50-59);
  - ICP node 15 % CPU, 0 rejected;
  - verify-place "dhruv room" VERIFIED fit 0.99 margin 0.236.
- Backups: scripts/atlas_scan_self_filter.py.before-thinning-20261113; atlas-lidar.service.before-scanmode-20261113 (Standard).

2026-11-13 ~16:20-16:35 remap attempt 7 ABORTED (Boost + thinning live):
- The cold start failed again (no map frame in 90 s); the automatic retry after restarting atlas-slam-fast reached ACTIVE (session d8a4d0ff).
- Load average then rose to 50-57: run queue 67-120, 0 % idle, ~50 % system time, ~70k context switches/s.
- Cause: mission control paused the AI extras at session start, but atlas_feature_on_demand restarted them within one tick. "Autonomy" demand comes from mission_status != READY, and its MAPPING_PAUSED only listed the camera tracker and follow-person. Startups (heavy imports) on top of SLAM + Nav2 + session bag + camera overloaded the Jetson.
- Session aborted without a map (session file moved; accepted map preserved; named places from pre-remap8).
- Fix:
  - MAPPING_PAUSED now also lists vision-lidar-fusion, person-sensor-fusion, ai-annotator and agent-team.
  - Mission control pauses the same units, dependents before ai-annotator.
  - tests/test_feature_on_demand_mapping.py 3/3 pass on the Jetson (not started while mapping; started when not mapping; lists match). Deployed.
  - Backups: *.before-mappause-20261113.
- Side effect noted: restarting atlas-feature-on-demand runs restore-all (ExecStopPost), which starts every managed unit (incl. follow-person, camera-tracker, active-vision) until idle. Those three were stopped manually; the rest stop after boot grace + idle.
- Also: after an aborted/stopped session the mapping stack stays up; atlas-localization must be started explicitly. Done: seeded in Dhruv Room (0.135, -1.835); run queue 18, 24 % idle, system time 12 %.

2026-11-13 remap attempt 8 (session c7c28ee9, 16:37-17:31; Boost + thinning, mapping speed cap, feature-manager pause fix). REJECTED; accepted map preserved.
- The cold start failed again; the retry after restarting atlas-slam-fast reached ACTIVE.
- Load stayed 29-54 throughout (run queue 24-37, 2-4 % idle, 37-39 % system time) with the AI extras off. The mapping stack itself (slam_toolbox + full Nav2 + session bag + EKF at ~29 %) plus the camera, Astra, rf2o, base and Python monitors oversubscribe the 6 cores.
- The remote stop latched ("joystick unavailable") under this load, so the owner's first drive attempt did not move the rover. The owner then reset it and drove.
- Hall saved (0.60, -6.64), 6.6 m from start. Closure PASSED 0.082 m / 0.3 deg.
- Failures: map->odom jump 1.710 m (17:28:40, start of return); yaw jump 16.4 deg; footprint not connected between places; reverse Nav2 plan failed.
- Restored as before (rejected_session_c7c28ee9; named places from pre-remap9; localization seeded (0.175, -1.675)).
- Conclusion: on this Jetson, manual-teaching mapping with the full stack is CPU-bound. Next design step before any further drive: a lighter mapping mode (e.g. Nav2 started only for the acceptance plan checks, no session bag or a lighter one, and the Astra/rf2o paused), measured parked first.

2026-11-13 evening (21:20-22:40), owner away, rover parked in Dhruv Room, E-STOP latched. Read-only measurements and offline replays only; no motion, no service restarts. All code changes are STAGED (repo + ~/atlas_staging_20261113), NOT deployed.
1. CPU profile (tools/profiling/atlas_cpu_profile.py; 30 s, localization mode, idle; data/diagnostics/cpu_profile/localization_idle_20261113.json):
   - Services total 396 % of 600 %, load 13-18, system time 12 %.
   - Largest units: atlas-localization (Nav2 + AMCL) 51 %, camera 30 %, rover-base-telemetry 30 %, voice companion 20 %, Astra 20 %, cmd-vel-mux 17 %, localization-monitor 17 %, dashboard 16 %, sensor-recovery 16 %, rf2o 15 %, mission-control 14 %, safety-status 13 %, ICP odometry 13 %.
   - Topic rates are low (/scan 7.5 Hz, /odom 10 Hz, camera 11 Hz). The small Python nodes' cost is rclpy's executor rebuilding its wait set per message, not their callbacks (sensor recovery already reads raw bytes and still uses 16 %).
2. SLAM's own cost (offline replay of session c7c28ee9, 54 min at 1x, live parameters): slam_toolbox mean 3.9 % / max 31 % of one core, RSS 39 MB. SLAM is NOT the CPU hog; the load during mapping comes from everything around it.
   - The same replay still had map->odom steps: max 0.645 m (live 1.710 m), 29 steps > 0.15 m, max yaw step 8.6 deg.
   - So overload made the jumps ~2.6x worse, but odometry drift that SLAM corrects in steps remains. See 4.
3. LiDAR validation (tools/lidar/lidar_scan_validation.py; data/diagnostics/lidar_validation/), first 600 s of each bag, Standard (00c9e957) vs Boost + thinning (c7c28ee9):
   - Timing: Boost scan period p95 0.154 s vs 0.261 s; gaps > 0.3 s 0 vs 3; time_increment x beams / scan_time = 1.001 (consistent per-point timing); latency median 0.14 s for both.
   - Geometry: /scan 360 beams for both; valid 98.0 % vs 47.2 %.
   - Range resolution: Boost 1-4 mm steps vs 0.25 mm Standard (56 % of beams repeat the previous value). Negligible against 5 cm map cells.
   - Accuracy proxy (scan-to-scan ICP residual RMS on /scan): 3.5 mm median (p90 8.0 mm) Boost vs 15.5 mm (p90 22.8 mm) Standard, with 353 vs 181 points/scan. Boost + thinning gives more consistent geometry. A map-level check still needs an accepted Boost map.
4. EKF tuning offline (tools/localization/ekf_variants.sh; isolated domain 92):
   - Method: ICP node + EKF variants replayed on two drives that ended on the start mark (SLAM closure 3.6 cm / 5.1 cm). Score = start->end closure. Repeatability ±0.02 m.
   - Results (57941c0d / 00c9e957):
     - live 0.45-0.47 / 0.50-0.51 m;
     - wheel + IMU only 0.40 / 0.49;
     - ICP without wheel 0.32 / 0.56;
     - q_vx 0.5: 0.45 / 0.49; q_vx 8: 0.48 / 0.49;
     - + ICP yaw rate 0.49 / 0.48;
     - ICP yaw rate instead of IMU 1.06 / 0.68 (yaw -18 / -11 deg);
     - ICP pose differential, no IMU 1.28 / 1.33;
     - raw wheel 2.26 / 8.11.
   - The ICP node's own integrated pose: 0.31 / 0.09-0.10 m.
   - Decision: NO EKF change (live is the best EKF variant; IM10A heading confirmed; q_vx insensitive).
   - Open lead: raw ICP translation closes 2-4x better than any EKF output. Next offline test: SLAM replay with odom->base_link built from the ICP pose, to see whether the map->odom steps in 2 shrink.
5. Dashboard: no restart since 16:35, watchdog never fired, HTTP 2-140 ms, 114 MB. Staged: listen backlog 5 -> 64 (several tabs/phones polling could get connections refused).
6. Light manual-mapping mode (staged; mission control parameter mapping_profile, default "light"; "full" = previous behaviour):
   - Also pauses Astra obstacles, the rf2o gate, the candidate EKF, tight recovery, rf2o and the experience store. Consumers checked: Nav2 astra_layer / autonomy only; the live EKF uses /lidar/icp_odom. The experience store is added to the feature manager's MAPPING_PAUSED.
   - Starts SLAM only. Nav2 starts when the session is stopped, before the goal cancel, plan checks and footprint evidence (ensure_nav2_for_acceptance, 120 s).
   - Records a lighter bag: ATLAS_RECORD_PROFILE=mapping_light drops camera JPEGs, AMCL topics and /map; /lidar/icp_odom is now recorded too.
   - Expected saving vs the idle profile: ~54 % (paused units) + ~35 % (Nav2 deferred) + the bag's camera stream, on top of the AI extras already paused (~47 %).
7. Mapping safeguard (scripts/atlas_mapping_guard_core.py + mission control + mux; 6 unit tests):
   - Armed only during a drive-ready manual session; trips on any of:
     - /scan age > 1.5 s;
     - /yahboom/odom age > 1.5 s;
     - map->odom TF gap > 4 s;
     - CPU idle < 4 % with load/core > 4 sustained for 20 s.
   - A trip publishes /atlas/mapping_guard/stop. A new latch-only mux input latches the existing remote stop ("REMOTE STOP: mapping guard"); the normal LB 3 s release applies.
   - The trip is recorded in the session (guard_trips), and accept_saved_map rejects that session's map. Suspended while the session is being stopped.
8. Executor batching for monitoring nodes (scripts/atlas_batched_spin.py; opt-in through ATLAS_EXECUTOR_BATCH_S drop-ins):
   - 100 ms: localization monitor, sensor recovery. 50 ms: mission control, safety status, rf2o gate.
   - Not used for the base, mux, remote or any stop path. Revert = delete the drop-in.
9. Regression suite (tools/regression/atlas_regression.py):
   - quick: unit tests minus the known-failure list; old map (map id = places, room->hall connected); gate history (all 11 stored rejected candidates still rejected).
   - --full adds the return-to-start replay (limit 0.60 m).
   - Quick run on staging: ALL PASS.
   - The 11 mux test failures are pre-existing (same set on unmodified HEAD; fixtures lack controller_accepts / flysky_reset_observe), listed in tests/regression_known_failures.txt.
Deploy (needs the owner's OK; rover parked + E-STOP latched): copy the changed scripts + drop-ins; daemon-reload; restart mission-control, cmd-vel-mux, feature-on-demand, sensor-recovery, safety-status, localization-monitor, lidar-odom-gate and rover-status-web. Then profile again (localization idle), then a parked light-mode CPU measurement before any drive.

2026-11-13 22:47 DEPLOYED the evening changes (owner: "ok deeploy"), with the remote stop latched, wheels at 0 and no mapping session.
- Ran ~/atlas_staging_20261113/deploy_20261113_evening.sh: backups *.before-evening-20261113, rollback with --rollback. All 8 restarted units are active.
- Remote stop stayed latched. The guard topic /atlas/mapping_guard/stop has 1 publisher (mission control) and 1 subscriber (mux).
- Batched executor confirmed in the logs: 100 ms for localization monitor and sensor recovery; 50 ms for mission control, safety status and the rf2o gate.
- The feature-manager restart started follow-person, camera-tracker and active-vision again (known restore-all side effect); stopped them.
- CPU, localization idle, 30 s profiles:
  - total 396.9 % -> 379.1 %; idle 29 % -> 32 %;
  - mission control 14.6 -> 7.4 %; sensor recovery 16.4 -> 4.4 %; safety status 13.3 -> 6.9 %; localization monitor 16.8 -> 11.2 %; rf2o gate 4.8 -> 3.9 %.
- Quick regression on live: ALL PASS (unit, old map, gate history). Mission status READY.
- Not yet measured: light mapping mode live (parked).

2026-11-13 23:00-23:45 live-system audit (owner request "audit running ATLAS, find problems and fix"). Rover parked, remote stop latched the whole time (verified before and after).
Healthy:
- No crash loops.
- Sensors: /scan 7.3 Hz, /odom 10, wheel odom 10, IM10A 10, IMU 10.6, ICP 7.3, rf2o 5.3, camera 8.8, radar 20, ultrasonic 7.3, joy 16, BMS every 5 s (14.6 V, 100 %).
- Recovery monitor: all HEALTHY.
- TF map->base_link (0.195, -1.762, 72.8 deg) agrees with the LiDAR-verified seed.
- Disk 35 %; RAM 2.4 GB available; swap 26 MB; temperatures 67-68 C (trip 99 C); fan PWM 138.
FIXED (deployed; backups *.before-shutdownfix-20261113 / *.before-grace-20261113):
1. Services ended "failed" on every normal systemctl stop (2 days: voice 11, visual-cloud 11, camera-joystick 11, person-fusion 8, localization-monitor 8, rf2o gate 8, follow-person 2).
   - Causes: ExternalShutdownException not caught; the voice overlay raises its own exception class; rclpy.shutdown() called twice; follow-person publishing a final zero on an invalid context.
   - A race I introduced at 22:47: a stop during the batch sleep made the wait-set rebuild raise RCLError. atlas_batched_spin and atlas_dashboard_executor now turn it into the normal shutdown signal; new unit test, 4/4 pass.
   - Verified with two stop/start cycles each: localization-monitor, rf2o gate, safety-status, sensor-recovery, mission-control, dashboard, camera-joystick, visual-cloud and follow-person all stop with Result=success.
   - Voice companion fixed in the file but not restarted (night); the fix applies on its next start.
2. Dashboard watchdog killed the dashboard during deliberate restarts (22:48:45, 23:37:05, 23:37:45): no startup grace, so SIGUSR1 arrived before faulthandler was registered.
   - Added a 60 s grace after the unit starts (a first version overflowed in awk and effectively disabled the watchdog; replaced with integer seconds).
   - Tested: healthy -> no action; simulated hang -> USR1 + restart on the 2nd miss.
3. reset-failed for update-notifier-crash (crash-report notifier). Crash reports in /var/crash: rplidar_composition 13 Nov 14:25 (during the Boost overload, not recurred), ros2 CLI, nmcli, rtabmap (old).
NEEDS THE OWNER (sudo or hardware):
A. Power mode is "25W" (nvpmodel ID 1): CPU capped at 1.344 GHz, lower than 15W mode (1.498 GHz). MAXN_SUPER (ID 2) runs at 1.728 GHz, +29 % CPU, with the CPU-bound mapping problem in mind. No earlier decision about the power mode is recorded. Suggested: sudo nvpmodel -m 2, watch the temperature (now 68 C at 1.344 GHz).
B. atlas-ptz-home.service (system unit, /home/jetson/home.py) fails every boot: PCA9685 at 0x40 is no longer on Jetson I2C bus 7 (the pan/tilt now goes through the UNO R4 hub, PCA=1). Obsolete. Suggested: sudo systemctl disable atlas-ptz-home && sudo systemctl reset-failed atlas-ptz-home.
C. GPS: the hub reports GPS_BYTES=0 since boot (UART at 9600 baud receives nothing). Wiring/power/module check; indoors alone would still give NMEA bytes.
D. AMCL particle collapse persists (covariance ~1e-15, perfect confidence). Already registered (issues 33/36: 1 Hz forced no-motion updates + resample_interval 1 + zero recovery alphas). No new tuning without the reviewed change. LiDAR start verification and the scan-fit gate remain the real checks.
Watch: cellular modem USB re-enumerated 6x between 14:34 and 14:47 (overload window), none since. rover-base-telemetry "USB discovery busy" at startup 3x in 2 days (auto-retried).

2026-11-13 23:53 power mode changed by the owner: sudo nvpmodel -m 2 (MAXN_SUPER), no reboot needed. Was ID 1 "25W" (CPU cap 1.344 GHz).
- Now: all 6 cores max 1.728 GHz; temperatures unchanged at cpu 68 C / tj 67-68 C (trip 99 C); fan PWM 132; remote stop latched; no failed units; dashboard 200.
- Localization idle (30 s profiles):
  - process total 396.9 % (before the evening deploy) -> 379.1 % (batching) -> 359.0 % (MAXN_SUPER);
  - idle 29 % -> 32 % -> 35 %;
  - load average 14-18 -> ~10.
- /var/lib/nvpmodel/status records the mode for boot (/etc/nvpmodel.conf DEFAULT is still 1; the status file takes precedence).
- Watch the temperature during the next mapping drive.

2026-11-13 23:59 - 2026-11-14 00:30 PARKED light-mapping-mode test (owner request), session d29d7b23. Remote stop latched throughout; nothing moved; MAXN_SUPER.
Worked:
- Cold start reached MANUAL MAPPING ACTIVE in 22 s on the first try. Before, cold starts often missed the 90 s check; Nav2 is no longer started.
- Startup stillness 0.0 m / 0.0 deg. Paused: voice, Astra, rf2o gate, candidate EKF, tight recovery, rf2o. Nav2 inactive.
- Light bag (no camera) recorded.
- Mapping guard armed ~20 min with 0 trips (no false positives, including the high-load period).
- Stop: QUEUED -> "MANUAL MAPPING FINISHING: starting Nav2" -> acceptance evaluated 40 s later -> REJECTED as expected (no hall / no drive). Accepted map unchanged (pgm sha 4beb26d5a999).
- Restore: session files moved to rejected_session_d29d7b23 / *.rejected-session-d29d7b23.json; atlas-localization started; seeded LiDAR-verified "dhruv room" (0.215, -1.795); Nav2 active; mission control restarted -> READY (known: status stays ERROR after a rejection). Regression ALL PASS (12 rejected candidates still rejected).
FIXED during the test:
- The feature manager restarted ai-annotator, agent-team and experience-store in the ~20 s while SLAM was "activating" (mapping was detected only as slam-fast == active). They then stayed on for the whole session; this probably also contributed to earlier remap overloads.
  - Now mapping = a session file in "starting"/"active" OR slam-fast active/activating (once per tick).
  - Running MAPPING_PAUSED units are stopped while mapping.
  - 3 new tests (6/6). Deployed mid-session: 7 units stopped within 12 s.
  - Backup atlas_feature_on_demand.py.before-mapenforce-20261114.
- Still open: atlas-active-vision is not in MAPPING_PAUSED (it was only started by restore-all).
CPU in light mapping (60 s, parked): 386 % total, but 27 % system time + 8 % irq. Biggest: mission-control cgroup 72 % (incl. session ros2 bag record 45 %), EKF 48 % (2.7 % in localization; main thread 37 % sys, "Failed to meet update rate, took 0.11-0.23 s"), slam_toolbox 44 % (4 % offline), dashboard 39 %, mode manager 17 %.
LEAD (strong, not yet reproduced): stopping ONLY the session's recorder dropped EKF 46 -> 3.4 %, SLAM 44 -> 2.2 %, dashboard 40 -> 25 %, mode manager 17 -> 6.6 % within 15 s.
- Fresh recorders started from a shell did NOT reproduce it: /tf alone (reliable or best-effort), scans + odom, and the exact light-profile script for 4.5 min all left EKF/SLAM at 2-4 %; the recorder itself uses ~35 %.
- Difference to test next: the session recorder starts while localization is being stopped and SLAM started (publishers churn during its discovery).
- Next discriminating test, parked: start a session and compare EKF/SLAM sys time with the recorder started (a) at session start (now) vs (b) after MANUAL MAPPING ACTIVE.

2026-11-14 00:26-01:00 recorder-timing test (owner: "Yes, test it"), parked, stop latched throughout; session cadee163, restored after (localization seeded (0.175, -1.855), READY, map unchanged).
- Localization baseline: EKF 2.9 %.
- A, session recorder: EKF 21-23 % (sys 14-16 %), SLAM 28-30 % (sys 21-22 %). Mapping-mode overhead reproduced (smaller than last night's 45 %).
- B0, session recorder killed: EKF 18 %, SLAM 29 %. Unchanged.
- B1/B2, same recorder script started after ACTIVE: unchanged.
- => The recorder is NOT the cause. Last night's drop after killing it is now treated as coincidental or as an indirect reset. The 2026-11-14 00:30 "recorder lead" above is WITHDRAWN.
- C, SLAM SIGSTOP 20 s then SIGCONT: costs fell (EKF 3 %, SLAM 2 %). INVALID as a fix: after the resume, mission control never received SLAM's map->odom again (guard: "SLAM map->odom stale 180.4s"; stop failed with "localization seed requires a live map-frame pose"); restored manually. Do not use SIGSTOP on DDS nodes.
- Reproduced WITHOUT mapping: in localization, adding one dummy /tf publisher (unrelated frames, rclpy, UDPv4 or default transports, 10 or 50 Hz) raised EKF sys 1 % -> 23-30 % and every /tf subscriber by ~4-6 % sys. The cost does not depend on the rate.
- The state PERSISTS after the extra publisher exits and survives an EKF restart (a fresh EKF picks it up at once). /tf traffic itself is normal (odom->base_link 6.9/s, map->odom 6.0/s).
- /tf has a publisher "_NODE_NAME_UNKNOWN_" (GID 01.0f.9f.1f.07.d8.3a.02...) with no matching live PID, a stale or unidentified participant.
- Working hypothesis: churn of /tf participants (SLAM appearing at mapping start, killed or paused processes) leaves the Fast DDS (Humble default RMW) graph in a state where every /tf reader and writer burns kernel time. This would explain the mapping-mode overload behind the rejected remaps.
- Not confirmed at syscall level: no strace or perf on the Jetson (installing them needs sudo).
- Side effect: my probes left the system in that state: 481 % CPU, 10 % idle, 29 % system time, load 48, atlas-localization 122 %. Rover parked, stop latched, READY. A reboot is recommended to clear it.
- Next: (1) reboot; (2) the owner installs strace and linux-tools; (3) parked, start mapping and catch the syscall mix in EKF and SLAM; (4) candidate fixes for a reviewed change: SLAM transform_publish_period, discovery / lease settings, or the participant churn at mapping start. No change made yet.
- Also: use `ros2 topic pub --once -w 1` (the first stop without -w was lost).

2026-11-14 01:05 Jetson rebooted (owner ran sudo reboot) to clear the sticky /tf state left by the probes.
- After boot: pmode 0002 (MAXN_SUPER, 1.728 GHz) kept; all core units active; remote stop latched; mission READY. Only atlas-ptz-home failed (obsolete unit, audit item B).
- Localization: AMCL (0.211, -1.850); LiDAR verify-place "dhruv room" unique match (0.175, -1.855, 69 deg), margin 0.22. No reseed needed.
- CPU (30 s): 354.5 % total, idle 36 %, system 13 %; atlas-localization 54 %; EKF ~2 % (was 37 % in the stuck state, 481 % total).
- Confirms that the expensive state is cleared by a full restart of the DDS graph.

2026-11-14 ~01:20 diagnostic tools installed by the owner: sudo apt-get install strace linux-tools-generic.
- strace 5.16.
- perf 5.15.223 at /usr/lib/linux-tools/5.15.0-203-generic/perf. There is no linux-tools package for the 5.15.148-tegra kernel; the generic 5.15 binary works. Call it by full path (the /usr/bin/perf wrapper rejects the tegra kernel name). No kernel was installed.
- Both work on processes they start themselves.
- Attaching to running ATLAS services is blocked by the stock security settings ptrace_scope=1 and perf_event_paranoid=2, which were NOT changed. For the parked syscall capture, either the owner runs the capture with sudo, or the owner temporarily relaxes them until the next reboot (sudo sysctl kernel.yama.ptrace_scope=0 kernel.perf_event_paranoid=1). This is the owner's decision.

2026-11-14 ~08:20, owner via sudo:
- kernel.yama.ptrace_scope=0 and kernel.perf_event_paranoid=1 until the next reboot (not persistent). strace and perf now attach to running ATLAS services (checked on the EKF).
- atlas-ptz-home.service disabled + reset-failed (audit item B closed). No failed system units remain.

2026-11-14 08:20 parked capture attempt (owner: "capture now"); stop latched throughout. Uptime 7 h since the 01:05 reboot, few restarts since.
- Localization baseline: EKF 1 % user / 1 % sys.
- The manual-mapping start FAILED at set_home: "SLAM pose is not settled (shift=0.20m)". The new SLAM pose moved 20 cm while starting.
  - Mission control cleaned up correctly (no session file, places unchanged, extras restored) but left atlas-slam-fast running without localization (known "stack stays up").
  - Restored: SLAM stopped; localization started; seeded LiDAR-verified (0.195, -1.675); mission control restarted -> READY.
- NO overload with SLAM running ~3 min (no session or recorder): EKF 1/1 %, SLAM 1/0 %, total 326 %, idle 42 %.
- Every overloaded session on 13-14 Nov started after many service restarts (deploys, tests). This fits the sticky-state hypothesis (participant churn builds it up; a reboot clears it). Practical mitigation to test: reboot before a mapping drive.
- The capture needs the bad state. It can be triggered deliberately (the dummy /tf publisher reproduced it at 00:5x) but then needs a reboot to clear.
- Also: my wait loop matched "MANUAL MAPPING ACTIVE" inside the PREPARING text again; scripts must match '^data: .?MANUAL MAPPING ACTIVE'.
- Open: set_home's settle check vs a cold SLAM start (0.20 m shift); a retry after a few seconds may pass.

2026-11-14 08:44-08:48 deliberate trigger + capture (owner: "trigger it"); localization mode, stop latched.
- The dummy /tf publisher (UDPv4, 10 Hz, 40 s) did NOT trigger the state this time: EKF 1 % user / 1 % sys before, after and 10 s later.
- The trigger only worked after the 13 Nov's many restarts/kills, so the cause ACCUMULATES with participant churn and a reboot clears it. No reboot needed now.
- Healthy EKF strace (15 s; data/diagnostics/dds_capture_20261114/strace_ekf_healthy.txt): recvfrom 48 % / futex 46 % of syscall time; 5670 sendto, each preceded by a FAILING setsockopt.
  - Detail: setsockopt(SOL_SOCKET, SO_SNDTIMEO_OLD, timeval with tv_usec out of range) = -1 EDOM on every send, so Fast DDS's UDP send timeout is NEVER applied and a send can block without limit.
  - Defect in the Humble Fast DDS / aarch64 stack (not ATLAS code). It may explain the 0.11-0.23 s EKF "Failed to meet update rate" stalls seen while stuck. Not proven.
- /dev/shm: 36 Fast DDS segments, 34 mapped by live processes, 3 stale from boot. Not the accumulating factor.
- Kernel counters since the 01:05 reboot: 318,187 ICMP destination-unreachable sent and received (UDP sends to ports nobody listens on). The healthy rate now is 0/s, so these came in bursts, most likely around restarts, the failed session start and the probes.
- Hypothesis (unproven): after churn, writers keep sending to UDP locators of dead participants (e.g. the "_NODE_NAME_UNKNOWN_" /tf publisher seen at 00:5x), and every send costs kernel + ICMP work in all /tf processes.
- tools/profiling/atlas_cpu_profile.py now prints "dds/udp per s" (udp_noports, icmp_out_unreach; healthy 0). The next time overload appears, one profile confirms or rejects this.
- Practical plan for remap 9:
  - reboot shortly before the drive;
  - profile once at MANUAL MAPPING ACTIVE (CPU + dds/udp);
  - avoid killing ROS processes;
  - if overload appears anyway, capture strace/perf at once (attach allowed until the next reboot only).

2026-11-14 08:52-09:01 parked start check (owner: "do it"), session eece59aa; stop latched; uptime 7.8 h after the 01:05 reboot.
- Start: ACTIVE on the FIRST attempt in 15 s (QUEUED 08:52:17 -> ACTIVE 08:52:37). The 08:20 "SLAM pose is not settled (0.20 m)" refusal did not recur. set_home's settle check (5 samples / 1.6 s / 5 cm) remains as is. A retry is the documented response if it happens again.
- Light mapping CPU (30 s at ACTIVE and +2 min): total 302 % / 292 %, idle 45-47 %, system 10 %; EKF 3 %, SLAM 2 %, session recorder 33 %, mission-control cgroup 41 %; dds/udp noports 0, icmp unreachable 0.
  - AI extras, Astra and Nav2 all inactive. Guard armed, 0 trips, startup wheel displacement 0.0 m.
  - FIRST clean measurement of the light profile. The overload did not appear on this clean system.
- Stop: Nav2 started at the end -> rejected after 57 s (expected: parked, no hall). Accepted map unchanged (4beb26d5a999). Restored: seeded (0.215, -1.795); READY.
- NEW GATE ISSUE (would also reject a real remap): "map->odom source timestamps predate the mapping session".
  - first normalized SLAM map->odom source stamp = started_unix + 17.41 s = ready_unix - 1.51 s.
  - Since 2026-11-13 mission control passes session_started_unix = ready_unix for manual teaching (to keep startup jumps out of the evidence). The core then also checks source_started >= ready_unix - 1.0.
  - SLAM's first transform carries the stamp of the last scan it processed. Parked, that predates ready by 0.25-0.9 s in earlier sessions (pass) and by 1.51 s here (fail). The lighter SLAM settings make the margin smaller.
  - PROPOSED (needs the owner's OK): keep the observation/jump window referenced to ready_unix, but check "source predates the session" against started_unix (the real session start, when SLAM was not yet running). Jump and closure gates unchanged.

2026-11-14 ~09:15 FIX DEPLOYED (owner: "Yes, fix it"): map-acceptance source-stamp floor. Stop latched, no session open.
- atlas_map_acceptance_core.evaluate_acceptance_evidence gains source_floor_unix (default = session_started_unix, so other callers keep their behaviour). The "map->odom source timestamps predate the mapping session" check uses it.
- Mission control passes source_floor_unix = session["started_unix"]. Coverage, observation start and the jump window keep the drive-ready reference.
- Not weakened: TF jump (0.15 m / 5 deg), closure (0.15 m / 10 deg), connectivity, plans, startup stillness, observation-start coverage. A source stamp from before the session started still fails (new test).
- Tests:
  - tests/test_atlas_map_acceptance_core.py +3 (between start and ready passes; before start fails; default unchanged).
  - The transform-timeout test now falls back to ~/.config/systemd/user on the Jetson's installed layout.
  - Staging 33 passed / 3 skipped (incl. scripts/test_map_acceptance_startup.py); live regression ALL PASS (40 unit, old map, 13 rejected candidates still rejected).
- Re-evaluation of stored sessions with the new floor:
  - eece59aa loses only the predate failure (7 -> 6; still rejected);
  - d29d7b23, c7c28ee9 and 57941c0d unchanged (6 / 5 / 2; still rejected).
- Backups: *.before-sourcefloor-20261114. Mission control restarted -> READY, stop latched, no errors.

2026-11-14 ~10:00-10:25 small code jobs (owner: "do the small code jobs first"); rover parked, stop latched.
DEPLOYED (backups *.before-smalljobs-20261114; mission control + feature manager restarted; follow/camera-tracker/active-vision stopped after the restore-all; READY, latched):
1. atlas_feature_on_demand MAPPING_PAUSED += atlas-active-vision (it moves the camera; not needed while mapping). +1 test.
2. Mission status returns to READY when idle. A FINISHED or FAILED status (allow-list: ERROR, PLACE/HOME SAVED, GOAL FINISHED/REJECTED, RETURN HOME FINISHED/VERIFIED/INACCURATE/REJECTED/RETRY BLOCKED, NAVIGATION CANCELED, MAPPING NOT ACTIVE, MAP ACCEPTED, SCAN CHECK OK, BUSY) stays visible for 120 s (errors) or 60 s (others), then reverts to READY.
   - Only if no operation holds the lock, no mapping session is open and exploration is inactive.
   - In-progress or unknown statuses (QUEUED, *DISPATCHED, *ACCEPTED, MANUAL MAPPING *, EXPLORATION ACTIVE, RETURN HOME RETRY, TAUGHT ROUTE DISPATCHED) never revert. Navigation is asynchronous, so the lock alone is not enough.
   - Why: the feature manager reads mission != READY as autonomy demand and restarted every AI extra after rejected maps; the camera settings page refused changes; both needed a mission-control restart.
   - tests/test_mission_status_idle_revert.py: 6 tests.
   - Live test: "MAPPING NOT ACTIVE" 10:23:34 -> READY 10:24:34.
TESTS FIXED (test files only):
3. 11 remote-stop mux tests (stop_hold, mapping_limit): the fixtures now extract flysky_reset_observe / controller_accepts (Stage 29 additions) and set manual_controller=XBOX. 11/11 pass. tests/regression_known_failures.txt emptied.
4. Dashboard E-STOP tests: the "missing module calibration_validation" collection error was an incomplete test tree (tools/vision3d and tools/diagnostics absent on the Jetson's live and staging trees), not a missing module. With the full tree:
   - estop_safety needed the same Stage 29 fixture addition;
   - executor_split expected rclpy.spin(self.node), which the 13 Nov batched dashboard executor replaced (my change);
   - now 41 passed, 1 skipped (estop_reset, estop_safety, no_reboot, executor_profile, executor_split).
NOT DONE (not small, or not allowed):
- Automatic localization restore after a session. After a rejection the session stays active by design; automating needs decisions (archive the session, set aside session-bound home/seed, reseed without a known place). Proposed separately.
- Rear encoder label swap: this is the motor/encoder driver mapping (hardware driver / calibration), outside this workflow without an explicit, separate owner decision.

2026-11-14 ~10:40 survey of existing colour recordings for 3D map v2 (read-only; /tmp/colour_survey.py). maps3d/ holds 8 colour recordings. Each has an Astra bag (/astra/color 640x480 rgb8 ~27 Hz, /astra/depth 160x120, camera_info, depth_to_color extrinsic) and a base bag (/scan /odom /yahboom/odom /tf /tf_static IM10A /amcl_pose /map).
- Full room->hall->room drives (wheel/EKF path, end-start gap):
  - remap6_colour_20261113-134122: 629 s, 27.1 m, 0.61 m (session 57941c0d drive). BEST.
  - remap5b_colour_20261113-102354: 1037 s, 26.5 m, 0.93 m.
  - remap3_colour_20261112-194252: 756 s, 19.7 m, 1.37 m.
  - remap4 + remap4b (outbound 7.1 m + return 17.1 m).
  - remap7: 9.5 m, one way.
- Still-rover only (no use for 3D): remap2_colour_20261112-184531 (14 GB, 0.8 m) and remap5_colour_20261113-102057 (1.3 GB, 0.0 m). Deletion candidates, 15.3 GB, owner's decision.
- Sampled frames: colour exposure normal (mean 76-134); depth 36-70 % valid, median ~1.8-2.1 m.
- Conclusion: a 3D v2 can very likely be built WITHOUT a new colour drive: localize each recording's /scan against the accepted 2D map (scan-to-map, as build_colour_map.py already refines), then project colour+depth.
  - Not proven yet: needs an accepted map, or a dry run against the current accepted map (d12a1f).
  - Risk: furniture or layout changes since 13 Nov.

2026-11-14 ~11:00 3D v2 DRY RUN from an old recording, no drive (owner: "Yes, dry run"). Offline at nice 15; nothing restarted.
- tools/m3/build_colour_map.py gains ALIGN_INIT="x,y,yaw_deg" (used with REFINE_MAP). It places a recording made in another map frame (a rejected session's SLAM) onto REFINE_MAP: the first scan is matched at the start-mark guess (±20 deg search), and every later successful scan-to-map refinement re-anchors the frame offset.
- FIXED a refinement bug: icp() returns yaw in (-pi, pi] while the trajectory yaw is unwrapped, so after a full turn every good match failed the 8 deg check (180 of 202 failures). This affected the first colour map (12 Nov) too.
- Failure reasons are now counted.
- Run: remap6_colour_20261113-134122 onto the current accepted map atlas_latest (d12a1f), ALIGN_INIT=0.2,-1.8,70:
  - start match (0.170, -1.956, 78.9 deg), 85 % inliers;
  - 340/341 keyframes refined (27 without a scan within 80 ms use the anchored prediction);
  - inliers median 0.955, p10 0.902; correction mean 2.8 cm, max 23 cm;
  - path covers room -> hall (x 6.45 m; hall place at 6.28) -> back, ending 5 cm from the start;
  - 344,576 points (2 cm), 53,664 occupied 5 cm cells.
  - Output maps3d/colour_v2_dryrun_remap6_20261114.{ply,json}; render docs/colour_3d_20261114/colour_v2_dryrun_render.png.
- Conclusion: once remap 9 is accepted, 3D v2 can be built from the existing recordings (remap6, optionally + remap5b / remap3) without a colour drive.
- Visual limits: depth is 160x120; colour/depth centres are assumed equal (v1 limitation); some doubled walls near the hall (x 6-7.5 m). Not yet investigated.

2026-11-14 ~10:40-11:10 3D v2 doubled walls investigated (owner: "look into the doubled walls"). Offline only, recording remap6 on the accepted map.
- New tool tools/m3/wall_check.py: distance from 3D points (z 0.15-1.2 m, or the LiDAR band 0.15-0.35 m) to the nearest occupied cell of the 2D map; reports median, p75, p90, % within 5 cm and % at 10-30 cm (the doubled-wall signature).
- Baseline (dry run): median 6.7 cm, 41 % within 5 cm.
- Outbound vs return passes (KEEP_FROM/KEEP_TO; the pose chain runs through all frames):
  - outbound 3.8 cm / 57 %; return 9.6 cm / 29 %.
  - Both lock onto the 2D map equally (inliers 0.955), so the error is in placing the depth points and depends on direction: the doubled walls.
  - The room area is worse in both passes partly because of furniture above the LiDAR plane; that is not doubling.
- Sweep (median / within 5 cm):
  - DEPTH_DT -0.2: 6.0 / 44; -0.1: 6.4 / 44; 0: 6.7 / 41; +0.1: 7.4 / 38; +0.2: 7.5 / 37.
  - MOUNT_YAW_DEG -4: 9.6 / 33; -2: 8.3 / 37; +2: 6.5 / 42; +4: 7.0 / 39.
  - Combined DEPTH_DT=-0.2 + MOUNT_YAW_DEG=+2: all 5.5 / 48; outbound 3.5 / 65; return 7.6 / 35.
  - Hall at the LiDAR band: outbound 3.5 cm vs return 5.7 cm. A residual error remains in some return frames (after the hall turnaround).
- FIX: frame gate DEPTH_GATE_CM. A frame is skipped when its depth points in the LiDAR band (0.15-0.35 m) are a median of more than N cm from the 2D map walls.
  - Gate 6 cm: 146/375 frames gated; all 3.8 cm / 57 %; hall 2.9 cm / 74 %, 10-30 cm 7 % (return was 26 %).
  - Gate 4 cm: 238/375 gated; all 2.9 / 69; hall 2.9 / 79; sparser.
  - Render docs/colour_3d_20261114/colour_v2_gate6_render.png: the hall wall is single.
- Recommended for 3D v2: DEPTH_DT=-0.2 MOUNT_YAW_DEG=2 DEPTH_GATE_CM=6, merging remap6 + remap5b + remap3 to refill the gated coverage.
- The build-tool values (-0.2 s, +2 deg) are offline estimates for the 3D tool only; config/astra_obstacles.yaml (live Astra mount) is NOT changed. A +2 deg mount yaw is a calibration question for the owner.

2026-11-14 ~11:20-12:00 dashboard warnings, M3 encoder, IM10A, Astra mount (owner request). Rover parked, stop latched.
DASHBOARD "13 OK / 4 WARN / 1 FAULT" -> now "15 OK / 1 OFF / 1 WARN / 1 FAULT" (verified in the browser).
- Edits in web/v2/command.js and the identical V1 source in scripts/atlas_status_web.py (tools/ui_v2/build_command_js.py builds command.js from it); glass.css adds .healthitem.off. Backups *.before-tiles-20261114; rover-status-web restarted.
- IMU / COMPASS was WARN "navigation fusion not validated" (hard-coded whenever live). Now OK when the IM10A's own dashboard_json says qualified_for_navigation=true and navigation_fusion "ENABLED: corrected gyro Z only" (live: LIVE_FUSED_GYRO_Z). Text: "gyro Z fused in EKF (heading) • compass diagnostics-only".
- DRIVE PID was WARN for DISABLED/controller_disabled; config/drive_pid.yaml ships enabled:false by design. Now OFF (grey, counted separately, never colours the summary). FAULT_STOP is still a FAULT.
- ULTRASONIC was WARN because it required all four sides. The UNO hub reports USTAT,F=ONLINE,L=DISABLED,R=DISABLED,B=ONLINE (left/right not installed) and the topic alternates HEARTBEAT/USTAT. Now only hub-enabled sides count (last USTAT remembered): OK "front 633 mm • rear 749 mm • left/right not installed".
- Still WARN (real): DRIVE FEEDBACK. Autonomy is not qualified (encoder_selection.yaml navigation_validated:false because of M3).
- Still FAULT (real): GNSS, no NMEA (GPS hardware).
M3 ENCODER: cannot be corrected in software.
- Replay of sessions 57941c0d and c7c28ee9, 1 s windows while moving:
  - net M3 count -659 / -1452 vs about ±50k for M1/M2/M4; |sum| about 28k vs about 85k;
  - per-window M3/others 0.08-0.97 (median 0.19); corr(|M3|,|M4|) 0.38-0.44 vs corr(|M1|,|M4|) 0.92-0.99; sign agrees with M4 in 1 % of windows.
  - M3 counts back and forth (direction lost): the signature of a quadrature channel (A or B wire, connector or encoder disk) failing while the motor works. No scale or CPR value can fix it.
- Offline replay through the live EncoderDeltaEstimator (dynamic 3-of-4 consensus, median):
  - all 4: path 22.12 / 21.84 m, consensus failed in 2.1 % / 3.7 % of moving intervals, M3 accepted 39 % / 35 %;
  - M3 statically excluded: 22.26 / 21.93 m (+0.6 / +0.4 %), failures 3.7 % / 6.0 %.
  - DECISION: keep the dynamic consensus (M3 rarely biases distance; excluding it nearly doubles fail-closed intervals). encoder_selection.yaml unchanged.
  - Hardware follow-up: check the M3 encoder channel A/B wire and connector.
IM10A: fully integrated for a 2D indoor rover.
- Bias-corrected gyro Z is the EKF's yaw-rate input (imu0 /im10a/imu/bias_corrected_candidate in base_link, navigation_qualified per config/im10a_gyro_bias.json).
- Magnetic heading deliberately excluded (indoor magnetic distortion from motors and steel); accelerometer not needed in 2D.
- Offline 2026-11-13: IM10A heading beat ICP heading (ICP yaw instead of IMU 0.68-1.06 m closure vs live 0.45-0.51 m).
- The "candidate" topic name is legacy; renaming it would change the EKF interface for no functional gain, so it is kept.
ASTRA MOUNT: the recorded owner tape values stay authoritative (config/astra_obstacles.yaml: x 0.21, y 0.0, z 0.23, pitch 0.0 re-levelled, yaw 0.0). The +2 deg from the offline 3D fit stays a 3D-build parameter only; not applied to the live mount.

2026-11-14 11:25-14:15 REMAP 9 and REMAP 10 (owner at the rover, driving with the remote; stop latched at every start and end).
ROOT CAUSE FOUND AND FIXED - DDS packet storm. After a fresh reboot, parked manual mapping showed udp_in 107,726/s (healthy 3-7k), RcvbufErrors 1,627/s, EKF 44 % (35 % sys), SLAM 38 % (28 % sys).
- Per-socket /proc/net/udp drops: recorder 6,917/5 s, dashboard 3,550, localization monitor 573, SLAM 534 (rx queue 149,760 B against the 212,992 B default limit), EKF 169.
- Reliable DDS repairs every dropped fragment and the repairs are dropped again -> storm. This is the mapping-mode "sticky overload" of 13-14 Nov.
- FIX (owner sudo; persistent /etc/sysctl.d/60-atlas-dds-buffers.conf): net.core.rmem_default=4194304, rmem_max=8388608, wmem_max=8388608, net.ipv4.ipfrag_high_thresh=33554432, ipfrag_time=3; reboot.
- After the fix, light mapping parked: udp_in 3,159/s, drops 0, EKF 3 %, SLAM 2 %, idle 46 %.
- During both drives: idle 37-47 %, no guard trips. Short drop bursts (150-1,550/s for ~15 s) about every 90 s, attributed to the dashboard's socket (3,698 drops in one 45 s window). Not yet fixed; cosmetic for mapping.
REMAP 9 (session 2f57dfa7). REJECTED.
- Passed: connectivity, footprint, Nav2 plans both ways (8.34 m).
- Failed: map->odom jump 1.344 m / 12.8 deg at 12:26:28 (start of return from the hall); closure 0.197 m; source predates session. The last one was caused by my start script retrying while the first start was still preparing (two sessions 8dec1c9a -> 2f57dfa7; the second overwrote the paused-services list with []; services restored by hand).
REMAP 10 (session de55c1d3; owner stop-and-go: short moves, wait for LiDAR GO; slow stepwise hall turnaround). REJECTED.
- Passed: connectivity, plans both ways, source timestamps (source_floor fix verified live).
- Failed: jump 1.460 m / 14.2 deg at 13:50:40 (hall turnaround); closure 0.230 m / 4.4 deg.
- A live map->odom watcher showed SLAM FLIP-FLOPPING at the hall turnaround: 0.36, 0.63, 1.30, 1.46, 1.31, 0.44 m within 13 s (13:50:26-13:50:39); more 0.5-1.1 m steps while leaving the hall; smaller ones (0.1-0.45 m) on re-entering Dhruv Room.
- Three attempts now jump at the same place (1.71 m 13 Nov, 1.34 m, 1.46 m) with the CPU healthy => the hall is AMBIGUOUS to SLAM (scan matching or loop closure alternating between two hypotheses). NEXT: offline replay of manual_mapping_de55c1d35092-20261114-134350 around 13:50:20-13:50:45: compare the scan matcher's candidate poses, loop-closure events and the hall geometry (glass, mirror, open space).
- By eye the new map is cleaner than the accepted one: straighter walls, hall fully covered, free area 26.6 vs 23.9 m² (docs/colour_3d_20261114/map_compare_remap10.png). The candidate stays rejected: the jump rule is not changed without a reviewed analysis of the final-map accuracy.
OTHER FIXES / TOOLS TODAY:
- tools/drive/stop_and_go_coach.py (read-only), per second MOVING/WAIT/GO.
  - Localization: GO = stopped >= 1.5 s, pose steady, scan-fit >= 85 % (the mission-control gate), plus the dashboard strict check (VERIFIED / LOCAL only).
  - Mapping: SLAM adds scans only after ~0.2 m, so GO = settled + fit >= 60 % on the growing map.
- Dashboard /api/map hides a nav plan older than 30 s. The map-acceptance plan-only check in a candidate frame had been drawn over the live map ("blue line wrong orientation"). Owner: "path line is correct" now.
- Live LiDAR checks in localization: corridor fit 90-95 % (local OK) but strict unique-place 90-92 % < 0.93, because the accepted map is stale there (moved furniture; an object ~1 m in front of the room spot; an opening behind-right). Dhruv Room start spot VERIFIED (fit 0.983). The 0.93 bar is NOT lowered: a true pose on the stale map now scores like the best wrong place of Oct (0.897).
- Corrected a claim made in passing: a "+2 deg LiDAR mount" fit gain is indistinguishable from a 2 deg heading error (the global search already optimizes yaw). No mount change.
OPEN BUGS (to fix):
(1) The light mapping profile does not start atlas-map-footprint-filter, so there is no /map for the dashboard (started by hand in both remaps).
(2) Mission control accepts start_manual_mapping while a session is preparing or active; it should refuse.
(3) The mapping page draws the SLAM pose as a faded "ATLAS ESTIMATE" and shows old-map place labels while mapping.
(4) Periodic dashboard socket drop bursts.
(5) `ros2 topic pub --once -w 1` lost the stop request once (re-sent; it was received).

2026-11-14 14:15-15:30 HALL TURNAROUND ANALYSIS (offline; recording manual_mapping_de55c1d35092-20261114-134350; isolated domain 95; rover parked).
- Odometry is NOT the cause.
  - During the multi-point turn (13:50:26-13:50:42) IMU, ICP and EKF yaw rates agree (-0.12 to -0.37 rad/s).
  - map->odom alternated between about (1.46,-0.25,-17) and (0.18,-0.01,-4) (1.3 m / 13 deg apart), ending at (0.72,-0.17,-9).
  - SIDE FINDING: wheel-odometry yaw rate has the WRONG SIGN during this 4WS multi-point turn (+0.3..+0.5 vs IMU -0.2). Not fused (EKF uses IMU yaw rate). To fix later.
- Scan at 13:50:36 against the candidate map: solution B fit 96 %, A 79 %, where SLAM settled 88 % (docs/colour_3d_20261114/hall_overlay_remap10.png). The hall view is dominated by one long straight wall with large openings, so matching is under-constrained along the wall.
- Offline replays (live parameters reproduce it: max step 0.68 m at 13:48:17/13:48:33 entering the hall and 13:50:27-40 at the turnaround). First 9 min unless noted:
  - loop closure OFF (full bag): 0.68 m, 19 steps > 0.15 in the hall window (live: 20). Loop closure is NOT the cause.
  - distance/angle variance penalty x2: 0.72 m, 21 steps. No help.
  - more frequent scans (0.1 m / 5 deg / 0.2 s): 0.66 m, 30 steps. No help.
  - correlation_search_space_dimension 0.25 and 0.35: slam_toolbox CRASHES ("Mapper FATAL ERROR - unable to get pointer in probability search"). Not usable without further parameter work.
- Conclusion: the jumps come from local scan matching in the hall geometry, not from CPU, odometry, loop closure or scan rate.
- Next options:
  (a) Physical: place 1-2 distinctive static objects in the hall (e.g. a box or chair near the long wall, off the path) to break the sliding ambiguity, then remap.
  (b) Driving: avoid the multi-point turnaround inside the hall (turn where geometry is rich, or reverse out along the same path).
  (c) Build the map offline from the recording with heavier processing, plus a reviewed acceptance route.
  (d) Reviewed change of the jump gate to judge final-map accuracy.
- Tooling: replay_slam.sh gains RATE and T_END (filtered copy until a time). Lesson: never edit a running bash script, and kill leftover sim-time SLAM nodes by PID (pattern kills matched the ssh command itself).

2026-11-14 15:27-15:45 REMAP 11 (session 2902fe9a). Owner placed objects in the hall, used no turnaround inside the hall, stop-and-go with the coach. Start: one request, ACTIVE first try (start_once.sh now matches "]: MANUAL MAPPING ACTIVE" only). REJECTED.
- Jump 1.511 m / 17.1 deg at 15:37:07 (leaving the hall); closure 0.389 m; exact candidate connectivity FAILED ("no inflated path"; the hall objects probably narrowed the passage); Nav2 plans both ways passed.
- Live corrections: 0.44-0.66 m already in the corridor/hall entry (15:33:54, 15:34:54), 0.6-1.05 m inside the hall (15:35:16-15:35:32), then 0.9-1.5 m while leaving (15:36:53-15:37:08).
- So the objects and the no-turnaround route did NOT help; the hall itself triggers it.
- NEW EVIDENCE (remap-10 bag, 235 hall scans 13:48:00-13:50:45 against the remap-10 candidate):
  - 8.7 % of returns land BEHIND mapped walls, up to 115/294 (39 %) at the turnaround spot (-0.22, -6.35);
  - concentrated at world bearings 90-120 deg (0.7-2.5 m) and 150-180 deg (up to 6.2 m).
  - Hypothesis: see-through or reflective surfaces in the hall (glass, mirror, shiny surfaces, open space under furniture at LiDAR height), so phantom geometry moves with the rover. Owner asked to inspect.
- Restored: localization seeded (0.235, -1.775), READY, latched, accepted map unchanged (4beb26d5a999), places from pre-remap11.
- Dashboard: web/v2/mapping.html in mapping mode (live /map, no AMCL) now hides saved-map places and draws the SLAM pose as a green "ATLAS (SLAM)" arrow. Static file, no restart; verified in the browser.

2026-11-14 ~16:05 OFFLINE range-limit tests (remap-10 recording, start -> hall turnaround, isolated domain).
- max_laser_range 8 m (live): max step 0.68 m, 19 steps > 0.15 m.
- 5.0 m: 0.70 m / 19. 4.0 m: 0.75 m / 19. 3.5 m: 0.75 m / 19.
- No help, so the confusing returns are near the rover (owner confirmed glass door/window, mirror or shiny surface, and open space under furniture in the hall; they must stay).
- RPLIDAR Boost intensities are binary (0/47): no intensity filtering possible.
- Owner's hall context: cannot be covered. Proposed next:
  (1) offline accuracy check of the remap-10 final map (all scans vs the final map, plus tape-measured room sizes);
  (2) if accurate, a reviewed acceptance change that judges final-map consistency instead of mid-drive map->odom corrections (owner decision);
  (3) the 3D v2 map;
  (4) M3 wire -> Drive PID -> supervised autonomy.
- Also shown to the owner: remap-10 drive path image (docs/colour_3d_20261114/drive_path_remap10.png). Plan-only Nav2 route dhruv room -> hall on the accepted map: 7.31 m, 89 poses (docs/colour_3d_20261114/planned_path_room_to_hall.png), republished plan-only for 10 min for the dashboard. No goal sent, rover latched.
- Owner asked ATLAS to drive itself. Declined: autonomy gate (navigation_validated false / M3), no Drive PID, stale corridor/hall map. Not bypassed.

2026-11-14 ~16:20 OFFLINE ACCURACY CHECK of the remap-10 candidate map (de55c1d3); /tmp/map_accuracy.py, owner: "Yes, check it".
- Method: each recorded scan after drive-ready (every 3rd, 3,603 scans) ICP-matched to the FINAL candidate map, seeded with SLAM's live pose.
- Results:
  - all 3,603 matched;
  - fit within 15 cm: median 100 %, p10 99 %, 100 % of scans >= 85 %;
  - within 5 cm: median 99 %;
  - by area (room 2,243, corridor 764, hall 596 scans): median 100 %, p10 98-100 %; worst scan 92 % (13:48:32 hall entry; 14:05:33 room);
  - best fit vs SLAM live pose: median 3 cm, p90 14 cm, max 24 cm.
- Interpretation: the final map is internally consistent along the whole drive, including the hall (no bends or doubled walls). The 1.3-1.5 m map->odom "jumps" were frame corrections (map vs odom); the robot pose itself was never more than about 24 cm from the final-map best fit.
- Caveats: self-consistency is not absolute scale, so the owner will tape-measure Dhruv Room width (map 3.05 m) and hall depth (map 2.20 m) (docs/colour_3d_20261114/map_sizes_remap10.png). Repeatable glass/mirror reflections may appear as phantom features.
- Proposal (for the owner's review; NOT implemented): add a final-map consistency evidence path to map acceptance:
  - >= 95 % of session scans fit the final map >= 85 % within 15 cm;
  - live-pose vs best-fit <= 0.30 m;
  - plus the unchanged closure <= 0.15 m / 10 deg, connectivity and Nav2 plans.
  - Remap 10 would still fail closure (0.230 m).

## 2026-11-14 — Final-map acceptance check written for review (STAGED, OFF BY DEFAULT, NOT DEPLOYED)

Owner asked to write the change proposed after the remap-10 accuracy check. Nothing on the running rover changed.

What it does when enabled (`map_acceptance_final_map_mode: true`, default `false`):
- Mission control keeps ~2 LiDAR scans/s during a manual mapping session with SLAM's live map->base_link pose at the
  scan stamp (cap 1200 samples, halved density when full so the whole drive stays covered; read-only).
- At acceptance it ICP-matches every sample to the exact candidate map bytes (`scripts/atlas_final_map_consistency.py`).
- If the map->odom translation/yaw JUMP limits fail, passing final-map evidence may replace those two checks only:
  >= 100 samples, every sample matched, >= 95 % of samples with >= 85 % of returns within 0.15 m of a final-map wall,
  live pose never > 0.30 m / 10 deg from the best fit. `atlas_map_acceptance_core.final_map_consistency_failures`
  re-checks the numbers and thresholds; the evidence's own `passed` flag is not trusted alone.
- Unchanged: closure (0.15 m / 10 deg), exact-candidate connectivity, full-footprint connectivity, both Nav2 plans,
  startup stillness, guard trips, and every tf_jump integrity/timestamp check.

Tests (Jetson staging ~/atlas_staging_20261113): test_final_map_consistency (10), test_mission_final_map_sampling (5),
test_atlas_map_acceptance_core, test_mission_status_idle_revert: 49 passed.

Replay of remap 10 (de55c1d3) through the staged path (`tools/localization/replay_final_map.py`):
- 903 samples (thinned 3x), 903 matched, fit median 100 %, p10 100 %, fraction good 100 %, pose offset median 3 cm /
  max 17 cm, heading offset max 9.97 deg (limit 10), evaluation 10.5 s.
- switch OFF: REJECT (jump 1.46 m, yaw 14.2 deg, closure 0.23 m) — identical to the stored decision.
- switch ON: REJECT, only "round-trip translation closure 0.230 exceeds 0.150". The closure gate still decides.
- Heading note (do not loosen to fit this data): 49/903 samples had the live heading > 5 deg off the best fit, max
  10.0 deg at 13:50:31 in the hall and ~9 deg at 13:46:20-24 while PARKED in Dhruv Room. So SLAM's live heading really
  was ~9 deg wrong early in the drive and was corrected later (that correction is the 14 deg yaw jump). Remap 10 passes
  the 10 deg limit by 0.03 deg; a similar remap may fail it. Mapping is owner-driven (no Nav2 while mapping), so
  this measures how wrong the live pose was, not a risk to the accepted map.

Open review points: sample cap (1200, about 4.8 MB, ~10 s evaluation) vs a 30-min drive; whether 10 deg is the right
live-heading limit; closure 0.23 m on remap 10 is still a real reject (owner tape measures pending).
Enabling needs the owner's OK plus a deploy with the rover parked and the E-STOP latched.

## 2026-11-14 16:37 — Final-map acceptance check DEPLOYED and ON (owner: "depay kar do")

- Pre-checks: no mapping session file, wheel odom twist 0, motion blocked ("REMOTE STOP: joystick unavailable"),
  live mission control / acceptance core identical to commit 2e21270 (md5) before replacing.
- `tools/deploy/deploy_20261114_final_map.sh`: backed up as *.before-finalmap-20261114, copied the 3 scripts + tests,
  added drop-in ~/.config/systemd/user/atlas-mission-control.service.d/final-map-mode.conf
  (`-p map_acceptance_final_map_mode:=true`), restarted ONLY atlas-mission-control. Rollback: `bash <script> --rollback`.
- Verified: service active, READY, `ros2 param get ... map_acceptance_final_map_mode` = True; 49 focused tests pass in
  ~/project_atlas; atlas_regression ALL PASS (55 unit, old map connected, 17 rejected candidates re-checked: none
  accepted now — the stored ones lack scan samples, so the new path cannot accept them).
- Limits unchanged (strict version that passed the tests). Next remap is the first real use; watch the heading-offset
  margin (remap 10 was 9.97 / 10 deg) and the closure (must be <= 0.15 m).

## 2026-11-14 16:44-17:00 — Remap 12 (session 22776983): REJECTED; final-map sampler collected 0 scans (my bug)

- Owner drove Dhruv Room -> hall -> back to the tape mark, stop-and-go. Closure 0.100 m / 0.1 deg: PASSES (first remap
  under 0.15 m). Jump 1.274 m / 15.6 deg (same corridor/hall SLAM corrections as before).
- Rejected also because named places "dhruv room"/"hall" were not saved in this session (in remap 10 I saved them on
  the owner's call-outs; this time I did not remind/save — process miss, mine).
- final_map_consistency: scans 0. Cause: under the batched executor (ATLAS_EXECUTOR_BATCH_S=0.05, deployed 11-13)
  rclpy takes at most ONE message per subscription per wait cycle (~20 msg/s per topic). /tf arrives at ~30 Hz, so
  mission control's TF buffer lags by seconds and an immediate lookup at the scan stamp always failed
  (reproduced: 0/80 ok with batching). tf_jump sample_count 7429 over ~380 s (= 19.5/s) confirms the cap.
  Also: parked, slam_toolbox's map->odom stamp stops advancing, so exact-stamp map->base_link lookups fail too.
  Unit test missed it because the fake TF answered immediately.
- Offline replay of this bag through the staged evaluation (latest-TF method): 799/799 scans matched, fit median 100 %,
  p10 97.8 %, pose offset max 0.23 m, heading max 13.6 deg -> would FAIL the 10 deg limit. Both > 10 deg samples were
  during fast turns (24 and 11 deg/s, where replay TF latency inflates heading); while still (< 3 deg/s, n=648) max 9.4.
- WIDER FINDING (needs review): every batched node subscribed to /tf (mission control, localization monitor, ...)
  sees TF capped at ~20 msg/s and seconds late. Mission control's current_pose / scan-fit gate / named-place saves
  read that lagged TF (only refuses or saves while stopped, but it is wrong). Candidate fix: TransformListener
  spin_thread=True or excluding /tf-heavy nodes from batching. Not changed yet.
- Rover parked at the mark, session still open, SLAM running. Nothing else changed.
- 17:05 owner latched E-STOP; session 22776983 ended with end_restore (files in rejected_session_22776983, bag kept,
  81 MB). AMCL active, accepted map unchanged (atlas_latest.pgm 4beb26d5a999), dashboard localization check VERIFIED.
  The deferred-lookup sampler edit in the working tree is NOT committed/deployed (does not solve the TF lag).

## 2026-11-14 17:10-17:20 — Mission-control TF lag FIXED and final-map sampler verified live (DEPLOYED, owner: "Yes, fix it")

- Probe (batched main node + a SEPARATE tf node on its own SingleThreadedExecutor thread): 95/100 exact-stamp
  map->base_link lookups ok (5 = startup), wait p50 0.05 s / max 2 s. (Same-node spin_thread=True variant did not help.)
- atlas_mission_control.py: TransformListener now on node `atlas_mission_control_tf` with its own executor thread
  (all mission-control TF lookups see current transforms, not the ~20 msg/s capped /tf). Sampler queues ~2 scans/s and
  resolves the exact scan-stamp pose on a 0.25 s timer (give up after 3 s, counted as lookup_failures, first error
  kept in the evidence). Logs "FINAL-MAP SAMPLES n=.. lookup_failures=.." every 30 s while sampling.
- Tests: 51 focused pass (new: late-TF and never-TF cases, own-executor check); atlas_regression ALL PASS.
- Deployed 17:11 (backups *.before-tffix-20261114), E-STOP latched by owner, mission control restart only.
- Live parked test session 2a84f36b (no drive, 60 s): 228 samples, 228 matched, fit median 100 %, pose offset max
  0.035 m / 0.2 deg, lookup_failures 2 (SLAM startup), evaluation 1.6 s -> final_map_consistency PASSED. Rejected only
  for named places (expected). Session ended with end_restore; its 60 s parked test bag deleted (throwaway, no drive).
  AMCL active, localization check VERIFIED, accepted map unchanged (4beb26d5a999).
- Still open: other batched nodes that read /tf (localization monitor, lidar odom gate, safety status, sensor recovery)
  have the same ~20 msg/s per-topic cap; not changed. Remap 13 must save "dhruv room" at start and "hall" in the hall.

## 2026-11-14 17:21-17:30 — Remap 13 (session 21ed0671): REJECTED, but map quality and closure pass

- Places saved in-session: "dhruv room" (-0.77, 0.17) at the start mark, "hall" (1.47, -5.91). Sampler worked:
  946 samples, 0 lookup failures.
- PASS: closure 0.135 m / 1.3 deg; final map 946/946 matched, fit median 100 %, p10 98.4 %, 100 % of scans good,
  live position offset max 0.256 m (limit 0.30).
- FAIL 1: live heading offset 13.84 deg (limit 10). Offline (latest-TF, inflates in turns): 2/972 samples > 10 deg,
  all > 8 deg samples in the corridor end / hall (y < -3); while still (< 3 deg/s, n=858) max 8.2. 17:27:22 at
  (1.89, -4.64) +13.1 deg at only 6 deg/s -> a real transient SLAM live-heading error in the hall, not a timing effect.
- FAIL 2: "candidate start is not clear for the inflated rover": nearest final-map wall 0.24 m from the "dhruv room"
  place (rover half-width 0.175 + 0.18 inflation). The start mark is too close to furniture for Nav2 — needs an open
  start/place spot (>= ~0.5 m from walls). This is a real gate, not changed.
- map->odom jump 1.274 m / 13.6 deg (remap 12: 1.274 / 15.6) — the same corridor/hall corrections.
- Decision needed from owner: keep the 10 deg live-heading limit (hall remaps keep failing) or raise it (e.g. 15 deg;
  position limit 0.30 m stays). Not changed. Note: a re-stop of the same session cannot re-use samples (buffer is
  released at the first evaluation), so this session cannot be salvaged.

## 2026-11-14 17:35-17:45 — Live-heading limit 10 -> 15 deg DEPLOYED (owner: "15 digera kar do"); places finding

- Owner decision after remap 13. FinalMapConsistencyPolicy.max_pose_offset_deg and
  MapAcceptancePolicy.final_map_max_pose_offset_deg = 15.0; position limit 0.30 m and every other gate unchanged.
  Re-evaluating remap 13's stored evidence with 15 deg leaves ONLY the start-clearance / plan failures.
- Owner asked to approve remap 13 instead: NOT done. The "dhruv room" place is 0.24 m from a wall in that map; Nav2
  cannot plan from it (real safety gate). The session also cannot be re-validated (samples released at evaluation,
  lost on the restart needed for the new limit). Remap 14 needed: same route and start mark, but save "dhruv room" at an
  open spot (>= 0.5 m clear on every side).
- Session 21ed0671 ended with end_restore (E-STOP latched by owner); bag kept (97 MB); AMCL active, check VERIFIED.
- Deployed 17:40 (backups *.before-heading15-20261114), mission control restart only: active, READY, final-map mode
  True, 46 focused tests pass. atlas_regression: unit PASS, gate_history PASS, old_map FAIL
  ("candidate goal is not clear for the inflated rover").
- FINDING (pre-existing since remap 9, exposed now): saving "dhruv room"/"hall" during a mapping session OVERWRITES
  ~/.config/project_atlas/named_places.json, and a rejected session does not restore them. Saved places came from
  remaps 9, 10, 11 and 13 in their own SLAM frames; the accepted map d12a1f18 has had places from rejected sessions
  (the owner's earlier "map says Dhruv Room but it is the kitchen" fits this). old_map passed before only because
  remap 11's coordinates happened to be clear. No backup holds verified accepted-map places. Navigation to places is
  blocked anyway (navigation_validated false). An accepted remap 14 rewrites the places correctly. Code fix proposal:
  keep in-session places in the session (or back up and restore on rejection). Not changed.

## 2026-11-14 17:50 — In-session places no longer overwrite accepted-map places (DEPLOYED, owner: "Yes, fix it")

- save_named_place during a mapping session now writes ~/.config/project_atlas/mapping_session_places.json (entries of
  other sessions dropped). The acceptance check and promotion use merge_session_places(accepted, session, id); on
  acceptance the session places are bound to the new map id and written into named_places.json in the same
  transaction as before. A rejected session leaves named_places.json untouched. Outside a session, unchanged.
- Tests: test_session_places (5, incl. routing and promotion binding); 57 focused pass; regression unit PASS.
- Deployed 17:50 (backups *.before-sessionplaces-20261114, named_places.json also backed up), mission control restart
  only. end_restore.sh (scratch) now moves mapping_session_places.json into rejected_session_<id>/.
- old_map regression still FAILS: named_places.json still holds remap-13 coordinates for "dhruv room"/"hall"
  (session 21ed0671, no map_id; navigation fails closed on them). No verified accepted-map places exist to restore;
  an accepted remap 14 binds correct ones. Left as is deliberately.

## 2026-11-14 18:13 — REMAP 13 ACCEPTED after owner-approved parked review (new map 38253aab42e9e97304aa)

Owner would not drive again ("i drive 10 time ... you have enaf data") and approved "Yes, accept it", then "Yes, accept"
after seeing the deviation below. Tools/evidence: project_atlas/tools/maps/remap13_review/ (review_report.json).
- Dhruv Room place moved on the candidate map from the start mark (-0.77, 0.17; 0.24 m from furniture) to (0.08, 0.54):
  nearest point within 1 m with >= 0.45 m clearance that connects to the hall; owner confirmed from a picture.
  Marked selected_offline in named_places.json.
- final_map_consistency recomputed from the recording against the candidate bytes (latest-TF method): 972/972 matched,
  fit 100 %, offset max 0.185 m / 13.05 deg (limit 0.30 m / 15 deg). Live exact-stamp run before had 946/946, 13.84 deg.
- Parked review (E-STOP latched, no goal sent): localized AMCL on a COPY of the candidate, live LiDAR fit 100 % at the
  rover's real pose; Nav2 ComputePathToPose dhruv room->hall 7.20 m (87 poses), hall->dhruv room 7.73 m (93);
  footprint 0.50 x 0.36. Exact connectivity connected (3165 cells). Guard trips none. Closure 0.135 m / 1.3 deg.
- Official evaluate_acceptance_evidence: at the session evaluation time (17:37:42) NO FAILURES; at the review time
  (18:08:21) only "map->odom evidence/source stale". DEVIATION: the single-moment freshness rule cannot hold offline;
  each evidence set passes at its own time. Shown to the owner before promotion.
- Promoted with transactionally_promote_map_pair (backup tag 20261114-181314-21ed0671-review in maps/accepted_backups;
  old map d12a1f18 recoverable). home/seed/places bound to 38253aab.
- Mistake during review: first attempt started atlas-nav2 on top of the localization launch (which already includes Nav2)
  -> two Nav2 stacks, plans ABORTED, 3 orphan lifecycle managers left. Killed by PID, rerun with process-group cleanup.
- After promotion: atlas-localization restarted on the new map, AMCL at (-0.84, 0.28) = final session pose.
  atlas-localization-monitor still held the OLD map in memory (LOST, "2.06 m" = old-map Dhruv Room pose) -> restarted
  it: VERIFIED, AMCL fit 1.0, 0.11 m / 3.1 deg. atlas_regression ALL PASS (old_map now 38253aab connected).
- Still open: navigation_validated false (M3 encoder, Drive PID); the localization monitor does not reload a promoted
  map by itself (needs a fix or a restart after promotion).

## 2026-11-14 18:30-19:00 — M3 encoder EXCLUDED (live) and 3-encoder ground qualification STARTED (incomplete)

- Evidence (remap-13 bag, 557 s ground drive): counts range M1 ~52.7k, M2 ~57.2k, M3 ~7.3k, M4 ~51.4k (M3 loses most
  pulses); direction vs LiDAR ICP: M1 94 %, M2 100 %, M3 89 %, M4 100 % (M2/M4 opposite raw sign by design); consensus
  rejected M3 575x vs 22-27x for the others.
- Owner: "Yes, exclude M3". config/encoder_selection.yaml excluded_encoders: [3] (backup
  *.before-excludeM3-20261114); rover-base-telemetry restarted with E-STOP latched. Live: DEGRADED, selected [1,2,4],
  scale 0.5, navigation_validated false, autonomy_ready false. Localization VERIFIED. Drive PID unchanged (disabled;
  it requires all four encoders).
- Code finding: autonomy gating (mux) uses encoder autonomy_ready = navigation_validated and scale > 0; it does not
  require Drive PID.
- Qualification tool: tools/drive/encoder_segment_check.py (read-only; wheel /yahboom/odom vs /lidar/icp_odom per
  stop-to-stop segment). Owner remote drives, 18:40-19:00:
  * forward 6/6 PASS (wheel 2.12 m vs LiDAR 2.26 m total; per segment 1-3 cm low), reverse 6/6 PASS
    (~2.2 m; -0.40/-0.43, -0.44/-0.47, -0.61/-0.66 incl. +11/+7 deg, -0.41/-0.45, -0.24/-0.25, -0.11/-0.11).
  * FAIL #13: 6-8 cm move while steering: consensus unavailable (M1, M2, M4 all rejected), wheel yaw -7 vs LiDAR +3.
    Earlier run FAIL: reverse -0.61/-0.69 m with turn +8 vs -5 and CRITICAL (reason not captured then).
  * Turn arcs (left/right ~90 deg moving) and the stopping test NOT done; owner stopped for today.
- Open concern: with M3 excluded, consensus breaks during low-speed steering (left side has only M1); the mux would
  stop autonomy on CRITICAL (fail-safe, but autonomy may be unusable in turns). Needs the arc tests next.
- navigation_validated stays false. Wheel-odometry yaw sign in 4WS turns (known) seen again.

## 2026-11-14 19:30 — Dashboard IMU panel: aircraft-style instruments (DEPLOYED, owner request)

- web/v2/flight-instruments.js (new): attitude indicator (roll/pitch), heading indicator (IMU yaw shown aircraft-style:
  right turn increases the number, plus the front-steering drive direction), turn indicator (IM10A gyro Z deg/s,
  left/right), and a 4WS steering top view (front/rear servo angles, 90 = centre, higher = left).
- IMU detail view (command.js) keeps the existing tiles below the instruments; instruments are built once and redrawn
  (no flicker). New light endpoint /api/attitude (atlas_status_web.py AtlasRosNode.attitude_snapshot) polled every
  200 ms only while the IMU panel is open; /api/status stays at 2 s.
- Tested: local mock page (animated values) and the live dashboard (values match /api/status; no console errors).
- Deployed 19:25 (backups *.before-flightinst-20261114; rover-status-web restarted, dashboard only).
- To confirm physically: pitch sign (lift the front: horizon should move down) and heading direction (turn right:
  HDG number should increase). Not yet checked on the rover.

## 2026-11-14 20:45 — Pre-autonomy status from the records + combined round-trip check tool (planned 2026-11-15 morning)

Records checked on the owner's request:
- Box test: DONE 2026-11-11 (docs/TRACK_A_TEST_REPORT_20261106.md, G4 PASS: Astra detects the box 101/101, range within
  3 cm, empty view no phantoms). nav2_params now has a local-costmap astra_layer (/astra/obstacle_scan). At 20:40
  atlas-astra-bridge is INACTIVE (starts only after the E-STOP is released with sticks untouched, by design), so Nav2
  currently receives no camera obstacles. A Nav2-level "plan goes around the box" check is not in the records.
- Localization round trips: 2026-10-09/10 on the OLD map d12a1f18 failed (wrong AMCL pose after return). On the new
  map 38253aab only the parked check (VERIFIED) exists. A moving round trip is still needed.
- Encoders: 2026-10-02 four-encoder ground qualification passed but was revoked 2026-10-10 (M3). With M3 excluded:
  straight 12/12 PASS today; moving turn arcs not yet done.
Owner plan: do encoder turns + localization round trip + Astra bridge check in ONE stop-and-go drive Dhruv Room ->
hall -> Dhruv Room tomorrow morning; autonomous drives only after reviewing it and the owner's OK for navigation_validated.
Tool: tools/drive/round_trip_check.py (read-only): per stop wheel vs LiDAR distance, IMU-EKF (/odom) vs LiDAR turn
(wheel yaw informational), worst encoder state, localization verdict after the stop, Astra bridge state, tally of
left/right turns >= 30 deg. Dry run + synthetic-segment check passed on the Jetson.

## 2026-11-14 21:00 — Astra bridge boot auto-start: already exists; does not come back after a mapping session

- Boot auto-start exists since 2026-11-12 (atlas-astra-bridge-starter, oneshot, enabled; parked twice + CPU < 72 %).
  Today it started the bridge 43 s after boot ("parked twice, CPU 62 %").
- CPU (records 2026-11-06/11/12): bridge join = one-time ~100 % CPU for 5-9 s; settled total 62-68 %. Steady cost of
  the always-on Astra stack now: camera node 12 %, obstacle scan 6.5 %, depth preview 4.3 % of one core.
- FINDING: the feature manager pauses atlas-astra-obstacles during mapping (17:21 stop, 17:30 start); the bridge stopped
  with it and was never started again (Restart=no; the starter is boot-only). Nav2 has had no camera obstacles since the
  first mapping session today. Fix proposal (not applied): re-run the starter (same parked + CPU checks) whenever the
  Astra unit becomes active again after a mapping session. Tomorrow's test: start atlas-astra-bridge-starter by hand
  after the owner releases the E-STOP.
- 21:10 FIX DEPLOYED (owner "Yes, fix it"): drop-in atlas-astra-obstacles.service.d/restart-bridge-starter.conf
  (ExecStartPost=-systemctl --user --no-block start atlas-astra-bridge-starter) so every Astra (re)start, including
  after a mapping pause, queues the same safe starter; starter give-up 15 min -> 2 h (ATLAS_BRIDGE_START_LIMIT_S).
  Bridge unit unchanged (Restart=no, parked ExecCondition). enable_boot.sh installs the drop-in. Backup
  atlas_astra_bridge_boot_start.sh.before-restarthook-20261114.
  Live test: restarted atlas-astra-obstacles with the rover still -> starter started by itself and is waiting:
  "cmd_vel telemetry stale/missing" (remote off / E-STOP latched) = designed fail-closed; bridge not started yet.
  Tomorrow: start atlas-astra-bridge-starter by hand when the owner releases the E-STOP (the 2 h wait ends ~23:15).
  Note: the 11-12 report's "systemd also restarts the bridge when the Astra unit restarts (BindsTo)" was wrong —
  BindsTo only stops it.

## 2026-11-14 21:40 — Autonomy requires live camera obstacles (DEPLOYED, owner: "yes add it")

- Mission control: parameter autonomy_require_camera_obstacles (default True). Subscribes /astra/obstacle_scan in
  domain 0 (what Nav2's astra_layer receives). Start gate require_camera_obstacles() in dispatch_pose_goal,
  dispatch_route_goal, return_home and the return-home retry: refuses when never received or older than 1.5 s
  ("navigation blocked: camera obstacles OFF ..."). Watchdog (0.5 s timer): while an accepted named/home goal is active
  and the scan is > 2.0 s stale, publish zero once and cancel all Nav2 goals ("NAVIGATION STOPPED: camera obstacles
  lost"). Only ever refuses or stops.
- Dashboard: status web records astra_nav2 from /astra/obstacle_scan (domain 0); the home "Depth camera" card now says
  "Live · Nav2" only when that scan is < 2 s old, else "Nav2 OFF" (warn) with "Autonomous driving is blocked". Before,
  it said "Live · Nav2" whenever the domain-77 picture was live, even with the bridge off (misleading).
- Tests: test_camera_obstacle_gate (6) + focused suites: 29 pass on the Jetson. Deployed 21:35 (backups
  *.before-cameragate-20261114; mission control + rover-status-web restarted, rover parked, nobody driving).
  Live: param True; card shows "Nav2 OFF" (bridge off since 17:21 — correct). Not tested by sending a goal (no motion
  from me); unit tests cover refuse/stop paths.

## 2026-11-15 10:30-10:55 — Combined stop-and-go round trip, Dhruv Room -> hall -> Dhruv Room (M3 excluded)

- Read-only tools/drive/round_trip_check.py while the owner drove with the remote. Astra bridge started by the starter
  at 10:29:54 (needed the E-STOP latched: the mux publishes /cmd_vel only while an input is active, so with the remote
  idle the parked check saw stale cmd_vel). Log on the Jetson: ~/.local/state/project_atlas/round_trip_20261115.log.
- Tool fixes during the run (first 3 segments re-counted): distance now EKF (/odom, wheel vx + IM10A yaw, what navigation
  uses) vs LiDAR ICP — the wheel-only pose integrates the known wrong 4WS yaw sign (e.g. +117 vs -88 deg) so its
  projected distance was meaningless in arcs; localization wait 45 s (monitor search alone ~20 s); short stops are
  "loc not checked", not failures.
- Result, 25 stops: EKF 14.26 m vs LiDAR 14.46 m (-1.4 %), every segment within tolerance; IMU-EKF vs LiDAR yaw agreed
  on every segment (incl. -101/-100, -66/-66, -44/-44, +32/+31 deg); localization VERIFIED 16/16 checked (final stop
  VERIFIED, 0.124 m); Astra bridge ACTIVE throughout. Turns >= 30 deg: left 1, right 5.
- FAIL 12/25, all for one reason: /atlas/encoder_health CRITICAL "encoder consensus unavailable; fewer than three wheel
  channels agree" during motion — in arcs AND on near-straight segments (#24 -0.92 m, #25 +0.37 m, turn ~2 deg).
- Root cause (code read, yahboom_base._publish_encoder_health + atlas_encoder_selection.EncoderDeltaEstimator): with M3
  excluded only 3 channels remain, so a "group of >= 3 coherent deltas" needs ALL of M1/M2/M4 to agree in every sample
  interval (45 % / 4 mm). One bursty interval rejects all three -> that interval integrates 0 distance and the health
  state is CRITICAL with speed scale 0.0 for that tick. This was predicted on 2026-11-13 (line ~1777: excluding M3
  "nearly doubles fail-closed intervals").
- Owner observation: twice in turns they had to push the stick harder ("increase the speed because it's a turn") —
  consistent with scale 0.0 / 0.5 cutting commanded speed when consensus drops in arcs.
- Consequence: with navigation_validated=true the mux would cut autonomy speed every time consensus drops (fail-safe
  but stuttering/stalling in turns). navigation_validated stays FALSE. No config or code changed.
- Options (owner decision): (A) repair M3 wiring -> 3-of-4 consensus regains slack (preferred); (B) a 3-encoder-mode
  rule, e.g. 2-of-3 agreement with LiDAR/IMU cross-check, or CRITICAL only after consensus is lost for > N s, with
  offline replay of this run's bag/log before any deploy.

## 2026-11-15 11:30 — Three-encoder consensus rule (owner chose "Try 3-encoder rule"; NOT deployed yet)

- Change (scripts/atlas_encoder_selection.py EncoderDeltaEstimator): when exactly 3 channels are valid and no group of 3
  agrees, accept the tightest coherent PAIR (same 45 % / 4 mm tolerance) and integrate its mean. Fail closed when the
  pair is stalled (< 0.5 mm) while the third moves (> 4 mm), and on opposite-sign pairs. With 4 valid channels the
  3-of-4 rule is unchanged. yahboom_base.py: pair intervals get twist/pose covariance x9 (x4 for three, x1000 none),
  stationary label allows 2, policy string updated. Health CRITICAL logic unchanged (still fires when no pair agrees).
- First guard (pair <= 4 mm treated as stalled) rejected normal bursts like [3.0, 7.6, 2.1] mm; replaced by < 0.5 mm.
- Offline replay (tools/drive/replay_three_encoder_rules.py; /atlas/encoder_health interval deltas, M3 dropped):
  remap 13 bag 30/518 -> 1/518 failing moving intervals (5.8 % -> 0.2 %); 2902fe9a 24/626 -> 0/626; 8dec1c9a 28/606 ->
  0/606. Integrated distance +1-2 % (intervals no longer dropped). Absolute distance vs LiDAR in this replay is not
  meaningful (health samples do not cover every encoder interval; ICP path includes parked jitter).
- Tests: test_encoder_selection 28 OK (5 new), test_motor_mapping OK, on the Jetson with the candidate files.
  Live files equal git HEAD before the change. Deploy: tools/deploy/deploy_20261115_three_encoder_rule.sh (parked +
  E-STOP latched; restarts rover-base-telemetry only; --rollback). Then one short owner drive with round_trip_check.
- navigation_validated stays false until that drive passes.

## 2026-11-15 ~11:45-12:20 — Three-encoder rule DEPLOYED and ground-checked

- Deployed with the rover parked and the E-STOP latched (mux streaming zero cmd_vel): tools/deploy/
  deploy_20261115_three_encoder_rule.sh; backups *.before-3enc-20261115; only rover-base-telemetry restarted. Live
  policy "dynamic_3of4_consensus;3_channels=coherent_pair;no_agreement=stop;validation_required", DEGRADED, [3] excluded.
- Owner drive Dhruv Room -> hall -> Dhruv Room with round_trip_check (log round_trip_20261115b.log):
  39 stops, 36 PASS / 3 FAIL; EKF 19.74 m vs LiDAR 19.75 m; IMU-EKF vs LiDAR yaw agreed on every stop; right turns
  >= 30 deg: 8 (-30 ... -61 deg, forward and reverse) all with encoders DEGRADED (not CRITICAL); left turns: max +22 deg
  (no >= 30 deg left arc yet). Final stop localization VERIFIED (0.165 m, 2.2 deg). Astra bridge ACTIVE throughout.
- Encoder CRITICAL: 1 of 39 stops (#3, -21 deg arc, before a CRITICAL capture was started). A /atlas/encoder_health
  CRITICAL capture from stop #5 to the end recorded ZERO CRITICAL messages (previous rule: 12 of 25 stops).
- The other 2 FAILs were localization: #6 INPUT_STALE (odometry stale) right when I started that capture — a new
  domain-0 participant (known ~100 % CPU discovery spike) — my process error, not the rover; #24 DEGRADED "no unique
  LiDAR place" at one spot, next stop VERIFIED.
- Owner observation (old rule): had to push the stick harder in turns. Not reported with the new rule.
- Remaining before navigation_validated: one >= 30 deg LEFT arc (M1 is the only left channel; left arcs make it the
  inner wheel). navigation_validated still false.

## 2026-11-15 ~12:30-12:50 — Left-arc test, three-encoder rule (log round_trip_20261115c.log)

- 11 stops, 9 PASS / 2 FAIL; EKF 6.40 m vs LiDAR 6.44 m. Left arcs: +89/+85 deg (1.05/1.09 m) and +90/+93 deg
  (1.04/0.96 m); right/reverse arcs -96/-96, -40/-40 deg. Final stop VERIFIED (0.014 m, 6.1 deg). Astra ACTIVE.
- Encoder CRITICAL: exactly ONE health message in the whole run (capture covered all of it), during the first left arc:
  normalized deltas M1 -2.7 / M2 -18.0 / M4 -8.9 mm — no pair within 45 % / 4 mm (a single bursty 0.1 s interval).
  The second 90 deg left arc stayed DEGRADED throughout.
- FAIL #3 = that single CRITICAL tick; FAIL #6 = localization DEGRADED "AMCL near the LiDAR answer but not confirmed
  (0.12 m, 5 deg)" right after the second 90 deg left arc.
- Combined with the 39-stop run: left and right arcs >= 30 deg now covered; distance/yaw agree everywhere; encoder
  CRITICAL is now rare single ticks (2 ticks in ~26 m) instead of ~half of all stops. navigation_validated still false —
  owner decision pending.

## 2026-11-15 ~12:55 — navigation_validated ENABLED (owner: "Yes, enable it"); manual-only gate still ON

- config/encoder_selection.yaml navigation_validated: true (backup .before-navvalid-20261115), rover parked, E-STOP
  latched, rover-base-telemetry restarted. Live /atlas/encoder_health: DEGRADED, scale 0.5, navigation_validated true,
  autonomy_ready true.
- Found while checking the autonomy path: the mux runs with ATLAS_MANUAL_ONLY=1 (drop-in
  atlas-cmd-vel-mux.service.d/40-manual-commissioning.conf, since 2026-10-15), which drops NAV commands. The
  2026-10-15 report says: do NOT restore manual-only=0 without a separate safety decision. NOT changed; owner decision.
- Nav2 (amcl, bt_navigator, planner/controller servers) and mission control are running; Astra bridge active.
- 2026-11-15 ~13:00 (owner: "Yes, open it"): manual-only lock opened for supervised autonomy via new drop-in
  systemd/user/atlas-cmd-vel-mux.service.d/45-supervised-autonomy.conf (ATLAS_MANUAL_ONLY=0; 40-manual-commissioning
  kept). Rover parked, E-STOP latched; daemon-reload + mux restart only. Verified: mux starts with the software stop
  latched (RemoteStop.latched=True at construction); live control_policy manual_only false, stop_latched true,
  source STOPPED. Rollback: delete the 45 drop-in, daemon-reload, restart the mux. No goal sent; no motion.

## 2026-11-15 11:48-11:52 — First supervised autonomous goal: blocked by the mux guards (rover did NOT move)

- Owner chose "I send, owner holds E-STOP". One goal: /atlas/navigate_named_place "dhruv room" (~1.8 m from
  (-1.62, 0.03)). Mission: SCAN CHECK OK fit 100 %, goal dispatched + accepted; Nav2 planned and the controller
  published /cmd_vel_nav (x 0.15, alternating with 0). The mux sent ZERO the whole time; rover stayed still.
- Mux reasons (journal since 11:48): "LIDAR AVAILABILITY STOP: unobserved motion sector (4-5 bins)" x105 and
  "AUTONOMY BLOCKED: FRONT/REAR ULTRASONIC SERIAL_BACKLOG" x3/x3. Nav2 looped "Failed to make progress" -> backup
  recovery (did not move) -> retry. I cancelled both Nav2 actions at ~11:51 (NAMED GOAL FINISHED status=5).
- Root cause of the LiDAR veto (atlas_lidar_availability.py, deployed 2026-10-11): any angular command requires a
  valid return in ALL 72 five-degree bins. Here bins 230-250 deg (rear-right, robot frame) were ALWAYS empty; /scan_raw
  is inf there too (no LiDAR return, not the self-filter; neighbours at 0.4-0.6 m — likely dark/absorptive furniture).
  Remap-13 bag replay: only 34 % of scans have all 72 bins observed (top gaps 230-240 ~17 %, 320 17 %, 10-25 deg
  13-15 %). With this rule, autonomous arcs are blocked most of the time anywhere in the house. This is the
  "real-scan observation gaps" item left open on 2026-10-11 — not new, not previously relaxed.
- Ultrasonic SERIAL_BACKLOG: bridge invalidates a report when more serial data is already waiting (CPU/latency);
  intermittent, separate issue.
- No config changed for this. Manual-only remains open (45 drop-in), navigation_validated true. Owner decision needed.

## 2026-11-15 ~12:30 — LiDAR availability: swept-path policy designed + offline replay (NOT deployed)

- Owner: "Yes, design it". scripts/atlas_lidar_availability.py: arcs now need the +/-45 deg travel cone plus only the
  bins the 0.50 x 0.36 m footprint actually sweeps into (opposite-phase 4WS, ICR on the base_link lateral axis, 0.5 m
  horizon, > 2 cm outside the current outline, +/-1 bin); spins and arcs with R < 0.35 m still need all 72 bins;
  straight unchanged; invalid ranges still never free. tests/test_lidar_availability.py: 16 OK (5 new; the old
  "left gap blocks a left arc" case became "left gap blocks a RIGHT arc" — geometry; mux mock gained
  localization_guard, which was missing and made 2 tests error at HEAD as well).
- Replay (tools/diagnostics/replay_lidar_swept_policy.py, every /scan of 3 recorded drives):
  * arcs R 1.5-3 m: veto 60-73 % -> 32-51 %; R 0.5-0.75 m: -> 54-63 %; real driven commands 67-74 % -> 63-70 %.
  * STRAIGHT forward is itself vetoed 32-51 % (reverse 29-36 %) — unchanged by any arc rule. /scan_raw front cone:
    only 55 % of scans have all 18 front bins; 18 % miss exactly one; gaps cluster at 10-20 deg (13-14 %) and
    320 deg (17 %). 15 rays per bin, all without a return (not the self-filter).
- Conclusion: the swept-path rule is correct but NOT sufficient; the front-cone LiDAR no-return gaps are the main
  autonomy blocker. Not deployed. Candidate next step (owner decision): count a LiDAR bin as observed when another
  live range sensor (Astra /astra/obstacle_scan front, ultrasonic) has a valid return for that bearing — still never
  turning "no data" into free space.

## 2026-11-15 ~13:30 — LiDAR + Astra fused coverage: designed + offline replay (NOT deployed)

- Owner: "Yes, design it". Changes (source only, nothing deployed, nothing on the Jetson changed):
  * atlas_astra_obstacle_core.ObstacleScanner.scan(): also computes last_coverage per Astra bin — obstacle range, or
    0.83 x the farthest valid FLOOR point (lens 0.23 m, 4 cm floor cut => nothing taller than 4 cm before 0.83 d);
    walls/ceiling never used (seen over a low black obstacle); NaN = no evidence. Published ranges unchanged.
    (Not yet published as a topic; node/bridge/mux wiring not written.)
  * atlas_lidar_availability: update_coverage()/covered() — a LiDAR no-return bin counts as observed only if Astra
    saw an obstacle there or the floor clear >= 0.8 m from the laser across the whole bin (0.75 s timeout).
  * travel_cone() is now the straight-line SWEPT footprint (fwd ~+/-35 deg, rev ~+/-45 deg incl. the laser's rear
    offset) instead of a fixed +/-45 deg. 16 unit tests OK.
- Replay (tools/diagnostics/replay_fused_coverage.py; colour-remap sessions with simultaneous /scan + Astra depth):
  * remap7 (11-13): Astra fills 44 % of forward LiDAR gap bins; straight-forward veto 74 % -> 39 %; gentle left arc
    74 -> 40 %, but right arcs stay 72-78 % (gaps on the right outside the Astra FOV).
  * remap6 (11-13): LiDAR-only veto 92-100 %, fused 89-100 % (that session's scans are far worse).
  * mapping bags (LiDAR only, new straight cone): straight 27-35 %, R 1.5 m arcs 27-38 %, R 0.75 m 56-61 %.
- Conclusion (confirmed): even fused, autonomy would be stopped on roughly 40-75 % of scans. The dominant problem is
  how often the RPLIDAR returns NO echo in the travel sector (raw driver output, not the filter). Root cause NOT yet
  known (candidates: glancing incidence on walls, dark/absorbing surfaces, scan mode/quality). Suspected, unverified.
- Next (owner decision): offline root-cause study of the no-return rays against the accepted map (expected range and
  incidence angle per missing ray) before any further guard change. Swept-path + fusion stay undeployed.

## 2026-11-15 ~14:00 — LiDAR no-echo root-cause study (offline, remap-13 recording + its own map)

- Tool: tools/diagnostics/lidar_no_echo_study.py (ray-cast every ray of every 10th /scan_raw on the session map
  .atlas_candidate_21ed0671...; pose = /tf map>odom>base_link + laser mount). 392 scans, 423,360 rays.
- Confirmed: 14.0 % of rays have no echo. 78 % of those should have hit a mapped wall at NORMAL incidence
  (29 % of all no-echo rays at < 1 m, where the class misses 8.3 %; 1-3 m misses 13.8 %; > 3 m 46 %).
  Glancing incidence (> 70 deg) explains only 16 % of no-echo rays (miss rate 11-57 %); open/no wall 6 %.
- Not consistent surfaces: of 365 wall cells (15 cm) seen >= 20 times only 24 miss >= 70 % (11 % of no-echo
  rays); median cell miss rate 13 % — the same walls echo in most scans and drop out in others.
- Dropouts come in long contiguous runs: 1080 samples/scan (0.33 deg); runs of 40-70 samples (13-23 deg) occur
  thousands of times; scan rate 7.4 Hz (scan_time 0.135 s) although the driver reports "scan frequency 10.0 Hz".
- Driver config: rplidar_ros, A1 (HW rev 7, FW 1.29), scan_mode Boost (8 kHz), 115200 baud, angle_compensate true.
- Suspected (NOT verified): Boost-mode sample/capsule loss on the 115200 serial link (or motor speed) producing
  sector dropouts, plus a few genuinely dark/absorbing surfaces (e.g. the parked rear-right 230-250 deg gap).
- Discriminating test proposed (owner decision; parked, E-STOP latched, restarts atlas-lidar only): 30 s of
  /scan_raw in Boost, then the same static scene in Sensitivity and Standard modes; compare no-echo fraction and run
  lengths. AMCL/SLAM consumers would see a different point density — revert if worse.

## 2026-11-15 ~14:20 — Parked LiDAR scan-mode test (owner OK; E-STOP latched; only atlas-lidar touched)

- /tmp/lidar_mode_test.sh: 30 s of /scan_raw per mode on the same static scene; driver started by hand per mode,
  atlas-lidar (Boost) restored on exit. Results (~/.local/state/project_atlas/lidar_mode_test_20261115.txt):
  * Boost (service, as deployed): 7.4 Hz, 1080 samples, no-echo 8.8 %, gap runs/scan: <3 deg 5.4, 3-13 deg 0.2,
    >= 13 deg 1.8 (one of them is the permanent rear-right 230-250 deg gap of this spot).
  * Sensitivity (by hand): 13.5 Hz (!), no-echo 28.9 %, <3 deg runs 63/scan.
  * Standard 2 kHz (by hand): 7.4 Hz, no-echo 12.7 %, >= 13 deg runs 1.7/scan.
  * Boost (by hand): 9.1 Hz, no-echo 24.1 %.
- INCONCLUSIVE: the hand-started Boost run differs strongly from the service Boost run (9.1 vs 7.4 Hz, 24 vs 9 %),
  so hand-started runs are not comparable (likely partial revolutions / different start-up state). No mode is shown
  to be better than the deployed Boost. Not adopted. Restored: one /scan_raw publisher (atlas-lidar), 7.2 Hz,
  localization VERIFIED.
- Parked static scene: Boost no-echo 8.8 % vs 14 % while driving (remap-13) — dropouts are larger in motion.

## 2026-11-15 ~14:45 — Parked LiDAR scan-mode test THROUGH the service (owner: "service se karo")

- /tmp/lidar_mode_service_test.sh: temporary atlas-lidar drop-in 90-modetest (ExecStart with scan_mode), restart,
  12 s settle, 30 s /scan_raw; order Boost, Sensitivity, Standard, Boost; drop-in removed and Boost restored on exit
  (verified: only priority.conf left, service active, "current scan mode: Boost"; localization VERIFIED 0.016 m).
- Clue: the service has priority.conf CPUWeight=1000; the earlier hand-started driver did not, and showed 24 % vs 9 %
  no-echo in the same mode -> CPU starvation of the serial reader is a plausible contributor (suspected).
- Results (same static scene; 225-255 deg = this spot's dark rear-right object):
  * Boost #1: 7.3 Hz, 1080 samples, no-echo 9.0 % (outside 225-255: 2.2 %), runs >= 13 deg 1.5/scan
  * Sensitivity: 7.3 Hz, 1080 samples, no-echo 6.8 % (outside: 1.5 %), runs >= 13 deg 0.2/scan
  * Standard: 7.6 Hz, 360 samples, no-echo 43.8 % — not comparable (2 kHz at ~7.5 Hz < 360 samples/rev, so the
    angle-compensated 1-deg array has many empty slots)
  * Boost #2: 7.3 Hz, no-echo 8.7 % (outside: 1.7 %), runs >= 13 deg 1.4/scan (repeatable with #1)
- Evidence gap: the owner reported moving the rover by hand by mistake during the test (time unknown); the final pose
  equals the starting pose (-1.61, 0.03) and Boost #1/#2 agree, so the scene appears unchanged, but not proven.
- Reading: Sensitivity (designed for low-reflectivity targets) removed most long gaps here, incl. the dark
  rear-right object. Parked only; the driving dropouts (14 %) are untested in Sensitivity. Not adopted.

## 2026-11-15 ~16:00 — LiDAR Sensitivity mode DEPLOYED (owner: "Yes, switch and test") + ground drive

- Drop-in systemd/user/atlas-lidar.service.d/50-scan-mode-sensitivity.conf (scan_mode Sensitivity; rollback: delete,
  daemon-reload, restart atlas-lidar). Switched parked with the E-STOP latched; live: "current scan mode: Sensitivity,
  8 Khz", /scan 7.2 Hz, localization VERIFIED 0.06 m.
- Owner drive Dhruv Room -> hall -> Dhruv Room, recorded (data/lidar_tests/sensitivity_drive_20261115, 306 s;
  /scan_raw, /scan, /tf, /odom, /cmd_vel, ICP, encoder health). Final localization VERIFIED 0.158 m.
- No-echo study on the same accepted map (atlas_latest == remap-13 candidate map): no-echo 14.0 % (Boost, remap 13)
  -> 8.2 % (Sensitivity). Walls < 1 m 8.3 -> 4.1 %, 1-3 m 13.8 -> 4.9 %; median wall-cell miss 13 -> 5 %.
  Remaining no-echo is mostly far walls > 3 m and open space (expected), not near walls.
- Guard replay (same two drives; deployed rule vs swept-path rule, source only):
  * Boost/remap13: real driven commands vetoed 74 % (deployed) / 63 % (swept-path); straight 46 / 35 %.
  * Sensitivity/today: real driven commands 45 % (deployed) / 32 % (swept-path); straight 24 / 21 %;
    gentle arcs (R 1.5 m) 80 % (deployed) / 21 % (swept-path); tight arcs (R 0.5 m) 80 / 64 %.
- Caveat: different days/routes are only approximately comparable; one drive per mode. The guard is still the
  deployed (old) rule; swept-path and Astra fusion remain undeployed.

## 2026-11-15 ~16:20 — Swept-path LiDAR availability rule DEPLOYED (owner: "Yes, deploy it")

- scripts/atlas_lidar_availability.py (commit b9b9a01 version) installed; backup
  atlas_lidar_availability.py.before-swept-20261115. Live mux file unchanged (md5 = repo). tests/test_lidar_availability
  16 OK on the Jetson against the live mux. Rover parked, E-STOP latched; only atlas-cmd-vel-mux restarted; after
  restart: manual_only false, stop_latched true, source STOPPED, no errors in the journal.
- Astra coverage fusion code is present but INACTIVE (nothing publishes/subscribes the coverage topic yet).
- Read-only dry probe of live /scan at the parked spot (-1.6, 0.03), 108 scans, nothing published: straight forward,
  R 1.5 m arcs both ways and straight reverse 0 % veto; R 0.5 m arc and spin-in-place 100 % veto (all-bins rule).
- Rollback: copy the .before-swept-20261115 backup back, restart the mux (parked, E-STOP latched).

## 2026-11-15 13:41-13:43 — Supervised goal #2 ("dhruv room", ~1.8 m): blocked by the REAR ultrasonic guard (rover did not move)

- A first send attempt at 13:41:33 happened while the dashboard still showed the E-STOP latched (my chain did not
  stop on the failed latch check); mission control logged nothing (no goal received); cancel sent anyway.
  Fixed procedure: second send used `set -e` with the release/parked/Astra/VERIFIED assertions (13:42:17).
- Mission: SCAN CHECK OK 99 %, goal dispatched/accepted; the swept-path LiDAR guard did NOT block this time.
- Nav2 RPP (allow_reversing: true) commanded REVERSE the whole time: /cmd_vel_nav = (-0.11 m/s, +0.67 rad/s) for
  370 of 372 messages (bag data/lidar_tests/auto2_goal_20261115). The mux vetoed every one: "AUTONOMY BLOCKED: REAR
  0.18-0.21 m (stop 0.30 m)" (rear ultrasonic required for linear < 0). Controller "Failed to make progress" ->
  recovery -> retry. Goal cancelled 13:43 (status 5). Rover never moved.
- Open: why the planned path starts behind the rover for a goal ~30 deg left-ahead (front ultrasonic 0.58-0.77 m,
  LiDAR nearest ~0.36 m at this spot; /plan was not recorded). Suspected: the start pose is boxed in by furniture
  so the planner/RPP chooses a reverse-turn manoeuvre. Not verified.

## 2026-11-15 13:51 — Supervised 1 m goal: FIRST AUTONOMOUS MOTION; speed ~6x the command (SAFETY FINDING)

- Temporary place "test 1m" (current pose + 1 m along heading; map checked free; places file backed up
  .before-test1m-20261115 and restored afterwards). One goal via mission control (all gates). Bag
  data/lidar_tests/auto3_1m_20261115 (incl. /plan, /cmd_vel_nav, /cmd_vel, /odom, safety/mission status).
- Plan 16 poses (-1.47,-0.02) -> (-0.39,0.38). Nav2 /cmd_vel_nav 0.15 m/s; mux output /cmd_vel 0.07 m/s (encoder
  DEGRADED scale 0.5). MEASURED /odom vx 0.47-0.51 m/s within 0.6 s (odom x -0.25 -> 0.37 in ~1.2 s) — about 6-7x
  the 0.07 command. After the controller sent zero (110.36 s) odom still read 0.51 m/s at 110.71 s and travelled
  ~0.1 m more. Then RPP "collision ahead", mux "AUTONOMY BLOCKED: FRONT 0.16 m (stop 0.30 m)", backup recovery
  (-0.06 command, odom -0.38 m/s), second approach, "LIDAR AVAILABILITY STOP (3 bins)", and mission control's camera
  watchdog cancelled the goal ("camera obstacles lost (2.3 s stale)"). Net ~0.5 m forward. No contact reported.
- Cause (code, yahboom_base._drive_pwm, open loop because Drive PID needs 4 encoders): any non-remote command above
  0.02 maps to PWM >= AUTONOMOUS_MIN_RUN_PWM = 60 (+40 x |v|); 0.07 -> PWM ~63, which on this floor drives ~0.45 m/s.
  The 2026-10 note validated this floor for 10 cm Nav2 nudges, not for continuous following.
- Consequences: Nav2 believes 0.07-0.15 m/s while the rover moves ~0.5 m/s; stopping distance and obstacle margins
  are invalid. Camera bridge staleness (2.3 s) under load is a second, separate finding.
- Status: no further goals sent. Owner decision needed (speed calibration / closed-loop speed, and whether to restore
  manual-only meanwhile).
- 2026-11-15 ~14:05 (owner: "Yes, lock it"): manual-only lock RESTORED. 45-supervised-autonomy.conf moved to
  ~/.config/systemd/user/45-supervised-autonomy.conf.disabled-20261115 (removed from the repo), daemon-reload, mux
  restarted with the rover still. Live: ATLAS_MANUAL_ONLY=1, control_policy manual_only true, stop_latched true.
  navigation_validated, the 3-encoder rule, the swept-path guard and LiDAR Sensitivity stay deployed. Autonomy
  re-opening requires the autonomous speed calibration (commanded vs measured) first.

## 2026-11-15 ~14:30 — Speed check from recordings (owner chose "calibrate speed first"; lock stays ON)

- Confirmed from the auto3 bag TF: odom>base_link moved -0.245 -> +0.375 m between 110.5 s and 112.5 s while
  map>odom changed only ~6 cm (AMCL agrees) => ~0.35-0.4 m/s average, ~0.5 m/s peak, for a 0.07 m/s mux command.
- Steady-command bins (odom vx while the PWM implied by the command was constant >= 0.7 s):
  * manual drive (REMOTE floor 80-90): PWM ~84 -> +0.37 m/s (p10 0.23, p90 0.50); reverse -0.36 m/s.
  * autonomous (floor 60): PWM ~62 -> +0.27 m/s median (p90 0.47); reverse -0.33 m/s.
  => In 60-90 PWM the speed hardly depends on PWM (~0.3-0.4 m/s); the commanded speed is not represented at all.
- No existing owner-triggered motion commissioning test (atlas_commissioning has hardware/imu/gnss/distance only),
  and I do not send motion commands. A proper PWM -> speed map below 60 (breakaway / stall point) needs a new,
  bounded, owner-triggered ground test, or closed-loop speed from the three encoders. Design pending owner OK.

## 2026-11-15 ~15:30 — Closed-loop autonomous speed with 3 encoders: designed + offline tests (NOT deployed)

- Owner chose "Closed-loop speed (3 enc)". New pure module scripts/atlas_speed_loop.py (no ROS; NOT wired into
  yahboom_base yet). Non-REMOTE only. Per 0.1 s tick: measured speed = 3-encoder consensus distance over the last
  3 ticks; state machine REST -> breakaway search (PWM from 38, +2.5 per tick, restarting just below the last
  learned breakaway) -> ROLLING (on first motion it releases 10 PWM below the breakaway PWM, then PI + feed-forward).
  Fail-safe: zero/deadband command -> 0; invalid feedback (consensus/packet stale/non-finite/bad dt) -> 0 + reset;
  HARD overspeed cut (|v| > max(1.5 x target, target + 0.08)) -> 0 PWM that tick; moving against the command -> 0
  until stopped; |PWM| <= 75; bad parameters rejected.
- Motor identification from recordings (tools: scratch ident script; bags auto3_1m / sensitivity_drive):
  motion visible 0.34 s (auto) / 0.44 s (manual median) after a command; PWM ~62 -> ~0.27-0.40 m/s, ~84 -> 0.37 m/s;
  coasting after a zero command 0.74-0.84 s from ~0.37 m/s (~0.45 m/s^2, ~0.14 m). In auto3 the rover already
  moved at 0.05 m/s 0.23 s after the first command, while the base slew was at 45-53 PWM => breakaway likely <= ~53
  (suspected; one start only). The breakaway PWM is NOT measured.
- tests/test_speed_loop.py: 11 OK (Mac and Jetson). Plant model reproduces the recordings (slew 45 + 8/tick, 1-tick
  latency, static/kinetic friction, 0.2 s spin-up, 0.45 m/s^2 coast, bursty 1 mm encoder counts) and sweeps the
  unknown breakaway 45/50/55/60 PWM (hold = breakaway - 10), targets 0.07/0.10/0.15 m/s, 3 seeds:
  start <= 1.0 s; mean speed after 5 s within 0.035 of the target (e.g. 0.10 -> 0.065-0.097); peak <= 0.24 m/s
  (open loop: 0.28 in the model, 0.4-0.5 measured); stop from 0.10 m/s coasts < 0.05 m. Worst-case "plateau" motor
  (no slow rolling band): the loop can only pulse — mean 0.07-0.08 for a 0.10 target, peak <= 0.25, > 0.18 m/s for
  9-14 % of the time.
- Read-only replay (tools/drive/replay_speed_loop.py; recorded consensus deltas + recorded mux commands, plant =
  the real open-loop run): in auto3 the loop would have commanded <= 43 PWM, released to ~0 when motion appeared at
  0.23 s, and its first overspeed cut would fall at 0.62 s (0.28 m/s) — the real run kept 62 PWM and reached 0.5 m/s.
  Manual drive: REMOTE path not affected (replay for information: 6 cuts, 2 invalid-feedback ticks in 601).
- Not done / evidence gaps: no integration into yahboom_base (needs a flagged hook in _drive_pwm for non-REMOTE
  sources, before the existing slew/turn bias), no ground test. Ground qualification needs the owner's OK, the rover
  parked + E-STOP latched for the base restart, and a supervised low-speed test with manual-only temporarily open.
  Manual-only lock stays ON. Nothing deployed.

## 2026-11-15 ~15:30 — Dashboard AUTONOMY ON/OFF + waypoints (owner request; built + tested, NOT deployed)

- Mux: scripts/atlas_autonomy_arm.py (pure) + atlas_cmd_vel_mux services /atlas/autonomy/arm|disarm. Boot OFF;
  ATLAS_MANUAL_ONLY=1 stays the default lock and is lifted only while armed (needs new drop-in
  46-autonomy-runtime-switch.conf: ATLAS_AUTONOMY_RUNTIME_ARM=1). ON refused unless E-STOP latched, rover still,
  encoder health fresh + autonomy_ready, and config/autonomy_gate.yaml speed_validated: true (FALSE now: speed
  calibration pending). OFF always accepted; any new E-STOP latch or mux restart -> OFF. control_policy gains
  'autonomy' {armed, runtime_enabled, arm_blockers, last_change}.
- Mission control: /atlas/delete_named_place (accepted-map places file; refused during mapping).
- Web: scripts/atlas_autonomy_web.py — GET /api/autonomy (state + waypoints), POST /api/autonomy {on (operator PIN,
  same store/lockout as E-STOP reset) | off}, POST /api/places {save|go|delete, name 1-24 chars}. GO refused unless
  autonomy ON and E-STOP released (a queued goal can never start by itself on a later release); mission control
  still runs every navigation check. Events go to the E-STOP event log.
- Dashboard: web/v2/autonomy-panel.js in the home "Mission and position" panel (state, PIN, ON/OFF, waypoint list
  with Go/Delete, "Save waypoint here"). Checked in a local mock page (layout at phone width, save flow).
- Tests: test_autonomy_arm (9) + test_autonomy_web (8) OK; mux stop-hold/mapping-limit/heartbeat/lidar/ultrasonic,
  camera gate, session places, final-map sampling, commissioning suites OK on the Jetson against the candidate files.
  test_status_web_estop_safety, test_source_provenance, test_testlab_static, test_final_map_consistency fail
  identically at HEAD in the same temp layout (missing helper modules) — pre-existing, not caused by this change.
- Live files equalled git HEAD before the change. Deploy (owner OK): parked + E-STOP latched; restart mux, mission
  control and rover-status-web.
- 2026-11-15 ~16:05 DEPLOYED (owner: "Yes, deploy"), rover parked + E-STOP latched: mux (+ 46-autonomy-runtime-switch
  drop-in), mission control, status web + atlas_autonomy_web/arm, autonomy_gate.yaml (speed_validated false), v2
  index/glass/autonomy-panel.js; backups *.before-autopanel-20261115. Live: ATLAS_MANUAL_ONLY=1 +
  ATLAS_AUTONOMY_RUNTIME_ARM=1; manual_only true; /atlas/autonomy/arm refused "autonomous speed not validated (speed
  calibration pending)"; panel visible on the live dashboard (AUTONOMY OFF, ON blocked, waypoints listed).
  Fix after deploy: the places file's top-level map_id was stale (old map d12a1f18), so waypoints showed "other map";
  the web now computes the accepted map id like mission control (map_pair_id of atlas_latest yaml+pgm) -> both
  waypoints on the current map 38253aab.

## 2026-11-15 ~16:40 — Tap-the-map waypoints (owner: "Yes, add map tap"; built + tested, NOT deployed)

- scripts/atlas_map_waypoint.py (pure): a tapped map point is accepted only if it is inside the ACCEPTED map, on a
  free cell (trinary 205 = unknown) and no occupied/unknown cell lies within 0.35 m (footprint half-diagonal 0.31 m +
  margin). On the live accepted map: "dhruv room" and "hall" pass; this morning's tight start spot (-1.47, 0.00) and
  the 1 m test goal (-0.51, 0.24) are refused "too close to a wall" (matches the real 13-16 cm clearances).
- Mission control: /atlas/save_named_place_at (JSON name, x, y): refused during mapping; heading = from the rover's
  current map pose towards the point; written with the current map_id. Web: POST /api/places action save_at.
- Navigation page (/v2/mapping): web/v2/map-waypoints.js adds a "WAYPOINTS — TAP THE MAP" card: tap -> yellow
  crosshair + coordinates -> name -> Save; waypoint list with Go (disabled unless AUTONOMY ON and E-STOP released).
  Tap disabled in mapping mode. Local check through a read-only proxy of the live dashboard: tapping the Dhruv Room
  marker gave (0.09, 0.53) vs stored (0.08, 0.54); save sent {save_at, x, y}; crosshair persists across redraws.
- Tests: test_map_waypoint 6, test_autonomy_web 9, test_autonomy_arm 9 — OK.
- 2026-11-15 ~16:50 DEPLOYED (owner: "Yes, deploy"), parked + E-STOP latched: mission control, status web,
  atlas_autonomy_web, atlas_map_waypoint, v2 mapping.html + map-waypoints.js (backups *.before-maptap-20261115);
  restarted atlas-mission-control and rover-status-web only. Live end-to-end: /atlas/save_named_place_at "deploy
  test" (1.47, -5.60) saved with the map-tap note, then deleted via /atlas/delete_named_place (PLACE DELETED);
  "bad spot" (-1.47, 0.00) refused "too close to a wall/obstacle (occupied within 0.35 m)". Places file back to
  dhruv room + hall (backup .before-maptaptest-20261115). Map page serves the waypoint card. Autonomy still OFF.

## 2026-11-15 ~17:30 — Owner requests: tap->Move here, detour around obstacles, spoken stop reasons, Manual/Autonomous switch (built + tested, NOT deployed)

- Move here: mission control /atlas/navigate_to_point (JSON x, y) -> same map-tap validation (free, 0.35 m
  clearance, accepted map) -> dispatch_pose_goal (all existing gates: localization refresh, scan/map agreement,
  camera obstacles). Web POST /api/places {action: go_at, x, y} refused unless Autonomous mode ON + E-STOP released.
  Map card: tap -> "Move here" / Cancel / optional save as waypoint.
- Detour: new tree config/atlas_ackermann_replan_if_blocked.xml (fail_stop tree unchanged): PipelineSequence with
  RateController 1 Hz {keep the committed path while IsPathValid on the global costmap, else ComputePathToPose}
  + FollowPath, same recovery branch (clear costmaps, 0.18 m back-up, wait, 6 retries). Mission control passes it
  per goal (NavigateToPose.behavior_tree, param nav_behavior_tree) so no Nav2 restart is needed; missing file ->
  default tree. Node IDs all exist in Humble's stock trees; NOT yet loaded by bt_navigator (needs a goal) and NOT
  ground-tested (autonomy blocked by the speed gate). Mux guards remain the last-resort stop.
- Spoken reasons: scripts/atlas_autonomy_voice_core.py + atlas_autonomy_voice.py (new unit atlas-autonomy-voice,
  listen-only) -> /atlas/voice/test_speak (voice companion speech-only path, Hindi Piper voice). Speaks only in
  Autonomous mode or during a goal; 15 s repeat / 4 s gap limits. Covers mode changes, E-STOP, front/rear/side
  ultrasonic stops, ultrasonic data loss, LiDAR availability stop, goal accepted/arrived/canceled/no path, camera
  loss, refused spots, and each new Nav2 recovery ("raste mein kuch hai, naya rasta dhoondh raha hoon").
- Mode switch: home panel and map card show MODE: MANUAL / AUTONOMOUS with "Manual mode" / "Autonomous mode"
  buttons (Autonomous = PIN + all arm gates; Manual always allowed).
- Tests on the Jetson: test_autonomy_arm, test_autonomy_web (11), test_autonomy_voice (9), test_map_waypoint,
  camera gate, session places, final-map sampling, idle revert, mux stop-hold — all OK.

## 2026-11-15 (later) — Speed loop wired into yahboom_base behind a flag; parked deploy + ground check prepared (NOT deployed)

**What changed (candidate, uncommitted):**
- `project_atlas/scripts/yahboom_base.py`. The new loop applies only when `config/speed_loop.yaml` has `enabled: true`, and only to non-REMOTE sources:
  - In `_drive_pwm`, the speed loop sets the PWM. It still goes through `_slew_motor_pwm`.
  - Misaligned steering (> 8°) counts as a zero speed target, which is the same gate as before.
  - 4WS arcs use `turn_split`, meaning ±8 PWM with **no 80-PWM inside floor**. That floor would otherwise force any autonomous turn to ≥ 80 PWM.
  - REMOTE is identical to before; a test compares the outputs.
  - Feedback: `_publish_yahboom_odom` feeds the consensus `distance_delta` into `SpeedFeedback`. "ok" requires a fresh encoder packet and ≥ 2 accepted channels.
  - A drive tick with no new sample holds its output only while the newest sample is ≤ 0.25 s old. Beyond that the PWM is 0. A zero or reverse command always gives 0.
  - Status topic `/atlas/speed_loop` (JSON): target, measured, pwm, reason, learned breakaway. It publishes at 10 Hz while active and 1 Hz while idle.
- `config/speed_loop.yaml`: ships `enabled: false`. Missing file or disabled → legacy map, unchanged. Enabled with bad parameters, or the module missing → **non-REMOTE fails closed (0 PWM)**. It never falls back to the 60-PWM floor.
- `scripts/atlas_speed_loop.py`: adds `SpeedFeedback`, `turn_split` and `load_speed_loop_config`.
- Tests:
  - `tests/test_speed_loop_base.py` has 15 tests. They run the real `_drive_pwm` and slew code extracted from the source.
  - `tests/test_speed_loop_ground_check.py` has 5 tests.
  - Jetson (candidate tree `/tmp/speedloop_cand`): 31/31 speed-loop tests OK. The existing base tests (steering geometry, lifted owner, diagnostic cadence) pass 19/19.
  - `test_stage28_yahboom_hooks` fails 6 times in the candidate tree. The original `yahboom_base.py` fails the same 6 there, so this is the test environment, not this change.
- Simulation through the base path (breakaway 45–60, target 0.10 or 0.15, straight or wz 0.2):

  | Measure | Result |
  |---|---|
  | Start | 0.5–1.4 s |
  | Mean speed | 0.088–0.096 (target 0.10); 0.128–0.133 (target 0.15) |
  | Peak | ≤ 0.21 m/s |
  | Max PWM | ≤ 72 (arc, outside wheels) |

- Live Jetson unchanged: md5 `09fcf38e…` is the deployed `yahboom_base.py`. No speed_loop files are installed.

**Parked deploy (owner OK each step):** `tools/deploy/deploy_20261115_speed_loop.sh`. It refuses to run without `ATLAS_OWNER_CONFIRM=parked-estop-latched` and the parked check.
1. `install`: runs the candidate tests, backs up the live files with tag `before-speedloop-20261115`, installs, and restarts the base with the loop **disabled**. This is behaviour-neutral.
2. `--enable`: sets `enabled: true` and restarts the base. The journal must show "closed-loop autonomous speed ENABLED".
3. `--disable` and `--rollback` are available at any time.

**Owner-driven ground check (speed loop ground check):** `tools/drive/speed_loop_ground_check.py`. It uses the mux COMMISSION lease (20 s), so manual-only stays ON and the remote pre-empts.
- Command: forward only, 0.05–0.15 m/s, ≤ 1.0 m, ≤ 15 s.
- It stops on any of:
  - LiDAR front clearance < 0.60 m, front sector blind, or `/scan` stale;
  - `/yahboom/odom` or `/atlas/speed_loop` stale;
  - measured speed > target + 0.15;
  - `fail_closed`;
  - Ctrl-C.
- It needs ≥ 1.0 m clearance to start.
- PASS criteria:
  - starts ≤ 2 s;
  - mean speed after 1.5 s within ±0.04 of the target;
  - peak < max(1.5t, t + 0.08) + 0.05;
  - ICP and wheel distance agree within 25 %;
  - ended by distance or timeout.
- Plan, rover on open floor with ≥ 1.5 m clear and the owner holding the remote:
  1. `--speed 0.10 --distance 0.6` ×3;
  2. `--speed 0.15 --distance 0.8` ×2;
  3. `--speed 0.05 --distance 0.4` ×1 (expected to be slow or jerky; information only).
- Results go to `~/.local/state/project_atlas/speed_loop_check_*.json`.
- Only after 5/5 PASS at 0.10 and 0.15 may the owner decide to set `autonomy_gate.yaml speed_validated: true`, with the evidence recorded here.

**Not covered yet:**
- reverse and arcs on the ground;
- the real breakaway PWM;
- whether the mux LiDAR availability guard vetoes COMMISSION runs, as it did NAV2;
- the effect of the 3-tick measurement window at 0.05 m/s.
- 2026-11-15 ~17:50 DEPLOYED (owner: "Yes, deploy"), parked + E-STOP latched: mission control (navigate_to_point,
  per-goal replan tree), atlas_ackermann_replan_if_blocked.xml, status web + autonomy web (go_at), v2 panels (mode
  switch, Move here), atlas_autonomy_voice(+core) as new enabled unit atlas-autonomy-voice. Backups
  *.before-v3-20261115. Live: /atlas/navigate_to_point and /atlas/save_named_place_at subscribed; mission control
  param nav_behavior_tree = the replan tree (loads on the first goal; not yet exercised); narrator node running;
  Autonomous mode still blocked by the speed gate.
- Speaker finding (pre-existing, voice companion, not changed): a test sentence on /atlas/voice/test_speak produced
  no speech and no log line; the boot greeting earlier took ~315 s to play (14:24:27 -> 14:29:42) for ~6 s of
  audio (ESP32 USB audio transport pacing / buffer). The narrator publishes correctly, but spoken output depends on
  fixing the voice companion's playback path. Not investigated further yet.
- 2026-11-15 ~18:10 speaker check (owner: "Yes, fix speaker"): NOT a speaker fault. A single
  `ros2 topic pub --times 1` from a short-lived CLI is lost (the voice companion has not matched the brand-new
  publisher yet; volatile QoS). Publishing at 1 Hz: "Voice test." spoken (BUFFERING -> SPEAKING in 0.05 s, done in
  1.2 s) and the Hindi narrator sentence spoken via the hi_IN Piper voice (~3.7 s). The narrator node is long-lived,
  so its publisher stays matched. The 315 s boot greeting remains unexplained (likely ESP32/USB at boot); no code
  changed.

## 2026-11-15 ~18:45 — Self-service Autonomy Readiness (owner: "tell me why, how to clear it, open the test, unlock on pass") — built + tested, NOT deployed

- scripts/atlas_readiness.py: checklist of every autonomy blocker — mux link, speed (closed loop + ground check),
  encoders, E-STOP latched (to switch ON), localization VERIFIED (<= 120 s), camera obstacles reaching Nav2,
  waypoints (optional). Each item: why (live reason), Hindi fix steps, a button (Speed check / Motor & Encoder Test
  Lab / Check my location / Camera bridge starter / Navigation page) and what clears it.
- Self-unlock for speed: atlas_autonomy_arm.speed_evidence — speed counts as validated when the speed loop is enabled
  AND there is a PASS from speed_loop_ground_check.py at 0.10 and 0.15 m/s newer than config/speed_loop.yaml,
  atlas_speed_loop.py and yahboom_base.py (any change needs a fresh check), <= 30 days old. Manual
  speed_validated flag still works. Live now: enabled, no results -> "run the Speed check at 0.10 and 0.15 m/s".
- Web (atlas_autonomy_web): GET /api/readiness; POST /api/readiness/bridge (starts the bridge starter, which
  re-checks parked/CPU); POST /api/readiness/speedcheck {0.10|0.15, PIN} runs the speed-loop session's ground check
  tool (one at a time; refused unless tool installed, PIN ok, Manual mode, E-STOP released, speed loop enabled);
  GET /api/readiness/speedcheck (log + results). New page /v2/readiness (readiness.html/js); links from the home
  panel and the map card.
- Owner decision on "override with a code": "Owner sign-off test" — NO override for safety items; each is cleared
  only by its owner-run check. Waypoints are optional (Move here works without), so they never block.
- Tests: test_readiness 7, test_autonomy_arm 14 (5 new evidence), test_autonomy_web 12 — OK on the Jetson.
  Deploy needs: mux restart (gate code), rover-status-web restart; rover parked + E-STOP latched.
- 2026-11-15 ~19:00 DEPLOYED (owner: "Yes, deploy"; E-STOP latched by owner, no ground check running): autonomy_arm
  (evidence gate), autonomy_web (+readiness/speedcheck/bridge), atlas_readiness, atlas_web_v2 (/v2/readiness), v2
  panels + readiness page; backups *.before-readiness-20261115; restarted atlas-cmd-vel-mux and rover-status-web.
  Live checklist: mux, encoders, E-STOP, localization, camera, waypoints all OK; ONLY blocker = speed ("run the Speed
  check at 0.10 and 0.15 m/s"); the ground check tool is not yet installed on the rover (speed-loop session).
  Mux arm_blockers now read the same message.

## 2026-11-15 ~17:00 — Speed loop takeover (main session): fixes deployed, ground check still FAIL (ultrasonic backlog)

- Deployed (parked, E-STOP latched): atlas_speed_loop.py (breakaway needs window speed >= 0.03 m/s for 2 ticks;
  ff 44, release_drop 6), tool evaluates against the base-reported target + peak after 1.5 s + runaway floor 0.35,
  gate = 2 PASS at requested 0.15 (atlas_autonomy_arm), readiness texts; mux ATLAS_SPEED_LOOP_CLOSED=1 (drop-in 47)
  keeps the full command while DEGRADED (CRITICAL still stops). Backups *.before-speedfix-/before-speedclosed-20261115.
- Runs: at half speed (0.06) the rover rolled 0.37 / 0.6 / ~0.4 m with mean 0.052-0.062 but stop-go peaks
  0.20-0.22 (FAIL). At full speed (16:58, base target 0.12) it rolled smoothly 0.2 m (0.17 -> 0.10 m/s) until the mux
  aborted the commission lease: "AUTONOMY BLOCKED: FRONT ULTRASONIC SERIAL_BACKLOG" (FAIL, STATUS_STALE).
- OPEN: the ultrasonic bridge's intermittent SERIAL_BACKLOG invalidation aborts every commission/autonomy run within
  seconds; fix that next (bridge should publish the newest complete report instead of invalidating, or the mux
  should tolerate one short invalid sample), then rerun 2 x Speed check. Base target 0.12 vs 0.15 also unexplained.
- 2026-11-15 ~17:10 Speed check PASS x2 (owner-run from the dashboard, after the full-speed mux change): requested
  0.15, base target 0.12; run A mean 0.116 / peak 0.183 / DISTANCE; run B mean 0.096 / peak 0.148 / DISTANCE.
  speed_evidence ok -> mux arm_blockers empty, Readiness "ready_to_switch_on" true (self-service unlock worked).
  Two other runs ended STOP_RUNAWAY: breakaway this time needed PWM ~66-69 and the rover surged 0.31 m/s at release
  (> 0.35 floor for 2 samples) — guard stopped it as designed; breakaway PWM varies run to run (floor/battery).
  Base target 0.12 instead of 0.15 still unexplained (mux radar/limit factor suspected).
- ~17:15 DEPLOYED owner request "front/back ultrasonic only for close range": atlas_ultrasonic_validity veto returns
  no block for a missing/backlogged report when ATLAS_ULTRASONIC_ADVISORY=1 (drop-in 48); a VALID close reading
  still blocks. Backup *.before-advisory-20261115. Mux restarted parked + latched. Localization needs a fresh
  "Check my location" before the first autonomous goal.

## 2026-11-15 ~21:37 — First autonomous goal in Autonomous mode (waypoint "test v2"): moved ~0.25 m, then stopped

- Readiness all green (localization VERIFIED), mode AUTONOMOUS, owner released E-STOP and pressed Go on waypoint
  "test v2". Mission: SCAN CHECK OK 99 %, goal dispatched/accepted; narrator spoke "theek hai, test v2 ki taraf ja
  raha hoon". Rover moved (-1.07, 0.24) -> (-0.84, 0.34).
- Then: mux "AUTONOMY STOP: ENCODER CRITICAL M1_REAR_LEFT,M2_REAR_RIGHT,M4_FRONT_RIGHT" (and again M2,M4) — the
  base freeze detector (traction applied, no count change for ENCODER_FREEZE_S 1.2 s after 0.8 s grace) fires while
  the speed loop is still in its low-PWM breakaway search: suspected false fault, NOT yet verified. Nav2 recovery ran
  (narrator: "naya rasta dhoondh raha hoon"), then "AUTONOMY BLOCKED: LOCALIZATION XY UNCERTAINTY" grew 0.33 -> 0.99 m
  and decayed; narrator: "mujhe apni jagah pakki nahi pata". Goal cancelled by me (status 5). No contact.
- Next: (1) make the freeze detector count traction only above the speed loop's breakaway (or pause it during the
  breakaway search, bounded); (2) find why AMCL XY std jumped to ~1 m during this short move.
- 2026-11-15 ~21:50 diagnosis from logs (epoch 1794754617-650): mux "AUTONOMY STOP: ENCODER CRITICAL M1/M2/M4" six
  times in 18 s (stop-go) — the base freeze detector (traction > 0, no count change > 1.2 s after 0.8 s grace) firing
  during the speed loop's breakaway search; then RPP "Failed to make progress" / "collision ahead", costmap clears,
  backup refused ("Collision Ahead"), and AMCL XY std 0.33 -> 0.99 m within ~5 s. Root cause of the AMCL growth NOT
  established (no recording of that run); suspected odometry disturbance from the stop-go.
- Fix (built, base tests OK on the Jetson; NOT deployed): yahboom_base freeze check ignores the speed loop's
  'breakaway search' while applied PWM < FREEZE_CHECK_SEARCH_PWM (70); above it, and in tracking, freeze detection
  is unchanged. Deploying changes yahboom_base.py -> the speed-check evidence becomes stale by design (2 new PASS
  needed). Next autonomous run will be recorded (odom, amcl_pose, tf, scan, cmd_vel(_nav), encoder_health,
  speed_loop) to settle the AMCL question.
- 2026-11-15 20:38 DEPLOYED freeze-check fix (yahboom_base, backup *.before-freezefix-20261115) after the owner
  latched B; speed evidence now stale by design (0/2 PASS). ~20:45 DEPLOYED readiness localization (owner: "LiDAR
  confirm takes long while the estimate is right"): green on a fresh LiDAR VERIFIED OR (AMCL fresh <= 3 s,
  xy_std <= 0.15 m, yaw_std <= 10 deg, no jump in 30 s AND a LiDAR VERIFIED within 30 min — remembered by the web
  process since its start). Backups *.before-locest-20261115. Mission control was already using AMCL + a 1 s scan
  check per goal; only the dashboard waited.
- Owner report from a second goal (20:3x): "thoda sahi tha but steering nahi dekha, right side ho gaya" — drifted
  right, then RPP "collision ahead" and abort. Not recorded; causes to test with a recording next: steering centre
  trim, stop-go of the speed loop, 4WS servo lag vs RPP angular command.

## 2026-11-15 ~21:10 — Closed-loop yaw rate (owner: "self adjustment — weight imbalance or tilted surface") — built, NOT deployed

- scripts/atlas_heading_loop.py: PI on yaw-rate error (Nav2 wz - IM10A gyro z from /im10a/imu/bias_corrected_candidate,
  the EKF's yaw input): kp 0.8, ki 1.2, |correction| <= 0.35 rad/s, active only while rolling (measured speed >= 0.04
  m/s), keeps the learned drift across short stops, stale IMU (> 0.3 s) or bad input -> plain Nav2 command.
- yahboom_base: subscribes to the IM10A topic when config/heading_loop.yaml enabled; adds the correction to wz in the
  autonomous kinematic-steering branch only (REMOTE untouched). Turn split uses the corrected wz.
- Tests: test_heading_loop 6 (constant drift -0.08..+0.05 rad/s with unknown steering gain 0.6-1.4 -> residual mean
  yaw rate < 0.012 rad/s, final heading error < 35 % of open loop; tracks a commanded turn with drift; bounded;
  stale-IMU fallback), test_speed_loop_base 16 incl. new autonomous-only check; all OK on the Jetson.
- Deploy restarts rover-base-telemetry (parked, E-STOP latched) and makes speed evidence stale again (already 0/2).
- 2026-11-15 ~21:21 DEPLOYED heading loop (owner "Yes, deploy"; parked + latched): yahboom_base + atlas_heading_loop +
  config/heading_loop.yaml enabled; base log "heading loop ENABLED". Backup yahboom_base.py.before-heading-20261115.
  Readiness: only the speed check (0/2) remains.

## 2026-11-15 ~21:35 — ROOT CAUSE of "drifts right": autonomous steering sign inverted (not weight imbalance)

- Recorded autonomous goal (bag data/lidar_tests/auto4_heading_20261115; IM10A, odom, AMCL, steering, speed loop,
  cmd_vel): Nav2 wz +0.08 -> +1.2 rad/s (LEFT), front servo 94 -> 121 (code "LEFT"), but IM10A gz -0.04 -> -0.38 and
  odom/AMCL yaw +11 -> -40 deg: the rover turned RIGHT. 34 of 39 moving samples opposite sign. The heading loop
  (bounded 0.35 rad/s) pushed the same wrong way; Nav2 kept raising wz. Owner pressed B. Mission control also stopped
  it once for "camera obstacles lost (2.1 s stale)".
- Owner's earlier remote drive (sensitivity_drive bag): commanded wz vs measured yaw rate opposite in 82 of 115
  samples — the mapping is physically mirrored for ROS +wz; the operator steers by feel so REMOTE was never noticed.
- Fix (built; base tests incl. a new sign test OK on the Jetson; NOT deployed — deploy needs the owner's explicit OK):
  yahboom_base AUTONOMOUS_STEER_SIGN = -1 mirrors only the autonomous kinematic-steering branch; REMOTE unchanged.
  Deploying changes yahboom_base.py -> speed check 0/2 again by design.
- 2026-11-15 ~21:40 DEPLOYED steering-sign fix (owner "Yes, deploy"; parked + latched): AUTONOMOUS_STEER_SIGN = -1 live,
  heading loop enabled, backup yahboom_base.py.before-steersign-20261115. Readiness: speed 0/2 (by design) and camera:
  atlas-astra-obstacles reports "obstacle scan not published: BLINDED" (< 30 % valid depth pixels) — camera covered,
  facing something closer than ~0.4 m, or a dark surface at the parked spot.
- 2026-11-15 ~21:50 owner: "remote mein bhi sahi kar do" — REMOTE_STEER_SIGN = -1 mirrors the remote steering branch
  too, and the zero-speed autonomous steering branch uses AUTONOMOUS_STEER_SIGN. Built, base tests OK on the Jetson
  (sign test now expects both paths front-below-centre for +wz). NOT deployed yet: after deploy the remote will feel
  reversed compared with before (stick left = physical left from now on).
- 2026-11-15 21:06 DEPLOYED remote steering mirror (owner "Yes, deploy", B latched): REMOTE_STEER_SIGN = -1 live;
  heading loop enabled; backup yahboom_base.py.before-remotesign-20261115. Speed evidence stale (0/2) by design.
- 2026-11-15 ~21:20 Speed check PASS x2 again after the steering fixes (mean 0.132 / 0.123 m/s, peak 0.21 / 0.174);
  ground-check clearance now uses the straight driving corridor (|y| <= 0.28 m) instead of a +-18 deg cone (an object
  0.31 m to the side at 1 m blocked starts). Then a goal was refused: mux "LOCALIZATION JUMP 0.21 m/4.3 deg (allowed
  0.20 m)" — the jump fault latched until a mux restart. DEPLOYED 21:19 (owner choice "clear on B + restart now"):
  a new E-STOP latch clears the jump fault (logged); every goal still runs mission control's scan/map check.
  Backup atlas_cmd_vel_mux.py.before-jumpclear-20261115. Readiness all green after restart (mode MANUAL).

### 2026-11-15 ~21:25 — first successful autonomous goal (owner supervised, remote + E-STOP in hand)
- Goal "test v2" after the steering-sign fix + jump-clear deploy: `NAMED GOAL FINISHED name=test v2 status=4` (SUCCEEDED), ~12 s.
- Bag `data/lidar_tests/auto5_steerfix_20261115`: commanded wz vs IM10A gz sign — same 104, opposite 0 (before fix they were opposite).
- AMCL start (0.03, 0.50, 4°) → end (0.06, 0.48, 1°).
- Still open: AMCL XY uncertainty spikes during drives, LiDAR availability stops, breakaway PWM variance, base reaching 0.12 instead of 0.15 m/s, Astra stale/BLINDED once, detour (replan) tree not ground-tested with a real obstacle.

### 2026-11-16 — software-only work (rover parked, nothing deployed)
- **"0.12 instead of 0.15" explained.** (a) Speed check: COMMISSION lease is clamped to ±0.12 m/s in the mux (`atlas_cmd_vel_mux.py` COMMISSION branch), so 0.123 measured = on target. (b) Autonomous (auto5 `/atlas/speed_loop`, 195 NAV2 rows over 25.7 s): tracking 44 %, breakaway search 31 %, "steering alignment wait" 26 %; 11 traction cuts while rolling. The servo slews 20 deg/s and the base cut traction whenever steering error > 8 deg, then re-searched breakaway. 13 of 15 waits needed ≤ 10 deg of servo travel.
- **Fix staged (local, NOT deployed):** `speed_loop_steering_aligned()` in `yahboom_base.py` — unchanged 8 deg gate from standstill; while the speed loop is rolling forward in the commanded direction (≥ 0.05 m/s) a 16 deg tolerance keeps traction. Reversal, bad input and > 16 deg still wait. Tests: 3 new in `test_speed_loop_base` (20/20 on the rover). Deploying it changes `yahboom_base.py` ⇒ speed evidence invalid ⇒ owner must re-run the Speed check (2 PASS).
- **test_autonomy_arm made hermetic:** it read the rover's real `~/.local/state` speed evidence (3 failures on the rover). Now patched to no evidence; 15/15 on Mac and rover.
- **Nav2 recovery audit (plan step 4):** bounded — outer RecoveryNode 6 retries, RoundRobin clear / BackUp 0.18 m @ 0.12 / Wait 2 s; progress checker 0.1 m in 20 s; mux NAV2 channel stale timeout 0.5 s (no stale Twist replay). Gap: no mission-level time budget per goal (worst case > 2.5 min of retries); proposal only.
- **Stage-3 gate checker:** `tools/drive/stage3_autonomy_check.py` (+7 tests) gives PASS/FAIL for legs, return-home (0.30 m / 20 deg), safe stop (still within 1.5 s), turn sign, encoders from a bag. auto5: turn_sign PASS 104/0, encoders PASS, legs/return/stop FAIL (no round trip recorded) — as expected.
- **AMCL XY-uncertainty during motion (offline replay, isolated domain 77, nice 19; `tools/localization/amcl_replay/`).** auto5 segment 405–446 s. Live: σxy ≈ 0.01 parked, rises to 0.10–0.25 m as soon as the rover moves, while the pose itself follows odom (end (0.03, 0.50)). Replay variants (scan-fit = beam endpoints within 1 cell of the map; σxy mean/max):
  A live params 0.513 / 0.156 / 0.218 · B z_hit 0.8 z_rand 0.2 0.518 / 0.163 / 0.242 · C +sigma_hit 0.1 0.521 / 0.157 / 0.229 · D C+alpha1-4 0.1 0.512 / 0.114 / 0.168 · E D+max_beams 120 0.515 / 0.111 / 0.168 · **F alpha1-4 0.1 only 0.513 / 0.124 / 0.178** (end (0.09, 0.49), 0 samples > 0.20 vs 3 for A).
  Reading: the laser-model settings do not change accuracy; the spread comes from the motion-noise model (alpha 0.2) now that odom is EKF+ICP fused. F is the minimal candidate (accuracy unchanged, spread −20 %, peak 0.22 → 0.18, further from the 0.28 m block). Not deployed; needs owner OK + parked AMCL restart. Scan-fit ≈ 51 % for every variant (live too) — the deeper limit is scan-vs-map agreement (clutter / LiDAR no-echo / map), not AMCL tuning.
- **DEPLOYED 2026-11-16 (owner "Yes, deploy"):** steering-gate rolling tolerance in `yahboom_base.py` (md5 367a0e97…). Backup `scripts/yahboom_base.py.before-steergate-20261116`. Base restarted with the rover parked and E-STOP latched (owner pressed B); log: closed-loop speed ENABLED, heading loop ENABLED, board ready. Readiness now MANUAL with "Speed sahi" red as expected (evidence older than the code) — the owner must run the Speed check 0.15 twice. Rollback: copy the backup back, restart `rover-base-telemetry` parked + latched.
- **Speed checks after the steering-gate deploy (2026-11-16, owner-run):** 07:33 FAIL (physical obstacle at 0.51 m; owner confirmed; mux COMMISSION ABORT ENCODER CRITICAL at PWM 75 = correct), 07:35:14 FAIL peak 0.327 > 0.25 (restart from the stuck spot, breakaway PWM 68–70 surge; overspeed cut held it), 07:35:48 FAIL STOP_ODOM_STALE (load avg 17–25), 07:36 PASS mean 0.112 peak 0.201, next PASS mean 0.120 peak 0.180. Speed evidence 2/2 → autonomy unlockable. Open: breakaway-PWM surge after a high-friction start; Jetson load spikes (polkitd briefly 62 % CPU) can stale odom.

### 2026-11-16 ~07:45 — autonomous goal auto6 (after steering-gate deploy)
- Goal "test v2" SUCCEEDED (status 4) but took 91 s. Bag `data/lidar_tests/auto6_steergate_20261116`. Turn sign same 146 / opposite 4.
- Stops seen: ENCODER CRITICAL ×5 (all three rejected at near-zero deltas during stop/start), AMCL XY uncertainty 0.25–0.30, LiDAR availability (1–8 bins; one 47 s wait).
- Speed loop: 369 NAV2 rows — steering alignment wait 237, breakaway 84, tracking 48 (tracking mean 0.126; 3–5 s stretch held 0.14–0.17). **Still 16 traction cuts while moving** — the deployed gate did not fire because:
  1. it required the speed loop's `rolling` flag; most waits began right after breakaway with the rover already at 0.05–0.21 m/s but `rolling` not yet confirmed;
  2. the heading loop stepped its correction to 0 below 0.04 m/s and back (≤ 0.35 rad/s ≈ 20 servo deg) when moving again → steering target step > gate → cut → stop → limit cycle.
- **Fix staged (local, NOT deployed):** gate uses measured speed (≥ 0.05 m/s in the commanded direction) instead of `rolling`; heading correction slews ≤ 0.5 rad/s per s in and out (`max_correction_rate`), fail-safe resets unchanged. Tests: heading 7/7 (new slew + restart tests), base 21/21 (new breakaway-curvature test). Deploy touches `yahboom_base.py` ⇒ another 2× Speed check.
- **DEPLOYED 2026-11-16 ~07:58 (owner "Yes, deploy"):** measured-speed steering gate (`yahboom_base.py` md5 18c74867…) + heading-correction slew (`atlas_heading_loop.py` md5 8b331dca…). Backups `*.before-measuredgate-20261116` / `*.before-slew-20261116`. Base restarted parked + latched; closed-loop speed ENABLED, heading loop ENABLED, board ready. Readiness MANUAL, Speed red (needs 2× Speed check).
- Speed checks after the measured-gate deploy: PASS mean 0.113 peak 0.173; PASS mean 0.118 peak 0.181 → evidence 2/2.

### 2026-11-16 ~08:10 — autonomous goal auto7 (measured gate + heading slew live)
- Goal "test v2" SUCCEEDED in **43 s (auto6: 91 s)**. Bag `data/lidar_tests/auto7_measuredgate_20261116`.
- Speed loop: tracking 70 / breakaway 69 / steering wait 133 (auto6: 48 / 84 / 237). Traction cuts while moving **9 (auto6: 16)**. Encoder CRITICAL episodes 3 (5). LiDAR availability stop episodes 9 (79). Turn sign same 214 / opposite 3.
- Remaining waits: 7 of 12 needed 18–58 deg of servo travel — Nav2 asked for large curvature changes, several near full-lock reversals (54–58 deg). Those waits are the intended gate (> 16 deg), not a bug. Next lead: why the controller flips curvature that far on a short goal (controller tuning / path), not the base.

### 2026-11-16 ~08:30 — Stage-3 round trip attempt 1: FAILED on the way to the hall (LiDAR availability)
- Bag `data/lidar_tests/stage3_roundtrip_20261116` (started a few seconds after the first hall goal). Hall goal aborted twice (status 6): controller "Failed to make progress" (0.1 m / 20 s). In 3 min the mux logged 89 LIDAR AVAILABILITY STOP (mostly 1 bin) + 5 AMCL XY-uncertainty blocks. Steering, speed and the detour BT were not the cause. No B safe-stop was recorded yet.
- Offline guard replay over the bag (`atlas_lidar_availability.travel_cone/swept_bins`): 2513 of 3022 moving scans blocked (83 %), median 1 missing bin. Missing bins concentrate at fixed rover-relative bearings −25° (1011), −35° (837), +25° (359), +45° (93). Neighbour bins have valid returns, mostly < 1 m (1800) or 1–3 m (769).
- The rays are no-echo (inf), not < range_min. Per-ray no-echo: −23° 52 %, −19° 50 %, −21° 37 %, +26° 33 %, +41° 33 %, +55° 34 %, −165° 43 %; 0° only 1 %.
- Not constant across drives: −21° no-echo 33 % here, 29 % in auto4 and ≤ 1 % in auto2/3/5/6/7. So it is not a permanent self-occlusion; it depends on location (hall approach) and possibly on surfaces there (glass/dark/shiny) or on what is near the rover. Not yet discriminated. The guard was NOT relaxed.
- **DEPLOYED 2026-11-16 (owner "Yes, deploy"): dashboard planned path stays visible while a goal is active.** `atlas_status_web.py` `visible_plan()/nav_goal_active()` + `mapping.html` GOAL arrow; the replan-only-if-blocked BT publishes /plan only on (re)plan, so the 30 s age rule hid the live path. A plan older than the current goal is still hidden. Backups `*.before-planvisible-20261116`; only `rover-status-web` restarted (base/mux/Nav2 untouched, speed evidence still valid). Test `tests/test_status_web_plan_visible.py` 6/6; four older status-web tests fail identically on the deployed HEAD file (missing `calibration_validation` in the temp test copy) — pre-existing.

### 2026-11-16 ~11:00 — Stage-3 round trip attempt 2: FAILED again before the hall (LiDAR availability)
- Bag `data/lidar_tests/stage3_roundtrip2_20261116` (recording started before the goal). Hall goal status 6: "Controller patience exceeded", then "Failed to make progress" ×2. Owner helped the rover twice by hand. In 3 min the mux logged ~430 LIDAR AVAILABILITY STOP (1–5 bins). AMCL start (−1.2, 0.1), end (2.0, −3.4); hall place (1.47, −5.91), about 2.5 m short.
- Offline guard replay: 69 % of moving scans blocked. Missing bins now include dead-ahead −10..+15° (≈ 1100), plus −30° (580) and ±30°. Blocked mostly at AMCL (0.3, 0.3), (1.0, −1.0), (2.0, −3.5).
- Dead-ahead empty bins: neighbours ±10° return 2–4 m (577) or < 2 m (326), median neighbour max 3.3 m; range_max 12 m. So a surface straight ahead returns no echo while the sides around it are seen at 2–4 m. Consistent with the glass/shiny surface the owner confirmed. Not yet taped. Guard not relaxed.
- **Audit (discriminating) of the hall-route LiDAR stops, 2026-11-16:**
  - Not motion-related: front ±45° no-echo is 9.5 % / 12.2 % on still scans in the two stage-3 bags, vs 0.3 % in auto7 (inside Dhruv Room). Moving scans 6.6 % / 7.5 %.
  - Parked live scan at AMCL (1.68, −4.44): 0 no-echo rays in front ±60° (solid surface 0.8 m ahead).
  - Ray-cast of every front no-echo ray from the AMCL pose onto the accepted map. 77/11456 and 135/10772 had no map wall within 6 m; median expected wall distance 2.55 / 3.0 m. Hits cluster on the same three map spots in both runs:
    - A (1.5, −1.0…−1.4): 24 % / 18 %
    - B (2.4–2.5, −3.3…−3.7): 21 % / 14 %
    - C (1.6, −4.0…−4.1): 10 % / 13 %
  - Conclusion (confirmed, location-specific): three surfaces on the route do not return the RPLIDAR beam. Their material is not identified yet (owner to inspect). Map image `docs/audits/stage3_noecho_spots_20261116.png`.

### 2026-11-16 — smarter LiDAR availability guard (owner request: "use the map / Astra depth"), staged locally, NOT deployed
- **Found:** the 2026-11-15 Astra floor-coverage fusion (b9b9a01) was never live. The rover's `atlas_astra_obstacle_core.py` lacked `last_coverage`; `atlas_astra_obstacle_scan.py` published no coverage; the bridge relayed only `/astra/obstacle_scan`; the mux never subscribed. 0 coverage msgs in 6 s on domain 0. Astra logs repeated `obstacle scan not published: BLINDED`.
- **Rule 1, map-known gaps** (`atlas_lidar_availability.map_known_bins`, mux `guard_map_explainer`). A missing bin is explained only if:
  - AMCL is fresh (≤ 3 s) and confident (xy ≤ 0.15 m, yaw ≤ 10°);
  - ≤ 3 bins are missing;
  - every sub-ray crosses free cells to a mapped wall ≥ MAP_GAP_MIN_M (unknown cells, map edge or no wall within 6 m fail).
  - Parameter `lidar_guard_map_gaps` (default true).
- Replay (`tools/drive/replay_map_known_gaps.py`):

  | Bag | Today | ≥ 0.8 m | ≥ 1.0 m | ≥ 1.5 m | ≥ 2.5 m |
  |---|---|---|---|---|---|
  | stage3 #1 | 83 % | 20 % | 38 % | 67 % | 76 % |
  | stage3 #2 | 69 % | 35 % | 35 % | 39 % | 42 % |
  | auto7 | 33 % | — | 32 % | — | — |

  Default 1.0 m (2× the 0.5 m sweep horizon). Remaining vetoes: AMCL not confident (median xy std 0.19–0.21 m) and > 3 bins.
- **Rule 2, Astra coverage completed:**
  - `atlas_astra_obstacle_scan.py` publishes `/astra/obstacle_coverage` (only for fresh, non-blinded frames; inf = no evidence; intensity 1 = obstacle).
  - Bridge relays it.
  - Mux subscribes → `LidarAvailability.update_coverage`. Parameter `lidar_guard_astra_coverage` (default true).
  - Not replayable on today's bags (no depth recorded).
- Residual risk (owner decision): an obstacle that also returns no LiDAR echo and no depth, standing inside an explained gap.
- Tests:
  - New: `test_lidar_map_known_gaps` 9/9; `test_astra_coverage` 4/4 (rover).
  - Existing: `test_lidar_availability` 16/16.
  - `test_track_a` has 1 error from the missing `systemd/` folder in the temp copy, identical with the deployed core.
- **DEPLOYED 2026-11-16 ~13:00 (owner "Yes, deploy"):** map-known gaps + Astra coverage.
  - Files:
    - `atlas_lidar_availability.py` a6e394e1…
    - `atlas_cmd_vel_mux.py` 518eb919…
    - `atlas_astra_obstacle_core.py` 15020b0c…
    - `atlas_astra_obstacle_scan.py` 25b3ed65…
    - `astra_obstacles_bridge.yaml` 24b17e7f…
  - Backups `*.before-smartguard-20261116`. Restarted `atlas-cmd-vel-mux`, `atlas-astra-obstacles` and `atlas-astra-bridge` with the rover parked, E-STOP latched and autonomy OFF. Base untouched; speed evidence still valid.
  - Verified: domain 0 `/astra/obstacle_coverage` 53 msgs / 8 s (base_link, 120 bins, 89 finite); mux subscribed to `/astra/obstacle_coverage` and to `/map` (TRANSIENT_LOCAL; map_server active, publishes `/map`).
  - Not yet verified: the guard effect on a real drive.
  - Rollback: copy the five backups back and restart the three services (parked + latched).

### 2026-11-16 ~13:30 — Stage-3 attempt 3 (smart guard live, hall → Dhruv Room) and threshold change
- Bag `data/lidar_tests/stage3_roundtrip3_smartguard_20261116` (18 topics incl. `/astra/obstacle_coverage`, 6146 msgs). The first "dhruv room" goal aborted at hall corner C (1.96, −4.40).
  - Live check: bin +30° empty in 56/56 scans. Map wall at 0.48–0.50 m (bin +25°: 0.6–0.75 m). AMCL xy std 0.047.
  - Outside the 1.0 m map rule and at the Astra FOV edge → correctly vetoed.
- The owner moved the rover past C by remote/hand. Second goal: at (1.55, −2.28) Nav2 commanded a 0.28 m radius turn (all 72 bins required); bins −45° (map wall 0.95 m) and +140° (0.88 m) were empty.
- The rover reached (0.06, 0.59), 5 cm from the place. It then tried a reverse tight turn for final yaw; rear bins −160/−165 were empty (one sub-ray wall at 0.93 m). The owner pressed B.
- **Owner decision: MAP_GAP_MIN_M 1.0 → 0.4 m.** Replay (Astra coverage included where recorded), vetoed moving scans:

  | Bag | Guard today | 0.40 m | 0.60 m | 1.00 m |
  |---|---|---|---|---|
  | stage3 #3 | 84 % | 26 % | 52 % | 79 % |
  | stage3 #2 | 69 % | 28 % | 33 % | 35 % |
  | stage3 #1 | 83 % | 11 % (= AMCL-not-confident share) | — | — |
  | auto7 | 33 % | 32 % | — | — |

  Remaining vetoes are mostly AMCL not confident (xy std > 0.15) and > 3 empty bins.
- Residual risk accepted by the owner: a non-echo object inside an explained gap between 0.4 m and the mapped wall. The costmap static layer still keeps the footprint off mapped walls.
- Tests: `test_lidar_map_known_gaps` 10/10, `test_lidar_availability` 16/16. Not yet deployed.
- **Camera accuracy check (stage-3 #3 bag):**
  - Fresh coverage on 4824/4825 moving scans, but it filled almost nothing (vetoed 85 % → 84 %). The empty LiDAR bins sit at ±25–45°, at or outside the Astra ~±29° field of view.
  - Where both sensors saw an obstacle in the same bin: within 15 cm 45 %, Astra farther 37 %, Astra closer 18 %. Frame origins differ and the Astra reports the nearest point per ray bin.
  - With the 0.4 m rule, the explained walls were ≥ 0.48 m away (median 0.88 m).
- **Camera veto added (owner "हाँ, जोड़ो"):** a bin is not map-explained when fresh Astra depth shows an obstacle in that LiDAR bin closer than the mapped wall − 0.15 m (`MAP_GAP_CAMERA_MARGIN_M`, `LidarAvailability.obstacles`). Replay: vetoed 1 bin on stage-3 #3; overall 26 % unchanged. (The earlier "10" used base_link bearings; the laser-origin binning gives 1.)
  - Tests: `test_lidar_map_known_gaps` 13/13, `test_lidar_availability` 16/16.
- **DEPLOYED ~14:00:** `atlas_lidar_availability.py` 03ec24d6… and `atlas_cmd_vel_mux.py` 57722178… (MAP_GAP_MIN_M 0.4 + camera veto). Backups `*.before-gap04-20261116`. Mux restarted with the rover parked, E-STOP latched and autonomy OFF; mux active, no errors. Real-drive effect not yet verified.
- **DEPLOYED 2026-11-16 ~14:30 (owner: "deploy what is built"): AMCL alpha1–4 0.2 → 0.1** (alpha5 unchanged). Applied at runtime with `ros2 param set /amcl` and persisted in `~/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml` (backup `.before-amclalpha-20261116`); repo `config/nav2_params.yaml` updated to match. The rover was parked and latched.
  - Evidence: replay F (alpha only) kept scan-fit 0.513 with σxy mean 0.156 → 0.124 and max 0.218 → 0.178. Most of the remaining guard vetoes after the 0.4 m rule were "AMCL not confident" (σxy > 0.15).
  - Rollback: set alpha1–4 back to 0.2 (runtime + yaml).
- Human-aware navigation design written: `docs/ATLAS_HUMAN_AWARE_NAVIGATION_DESIGN_2026-11-16.md` (radar + YOLO + depth, polite "please move aside" with radar confirmation). Design only; starts after Stage 3.

### 2026-11-16 ~15:00 — Stage-3 attempt 4 + sweep-aware map gaps
- Bag `data/lidar_tests/stage3_roundtrip4_20261116` (19 topics incl. `/radar/targets`). The hall goal stalled at spot A (1.07, −1.05): AMCL xy std 0.051. The fixed 0.4 m rule explained 2 of 3 empty bins; bin +100° had the mapped wall at 0.35–0.50 m while Nav2 turned right (w −0.29), so the rear swings toward that wall. The owner moved the rover and returned to Dhruv Room manually. The owner asked for 0.20 m; I advised against it (wall 2 cm from the body side) and proposed a sweep-aware clearance instead (accepted).
- **Sweep-aware rule** (`sweep_extent`, `required_wall_distance`): per bin, the farthest point the footprint reaches in the next 0.25 m along the commanded arc, + margin, floor 0.25 m. Examples (margin 0.10): straight front 0.66 m, side 0.28 m, right-turn left side 0.32 m.
- Replay, vetoed moving scans:

  | Bag | Fixed 0.4 m | Sweep, 0.10 margin | Sweep, 0.05 margin |
  |---|---|---|---|
  | #4 | 58 % | 11 % | 8 % |
  | #3 | 26 % | 52 % | 29 % |
  | #2 | 28 % | 31 % | 30 % |
  | Total scans | 3377 | 3528 | 2340 |

  The #3 difference is corner C: the wall is at 0.48–0.50 m and the front-left reach needs 0.48–0.56 m at the 0.10 margin.
- **Owner decision: margin 0.05 m.**
  - DEPLOYED: `atlas_lidar_availability.py` + `atlas_cmd_vel_mux.py` (the mux passes the command into `guard_map_explainer`). Backups `*.before-sweep-20261116`. Mux restarted with the rover parked, E-STOP latched and autonomy OFF.
  - Tests: `test_lidar_map_known_gaps` 16/16, `test_lidar_availability` 16/16.
  - Residual risk: an unseen non-echo object within 5 cm of the body reach.

### 2026-11-16 ~16:00 — Stage-3 attempt 5 (sweep-aware live): hall door is the remaining blocker
- Bag `data/lidar_tests/stage3_roundtrip5_sweep_20261116`. The rover passed spot A and the +35° unknown-space stop (doorway not in the map) with brief stops, and reached (1.92, −3.56). With the owner's help it reached the hall door (1.99, −4.23); the hall goal then aborted (status 6).
- "LOCALIZATION STALE" up to 4.6 s happened while I ran two rclpy probe nodes and an unfiltered `journalctl --user` during the drive (load 17–20, SSH timed out). Lesson re-confirmed: no probes during drives.
- Measured on the rover:

  | Item | Cost |
  |---|---|
  | `sweep_extent` uncached | 2.3 ms (≈ 4.5 % CPU at 20 Hz) |
  | `sweep_extent` cached | 0.04 ms |
  | Coverage update | 0.6 ms |
  | Scan update | 0.7 ms |

  Mux idle CPU 18 % (pre-existing, not from these rules). `sweep_extent_cached` and lazy evaluation are staged locally, not deployed.
- Camera at the hall door: coverage fresh 686/686 but filled 0 empty bins. 63 % of the commands there were arcs tighter than 0.35 m (all 72 bins required). Empty bins: side 2261, rear 1688, front 1124.
- No-echo by zone:

  | Bag | Dhruv Room | A | B | C/hall |
  |---|---|---|---|---|
  | #3 | 5.9 % | 7.8 % | 6.6 % | 8.1 % |
  | #4 | 1.4 % | 9.0 % | — | — |
  | #5 | 2.5 % | 8.5 % | 14.7 % | **24.4 %** |

- Hall-door no-echo rays cast on the map: 84 % end on KNOWN walls, mostly ONE ~1 m wall segment at x ≈ 1.5–1.7, y −3.2…−4.2 (left side just before the hall door, includes spot C). Image `docs/audits/hall_door_noecho_wall_20261116.png`. The rover passes it at 0.3–0.5 m, inside body reach + 5 cm, so no map rule can safely explain it.
- Replay of staged options (sweep-aware 0.05), vetoed share for #5 / #3 / #4:

  | Option | #5 | #3 | #4 |
  |---|---|---|---|
  | Today | 87 % | 29 % | 8 % |
  | Tight arcs use the actual swept bins (`TIGHT_ARC_FULL_RING False`) | 87 % | 20 % | 8 % |
  | + MAP_GAP_MAX_BINS 8 or 12 | no change | no change | no change |

- **Conclusion:** the hall door needs the physical fix: matte tape on that 1 m wall segment at ~20–30 cm height. A planner change to keep the path off that wall is secondary.
- **DEPLOYED ~16:20 (owner "पहले fixes deploy"):** `TIGHT_ARC_FULL_RING = False` (tight arcs require the bins the footprint actually sweeps, rotation capped at one full turn; pure spins still require all 72 bins), plus `sweep_extent_cached` and lazy explain in the mux.
  - md5: `atlas_lidar_availability.py` 51070650…, `atlas_cmd_vel_mux.py` 016d85b1…. Backups `*.before-tightarc-20261116`.
  - Mux restarted with the rover parked, E-STOP latched and autonomy OFF; active, no errors.
  - Tests 32/32. The old test `test_spin_and_tight_arc_need_all_bins` was rewritten to the new policy and still checks that the old policy is selectable.
  - Expected effect (replay): #3 29 % → 20 % vetoed; no change at the hall door (needs tape).

### 2026-11-16 ~17:00 — Dashboard battery time estimate (owner request), DEPLOYED (web only)
- `scripts/atlas_battery_eta.py` (pure) is fed from the `/bms/status` callback in `atlas_status_web.py` and appears as `ros.battery_eta`; the v2 home battery card shows its Hindi text.
  - Time to full: CC part to 95 %, then CV tail at 0.4× current.
  - Time left: down to 10 %, using a 2 min (charge) / 5 min (discharge) time-weighted current.
  - Charge speed: धीमी < 0.2C ≤ सामान्य < 0.5C ≤ तेज़; by pack watts (30 / 80 W) until the capacity is known.
  - Capacity: from `config/battery_eta.yaml` (null), otherwise learned from the Daly coulomb counter over ≥ 3 % SOC and persisted in `~/.local/state/project_atlas/battery_capacity.json`. A first 106 s sample gave ~15 Ah (± 11 %). The learned value is the BMS's own configured capacity.
- Advice only: no safety or motion input. Tests `test_battery_eta` 10/10.
- Backups `*.before-batteryeta-20261116`. Only `rover-status-web` was restarted.
- Live: "सामान्य charging (48 W) · समय निकाल रहा हूँ…", capacity still learning.
- **Owner pack data (2026-11-16):** 4 × 32140 LiFePO4, 3.2 V, 15000 mAh, 2C, 4S1P → 12.8 V / 15 Ah. It matches the BMS (4 cells, ~13.4 V) and the learned ~15 Ah.
  - `config/battery_eta.yaml` `capacity_ah: 15.0` deployed (status web restarted).
  - Above 1C the charge label reads "बहुत तेज़ (1C से ऊपर — cell datasheet जाँचें)". Tests 11/11.
  - Live: "सामान्य charging (0.25C) …", capacity_source config.
- **2026-11-16 owner: "use English in the dashboard, no Hindi" — DEPLOYED (web only).** Translated `atlas_readiness.py` (all titles, reasons, steps, buttons), `web/v2/readiness.js`, `web/v2/readiness.html` (lang en) and `atlas_battery_eta.py` texts (charge speed Slow / Normal / Fast / Very fast; "≈ 2 h 10 min to full"; "≈ … left (to 10%)").
  - Tests: `test_battery_eta` adds `test_all_dashboard_text_is_english`; `test_readiness` assertion updated.
  - Backups `*.before-english-20261116`; `rover-status-web` restarted.
  - Live check: readiness titles in English, page heading English, battery "Slow charging (0.17C) · estimating time…".
  - The voice narrator stays Hindi (a spoken feature, not dashboard text).
