# Reboot check and controlled GNSS restart — 24 Oct 2026

Owner-requested Jetson reboot ~18:09 IST (done by the owner; the agent has no reboot rights). The robot was parked
throughout: E-STOP latched, manual-only, commissioning disarmed. No motor command was sent at any point.

## Boot result (18:13, 4 min after power-on)

Compared with the pre-reboot snapshot (80 user and 82 system services active, none failed):

| Service | After boot | Cause |
|---|---|---|
| atlas-lidar | restart loop (54×) | RPLIDAR A1 answered (fw 1.29, health OK) but returned **no scan modes** (`80008001/80008002`). Fixed by the owner **replugging the LiDAR USB** (~18:20); `/scan` 7 Hz since |
| rover-base-telemetry | restart loop (471×, about every 7 s) | `OSError: USB discovery busy` — the shared CH340 discovery lock was held by the GNSS driver. Got the lock in a gap at 18:59 and has run since |
| atlas-localization | restart loop (54×) | waits for rover-base-telemetry; active since about 19:00 |
| atlas-ptz-home | failed once at boot | not yet investigated |
| 8 on-demand AI features | on for 5 min, then off | expected (boot grace) |

CPU kept spiking because of the restart loops: each attempt started a new Python/ROS process.

## Controlled GNSS restart (owner approval 20:46)

Pre-checks (fresh, 20:46): GNSS `gnss_node` PID 3042 held `/run/user/1000/atlas-usb-discovery.lock` and
`/dev/ttyUSB1`, logging `gps: expected one unclaimed verified device, found 0` every ~2 s; `stop_latched: true`,
`commission_armed: false`, `manual_only: true`; `/cmd_vel` zero; mission `READY` (no navigation goal).

`systemctl --user restart atlas-gnss` at 20:48:01, rc 0, new PID 112259/112294. Only that unit was restarted.

| Check after restart | Result |
|---|---|
| USB discovery lock released | **No.** The new GNSS process re-acquired it at once (10/10 samples over 10 s) and again holds `ttyUSB1` |
| GPS telemetry | **No data.** `/gps/fix` silent; same "found 0" error (9 attempts in 20 s) |
| Yahboom motor board | connected (base holds `ttyUSB0`, `/yahboom/odom` 10.8 Hz); already restored at 18:59, before the restart |
| Encoders | `/atlas/encoder_health` READY, encoders 1–4 selected, no faults; encoder packets fresh (age 13 ms). Counts are static because the wheels are stationary — not moved, by design |
| Motor commands | `/cmd_vel` zero; E-STOP still latched |
| IMU | `/yahboom/imu/data_calibrated` 10.7 Hz |
| LiDAR | `/scan` 7.0 Hz |
| Navigation | controller, planner, bt_navigator, AMCL, map_server all `active` (not commanded, no goal) |
| Protected services | mux, safety-status, voice, dashboard, sensor hub, mission control, remote, IMU, LiDAR, base, localization, on-demand: PIDs and restart counts unchanged |
| CPU | 68.2% (30 s) after the restart |

The restart was not repeated (owner rule).

## Root cause

The lock was not left behind by a crashed process. With `auto_usb:=true`, the GNSS driver retries every 2 s. Each
retry takes the shared lock and listens on every unclaimed CH340 port for 1.6 s. Because no port produces NMEA, it
never finds a GPS and keeps retrying, so it holds the lock about 70–80% of the time, permanently. Any other
auto-discovering driver — the Yahboom base — can then only start in a lucky gap. That is why the base needed 471
attempts after this boot.

Why no GPS is found: the three CH340 adapters are `ttyUSB0` (USB path 2.2.3, Yahboom base), `ttyUSB2` (2.4.3, IMU)
and `ttyUSB1` (2.4.2). `ttyUSB1` is the only unclaimed one, and it sends no NMEA at 9600 baud within 1.6 s. The
earlier fixed-port config named USB path `2.2.4.3`, which no longer exists. So the GPS module is likely unpowered,
disconnected or moved to `ttyUSB1` and silent. A GPS module sends NMEA even without a fix, so this is not an
antenna/sky issue.

## Proposed fixes (not applied; each needs owner approval)

1. Physical: check the Hiwonder GPS V1 power LED and cable, and that it is the device on `ttyUSB1` (path 2.4.2).
2. Driver: back off GNSS auto-discovery after failures (e.g. 2 s → 30–60 s), so it holds the shared lock for at most
   a few percent of the time. The motor board can then always connect after a reboot or restart. Offline-testable
   with fake ports.
3. Investigate the `atlas-ptz-home` boot failure and the ros2 CLI crash report (`/var/crash`, 18:22).

## Fix deployed — GNSS lowest priority (owner approval 20:59; deployed 21:09)

Change (commit 9febaba, code `cc638c69…`): with `auto_usb`, GNSS waits 90 s after start before its first USB probe;
after a failed discovery it retries only after **600 s**, or 60 s after a new USB serial adapter appears. Drop-in
`low-priority.conf`: `Nice=19`, `IOSchedulingClass=idle`. The fixed-port mode and NMEA parsing are unchanged.
Offline: 19/19 tests (the old driver fails 7 of the 8 new ones).

Fresh pre-checks (21:08): stop_latched true, commission_armed false, manual_only true, `/cmd_vel` zero, mission
READY, encoder health READY, Astra off. Backup: `~/project-atlas-migration/gnss_lowprio_20261024_2112/backup/`
(gnss_node.py `e7a44c55…` + original drop-in dir). Install: src file (colcon symlink install) + drop-in,
`systemctl --user daemon-reload`, `systemctl --user restart atlas-gnss` (rc 0). No other unit was restarted.

| Check | Before fix | After fix |
|---|---|---|
| USB discovery lock held (1-s samples) | 10/10 | **1/125** (the single probe 91 s after start) |
| `ttyUSB1` held by GNSS | yes | no |
| GNSS process priority | nice 10 | nice 19, idle I/O |
| Protected services (base, localization, LiDAR, IMU, mux, safety, voice, dashboard, sensor hub, mission, remote, on-demand, EKF, scan filter) | — | PIDs and restart counts unchanged |
| `/scan`, IMU, `/yahboom/odom`, ultrasonic | 7.0 / 10.7 / 10.8 / 3.3 Hz | 8.1 / 9.4 / 7.6 / 3.3 Hz (10-s CLI samples on a loaded Jetson) |
| Encoders / motor commands / E-STOP | READY / zero / latched | READY 4/4 / zero / latched |
| Navigation | active | active |
| GPS | PORT_OFFLINE (silent device) | PORT_OFFLINE; `/gps/diagnostics` `usb_discovery` = lowest priority, next attempt in 469 s |
| Whole-Jetson CPU | 68.2% (30 s) | **66.3% mean, 64.4–70.1%, 0 of 60 samples over 75%** (60 × 1 s) |

GPS still has no data: the module on `ttyUSB1` sends no NMEA (hardware check pending). Indoor operation and USB
communication no longer depend on it. Rollback: copy `backup/gnss_node.py` back, remove `low-priority.conf`,
daemon-reload, restart atlas-gnss.
