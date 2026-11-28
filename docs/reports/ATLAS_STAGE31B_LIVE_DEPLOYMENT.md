# Stage 31B live deployment and Depth-only test (21 Oct 2026, 15:07–15:13 IST)

Owner approval (15:07 IST): install Stage 31B from commit `abf375b`, then ONE guarded Depth-only test.

## Result

| Item | Status |
|---|---|
| **UI fix (stale summary) deployed** | **YES**, 15:07:45. Verified live: after Start the page showed "Checking before start", not the previous session. |
| **Guard update (≥1 s window, ≤2 s fail-closed) deployed** | **YES**, 15:07:45, no restart. Verified live: all 59 guard samples used 1.0 s windows. |
| **Sustained real Depth viewing verified** | **YES (uncalibrated).** One uninterrupted 60-second Depth-only session: 607 real frames on the Dashboard, click-to-measure worked, no guard trip, and the session ended normally. |

Depth values are **uncalibrated axial Z**. Accuracy is not verified, and XYZ, point cloud and registration stayed disabled.

## Installation

**Pre-install checks** (`evidence/stage31b_live/pre_install.txt`):
- Live hashes `atlas_vision3d_runtime.py a09fc019…` and `vision3d.js f2939d19…`.
- Astra off, E-STOP latched, manual only, `cmd_vel` zero, mission READY, recorder (stage20) inactive.
- Sensors fresh: encoders and drive_pid at 10 Hz, IMU and LiDAR fresh, Pi camera JPEG 200.
- CPU 64.8%, RAM 67%, 61 °C.

**Package and install:**
- Package `stage31b_pkg.tgz`, sha256 `b080b23233fa2e3f3feb1198b8e32a3540055cb00de9d0ac4ff07c82aee4d9f2`, matching `abf375b`.
- Unpacked at `~/project-atlas-migration/stage31b-deploy-20261021/`.
- Installed `scripts/atlas_vision3d_runtime.py` `077edc293a163c6b` and `web/v2/vision3d.js` `05b83020d67f2db4`.
- `tools/vision3d/stationary_gate.py` (75/80/70 and freshness checks) is unchanged at `0c5ec244…`.
- **No service restarted.** `rover-status-web` stayed PID 117520, NRestarts 0.

**Post-install checks:**
- The page served the new JS with no browser errors and no POST request.
- The 12 candidate guard tests passed against the installed file on the Jetson (Python 3.10, nice 15, run in `/tmp` and removed).

**Rollback ready:**
- Backup `~/project_atlas/.pre_stage31b_20261021_150745`; its `SHA256SUMS` is OK.
- Command:
  ```
  cd ~/project_atlas && OWNER_APPROVED=yes ~/project-atlas-migration/stage31b-deploy-20261021/pkg/project_atlas/tools/deploy/stage31b/stage31b.sh rollback
  ```
  It restores both files and restarts nothing.
- The same script rolled back byte-identically in the Jetson rehearsal. A live rollback was not needed.

## The one Depth-only test (15:09)

**Preparation:**
- Fresh preflight passed (`pre_test.txt`).
- A 12-second settling check read 61.8–66.8%.
- The persistent recorder (`systemd-run --user`, one `/proc` line per second, 220 s) started 40 s before Start.
- The browser reached the dashboard directly on the LAN. **No SSH, ROS CLI or process inspection ran while streaming.**

**Session:** Start was clicked **once** (Depth only). The session ran its full 60 s and ended normally ("60-second session complete"). No retry.

**From the page** (`depth_test3.json`):

| Measure | Value |
|---|---|
| UI after Start | "Checking before start" at 2 s and 4 s (stale-summary fix confirmed); "Camera streaming" from 6 s |
| First frame on the Dashboard | about 10 s after click (driver launched at 3.6 s) |
| Frames received by the Dashboard | **607** (160×120 16UC1), largest gap 0.38 s |
| Dashboard receive rate | 9.3–14.6 fps (≈ 11 fps average); the driver runs at 30 fps and the viewer keeps the newest frame |
| Frame age when displayed | 0.01–0.33 s |
| Click-to-measure | 21 s and 42 s: **2.721 m at pixel (80, 53), uncalibrated** |
| Guard samples (59, each a 1.0 s window) | 63.7–71.1% CPU; RAM 68–69%; 60.7–61.0 °C; all under 75 / 80 / 70 |
| End | driver stopped safely; camera off |

## CPU trace (`evidence/stage31b_live/s31c_trace.jsonl`, 1-second samples)

| Window | Mean | Min | Max |
|---|---|---|---|
| Before Start (44 s) | 64.9% | 61.4% | 68.5% |
| **During session (58 s)** | **66.8%** | 62.2% | **70.0%** |
| After (107 s) | 64.6% | 61.8% | 69.0% |

**Where the extra ~2 points came from:**
- **Astra driver:** 31% of one core in its start-up second, then a steady **3–4% of one core**.
- **Dashboard (`rover-status-web`):** +8–17% of one core while streaming, from receiving and deserializing depth messages in the private domain and producing PNG previews for the page. This is the largest streaming cost.
- **Vision Lab worker:** +24% of one core for one second while hashing the 458 runtime files before admission.
- **The network-fallback `curl` probe:** fired once during admission (+11% of a core) without harm.

No 1-second sample anywhere in the 220 s exceeded 70.03%.

**Why this run passed when test 2 did not:**
- In test 2, a 0.68 s guard window landed on the start-up burst plus kernel memory reclaim plus a `curl` probe, and read 76.0%.
- Here every guard window was a full second. The start-up second read 66.5% on the recorder, and the highest guard sample was 71.1%.
- The 75% limit and every other check were unchanged.

## After the test (`post_test.txt`)

- E-STOP latched, `cmd_vel` zero, mission READY; no Astra driver or worker running; no domain-77 user; recorder inactive.
- Protected identities unchanged: atlas-camera 1982/0, base 3534/1, mux 1975/0, EKF 3260/0, localization 5713/1, LiDAR 5523/5, rover-status-web 117520/0.
- Pi camera JPEG 200; encoders and drive_pid at 10 Hz; IMU and LiDAR fresh.
- CPU 67.5%, RAM 69%, 60 °C.
- Nothing recorded; no point cloud.

**Odometry note:** odometry x read 0.0235 m both before and after (it was 0.0009 at 14:43), with zero speed throughout this session. The change predates this test and is not from it.

## Screenshots (`evidence/stage31b_live/`)

`c_depth_10s.webp`, `c_depth_30s.webp` (live depth with the 2.721 m measurement), `c_depth_52s.webp`, `c_depth_end.webp` (session finished, driver stopped safely), and `c_depth_0_before.webp`.

## Remaining limits

- Calibration is still invalid, so distances are not accuracy-verified and 3D geometry stays disabled.
- The Dashboard shows about 11 fps although the camera produces 30.
- One session does not establish reliability. Each new start is still guarded and may be stopped.
