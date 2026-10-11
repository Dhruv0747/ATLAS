# Localization during motion: investigation, 2026-10-10

Scope: the operator's report that AMCL is UNCERTAIN while driving, becomes
CONFIDENT 5–10 s after stopping, lags behind when driven fast, makes 1–2 m
jumps, sometimes fails to recover at home, and shows POSE/CONNECTION DELAYED
when Wi-Fi/Tailscale pings time out. Analysis used saved recordings and logs;
the only production change is the dashboard status label (see "Changes").
No movement, calibration change, AMCL/EKF parameter change, service restart
or safety bypass was made. `navigation_authorized` stays false.

## Answer first

| Rank | Finding | Status |
| --- | --- | --- |
| 1 | **Wheel odometry under-reports distance by roughly 40%.** Three agreeing encoders (M1, M2, M4) give 0.60–0.62 × the distance LiDAR scan matching (ICP) measures, on every drive. The EKF `/odom` is 0.36–0.54 × above 0.3 m/s. AMCL's motion step therefore puts the particles well short of the true pose on every update. | **Confirmed** (3 independent methods + 2 historical tape measurements) |
| 2 | **UNCERTAIN while moving is mostly the motion-noise model.** With alphas 0.2, the whole-cloud spread stays above the dashboard's 0.25 m / 20° limit while driving even when odometry is corrected. Lowering alphas *without* fixing odometry makes the label look better and the pose **worse**. | Confirmed offline (replay) |
| 3 | **CONFIDENT after stopping comes from the 1 Hz forced no-motion updates.** Each forced resample narrows the cloud with zero odometry; ~5–54 updates later it crosses the threshold. That is convergence of the cloud, not proof of accuracy. Without forced updates the replayed cloud never became confident on at least one stop per drive. | Confirmed (recorded + replay) |
| 4 | **The 1–2 m jumps are winner switches in a spread, multimodal cloud**, mostly while stopped with odometry ≈ 0 and pre-jump XY std 0.9–1.9 m. The spread is caused by 1 and 2; forced resampling while parked triggers most stationary switches. | Confirmed mechanism; corrected-odometry replays remove them on 3/4 drives |
| 5 | **The EKF future-dates `odom→base_link` by 0.2 s** (`transform_time_offset: 0.2`). Best fit of `/odom` against scan timing: +0.10 to +0.18 s. Compensating it improved held-out fit on 3/4 replays. | Suspected contributor; not deployed |
| 6 | **Wi-Fi/Tailscale do not affect localization.** All ROS topics are produced and consumed on the Jetson; at every Wi-Fi roam during the drives, `/scan`, `/odom`, `/tf`, `/imu/data` and `/amcl_pose` had no gaps beyond their normal maximum. The dashboard, however, relabelled network stalls as **POSE DELAYED**. | Confirmed; dashboard label **fixed and deployed** |
| 7 | **The Jetson rebooted uncleanly 4 times today** (13:41, 13:46, 13:54, 14:29 IST), two preceded by tens of thousands of NVMe PCIe link errors per minute. Every boot reseeds AMCL at the saved home pose (0.254, −1.539) regardless of where the rover is. | Confirmed crashes; link to "did not recover at home" is a **hypothesis** (journal for the 13:54–14:29 boot was lost) |

Slower AMCL processing is **not** the cause: AMCL header-to-publish latency
was 0.14–0.17 s and updates arrived every 0.13–0.40 s (median) while moving.

## Evidence analysed

Recordings (Jetson SQLite bags, Oct 9 IST; no drive was recorded on Oct 10):

| Bag | Wall time | Use |
| --- | --- | --- |
| `hall_to_dhruv_20261009-20261009-122252` | 12:22:56–12:27:51 | Hall→Dhruv return |
| `amcl_hall_outbound_20261009_1636` | 16:36:40–16:42:33 | manual-move offset (earlier audit); excluded from motion stats |
| `amcl_hall_outbound_20261009_retry2` | 16:47:31–16:50:26 | Dhruv→Hall |
| `amcl_hall_return_20261009_retry2` | 16:51:50–16:55:57 | Hall→Dhruv |
| `atlas_amcl_roundtrip_20261009_final` | 17:45:51–17:53:36 | full round trip |
| `amcl_stationary_passive_20261009_2113` | 21:13 | stationary only |

