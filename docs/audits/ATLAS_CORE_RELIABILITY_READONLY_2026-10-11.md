# ATLAS core reliability: read-only diagnostics, 2026-10-11 (13:15–13:35 IST)

Scope, in the operator's priority order:
1. Wi-Fi and Tailscale.
2. RPLIDAR start.
3. Encoder and gyro errors.
4. Moving localization.
5. Corridor map.

Rules for this session:
- Read-only on the Jetson. No reboot, restart, network, navigation, calibration or map change.
- No motion commanded. No latch change.
- Evidence files (journal extracts, ping logs, samples, a monitor-history snapshot) are kept on the
  Jetson under `~/project_atlas/data/diagnostics/2026-10-11-reliability/`. They are not committed:
  they are generated logs and contain network identifiers.
- The parsers that produced every number below are committed in `project_atlas/tools/diagnostics/`.
  `net_timeline.py` and `lidar_starts.py` were re-run from the committed copies and reproduced the
  tables exactly.

Labels used:
- **CONFIRMED**: directly observed in logs or data.
- **SUSPECTED**: plausible cause, not yet separated from the alternatives.
- **GAP**: evidence that does not exist.

Registry IDs: ATLAS-019 (network), ATLAS-015 (LiDAR), ATLAS-001/010/013 (odometry and IMU),
ATLAS-011 (localization and map), ATLAS-018 (power and clock).

## 0. Live state during this session (relevant to everything below)

- **13:23:16 and 13:26:29: the operator used the web RESET from the PC** (`100.98.59.32`) and drove
  with the web pad. `estop_events.jsonl` logs:
  - `reset_granted` twice;
  - one `e_stop` at 13:26:18;
  - 39 web hold-releases between 13:23:20 and 13:24:09;
  - many `stop` events.
- **The latch is currently released.** The fresh-press rule is active. Claude did not touch the latch.
  These operator actions are logged evidence only; they are **not** the formal E-STOP/RESET test
  session.
- A 60 s stationary sample started at 13:25:59 overlapped this driving and was **discarded**.
  The repeat at 13:28:26–13:29:26 was clean: wheel odometry unchanged and no drive events.

## 1. Wi-Fi and Tailscale (ATLAS-019)

Evidence: 8 boots of NetworkManager, wpa_supplicant, tailscaled and ModemManager journals
(Oct 8 19:00 to now), the fallback-agent journal, live `iw`/`nmcli`/`tailscale status`, and 60 s
pings.

**Network layout:**
- One SSID served by three APs, each on 2.4 and 5 GHz:
  - main router **A** (`b4:a7:c6`);
  - **B** (`f0:ed:b8`);
  - extender **X** (`8c:a3:99`).
- Cellular RNDIS (`usb0`) is a standby default route at metric 600; Wi-Fi uses metric 50.
- Tailscale reaches the PC directly over the LAN (`192.168.1.4:41641`). Its home DERP relay is
  Bengaluru, with occasional changes to Singapore.

### CONFIRMED

| # | Finding | Numbers |
|---|---|---|
| N1 | **Roams to B or X fail DHCP; roams to the main router never do.** Every roam restarts DHCP | A2.4 8/8 and A5 18/18 leases, all within 0–2 s. B2.4 2/3, B5 2/3, X2.4 5/7, X5 2/3, with one more X5 attempt open when the 13:45 boot's journal ends |
| N2 | **Long outages are DHCP failures on B/X, not radio loss.** Two cases | Oct 10 13:42–13:45: two `ip-config-unavailable` on X, then a crash. Oct 10 14:49:04–14:51:23: B5 → X5 → B2.4 with no lease, cellular default route for **73 s**, Tailscale rebound twice |
| N3 | **The fallback agent saw Wi-Fi Internet fail 5 times with no roam.** It routed via cellular each time | 17–109 s each: Oct 8 17:44 (26 s), Oct 9 17:04 (35 s), Oct 10 14:49 (109 s, roam storm), Oct 10 19:55 (17 s, roam storm), **Oct 11 09:39:54 (26 s, no roam; associated to A2.4 since 09:21)** |
| N4 | **NetworkManager briefly makes cellular the default route (1 s) with no Wi-Fi event** | 6 times: Oct 9 09:47, 15:18, 18:28; Oct 10 12:23, 12:38; Oct 11 13:17:05. Each forces a Tailscale "major link change": the DERP and control connections close, and the direct path to the PC is re-found **within the same second**. Info-level logs give no trigger |
| N5 | **Power saving is on at two levels; reported TX power is 7 dBm** | NetworkManager `wifi.powersave = 3` (`default-wifi-powersave-on.conf`); driver `rtw_power_mgnt=2`. Regulatory domain `00` (world). Now on A5, channel 161, −51 dBm, 13 excessive TX retries |
| N6 | **The Wi-Fi radio shares its chip with the Bluetooth link to the BMS, which reconnects constantly** | RTL8822CE combo with BT coexistence enabled (`rtw_btcoex_enable=2`). **1,164** failed bonding attempts this boot, every few seconds |
| N7 | **Tailscale latency** | Disco ping to the PC 2–55 ms. ICMP over Tailscale p50 54 ms, p90 101 ms, max 210 ms. Gateway ping p50 1.6 ms, max 48 ms, 0 % loss. The PC does not answer plain LAN ICMP (firewall) |
| N8 | **Tailscale reports a connmark iptables error** | `xt_connmark` missing on the L4T kernel. Basic tailnet traffic works; affects only Tailscale's netfilter features |
| N9 | Jetson-local ROS is unaffected by roams (Oct 10 finding, unchanged) | — |

