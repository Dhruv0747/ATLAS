# CPU "100%" readings after the 24 Oct 18:09 reboot — what the logs can and cannot prove

Owner question (21:05): the dashboard showed CPU at 100% about 54 times. For each spike: duration, process, sampling
interval, impact on E-STOP / encoders / IMU / LiDAR / motor commands. Evidence only — no estimates.

## What is NOT available (stated plainly)

- No CPU history is recorded on the Jetson: no `sar`/`sysstat`/`atop`, no CPU log in ATLAS. The dashboard keeps no
  CPU history server-side. **Per-spike duration and per-spike process attribution cannot be reconstructed from
  ATLAS logs for 18:09–21:05.** Any per-spike table would be a guess, so none is given.
- The owner's screenshot did not reach the session (no attachment, nothing new in the PC Downloads folder), so its
  time axis cannot be matched against the logs.

## How the dashboard number is sampled (from source, `atlas_status_web.py` `cpu_percent()`)

- Whole-Jetson CPU (all 6 cores) from `/proc/stat`, computed over the interval **since the previous `/api/status`
  request from any client**. The previous-sample state is shared by every caller.
- The V2 page polls `/api/status` every 2 s (`web/v2/command.js`, `setInterval(refresh,2000)`); every open page
  (PC, phone, touch screen) and the Vision Lab safety probe also call it. With several callers the window can be
  far shorter than 2 s, and one short busy burst then reads as 100%. The value is a point reading, not an average.

## Logged events after the reboot (journal, exact times; each launches new processes)

| Event | Count | First | Last | Evidence |
|---|---:|---|---|---|
| rover-base-telemetry failed starts (`USB discovery busy`) | 471 | 18:10:16 | 18:59:12 | `journalctl --user -u rover-base-telemetry -b` |
| atlas-lidar failed starts (no scan modes; fixed by replug) | 61 | 18:10:16 | 18:20:06 | `journalctl --user -u atlas-lidar -b` |
| atlas-localization failed starts | **54** | 18:11:12 | 18:58:44 | `journalctl --user -u atlas-localization -b` |
| Boot (≈165 services) + on-demand AI restore (8 features, 5-min grace) | 1 | 18:09 | ~18:15 | load average 39.5 at 18:13 |
| atlas-gnss restart (owner-approved) | 1 | 20:48:01 | — | `restart.txt` on the Jetson |

The localization count equals the owner's "about 54", but each attempt only polled `systemctl is-active` for up to
45 s and exited (`atlas_wait_navigation_inputs.sh`), which is light. The heavier repeated launches were the
base-driver restarts (a new Python/rclpy process about every 6.3 s for 49 min) and the LiDAR driver restarts.
Without CPU history, which of these produced which 100% reading is not provable.

## Impact on safety and sensors (journal and safety ledger, since boot)

| Item | Evidence | Result |
|---|---|---|
| E-STOP | `data/safety/estop_events.jsonl`: every event since boot is `stop` from 192.168.1.4 with `zero=published`; policy `stop_latched: true` at every check (20:46, 20:48, 20:50) | latched; no unlatch event logged |
| Motor commands | `atlas-cmd-vel-mux`: 0 WARN/ERROR since boot, 0 restarts; `/cmd_vel` zero at 20:46 and 20:50 | zero |
| Encoders | unavailable 18:10–18:59 because the base driver could not get the USB lock (not CPU). Since 18:59: `/atlas/encoder_health` READY, 4/4 selected, 0 base WARN/ERROR | OK since 18:59 |
| IMU (im10a) | 0 restarts, 0 WARN/ERROR since boot; 10.7 Hz at 20:50 | OK |
| LiDAR | down 18:10–18:20 (hardware: no scan modes; fixed by USB replug), 0 WARN/ERROR since 18:20:30; 7.0 Hz at 20:50 | OK since 18:20 |
| Safety status, remote, sensor hub | 0 WARN/ERROR, 0 restarts since boot | OK |

None of the protected services logged a watchdog, stale-command or timeout event during the period.

## What would make per-spike answers possible

A lightweight recorder (1-s `/proc/stat` plus the top processes whenever CPU > 90%, written to a capped file) would
give duration, process and timestamp for every future spike. Not installed — needs owner approval.
