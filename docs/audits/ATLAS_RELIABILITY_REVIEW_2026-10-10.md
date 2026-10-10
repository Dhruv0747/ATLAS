# ATLAS reliability review package — 2026-10-10 (evening)

Scope: the "FINAL MASTER DEVELOPER TASK" (localization verification and
recovery, latency, narrow spaces, dashboard, resources, LiDAR startup,
shutdowns/storage). This is the **Phase D review package**. Nothing in it is
deployed. Branch: `claude/localization-motion-investigation`.

Status labels: SIMULATED / BUILT / TESTED OFFLINE / DEPLOYED /
VERIFIED ON JETSON / VERIFIED BY USER.

Safety state at the time of writing:
- autonomy disabled; `navigation_validated=false`; `atlas_closed_loop_control`
  refuses AUTONOMOUS while it is false;
- monitor deployed earlier today in `suggest` mode; no automatic reseeding;
- no motion, reboot or service restart was made for this review;
- Jetson work was read-only, plus benchmarks run from `/tmp`.

## 1. Confirmed findings

| # | Finding | Evidence |
|---|---|---|
| C1 | **Slow verification is mostly search time.** The global search took 17–20 s on the Jetson, so checks completed every 46.6–47.4 s. Stop → VERIFIED was 30–40 s. | Live 120 s probe (completions every 47.4/46.6/47.4 s). Jetson benchmark: old search 18.5–20.2 s. |
| C2 | **"Still moving after stop."** The deployed monitor stays MOVING_UNVERIFIED until the first check result arrives. It has no parked or verifying state. | Code: `on_motion(False)` only set `parked_since`. |
| C3 | **Stale results could be applied.** If ATLAS moved and parked again during a check, the old result was applied, because the only guard was `parked_since is not None`. | Code; now covered by a unit test that fails on the old logic. |
| C4 | **No freshness checks** on odometry or the AMCL pose. Scans were pruned only when a new scan arrived, so a dead LiDAR left its last scans usable. | Code. |
| C5 | **Unsynchronised shared state.** The worker thread wrote `logic.state` concurrently with ROS callbacks. | Code. |
| C6 | **The recheck interval was measured from check completion** (30 s + search time). | Code; matches C1. |
| C7 | **The LiDAR start failure is chronic.** 6 of the last 10 boots had 10–21 failed `rplidar` starts. Errors: `SL_RESULT_OPERATION_TIMEOUT`, then health OK with "Can not start scan 80008000/80008002". Scanning began about 3 min after boot. | `journalctl --user -u atlas-lidar` per boot. |
| C8 | **Two restarters act on the LiDAR.** systemd `Restart=on-failure` with `RestartSec=5` makes the default 5-in-10 s start limit unreachable, so the loop is unbounded. `atlas_sensor_recovery` additionally runs `systemctl restart` (3 per 600 s). At 18:24:34 systemd started rplidar, and at 18:24:35 the recovery restart killed it mid-handshake. | Journal; NRestarts=16 this boot. |
| C9 | **The CH340 discovery code never touches the LiDAR.** `atlas_usb_identity.candidates()` only matches 1A86:7523. The LiDAR is a CP2102 (10C4:EA60). vc02 voice denies the port. | Code. **Hypothesis rejected.** |
| C10 | **Bounded systemd user services are not CPU-limited.** The user manager delegates only the memory and pids controllers, so `CPUQuota`/`CPUWeight` on user services are **not enforced**. Earlier statements today that `CPUQuota=60%` caps the monitor were **wrong**. `Nice=10` does apply. | `cpu.max` absent. |
| C11 | **The scan-fit gate can pass at the alias peak.** Mission control's gate needs held-out fit ≥ 0.85. The recurring Dhruv Room alias peak scores 0.872 for the true Dhruv Room view. The actual wrong AMCL pose today fit 0.80–0.81 (refused), but a pose closer to the alias peak would pass. Covariance gates in mission control and the mux also pass with collapsed covariance. | Moving-failure report, findings 1–2. |
| C12 | **The journal is 91% rf2o INFO logging.** That is 14,358 of 15,815 user-journal lines in 10 min (~24 lines/s). A 128 MB user journal file fills in about 1.3 h. | `journalctl` counts. |
| C13 | **The crash boot left no journal.** `last -x` records boots at 16:24 (clean shutdown 17:34:21) and 17:34 (ended "crash"). `journalctl --list-boots` has neither. Boot −1 (journal 14:29–15:50:52) ends mid-rf2o output with no shutdown messages. | `last -x -F`, `--list-boots`. Wall-clock labels before time sync are unreliable. |
| C14 | **Odometry reaches the parked thresholds 0.17–3.2 s after the zero command** in 8 real stops across 6 recordings. Three apparent 15 s cases were my own artifact: the next drive command arrived 4.2–8.5 s later. | `stopdecay_ros.py` on the Jetson bags. |
| C15 | **The encoder CRITICAL events happened only in reverse.** In every one, all four encoders were consensus-rejected: M3 ≈ 0 and M4 under-reading while M1 ≈ M2 ≈ −0.012 m. | Recovery journal plus the earlier experience-store analysis. |