Logs: NetworkManager, wpa_supplicant, tailscaled and kernel journal from
Oct 9 11:00 to Oct 10 15:50; user units (status web, network fallback,
localization, seeder); `last -x`; live `iw`, `nmcli`, `tailscale status`.

Commits: integration branch `agent/integrate-localization-20261010`
(`5653c0a`), including the weak-hypothesis trace, parked-diversity,
outbound-1636, safety-hardening and mission scan-fit-gate commits listed in
the [developer branch review](ATLAS_DEVELOPER_BRANCH_REVIEW_2026-10-10.md).
Deployed config identity checked against the repository: `atlas_ekf.yaml`
and `encoder_calibration.yaml` match byte for byte; the Jetson
`nav2_params.yaml` differs in hash but its AMCL values are identical
(alphas 0.2, update_min_d/a 0.05, 500–2000 particles, 60 beams,
z_hit/z_rand 0.5, no recovery injection). Mission control calls
`/request_nomotion_update` unconditionally every 1 s (the experimental
motion gate is off).

## 1. Odometry distance scale

Three methods, all independent of AMCL's own estimate:

**a. Scan-pair ICP** (`atlas_odometry_icp_scale_check.py`; scans ~0.43 s
apart while moving, inlier RMSE < 5 cm). Forward distance relative to ICP:

| Drive | EKF `/odom` | wheel `/yahboom/odom` | yaw: `/odom` | IM10A gyro | `/imu/data` gyro |
| --- | --- | --- | --- | --- | --- |
| outbound retry2 | 0.53 | 0.57 | 0.96 | 0.97 | −0.99 |
| return retry2 | 0.53 | 0.58 | 1.02 | 0.97 | −0.98 |
| 122252 | 0.54 | 0.55 | 0.95 | 0.96 | −0.98 |
| round trip | 0.41 | 0.45 | 0.86 | 1.00 | −1.02 |

Heading is close to right; distance is not. (`/imu/data`, the board IMU,
has an inverted Z sign. The EKF does not use it, but nothing else should
either without correcting the sign.)

By ICP speed, wheel/ICP falls from ~0.77–0.84 below 0.1 m/s to ~0.43–0.62
above 0.3 m/s. The EKF falls further (0.36–0.52 above 0.3 m/s) because it
also lags 0.10–0.18 s. Very slow bins are noisy (ICP over 1–4 cm), so the
speed trend is indicative, not a calibration curve.

**b. Raw encoder counts** with the configured CPR and 125 mm wheels:
M1 0.62/0.62, M2 0.60/0.62, M4 0.62/0.61 × ICP (return retry2 / 122252).
M3 gave −0.46 and 0.31: incoherent, consistent with ATLAS-001.

**c. End-to-end displacement** between the first and last confident AMCL
poses: AMCL 6.50 / 6.61 / 6.05 m; a keyframe ICP chain 6.59 / 7.33 / 6.39 m;
EKF odometry 4.78 / 4.45 / 4.24 m (0.64–0.74 × AMCL).

Historical corroboration in this repository: 2026-09-16 "manual 40 cm
produced roughly 21 cm odometry" (0.52); 2026-09-25 "commanded 0.20 m run
physically travelled about 0.50 m while wheel odometry reported 0.294 m"
(0.59), with LiDAR odometry then matching the tape (39.7 vs ~39 cm).
`encoder_calibration.yaml` itself says the CPR values "predate final motor
replacement and require per-wheel ground revalidation". The scale error was
seen twice before and never closed.

Not yet separated: wrong CPR/gear ratio after motor replacement versus
wheel slip versus lost counts. A ~1.6× CPR error is the simplest fit to the
consistent 0.61 across three wheels; slip would not normally be this uniform.

## 2. Moving versus stopped, and why stopping "fixes" confidence

Recorded behaviour (motion audit, `atlas_motion_localization_audit.py`):
UNCERTAIN for 69–100% of moving time; moving XY std median 0.18–1.6 m;
first stop after motion reached CONFIDENT after 11.1 s / 12 updates
(outbound), 21 s / 21 updates (return), 53.9 s / 53 updates (122252),
42.6 s / 43 updates (round trip, and never on its final stop). Moving
map→odom corrections had median size 0.16–0.68 m and summed +3.0 to +3.5 m
**forward** on the outbound and 122252 drives, the direction expected when
odometry under-reports.

