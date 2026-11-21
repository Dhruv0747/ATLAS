# ATLAS developer handover — 2026-11-04 (snapshot 09:54 IST)

Main objectives: **LIVE Neural Data Flow** and **operational 3D Vision Lab**. Mux and Yahboom upgrades are ON HOLD.
Everything below is either verified (with the source named) or marked UNKNOWN / PENDING. No PASS is claimed without evidence.

## 1. Operational status (read-only, 09:54 IST, boot 33363f37)

| Item | State |
|---|---|
| Safety | stop_latched=true, manual_only=true, commissioning off, cmd_vel 0/0, MCU encoder packet 0.026 s old (LIVE) |
| Resources | CPU 62 %, RAM 58 %, 63 C. Limits unchanged: CPU < 75 %, RAM < 80 %, temp < 70 C |
| Recovery | active, PID 1995, 0 restarts. Original script `5f44cc1f` (no snapshot producer). Snapshot deployment **NO-GO** |
| Mux | active, PID 1941, 0 restarts. ON HOLD |
| Yahboom base (`rover-base-telemetry`) | active, PID 3464, **1 restart every boot** (see 7) |
| Dashboard (`rover-status-web`) | active, PID 2077, port 8088 |
| Pi camera (`atlas-camera`) | active, PID 1950 (existing IMX708 driver) |
| Astra / Vision3D | **OFF** (`/api/vision3d/summary` state OFF). No camera session started today |
| Feature manager | active, PID 2080, new code `5bcd4f08` (see 3) |
| Foxglove bridge + nav-goal | **stopped and disabled** on the owner's request (port 8765 closed) |
| Monitoring (Jetson) | firewall/watchdog/exporter **inactive**; M2 fault latch **retained**; Prometheus has **no fresh Jetson data** |
| `atlas-ptz-home` | failed every boot (stale script, harmless, see 7) |

## 2. Branches, commits, working directories (all pushed to github.com/Dhruv0747/ATLAS)

| Branch | Head | Local worktree | Content |
|---|---|---|---|
| `codex/neural-monitor-20261102` | `a8fd494` | `/home/claude/atlas_neural` | Monitoring recovery (M2 noreload), Windows auto-start (`1ffe629`), Pulse View (`a8fd494`) |
| `codex/boot-cpu-optional-features-20261104` | `5008534` | `/home/claude/atlas_bootcpu` | Boot optional-AI correction (`5c2e9f6`), boot fault analysis (`5008534`) |
| `codex/onboard-map-final-20261102` | `10cb020` + this doc | `/home/claude/atlas_mux` | Vision Lab offline tests (`562d52d`), Recovery CPU/boot work (`b9b3dae`..`10cb020`), Mux (closed, `32232b8`) |

Unmerged PRs #15, #16, #19 and issue #17 are unchanged. Commits use the owner's identity (Dhruv0747); the stop hook's
request to rewrite them to noreply was declined by rule. Do not rewrite pushed history without approval.

## 3. Installed vs staged vs offline-only

**Installed on the Jetson today**
- Boot optional-AI correction (`5c2e9f6`, apply 08:32): manager `b0fb5b43` → `5bcd4f08`; 8 autostart links removed
  (vision-lidar-fusion, person-sensor-fusion, experience-store, agent-team, ai-annotator, follow-person,
  camera-tracker, active-vision). Measured: longest boot overload 149 s → 48 s, last breach +290 s → +125 s,
  0 optional starts. Boot still **FAILS** the strict 75 % rule (core services saturate ~60 s).
- Foxglove bridge and nav-goal stopped and disabled (owner request, 08:33).

**Staged on the Jetson, not active**: `~/project-atlas-migration/recovery-reboot-4af4ddad/` (boot monitor,
disarmed); `monitoring-recovery-m2-noreload-20261104.tar.gz` (consumed, see 6); `boot-optional-features-5bcd4f08/` (rollback).

**Offline only (repo)**: Pulse View changes (`a8fd494`), Windows auto-start (`1ffe629`), Vision Lab Object/Target,
the Recovery snapshot candidate `4af4ddad`.

## 4. Windows installation — PENDING the owner's output (not run yet)