## 2. Remaining hypotheses and evidence gaps

- **LiDAR start-failure cause (unconfirmed).**
  - Strongest candidate: insufficient or unstable 5 V to the RPLIDAR during boot. "Health OK but cannot start scan" fits a motor that does not reach speed. The CP2102 shares an unpowered-status 5-port hub with the ESP32, a CH340 and an unidentified 480M device. Success came about 3 min after boot, not after a fixed number of attempts.
  - Needs: a voltage measurement at the LiDAR during boot, or a test on a powered hub. **Hardware investigation; not done.**
  - Competing explanation: boot-time CPU load (load average 13–17 on 6 cores now).
- **Shutdown cause (unconfirmed).** The crash boot left no journal, so its cause cannot be read from logs. Candidates:
  - abrupt power loss before journald flushed;
  - a storage write failure (ATLAS-018 NVMe AER history);
  - clock-skewed wtmp labels.

  No INA3221/BMS log covers 16:24–18:12. **No risky storage tests were run.**
- **Narrow-space behaviour (gap).** The deployed monitor kept no history, so its states in tight spots during the 19:40–20:02 drive cannot be reconstructed. The new monitor writes a history file, which closes this gap for future drives. Narrow/ambiguous offline cases still return UNKNOWN or DEGRADED (existing symmetric-room and ambiguity tests).
- **IM10A turn under-report on the fast drive (open).** H1/H2 are as stated in the moving-failure report.

## 3. Changes on the branch (not deployed)

| Commit | Change | Status |
|---|---|---|
| `1c1ff7a` | `atlas_localization_verify_core.py`: cached map index plus flat gather for coarse scoring. Scores are bit-identical (new test asserts max diff 0.0). Policy and thresholds are unchanged. | BUILT, TESTED OFFLINE; benchmarked on the Jetson in `/tmp` |
| `b28819c` | `atlas_sensor_recovery.py` publishes **RECOVERY DEFERRED** while systemd is mid-restart (the deferral counts as an attempt). `systemd/user/atlas-lidar.service.d/20-bounded-restart.conf` is a **proposal**: `StartLimitBurst=40` per 900 s, about 2× the worst observed boot. | BUILT, TESTED OFFLINE |
| `7314f11` | Monitor state machine: PARKED_SETTLING → VERIFYING → result; episode tokens; outdated-pose discard; INPUT_STALE; RLock; 0.25 s scheduling with publish on transition; recheck interval from check start; single in-flight check with 30 s timeout; timing fields; JSONL history (2 MB + one rotated copy). Dashboard labels for STOPPED-CHECKING and INPUT_STALE (red). Status web passes `timing` and `rechecking` through. | BUILT, TESTED OFFLINE |

**Tests**
- 82 localization tests pass, 16 of them new:
  - 15 monitor edge cases: stop timing; move/stop during a check; AMCL change mid-check; stale odom/LiDAR/AMCL; no flicker on recheck; check errors; LOST never hidden; auto confirmation rate limit; concurrent callbacks; scan filtering; bounded history; transition log; hung search.
  - 1 search-equivalence test.
- Mutation check: removing the episode check, the LiDAR-staleness check, the no-flicker rule or the in-flight guard each makes a test fail.
- 15 sensor-recovery tests pass, 2 of them new.
- 3 dashboard state tests are new.
- The full `tests/` discovery run (387 tests) has one pre-existing failure, `test_ultrasonic_validity…navigation_localization_guard`. It fails identically on the clean tree and is unrelated.

**Not changed**
- verify thresholds (0.93 / 0.06 / 120 endpoints) and tracking tolerances;
- encoder, EKF, motor, AMCL or Nav2 parameters;
- the network;
- `relocalize_mode` stays `suggest`.

## 4. Timings and resources