In the 6 recordings, AMCL covariance never went from confident to
uncertain while the rover had been stopped for 3 s. The dashboard symptom
"confidence drops while stationary" is therefore not explained by AMCL
covariance in this data. The confirmed dashboard staleness relabelling
(section 5) is the supported explanation. Today's sessions were not recorded.

## 3. Offline replay (AMCL 1.1.20 core, with motion)

`atlas_amcl_motion_replay.cpp` re-runs AMCL's per-scan loop with the
production parameters, the recorded initial particle cloud, recorded scans,
recorded `odom→base_link` TF at scan time and 1 Hz forced updates. Nav2's
`DifferentialMotionModel` logic is copied verbatim. 8 seeds per setting.
Accuracy proxy: held-out scan fit, the fraction of endpoints from beams AMCL
does not use that land within 15 cm of a mapped wall (same metric as the
mission scan-fit gate). There is no surveyed ground truth.

The baseline replay reproduces the recordings, which validates the harness:

| Drive | UNCERTAIN moving: recorded / replay | Held-out fit moving: recorded / replay |
| --- | --- | --- |
| outbound retry2 | 0.75 / 0.76 | 0.76 / 0.74 |
| return retry2 | 0.85 / 0.81 | 0.69 / 0.70 |
| 122252 | 0.86 / 0.92 | 0.70 / 0.69 |
| round trip | 0.88 / 0.89 | 0.55 / 0.57 |

