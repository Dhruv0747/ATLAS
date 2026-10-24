# ATLAS — 3D preview and CPU headroom validation (24 Oct 2026, 21:20–21:50 IST)

Owner directive: measure real CPU after the GNSS fix, measure the Visual Cloud's cost, run the one approved
Depth-only experiment, verify real 3D data, and judge headroom for Depth + LiDAR + IMU (+ detection) fusion.
ATLAS was parked throughout: E-STOP latched, manual-only, commissioning disarmed, motor commands zero, recorder OFF.
No movement was commanded and autonomous navigation was not enabled.

Evidence folder on the Jetson: `~/project-atlas-migration/headroom_20261024_2122/` (1-s monitor logs, Vision Lab
status samples, session state, backups). Tools: `project_atlas/tools/vision3d/headroom/`.

| Verdict | Status |
|---|---|
| GNSS FIX VERIFIED | **YES** |
| CPU BASELINE MEASURED | **YES** |
| VISUAL CLOUD SAVINGS VERIFIED | **PROCESS LEVEL ONLY** (whole-Jetson difference not separable from noise) |
| UNCALIBRATED 3D PREVIEW LIVE VERIFIED | **PARTIAL** — real depth frames and 3D points from them verified on the Jetson; browser rendering and rotate/zoom/pan/select reported by the owner (section 4) |
| CONTROL/SENSOR TIMING VERIFIED | **YES** for this 160×120 Depth session (no change in any gap) |
| CPU POLICY RESTORED | **YES** — original runtime `ebaaa3c7…`, flag removed |
| FULL FUSION READY | **NOT READY** — not demonstrated (section 6) |

## 1. Visual Cloud CPU (camera off)