Normal PowerShell, in order. Each prints PASS or FAIL:
```powershell
cd $env:USERPROFILE\Downloads\atlas_deploy\atlas-monitoring-autostart; powershell -ExecutionPolicy Bypass -File .\install.ps1
cd $env:USERPROFILE\Downloads\atlas_deploy\atlas-pulse-install;      powershell -ExecutionPolicy Bypass -File .\install-pulse.ps1
```
- Auto-start: ONE per-user logon task, "ATLAS Monitoring WSL Autostart": `conhost --headless wsl.exe -d Ubuntu-22.04 -u root
  keepalive.sh`, flock single instance, bounded 180 s readiness check, no stored password. Never runs compose up/down.
  Rollback: `uninstall.ps1`. Log: `/var/log/atlas-monitoring-autostart.log` in WSL.
- Pulse View: copies 5 verified files into the running Grafana container (`/usr/share/grafana/public/atlas-pulse`), no restart;
  refuses an existing destination; checks dashboards unchanged and anonymous data API = 401.
  Rollback: `uninstall-pulse.sh` in WSL. Recreating the container drops these files; reinstall afterwards.
- Verify after: Grafana `/api/health`, Prometheus `/-/ready`, Health Monitor unchanged, Pulse View after login.
  A Windows **reboot test needs separate approval**.
- Root cause this morning: the WSL keep-alive had died (manual `sleep infinity` from 2026-10-30), so Prometheus/Grafana were down.

## 5. Neural Pulse View

- URL (after install and Grafana login): `http://127.0.0.1:3000/public/atlas-pulse/pulse-view/index.html`
- 19 nodes, **8 verified** (can animate), **12 unverified** (never animate). Labels: LIVE / IDLE / STALE / DISCONNECTED /
  UNAVAILABLE / UNVERIFIED; arrows source → destination; speed is a bounded log of rate (1 Hz 3.0 s ... 1 kHz 1.05 s).
- Tests (`a8fd494`): 6 Node + 2 browser suites PASS on bundled Chromium (the suites pin Edge on Windows; an Edge run on Windows is still pending).
- **Real-data blocker:** the Jetson exporter is DOWN (M2 latch). It currently shows DISCONNECTED. **0 live animated paths.** Never animate stale or unverified data.

## 6. Monitoring recovery

- Fault latch `FAULT.json` = `fc5479c9…` (M2 watchdog, 2026-10-31 18:40:47, M2 encoder −126 → −127 while stationary; physical cause UNKNOWN).
- State files (owner sudo read 09:21): rollback.json `638a9e65`, fault-events.json `81b9b1e5` (8 boot-time firewall
  refusals), the other five unchanged.
- Attempt `m2-noreload-20261104` (package `dc1b174a300aeed1193dc47a155c0b40dce6f4a2c8dff8b3484b3954b77a15ab`,
  source `e87a545`) ran 09:22:06–09:27:11. **No CPU rejection (max 63.7 %)**, so the `--no-reload` fix works. Real data
  flowed about 09:23:45–09:27:15. It **EXPIRED**: no confirm-client inside 120–240 s. Cleanup PASS: latch restored to `fc5479c9`,
  archive in `/var/lib/atlas-monitoring-recovery-m2-noreload-20261104/` (root only). This identity is **consumed**.
- **Next attempt** needs a NEW identity:
  1. Copy commits `12a1609` + `e87a545`: rename E/TX in `recover_once.py`, add the consumed noreload identity to the reuse test.
  2. Owner sudo re-reads the 8 hashes (the expired attempt's cleanup may have changed rollback.json; every later boot adds a
     firewall refusal to fault-events.json, limit 16), then bind them.
  3. Build the archive from git blobs (0644, root, commit mtime) and run 52 transaction tests.
  4. **Before start: verify Prometheus/Grafana on the PC are UP** (the auto-start installation removes this risk).
  5. Fresh Jetson gates, then a separate execution approval.
  6. The owner keeps the `confirm-client` command ready and runs it at about start + 120 s once fresh data is verified.
  No retries, no latch bypass, no limit change. Procedure template: `monitoring/atlas/persistent/M2_NORELOAD_PACKAGE_20261104.md`.

## 7. Vision Lab — all six features