| Quantity | Before | After | Label |
|---|---|---|---|
| Global search on Jetson (load ~17, nice 10) | 18.5–20.2 s | 2.2–2.6 s, identical hypotheses (3 windows) | VERIFIED ON JETSON (benchmark only) |
| Global search, container | 6.34 s | 0.66 s, identical verdicts on 11 recorded windows | TESTED OFFLINE |
| Odom parked → result | ~20–40 s (2 s settle + ≤1 s tick + 17 s search, +17 s if a check was in flight) | ~4.6–4.9 s (2 s settle + ≤0.25 s + ~2.3–2.6 s) | SIMULATED from measured parts |
| Zero command → result | 30–40 s (user observation) | ~4.8–8 s (adds the 0.17–3.2 s odom decay, C14) | SIMULATED |
| Monitor CPU | ~0.30 core average (measured) | estimated ≤0.1 core while parked (one 2.5 s search per 30 s) | ESTIMATE; measure after deploy |
| Monitor memory | 92 MB | similar (index ~ map-sized uint8) | ESTIMATE |
| Status web | ~0.53 core, 114 MB | unchanged | measured |

The ~5 s target is reached measured from when odometry shows ATLAS stopped. From the operator's stop command it is up to about 8 s, because the EKF twist can take up to 3.2 s to decay. The 2 s settle and the thresholds were **not** shortened to hide this.

## 5. Deployment proposal (needs your approval; nothing done)

Each step is separate, can be done while ATLAS is parked, and has backups under `data/backups/2026-10-10-reliability/`.

1. **Monitor + fast search + dashboard.**
   - Files: core, monitor, `atlas_status_web.py`, `atlas_mapping.html`.
   - Restart `atlas-localization-monitor` (read-only; it does not drive or seed in `suggest`) and `rover-status-web` (page blinks ~2 s).
   - The seeder imports the same core, so the next boot's start check also gets faster, with identical verdicts.
   - **Not restarted:** motors, odometry, Nav2, AMCL, the network.
2. **Sensor-recovery deferral.**
   - Restart `atlas-sensor-recovery`.
   - It restarts no motor I/O, and its stop guards are unchanged.
3. **LiDAR bounded restart drop-in.**
   - Copy the file and run `systemctl --user daemon-reload`. No restart; it applies to the next start.
   - **Trade-off:** after 40 failed starts in 15 min the LiDAR stays down until a person restarts it. Today it would retry forever.

**Rollback**
- Steps 1–2: copy the backups back, then `systemctl --user restart` the same two services.
- Step 3: delete the drop-in and run `daemon-reload`.

**Phase F verification after deploy** (VERIFIED ON JETSON only after this; VERIFIED BY USER only after your drive):
- Measure monitor CPU for 10 min.
- Confirm a VERIFIED result while parked.
- On your next supervised short drive, read `stop_to_result_s` from `localization_check_history.jsonl`. Pass target: ≤ 6 s from odom stop in 5 of 5 stops.

## 6. For separate review (not implemented)

- **Autonomy gate integration (C11).** Mission dispatch and the mux autonomy guard should also require:
  - a monitor result with `state == VERIFIED`;
  - same episode and still parked;
  - `checked_unix` ≤ 30 s old;
  - monitor heartbeat ≤ 2 s.

  LOST, UNKNOWN, INPUT_STALE, VERIFYING, a missing monitor or a stale monitor all refuse. This only ever adds refusals, but it changes a safety-critical path, so it needs its own approval and tests.
- **Reduce rf2o logging (C12).** Set its log level to WARN to cut journal writes by ~90%. This is a service configuration change.
- **journald.** `SyncIntervalSec=30s` would narrow the log loss on power cuts. System config.
- **Network (ATLAS-019).** Recommendations only; there are no Wi-Fi, Tailscale or route changes without separate approval.
  - Pin to one AP/BSSID or disable roaming.
  - Turn off Wi-Fi power save.
  - Keep cellular at a higher route metric.
- **Hardware.**
  - Measure LiDAR 5 V during boot.
  - Try the LiDAR on a powered hub.
  - Check M3/M4 encoders in reverse.
  - Fit power telemetry logging that survives a crash.

## 7. Limitations

- All latency numbers after the change are composed from measured parts, not measured end-to-end on the rover.
- The benchmark windows were map ray-casts, not live scans. Live-scan equivalence was shown in the container on 11 recorded windows.
- The monitor checks only while parked. It cannot detect a wrong pose during motion; MOVING is always "not verified".
- The bounded LiDAR restart and the deferral do not fix the underlying start failure.

## 8. Deployment record — steps 1 and 2 (approved 21:24 IST, deployed 21:29:50)

**Approval scope**
- Approved: steps 1 and 2.
- **Step 3 (LiDAR restart limit) is on HOLD**, along with all other safety-critical changes.
- Not done: reboot, driving, motor/EKF/AMCL changes, network changes.