Comparisons (medians over 8 seeds; "fit ≥ .85" = share of moving updates
that would pass the mission gate's 0.85 threshold):

| Setting | Drive | UNCERTAIN moving | fit moving | fit ≥ .85 | jumps > 0.5 m |
| --- | --- | --- | --- | --- | --- |
| baseline (recorded odom, α 0.2) | outbound | 0.76 | 0.74 | 0.23 | 0 |
| | return | 0.81 | 0.70 | 0.18 | 2 |
| | 122252 | 0.92 | 0.69 | 0.13 | 4.5 |
| | round trip | 0.89 | 0.57 | 0.08 | 4 |
| alphas 0.05 only (**rejected**) | outbound | 0.52 | **0.52** | **0.00** | 0 |
| | return | 0.72 | 0.67 | 0.16 | 0 |
| | 122252 | 0.69 | 0.71 | 0.11 | 1 |
| | round trip | 0.81 | 0.50 | 0.04 | 6.5 |
| distance ×1.6, α 0.2 | outbound | 0.71 | 0.93 | 0.73 | 0 |
| | return | 0.87 | 0.73 | 0.39 | 0 |
| | 122252 | 0.93 | 0.80 | 0.38 | 2 |
| | round trip | 0.88 | 0.65 | 0.28 | 15 |
| ×1.6 + 0.2 s TF shift, α 0.1 | outbound | 0.48 | 0.94 | 0.74 | 0 |
| | return | 0.71 | 0.92 | 0.64 | 0 |
| | 122252 | 0.66 | 0.88 | 0.57 | 0 |
| | round trip | 0.83 | 0.62 | 0.27 | 11 |
| ×1.6 + 0.2 s TF shift, α 0.05 | outbound | 0.24 | 0.93 | 0.69 | 0 |
| | return | 0.51 | 0.91 | 0.61 | 0 |
| | 122252 | 0.41 | 0.84 | 0.47 | 0 |
| | round trip | 0.78 | 0.58 | 0.21 | 7.5 |

Forced updates off (recorded odometry): the cloud never became confident
on at least one stop per drive, and the final held-out fit fell (e.g.
return 1.00 → 0.33; 122252 1.00 → 0.40). Forced updates are not the root
cause, and removing them alone is rejected.

Readings:
- Correcting distance is what makes the pose right (fit 0.69–0.74 → 0.84–0.94
  on three drives). Lowering alphas only makes it *look* confident.
- Lower alphas are only reasonable after the distance error is gone.
- The round trip is not repaired by any setting tried. Its turns show
  wheel yaw at 0.68 × ICP (EKF 0.86), and earlier audits found M3 and
  multimodal Hall geometry problems there. It stays open.

Limits: the ×1.6 factor was estimated from these same bags (in-sample).
Scaling the EKF output is not identical to a recalibrated encoder feeding
the EKF. Replay is the AMCL core library, not a full ROS replay. These are
diagnostics for choosing the next physical test, not settings to deploy.

## 4. Lag while moving (measured)

| Component | Value | Source |
| --- | --- | --- |
| AMCL scan stamp → `/amcl_pose` receipt | 0.14–0.17 s median | bags |
| AMCL update interval while moving | 0.13–0.40 s median, ≤ ~1.07 s max | bags |
| AMCL update interval while stopped | ~1.04 s (forced 1 Hz) | bags |
| EKF TF future-dating | +0.2 s configured; +0.10–0.18 s fitted | `atlas_ekf.yaml`, ICP timing fit |
| Odometry distance shortfall between AMCL corrections | ~40% of travelled distance (≈ 0.16 m per second at 0.4 m/s) | ICP / encoders |
| Dashboard pipeline (good link) | TF sampled every 0.5 s, fetched every 0.75 s, drawn every 0.5 s: up to ~1.75 s | `atlas_status_web.py`, `atlas_mapping.html` |

"Falls behind when fast" is mainly the odometry shortfall. Between AMCL
corrections the displayed pose advances about 60% of the real distance,
then AMCL drags it forward (median corrections 0.16–0.68 m). Faster driving
means more distance per correction and a lower measured scale. The display
pipeline adds up to ~1.75 s of age.

## 5. Wi-Fi and Tailscale

- Access points: one SSID served by three radios: main router
  `b4:a7:c6:41:fc:99/9a`, extender `f0:ed:b8:33:16:49/4a` and extender
  `8c:a3:99:e7:a3:c1/c2`, on 2.4 and 5 GHz. The Jetson's RTL8822CE runs with
  **power save on** and txpower 7 dBm.
- Oct 9: 9 roams. Roams landed inside 3 of 4 drive windows: 122252 at
  t=185 s; return at t=74/88 s; round trip at t=173/324 s. Each roam
  restarted DHCP (same lease in 0.1–2.3 s). After the 16:50 roam the
  Tailscale path to the PC fell back to the DERP relay (Bengaluru) for
  ~16 min (16:50:57–17:06:40). At 17:04:36 the default route moved to
  cellular for 35 s.
- **Jetson-local ROS was unaffected:** the maximum gap in ±10 s around every
  roam was at or below that topic's normal maximum gap for the whole bag:
  `/scan` ≤ 0.28 s, `/odom` ≤ 0.12 s, `/tf` ≤ 0.12 s, `/amcl_pose` ≤ 1.18 s
  (the 1 Hz forced cadence). The round-trip 3.8 m stationary jump came 7.7 s
  after a roam with no data gap and matches the cloud-switch mechanism.
- Oct 10: 46 roams between 14:00 and 15:00, ping-ponging across all six
  BSSIDs. The extender `8c:a3:99` repeatedly failed DHCP
  (`ip-config-unavailable`, 13:40–13:46) and a 4-way-handshake failure
  triggered the ATLAS-Rescue fallback. The default route flipped to
  cellular several times (14:16, 14:25–14:27, 14:49–14:51), each time
  forcing Tailscale through DERP. These match the reported ping timeouts.
- Dashboard defect (confirmed in code and in a browser simulation): on a
  failed or slow fetch the page set CONNECTION DELAYED, but the 500 ms
  render loop aged every item by browser time and overwrote it with
  **POSE DELAYED**. During a simulated 6 s stall the old page showed POSE
  DELAYED for 67% of samples and CONNECTION DELAYED for 12%. A slow link
  also aged the 1 Hz AMCL message past 2.5 s and showed AMCL UNVERIFIED
  while the rover was parked.

## 6. Unclean reboots and the home pose

`last -x` shows reboots at 13:41:39, 13:46:27, 13:54:08 and 14:29:04 IST,
each ending the previous session as **crash**. Before the first two, the
kernel logged PCIe corrected receiver errors on `0004:00:00.0`, the NVMe SSD
root port, at up to ~44,000 per minute (13:22–13:24 and 13:40–13:42). None
have been logged since the 14:29 boot. The user journal for the 13:54–14:29
boot is missing, so whether the 14:03–14:27 roaming was a drive cannot be
confirmed from the rover. On each boot,
`atlas_localization_seeder` sets AMCL to the saved home pose
(0.254, −1.539) wherever the rover actually is. A mid-drive crash therefore
restarts localization at home with a tight cloud while the rover is
elsewhere. The deployed mission scan-fit gate refuses missions in that
state; the dashboard does not yet warn about it.

## Changes

Deployed (display only; Jetson 16:08 IST, no restart: the page is read from
disk on every request):

- `atlas_mapping.html`: a new pure `liveStatus()` separates link freshness
  (time since this browser last heard from ATLAS) from rover-side freshness
  (the server's own item ages). A link stall now reads **CONNECTION DELAYED
  - NO DATA FROM ATLAS (ROVER STATE UNKNOWN)**. **POSE DELAYED ON ATLAS** is
  shown only when a fresh response says the Jetson's pose is old. A link
  lag below 2.5 s no longer downgrades a confident AMCL state. The pose
  panel shows "Data age on ATLAS" and "Link to this screen" separately.
  Backup: `~/project_atlas/data/backups/2026-10-10-dashboard-link-status/`
  (sha256 `a6837052…`); deployed sha256 `fb6589a3…`.
- Before/after (browser simulation, 6 s hung requests, 100 ms samples):
  old page POSE DELAYED 40/60, CONNECTION DELAYED 7/60; new page
  CONNECTION DELAYED 40/60 (after the 2.5 s grace), never POSE DELAYED.
  With a working link and a rover-side stale pose, the new page shows POSE
  DELAYED ON ATLAS. 7 Node-run unit tests pass.

Added (offline, read-only tools): `atlas_motion_localization_audit.py`,
`atlas_odometry_icp_scale_check.py`, `atlas_amcl_motion_replay_extract.py`,
`atlas_amcl_motion_replay.cpp`, `atlas_amcl_motion_replay_summary.py`, and
5 pure tests.

Not changed, on purpose: encoder CPR, EKF `transform_time_offset`, AMCL
alphas and the forced-update policy, Wi-Fi power save and AP selection, and
the saved map. Each needs a physical or live check first.

## Remaining problems and next steps (ordered)

1. **Physical distance calibration (blocks everything else).** With the
   rover on its normal floor, drive straight runs of
   2 m and 4 m at ~0.15 and ~0.35 m/s, forward and reverse. Measure with a
   tape and record raw M1–M4 counts and `/lidar/odom`. Accept a new CPR
   only if three wheels agree and LiDAR and tape agree within 3%. This
   decides CPR versus slip versus lost counts. It needs operator approval
   and supervision.
2. After 1, repeat the ICP check and replay on a fresh recorded route.
   Expect wheel/ICP 0.97–1.03 at every speed bin. Then re-test the EKF
   `transform_time_offset` (0.2 → 0.0) offline before any live change.
3. Only then evaluate AMCL alphas 0.1 (offline first, against held-out fit
   and the mission gate). Do not lower alphas on the current odometry.
4. NVMe PCIe errors and crashes: reseat the SSD, check its power and
   mounting, and run a stopped soak with `journalctl -k -f | grep AER`.
   Treat a crash during a drive as a reason to reseed from a confirmed
   place, never from the home pose.
5. Wi-Fi: turn Wi-Fi power save off
   (`nmcli connection modify Airtel_dhruv_9030 802-11-wireless.powersave 2`,
   applied on the next reconnect while parked). Fix DHCP on the `8c:a3:99`
   extender, or keep ATLAS off it. Measure with a 10-minute ping log
   during a parked and a carried walk before and after.
6. Targeted recording for the next supervised drive (today's drive was not
   recorded): `/scan /scan_raw /odom /yahboom/odom /tf /tf_static
   /amcl_pose /particle_cloud /imu/data /im10a/imu/bias_corrected_candidate
   /yahboom/encoder/m1..m4 /atlas/encoder_health /cmd_vel /lidar/odom`, plus
   `journalctl -f` of NetworkManager/wpa_supplicant/tailscaled and a
   browser-side ping log. Note the times of each stop and fast segment.
   Leave the rover still for 10 s at each end.

Correction to an earlier claim in this session: `ATLAS_MANUAL_ONLY=0` is
installed. Autonomous motion is blocked by the encoder `autonomy_ready`
flag (`navigation_validated: false`), not by a manual-only setting.