### Correction to earlier records

The Oct 10 motion investigation said "46 roams between 14:00 and 15:00, ping-ponging across all six
BSSIDs". The journal today contains **6 associations** in that hour, all after the 14:29 boot. The
13:54–14:29 boot has no journal. The figure of 46 cannot be reproduced from retained logs.
**Treat it as unverified.** The extender DHCP and cellular-route findings stand.

### SUSPECTED, not separated

- **S-N1: the B and X DHCP failures are on the AP side** (extender or mesh DHCP relay). They are not
  Jetson-side, because A never fails.
- **S-N2: Wi-Fi power saving, BT coexistence and low TX power together cause roaming and latency
  spikes.** No before/after measurement exists.
- **S-N3: the 1 s cellular flips** may come from a route re-sync in NetworkManager 1.36 or the
  fallback agent's probes. Would need NetworkManager debug logging, which is a runtime change and so
  needs approval.
- **S-N4: the 54 ms Tailscale median** may be on the PC side (Windows Wi-Fi power save) or due to
  Jetson CPU load. The load average is 13–16 on 6 cores. Not separated.

### Proposed fixes (none applied; each needs approval under the networking rule)

1. **Lock the Jetson to the main router.** Pin the BSSID, or prefer A with a lower roam aggressiveness.
   Or fix DHCP relay on B and X on the router side. This addresses N1 and N2, the biggest outages.
2. **Turn Wi-Fi power save off.** NetworkManager `wifi.powersave=2` for this profile, applied on the
   next reconnect. Then compare 10-minute ping logs with the rover parked and carried.
3. **Set the regulatory country to IN** so TX power limits are correct. Measure before and after.
4. **Stop the BMS reconnect loop** (ATLAS-007). This also removes the BT coexistence load.
5. **Short NetworkManager debug window** to capture one 1 s cellular flip (N4).
6. **A bounded ping logger** (gateway, PC, 1.1.1.1; 1 Hz; 24 h; about 3 MB). This is the evidence
   ATLAS-019 has always lacked. It is background work, so it needs approval.

## 2. RPLIDAR start (ATLAS-015)

Evidence: `atlas-lidar` and `atlas-sensor-recovery` user journals for 8 boots, ModemManager
journal, USB topology and power attributes, by-id links, open serial handles.

### CONFIRMED

| # | Finding | Numbers |
|---|---|---|
| L1 | **Failures happen only at start; once scanning, the LiDAR never failed within a boot** | Every boot has exactly one successful start, then no runtime failure |
| L2 | **Delay before the first scan varies widely** | 20 s, 24 s, 40 s, 47 s on good boots. **101 s, 146 s, 233 s, 257 s** on bad ones. Today: 6 failed starts (`TTIITI`), scanning at 101 s |
| L3 | **Two failure signatures** | T: no reply to the first query (`SL_RESULT_OPERATION_TIMEOUT`). I/S: device info and health OK, then the scan start fails (`80008000` invalid data, or `80008002` timeout). Both can occur in one boot |
| L4 | **No USB re-enumeration or error during the failures** | No cp210x, `usb 1-2.2` or over-current kernel lines after 14 s in any examined boot. The device stays enumerated on `ttyUSB3` |
| L5 | **ModemManager does not probe the LiDAR** | It logs "couldn't check support" for `1-2.2.1` (strict filter). **Hypothesis rejected** |
| L6 | **No other process holds the LiDAR port; vc02 voice is not running** | Only `rplidar_composition` has `ttyUSB3` open. vc02 denies the CP2102 by name and by fixed tty numbers |
| L7 | **The recovery deferral (b28819c) works on the Jetson** | Today: "RECOVERY DEFERRED … systemd is already restarting". No recovery-initiated restart |
| L8 | **The LiDAR sits on a downstream USB-C hub** | VIA VL817 (2109:2817 + billboard 2109:8817) at `1-2.2`, alongside an ESP32-S3 (500 mA declared) and a CH340. That hub is behind the Realtek hub at `1-2`. All hubs report self-powered (`e0`). Sharing the Realtek hub on other branches: Arduino (500 mA), and the SIM8230 modem hub (modem 500 mA, Xbox pad 500 mA, 2× CH340) |