| State | Visual Cloud agent | Server | Evidence |
|---|---:|---:|---|
| Page open (owner's screenshot 21:12) | **12.46%** of one core | 1.02% | 30-s cgroup sample, 21:13 |
| Page closed | **1.57%** | 0.03% | 30-s cgroup sample, 21:21 |

Process-level saving ≈ 10.9% of one core, about 1.8 points of whole-Jetson CPU (6 cores). Whole-Jetson: 65.8% mean
(page closed, 60×1 s, 21:21) against 66.3% (60×1 s, 21:11, page state not recorded). This 0.5-point difference
is inside normal second-to-second variation (63–74%), so a whole-Jetson saving is **not claimed**. The service was not
stopped or reconfigured. The agent is already viewer-activated: it only collects at full rate while its page is open.

## 2. GNSS fix and base health (21:23–21:26)

- GNSS child process nice 19, I/O class idle; source `cc638c69…` (commit d37cd7d on agent/reliability-optimization-20261023).
- Probes after the fix: 21:10:49 and 21:20:49 — exactly the 600-s retry. The 21:09:02–21:09:10 entries came from the
  old process before its restart.
- USB discovery lock: free in 20/20 samples. `/gps/diagnostics.usb_discovery` = `{priority: lowest, retry_s: 600}`.
- Yahboom base connected. Encoder packet fresh (age 8 ms), channels 1–4 accepted, no faults; health READY.
- `/scan` 6.9 Hz, IMU 9.9 Hz, `/yahboom/odom` 10.1 Hz; mux, localization, LiDAR, IMU, safety active; controller,
  planner, bt_navigator, AMCL, map_server active.
- E-STOP latched, commissioning disarmed, manual-only, `/cmd_vel` zero, recorder inactive, mission READY.
- GPS: PORT_OFFLINE (the receiver sends no NMEA). Indoor operation does not depend on it.

## 3. Experiment preparation

- Approval not consumed: runtime `ebaaa3c7…` and gate `0c5ec244…` unchanged since 21:03, no flag present, last
  camera attempt 20:32 (before the 21:03 approval, blocked by the guard).
- Temporary change (`cpu_monitor_only_experiment.patch`, 41 lines, CRLF preserved): a single-use, 15-min tmpfs flag,
  Depth mode only, consumed by the first worker. With it, CPU above 75% is logged (`cpu_trace`,
  `cpu_over_limit_samples`), not blocking. RAM 80%, temperature 70 °C, unknown-CPU, policy / E-STOP / zero-command /
  recorder checks, sensor freshness (`extra_safety`), the 4-s lease, the stalled-guard (>2 s window) fail-closed check and
  driver cleanup are unchanged.
- Offline: 14/14 scenarios against the real worker with fake hardware (`scenarios.py`): monitor-only run completes
  at 90% CPU; no flag → blocked; RAM 85 / temperature 72 / policy failure / lease loss / stalled guard → stop;
  flag single-use, expiry, >30-min, wrong-mode and multi-session flags refused; unflagged behaviour unchanged.
- Independent monitor (`atlas_headroom_monitor.py`, nice 10, subscriptions only): 1-s whole-Jetson CPU, runnable tasks
  (this kernel has no PSI), RAM, temperature, service and process CPU, and max gaps of `/scan`, IMU, encoders,
  control policy and `/cmd_vel`. It would SIGTERM the worker on a stale deadline (scan > 1.0 s, IMU/encoders > 0.5 s,
  policy > 2.0 s), unlatch, arming, nonzero command, RAM > 80% or temperature > 70 °C.
- **Finding:** a new ROS participant joining the production domain costs **~8 s at 93–99% whole-Jetson CPU**
  (measured when the monitor started; it matches the Stage 31 measurement). Every `ros2` CLI check does this.

## 4. The Depth session (owner in Chrome, 21:43)

Install 21:42:15: backup `backup_runtime/atlas_vision3d_runtime.py` (`ebaaa3c7…`), patched runtime `8628d04f…`, flag
written, monitor and status sampler started.

| Worker | Start | CPU policy | Result |
|---|---|---|---|
| 148178 | 21:43:03 | MONITOR_ONLY (flag consumed) | ACTIVE at 21:43:08 with live depth; OFF after ~14 s. No monitor violation, no monitor action. The stop reason was overwritten by the next session (most likely the Chrome tab losing visibility — the page stops the viewer when hidden). |
| 148548 | 21:43:33 (second Start by the owner) | **ENFORCED (normal 75% guard)** | **Full 60-s session, never blocked**: 60 guard samples, driver spawned at 3.19 s, reaped at 61.28 s, `driver_stopped: true` |

The second session therefore ran under the unchanged production guard.

**Hardware depth frames** (Vision Lab receiver, domain 77): Astra negotiated `160×120@30Hz` 16UC1. Observed
**13.9 fps mean** (min 10.7) at the receiver, 775 frames, largest gap 0.138 s, source age mean 0.124 s (max 0.52 s).

**3D points from real frames** (Jetson-side, same algorithm as the browser preview: nominal FOV, stride 2, 0 < Z ≤ 8 m),
three raw frames from session 148178: **2907 / 2930 / 2970 valid points** of 4800 sampled pixels;
Z 0.58–5.93 m, median 2.32 m.

**Browser rendering and interaction** (owner's Chrome, PC-side computation): to be filled from the owner's report —
the point-count line under the 3D view, and rotate / zoom / pan / point selection. Until then this part is unverified.

### CPU and resources (monitor, 1-s samples)

| Window | n | Mean | p95 | Max | >75% | Dashboard (one core) | Astra driver | Worker |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Pre-start baseline (monitor running) | 30 | 66.6 | 69.1 | 72.4 | 0 | 42.0% | — | — |
| Start burst (first 6 s, 148548) | 6 | 68.7 | 69.3 | 71.3 | 0 | 57.5% | 3.4% | 3.8% |
| Depth ACTIVE (148548) | 55 | **67.2** | 69.9 | **71.3** | **0** | 55.2% | **3.3%** | 1.3% |
| Depth ACTIVE + raw-frame fetches (148178) | 8 | 68.4 | 69.7 | 71.5 | 0 | 56.2% | 3.2% | 1.2% |
| After the session (camera off) | 174 | 66.5 | — | 75.3 | 1 | — | — | — |

RAM max 62.9%, temperature max 61.4 °C during the session. Runnable tasks peaked at 55 (baseline 36).

### Control and sensor timing (max inter-arrival gap per second)

| Topic | Baseline max | During Depth max |
|---|---:|---:|
| `/scan` | 0.269 s | 0.277 s |
| `/yahboom/imu/data_calibrated` | 0.121 s | 0.123 s |
| `/atlas/encoder_update` | 0.126 s | 0.125 s |
| `/atlas/control_policy` | 0.124 s | 0.123 s |
| `/cmd_vel` | 0.263 s | 0.266 s |

E-STOP latched, manual-only, commissioning disarmed and commands zero in every sample. No violation and no monitor
action during either session.

## 5. Restore (21:46)

- `atlas_vision3d_runtime.py` restored from the backup: `ebaaa3c7…` (original); gate `0c5ec244…` (never changed).
- Flag: consumed by worker 148178, then removed from `/run/user/1000` (copy kept as `flag_consumed.json`).
- No Astra / worker / cloud processes left. Vision Lab summary OFF with `cpu_limit_percent: 75`.
- Protected services (base, localization, LiDAR, IMU, mux, safety, voice, dashboard, sensor hub, mission, remote,
  on-demand, EKF, scan filter): PIDs and restart counts unchanged since 21:08. Pi camera active, 0 restarts.
- After the session: E-STOP latched, commands zero, recorder inactive; `/scan` ≤ 0.27 s, IMU 0.12 s, encoders
  0.12 s, policy 0.10 s.

## 6. Engineering assessment

| Condition | Whole-Jetson CPU (mean / max) |
|---|---|
| Parked after the GNSS fix (21:11) | 66.3 / 70.1 |
| Visual Cloud closed, camera off (21:21) | 65.8 / 73.7 |
| Real Depth-only operation (160×120, 60 s) | 67.2 / 71.3 |
| Depth + browser 3D preview | 68.4 / 71.5 (8 s, worker 148178; the 3D conversion runs in the browser on the PC) |
| A ROS participant joining the production graph | 93–99 for ~8 s |

- **Astra cost at this resolution is small:** 3.3% of one core (~0.55 points). The dashboard process rose from 42% to
  55% of one core while serving frames to the browser. Whole-Jetson rose about 0.6 points; that is within noise.
- **Why earlier attempts were blocked:** the guard's start-up samples hit 80.3% (14:45) and 84.9% (18:01). Today the
  same start-up peaked at 71.3%. The difference coincides with the 8-s join spikes (any concurrent `ros2` CLI call or
  newly starting node) and, before 18:59, the restart loops. Without per-second history from those times this is
  consistent with the evidence, not proven.
- **Fusion: NOT READY.** One 60-s session at 160×120 depth (~14 fps observed) proves Depth viewing fits. It does not
  prove fusion. Fusion needs: higher depth resolution (640×480 is 16× the pixels), sustained operation, a ROS
  PointCloud2 path (calibration not validated), and detection (the TensorRT annotator takes ~80 s to load). The Jetson
  averages ~66% busy, about 2 of 6 cores free, with recurring join spikes to 93–99%.

### Proposed architecture changes (none applied; each needs separate approval)

1. **Remove join spikes from operation:** no `ros2` CLI or newly started ROS nodes during camera or autonomy use; use
   one persistent low-rate monitor. Largest single source of 100% readings measured today.
2. **Dashboard (42–55% of one core) is the biggest non-Nav2 consumer:** serve depth previews as raw buffers only
   (the browser already converts them) and drop server-side PNG encoding of depth when the 3D preview is the active
   view. Owner decision 2026-10: the production dashboard stays hosted on the Jetson.
3. **Pi camera (40% of one core):** stream only while a viewer or an autonomy consumer needs it (on-demand, like the
   AI features).
4. **GPU for fusion:** depth→XYZ and detection belong on the Orin GPU (CUDA/TensorRT), not CPU Python.
5. **Raspberry Pi 5 (owner says it is available):** a candidate for non-control, non-safety loads only — Visual
   Cloud agent/server, Foxglove bridge, recording, diagnostics history. Control, safety, sensors, Nav2 and the
   dashboard stay on the Jetson.
6. **Before any fusion work:** a 10-min 640×480 Depth soak under the normal 75% guard with this monitor, then the same
   with LiDAR/IMU fusion running offline-replayed, measuring the same timing table.
