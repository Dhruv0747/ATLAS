# Localization recovery, voice fix and startup evidence, 2026-10-11 20:00–20:15 IST

Branch `agent/sync-developer-20261011`. Owner brief received 19:57 (voice fix approved; AMCL reseed
only on explicit confirmation).

| Item | Built | Tested | Deployed | Verified on Jetson | Physically validated |
|---|---|---|---|---|---|
| Stage 14 voice: latch **and** release announced | `27ccfcd` + `e2197f9` | 35 voice tests | 19:59:34 | Restart announced "Safety stop latched…" (true state); no error | **No.** A spoken release needs a real release in a supervised session |
| Stage 15 location-check motion gate on the EKF gyro | `686fb03` | 58 location tests | 20:03:01 | 3/3 live checks **VERIFIED** | No (parked only) |
| Startup evidence capture (verdict history and replayable scans) | `b81d7ac` | 26 seeder tests incl. replay | **No.** Staged decision for the owner | — | — |
| AMCL initial pose | — | — | **Not applied by Claude.** Seeded by the existing startup verifier at boot | VERIFIED (below) | No |

## 1. AMCL: no manual seeding was needed

The owner's dashboard power action at 19:52:44 (`shutdown_latch` from the PC) restarted ATLAS.
The previous restart, at 19:03:47, came from the same action. On this boot:
- the RPLIDAR started first time and was scanning 21.8 s after boot;
- `atlas-localization` started with no failures;
- the existing verify-before-seed startup check (threshold unchanged at 0.93) gave **VERIFIED**:
  (0.235, −1.535, 81°), fit 0.989, margin 0.111, from 23 scans;
- it seeded AMCL through its existing service at 103.8 s (`initialPoseReceived`).

Claude proposed no pose and applied none.

**Fresh comparison** (CHECK MY LOCATION, three runs at about 20:03, latched, parked):

| | AMCL | Independent LiDAR | Disagreement | Fits | Margin | Runner-up |
|---|---|---|---|---|---|---|
| Result | (0.178, −1.473, 78.2°) | (0.235, −1.435, 72° or 75°) | **0.069 m, 3.2–6.2°** | LiDAR 0.994–1.000, AMCL 0.988–1.000 | 0.086–0.092 | alias (3.915, −0.655, 171°) at 0.907 |

- **Heading:** the 72° and 75° LiDAR headings are adjacent points of the search's 3° heading grid
  (`yaw_step_deg`), not rover motion. The same applies to the earlier 72°/78°.
- **Position:** AMCL is 0.01 m from the operator-confirmed Dhruv Room pose (0.187, −1.477).
- **Margin:** the alias margin of about 0.09 is thin. That is a map property, not noise.

## 2. Why the check said ROVER_MOVING after this reboot (fixed: stage 15)

- **What tripped it:** the location check gated motion on `/imu/data`. That is the Yahboom board
  IMU, which has no gyro-bias calibration; the driver logs "navigation qualification=False".
- **Bias:** parked, it read **−0.0298 rad/s (−1.71°/s)**, standard deviation 0.0067. At 13:29
  today, on the previous boot, it read +0.006°/s.
- **Effect:** 112 of 126 samples exceeded the 0.02 rad/s gate, so every request was refused as
  ROVER_MOVING, while `/odom` and `/cmd_vel` were exactly zero.
- **Fix:** the gate now uses `/im10a/imu/bias_corrected_candidate`, the gyro the EKF fuses for yaw
  (`config/atlas_ekf.yaml imu0`). Thresholds are unchanged.
- **Impact elsewhere:** the EKF never used `/imu/data`. Anything that displays its orientation (the
  compass or heading tiles) would drift by about 100° per minute on this boot. That is a finding
  for ATLAS-010.

## 3. Voice (stage 14)

- **Source:** `atlas_voice_status.py` announces both edges, with corrected release instructions. A
  release is announced only after an announced latch.
- **Companion:** `atlas_voice_companion.py` exempts the stop key from the 60 s per-key alert
  throttle. Without that, a release within 60 s of a latch was dropped, recreating the stale
  spoken state. Stop alerts are already debounced (2 s stable, change-only).
- **No authority change:** no motor, mux or E-STOP authority changed. The diff is announcement
  text and the throttle condition only.
- **Restart scope:** only `atlas-voice-companion`. The mux (1890), base (1893), AMCL (4298) and
  monitor PIDs were unchanged.
- **Pre-existing test issue:** the live tree's older `test_voice_status.py` has a pre-existing
  failure (`test_low_battery_hysteresis`), identical with and without stage 14. The repository
  suite (35) passes.

## 4. Startup score 0.90 (19:06 boot): investigation status

**Known:**
- That boot had 15 failed RPLIDAR starts; scanning began at 216 s.
- `atlas-localization` failed 5 times, then started.
- The verifier ran at 262 s: "best 0.90 < 0.93".
- This boot, with a clean LiDAR start, scored 0.989 at 104 s.
- After the owner's 19:12:55 LB release, paired web `stop` events at 19:13–19:32 indicate web
  driving. ATLAS's pose during the 19:10:55 attempt may therefore not equal the pose measured at
  19:46.

**Lost:** the 19:06 boot's attempt detail (`localization_verdict.json`) was overwritten by the
19:52 boot. Its ROS user journal is no longer retrievable either; that boot began with the clock
at 1970. Claude did not copy the verdict file at 19:20, when it was still available.

**Status:** the cause is undetermined. Do not attribute it to the operator. Candidates are a
different pose or heading, transient occlusion, and LiDAR behaviour right after a start-failure
storm.

**Prepared (not deployed), `b81d7ac`:**
- every attempt stores median ranges in mm, scan stamps, coverage quadrants, laser pose and the top
  five hypotheses;
- every boot is appended to `localization_verdict_history.jsonl`, capped at 4 MB plus one rotated
  copy;
- a test reruns the identical search from the stored evidence.

**Effect:** the file runs only when `atlas-localization` starts, so installing it changes nothing
until the next restart. It sits in the seeding path, so it awaits owner approval.

## 5. Health (read-only, about 20:10)

- **BMS:** connected, data 2.1 s old; SOC 100%, 14.0 V, 0.0 A.
- **Wi-Fi:** connected; gateway RTT average 1.9 ms over 20 pings; default route Wi-Fi (metric 50),
  cellular standby (600).
- **System:** CPU 71.9%, RAM 5163/7620 MB, 61°C, load 9.5.
- **Location monitor:** idle 11.4% of one core; about 3 s per CHECK MY LOCATION.
- **Voice companion:** about 23% of one core on average; unchanged from before (5228 CPU-s over
  5.7 h earlier today).

## 6. Rollback

| Stage | Backup in `~/project_atlas/data/backups/` | After `ROLLBACK.sh`, restart |
|---|---|---|
| 14 | `2026-10-11-195934-371124538-stage14-voice-stop-announcements/` | `atlas-voice-companion` |
| 15 | `2026-10-11-200301-456649929-stage15-location-check-gyro/` | `atlas-localization-monitor` |
| 13 | `2026-10-11-194559-575361028-stage13-location-check-no-amcl/` (undo 15 first) | `atlas-localization-monitor` |