### SUSPECTED, not separated

- **S-L1: 5 V supply sag or noise at the LiDAR during boot.** Strongest candidate:
  - fits failures that clear after a variable time, not after a fixed number of retries;
  - fits "health OK but cannot start scan" (motor not reaching speed);
  - the boots with the most failures are ones where everything starts at once.
- **S-L2: the LiDAR is left mid-scan or with its motor on from a previous instance**, so its first
  replies are corrupted. The rplidar_ros 2.1.4 driver does not reset or flush the device before
  `getDeviceInfo`. Partly argued against by cold boots with failures (today's boot followed about
  6.7 h of power-off).
- Boot-time CPU load alone is unlikely: good boots also started under full boot load.

### Proposed fixes and tests

- **Read-only software instrumentation.** Record, per start attempt:
  - the INA3221 `VDD_IN` voltage and current (`/sys/bus/i2c/drivers/ina3221/1-0040/hwmon`). This
    is the module input, not the USB 5 V rail, so it is only indirect evidence;
  - the time since boot;
  - the load average.

  It is a small `ExecStartPre` logger, so it still needs approval as a unit change.
- **Physical tests (need you):**
  1. Measure the 5 V at the LiDAR adapter during a cold boot (USB meter).
  2. Move the LiDAR to its own powered port or hub, or give the A1 motor its own 5 V supply.
  3. Boot once with the modem hub unplugged.
- **Step 3 (`StartLimitBurst=40/900 s`)** stays on HOLD. It bounds the restart loop but does not fix
  the cause.
- **Candidate software mitigation (not built):** an `ExecStartPre` that opens the port, sends
  STOP + RESET, waits 2 s and flushes. This targets S-L2 only. Do not build it until the
  measurements show S-L1 is not the cause.

## 3. Encoders and gyro (ATLAS-001/010/013)

No new drive recording exists since Oct 10. The newest bags are from Oct 10 16:55–19:17, all
stationary or pre-deploy. Nothing was recorded for today's operator drives.

### CONFIRMED (new)

| # | Finding | Numbers |
|---|---|---|
| E1 | **The live EKF's gyro input outputs exactly zero when parked** | EKF `imu0` = `/im10a/imu/bias_corrected_candidate` (vyaw only; bias file `[0,0,0]`, `navigation_qualified: true`). Parked 60 s: **587 samples, gyro-Z exactly 0.0, standard deviation 0.0**. The observer has no software dead-band (the raw int16 is scaled directly), so the zeros come from the sensor |
| E2 | **Same pattern on the Oct 2 qualification drive** | 471 of 877 samples are exactly 0 counts, while ±1, ±2 and ±3 counts occur only 4–10 times each. A free-running MEMS gyro at rest would spread across small counts |
| E3 | **The board IMU (`/imu/data` = Yahboom) is noisy and its orientation drifts** | Gyro-Z mean +0.006 °/s, standard deviation 0.32 °/s; orientation yaw drift −0.66° per 60 s (about −40°/h). It is not the EKF yaw input |
| E4 | **Raw laser odometry creeps while parked** | `/lidar/odom_raw` (rf2o) moved 1.8 cm and −0.74° in 60 s. The processed `/lidar/odom` and wheel `/odom` held at 0. rf2o logs "Waiting for laser_scans" at its 10 Hz tick against 7.1 Hz scans |
| E5 | **Encoders parked: healthy and silent** | READY, M1–M4 selected, 0 checksum errors, interval delta 0 |

### Interpretation

- E1/E2 mean the Oct 2 "zero stationary drift" qualification measured the IM10A's own static
  zeroing (probable WitMotion-style static detection), not its bias. The parked gyro bias of this
  sensor is unobservable when parked.