**Pre-deploy checks**
- Parked: `/odom` twist about 0 and drive mode `STOPPED`.
- `navigation_validated: false` in both configs; `relocalize_mode=suggest`.
- Live files matched the repo baseline `72b4ca1` byte for byte.

**Backups**
- Location: `~/project_atlas/data/backups/2026-10-10-reliability/`.
- Contents:
  - the 5 previous files, read-only, with `SHA256SUMS`;
  - evidence (unit journals, unit state, last check and verdict, `cpu_before.jsonl`, `cpu_after.jsonl`);
  - `ROLLBACK.sh`.
- `ROLLBACK.sh` was syntax-checked and its backups checksum-verified and compiled. It was **not** run.

**Deployed files** (from commit `2120613`; checksums verified on the PC and on the Jetson)

| File | sha256 (first 16) |
|---|---|
| `atlas_localization_verify_core.py` | `2e6e22393df9166b` |
| `atlas_localization_monitor.py` | `35dd7407b300b5be` |
| `atlas_status_web.py` | `51f8e111ce08e7c4` |
| `atlas_mapping.html` | `876f58e71d403265` |
| `atlas_sensor_recovery.py` | `fb5d76021625d29d` |

**Restarted:** `atlas-localization-monitor`, `rover-status-web`, `atlas-sensor-recovery`. All are active with NRestarts=0. The old monitor exited with status 1 on stop because `rclpy.shutdown()` was called twice. That bug is pre-existing and also present in the new `main()`: cosmetic, and it causes no restart.

**Jetson results**

| Check | Result | Label |
|---|---|---|
| Live location | Monitor VERIFIED: fit 0.91–1.00, 0.05 m, 4–6°. Independent `seed --dry-run`: VERIFIED (0.175, −1.495, 75°), fit 0.984, margin 0.116, not seeded, verdict file untouched. AMCL at (0.238, −1.485, 81.7°), i.e. Dhruv Room. | VERIFIED ON JETSON |
| Live recheck search | 1.87–2.31 s, interval 29.7–30.3 s, over 30+ checks | VERIFIED ON JETSON |
| Live parked stability | 21 checks after deploy: 18 VERIFIED, 3 DEGRADED (ambiguous second place 0.95–0.96). Never LOST. | VERIFIED ON JETSON |
| Contention | Searches took 10.0 s (first check, while 3 services were starting) and 10.7 s (during a seeder dry-run). The dry-run also caused a >1 s scan gap, so the state went INPUT_STALE and recovered. It fails toward unknown, never toward a false VERIFIED. | observed |
| Stop → result, recorded drive (isolated replay of the deployed code on the Jetson, ROS domain 77, localhost only, `relocalize_mode=off`) | Clean stops: 4.07, 4.17, 5.25 s. One stop: 13.2 s, because AMCL kept moving for ~9 s after the stop (4 results discarded as outdated). | VERIFIED ON JETSON (replay); **real drive not yet measured** |
| States | MOVING, PARKED_SETTLING, VERIFYING, VERIFIED, DEGRADED and LOST all seen. The known alias at the end of the round trip was LOST on all 6 checks. | VERIFIED ON JETSON (replay) |
| Stale inputs | Odometry gap → INPUT_STALE (odometry). Replay without `/scan` → LiDAR stale after 2.2 s. Without `/amcl_pose` → AMCL stale after 2.1 s. No result was applied in any of them. | VERIFIED ON JETSON (replay) |
| CPU, 150 s windows before/after | Monitor 0.281 → 0.099 core, RSS 175 → 96 MB. Status web 0.526 → 0.556. Sensor recovery 0.143 → 0.153 (noise). | VERIFIED ON JETSON |
| Dashboard | Local `/api/map`: p50 18 → 15 ms, p95 55 → 49 ms, 0/300 failures. Remote (Tailscale): p50 117 ms, p95 171 ms, max 0.59 s, 0/100 failures. New labels are served. | VERIFIED ON JETSON |
| Autonomy / reseed | `navigation_authorized=false`, `relocalize_mode=suggest`, `navigation_validated=false`. No reseed since deploy. | VERIFIED ON JETSON |
| Sensor recovery | READY. `restart_pending(atlas-lidar)` = False against live systemd output (`active` / `running`). Deferral not yet exercised live; that needs a LiDAR failure. | VERIFIED ON JETSON (partial) |

**Not verified:** real drive stop latency, live LOST, and a live deferral during a LiDAR fault. All of these need your supervised drive or the next boot.