| Feature | Status | Blocker |
|---|---|---|
| Object Detection | OFFLINE PASS (letterbox, NMS, UI 21 checks; engine `97cd6658`, onnx `b2bc52f4`) | Live activation blocked (below) |
| Target Tracking (read-only 2D) | OFFLINE PASS (IoU tracker) | Same |
| Face Recognition | identity storage `7abe734` (8 tests) | No verified embedding extractor or calibrated threshold |
| Gesture | not installed | No hand-landmark model |
| Body/Skeleton | person boxes only | No keypoint model |
| RGB-D Mapping | not verified | Intrinsics, RGB-depth registration and mount TF unverified |

**Why live activation is blocked:** the installed design restarts the dashboard web service. Its restart is (a) unobserved
by an independent safety observer, which needs the Recovery snapshot, NO-GO, and (b) a new DDS participant, so it would
**probably** exceed 75 % CPU (predicted from the Recovery measurement of +15.3 points fan-out; not measured for the web service).
**Approved next design (offline, not started):** a separate lightweight process with **no rclpy**:
- reuse `atlas_vision_feature_lab.Lab`, the worker and the guard unchanged;
- frames via the existing dashboard `GET /api/vision3d/frame?kind=rgb` (PNG, max 240 px wide, at most 2 Hz). Note that
  each GET calls `svc.touch()` and renews the viewer lease, so bound the polling to the test session;
- safety via the existing `GET /api/status` (guard `observe()`);
- access mirrors the dashboard: same-origin + LAN/Tailscale.

The camera viewer still needs its own approval. Finding: the user manager has **no CPU controller** (only memory/pids), so
every `CPUQuota`/`CPUWeight` in ATLAS user units is ignored (web 47 % against a 30 % "quota"; Yahboom CPUWeight=1000 is ineffective).

## 8. Startup faults (root causes, no change made)

- Yahboom exit-1 at boot: the shared USB-discovery flock is held by the IM10A probe. Self-heals after a 3 s systemd restart. Left as is.
- `atlas-ptz-home`: stale July `/home/jetson/home.py` writes a PCA9685 at Jetson I2C bus 7/0x40, which isn't there.
  The pan-tilt now runs through the UNO R4. Optional: `sudo systemctl disable atlas-ptz-home.service` (rollback: `enable`).
- Remaining boot CPU: ~45 services start together at +16.7 s; localization 54.4 CPU-s at +60 s (estimate method in `5008534`).

## 9. Rollback locations and hashes (on the Jetson unless noted)

| What | Where | Key hashes |
|---|---|---|
| Feature manager | `~/project-atlas-migration/boot-optional-features-5bcd4f08/` (`rollback.sh`, `backup/`) | original `b0fb5b43…`, new `5bcd4f08…`, archive `be3c59ff…` |
| Foxglove | `~/project-atlas-migration/foxglove-disable-20261104/rollback.sh` | unit file sums in `unit-files.sha256` |
| Recovery script | live `5f44cc1f…`; candidate `4af4ddad…` (r3 package `e145eb61…`); PC copy `Downloads\atlas_deploy\recovery_live_5f44cc1f.py` | |
| Boot evidence | `~/project-atlas-migration/boot-evidence-{bfa7996c,33363f37}/` + PC copies | summaries `e4c8dff7…`, `a6446faf…` |
| Monitoring M2 | `/var/lib/atlas-monitoring-recovery-*` (all attempts kept) | FAULT `fc5479c9…` |
| Windows | `Downloads\atlas_deploy\atlas-monitoring-autostart\`, `...\atlas-pulse-install\` | `SHA256SUMS` in each |

## 10. Pending owner approvals

1. Run the two Windows installers (4) and paste the outputs.
2. After PASS: one Windows reboot test.
3. New single-use monitoring recovery identity, then execution (6).
4. Vision Lab separate-process design/implementation: the next work item. A camera session needs its own approval.
5. Optional: disable `atlas-ptz-home` (sudo).
6. Policy decision: the boot is not compliant with the 1 s 75 % rule (Recovery snapshot stays NO-GO until decided).

## First action for the next developer

Ask the owner for the outputs of the two Windows installers. If both PASS, open the Pulse View (it should show DISCONNECTED)
and confirm the Health Monitor is unchanged. Then prepare the new monitoring recovery identity (6) for approval.
Do not restart services, start cameras or touch the M2 latch while doing so.