- This does **not** by itself explain the Oct 10 fast-turn shortfall (0.46×). Small non-zero counts
  do pass during motion.
- The open items stand:
  - 0.6× wheel distance;
  - wrong-sign wheel yaw;
  - 0.46× IM10A turn on one fast drive.

  All need the supervised tape-measured runs. **No CPR, EKF or IMU change is proposed from this
  data.**

## 4. Moving localization (ATLAS-011): repeated live today

The localization monitor (suggest mode) history, snapshotted at 13:32:

| Time | Monitor result |
|---|---|
| 13:10–13:23:26 parked | **VERIFIED** on every check (fit 0.91–0.96; one DEGRADED at 13:16, 0.14 m) |
| 13:23:16–13:24:11 | Operator web reset and short web drive (39 hold presses) |
| 13:24:15, first check after the drive | **LOST: LiDAR places ATLAS 1.05 m / 24° from AMCL**, AMCL fit 0.51 |
| 13:24–13:30 | Still LOST, 0.74–1.02 m / 11–21°. The monitor's recovery pose fits 0.972 but with a small margin (0.061) |

- **CONFIRMED:** a single short manual drive took a LiDAR-verified pose to about 1 m / 20° wrong.
  The monitor caught it within 4 s of stopping, as designed (stop → result 5.07 s). Autonomy stayed
  disabled and nothing was reseeded.
- **GAP:** there is no bag for this drive. Wheel distance against LiDAR truth cannot be measured, so
  it cannot be attributed between odometry scale (ATLAS-001) and AMCL behaviour. rf2o's logged pose
  is too noisy for that: about 4 m of jitter path against 0.25–0.30 m net per episode.
- **Proposal (needs approval; background work):** a bounded always-on drive recorder. It would
  record `/odom`, `/yahboom/odom`, encoders, `/imu*`, `/scan`, `/amcl_pose`, `/cmd_vel` and the mux
  policy; only while moving plus 10 s either side; capped at about 500 MB with rotation. Every
  failure so far (Oct 10 18:30, today 13:24) arrived without a recording.
- **ATLAS is currently not localized** (monitor LOST). Reseeding needs your decision, and preferably
  your physical confirmation of the place.

## 5. Corridor map (ATLAS-011)

Unchanged since Oct 11 00:00:
- candidate v1 rejected; the safe v3 gives no benefit;
- the repair is a supervised slow re-map (≤ 0.15 m/s, ≤ 15°/s), operator-driven, preceded by fresh
  scans at the corridor midpoint and the Hall.

No new evidence was gathered; it needs the rover at those places.

## 6. Power, clock and journal (ATLAS-018)

- **CONFIRMED:** boot −1 (from 22:24:45) ended **uncleanly at 00:55:16**. The journal stops
  mid-stream with no shutdown messages.
- **CONFIRMED:** the Jetson came back at **07:36:51 real time** (from `/proc/uptime`), but its
  clock started at **01:16:30**. NTP corrected it at 07:37:24, so boot 0's first about 54 s of
  journal are labelled 6 h 20 min early.
  - **SUSPECTED:** the RTC did not keep real time across the power-off. Which saved time was
    restored is unverified.
  - Use monotonic timestamps for boot-start analysis.
- No NVMe AER lines in boots −3 to 0.
- **GAP:** whether 00:55 was a power cut or a crash. The BMS and supply have no log for that window.

## 7. Deployed changes in this session

**None.** All work was read-only.
- Added: four read-only diagnostic tools in `project_atlas/tools/diagnostics/`.
- Written on the Jetson: evidence files only, in the diagnostics folder.

## 8. Tests that need you (suggested grouping)

| Session | Tests | Motion |
|---|---|---|
| E-STOP (already planned) | Blocks A–E from the deployment record | none / wheels lifted |
| Bench, rover off charger | LiDAR 5 V measurement on a cold boot; a second cold boot with the LiDAR on a separate powered port | none |
| Supervised drive (needs approval) | Tape-measured 2 m and 4 m straight runs at two speeds, plus ±90° turns, **with the drive recorder running**. Resolves ATLAS-001 scale, wheel-yaw sign and IM10A turn ratio | yes, slow |
| Map (later) | Fresh scans at the corridor midpoint and the Hall, then a slow operator re-map | yes, slow |
| Network (no presence needed) | Approval for items 1–6 in §1. They can be tested while parked | none |
