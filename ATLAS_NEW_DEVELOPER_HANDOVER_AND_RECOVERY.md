# ATLAS takeover, Astra resource-block root cause and recovery (Stage 31)

Date 2026-10-21 (Asia/Calcutta). Branch `agent/sync-developer-20261011`, continuing from `1cbc0001a9b9f08286f587f7cd5da4af02c3a3f9`.
Companion document for the interface work: [`ATLAS_DASHBOARD_V2_UI_REDESIGN.md`](ATLAS_DASHBOARD_V2_UI_REDESIGN.md).

## Status at a glance

| Item | Status |
|---|---|
| Takeover audit (GitHub vs Jetson, safety, rollback baseline) | INVESTIGATED, JETSON VERIFIED |
| Astra CPU contention root cause | INVESTIGATED, JETSON VERIFIED (camera-free measurement) |
| Private ROS domain fix for the Astra viewer | FIX IMPLEMENTED, OFFLINE TESTED, JETSON VERIFIED (mechanism and package rehearsal), **not DEPLOYED** |
| Astra live depth/RGB viewing | **BLOCKED**: needs your approval to install and one guarded camera start |
| Dashboard Home + Vision Lab redesign | FIX IMPLEMENTED, OFFLINE TESTED, JETSON VERIFIED (package rehearsal), **not DEPLOYED** |

Nothing in production was changed in this stage. No service was restarted, the camera was never opened, and ATLAS stayed E-STOP latched and manual-only throughout.

## 1. GitHub and Jetson baseline

- The local branch was fast-forwarded to `origin/agent/sync-developer-20261011` = `1cbc000` (verified by `git fetch`).
- I hashed 39 deployed Dashboard and Vision Lab files on the Jetson (`~/project_atlas`).
  - 37 are byte-identical to `1cbc000`.
  - `scripts/atlas_status_web.py` differs by design: the live file is a patched baseline that excludes the repository-only steering hooks (documented in Stage 29).
  - `web/v2/index.html` differs only by one `title=` attribute on the 3D Vision Lab link.
  - The live file hashes are the baseline the Stage 31 package checks: `index.html f53d6812…`, `vision3d.html 2d5b6bf8…`, `vision3d.js d27d6907…`, `vision3d.css f422f69e…`, `atlas_vision3d_runtime.py 6a0e9c1c…`, `atlas_vision3d_web.py b51a1870…`.
- Safety state, read through HTTP only so no ROS participant was created:
  - E-STOP latched (reason "REMOTE STOP: joystick unavailable").
  - `manual_only` true, commissioning disarmed, source STOPPED.
  - `/cmd_vel` zero, mission READY.
  - No Astra driver or Vision Lab worker process running.
- Existing backups and rollback packages were not touched: Stage 26/27, Stage 29 `vision3d-deploy-20261021-124126`, and Stage 30 `stage30-approved-deploy-20261021-133843`.

## 2. Existing features preserved

- No production file, service, threshold, map, calibration, steering, Nav2/EKF/AMCL or STM32 setting was changed.
- The redesigned Home keeps every element, control, request path and repeat rate of the old Home (see the UI report). The old Home is preserved byte-for-byte as `/v2/classic.html`.

## 3. Astra CPU contention: what is actually happening

All measurements below are passive reads of `/proc`. The profilers are in `tools/vision3d/stage31_sysprof.py` and `stage31_joinprof.py`. Each one costs a single short Python process.

### 3.1 The parked baseline is about 65%, spread over about 70 processes

20-second window, Astra off:

| Measure | Value |
|---|---|
| Busy (whole machine) | 65.4% |
| user / **nice** / system / irq+softirq | 31.2 / **20.1** / 10.8 / 3.3 |
| Largest single process (`rover-status-web`, nice 10) | 45% of one core = 7.5 points |
| Pi camera_node / yahboom_base / voice companion (nice 10) | 33% / 27% / 25% of one core |
| Command mux / sensor recovery / safety status | 16% / 16% / 13% of one core |

No single process explains the load: the top 10 together are about 37 points. A fifth of the machine (about 20 points) is nice 10/15 background work, mainly the AI companion, voice, annotator and agents.

### 3.2 The spike that trips the guard is DDS discovery fan-out, not the camera

I ran one read-only `ros2 topic list --no-daemon`, the same command earlier preflights used routinely, while sampling every second:

| Join | Whole-machine CPU per second | Other processes affected |
|---|---|---|
| None (control) | 61.8 – 66.6% | — |
| **Production domain 0** | 64 → **75.1 → 92.0 → 92.1** → 65% | **34 processes**, each +3–5% of a core for about 3 s (≈ +20 points combined, plus the joiner) |
| **Private domain 77** | 65 → 76.6 (joiner's own Python start, 1 s) → 64% | **none** above noise |

Every new ROS participant in the production domain makes about 34 existing nodes (mostly Python rclpy) process its discovery traffic for about 3 seconds. That alone pushes the 65% baseline past 75%.

This explains three observations:
- Stage 30's camera-free participant tripped the guard at 81.7%.
- Every real Astra start was blocked: 77.9%, 75.9%, 83.2% and 80.8%.
- The independent observer saw 89–100%. The observer's own ROS CLI calls were themselves participant joins.

### 3.3 Fix implemented (smallest change that removes the mechanism)

- `scripts/atlas_vision3d_runtime.py`:
  - The Astra driver is launched with `ROS_DOMAIN_ID=77`, a private domain no production node uses.
  - Before launch, the worker refuses if any process already declares that domain (read-only `/proc` scan).
  - Thresholds, lease, 60-second limit and guard logic are unchanged.
- `scripts/atlas_vision3d_web.py`:
  - The viewer receives frames with its existing `RosTransport` in domain 77, instead of through the production Foxglove bridge. The bridge path required the driver to join domain 0.
  - `BridgeTransport` is kept for rollback.
  - Also fixed: `rgb_info` is now subscribed as `CameraInfo` instead of `Image`.
  - New read-only `/api/vision3d/summary` route for the Home card. It never touches the viewer lease.

### 3.4 Jetson verification (camera-free)

The real modified receiver code ran on the Jetson in domain 77 against a synthetic 160×120 16UC1 publisher at 30 Hz for 12 s:
- **300 frames received at 30.01 Hz**, first frame at 2.35 s.
- Whole-machine CPU stayed 63.1–67.9%. The only higher sample was a single 74.5%, when the probe's own Python interpreter started; in production the receiver runs inside the already-running dashboard, so that start-up cost does not occur.
- No production process rose more than about 4% of a core.

## 4. Before / after numbers

| | Before (Stage 30, production domain) | After (private domain, measured or projected) |
|---|---|---|
| Discovery fan-out cost | +20–27 points for about 3 s (measured) | 0 (measured, camera-free) |
| Guard sample at start | 75.9 – 83.2% (four real attempts) | **projected ≈ 73%**: 65% baseline + Astra start-up 43.5% of one core (7.3 points, Stage 30) + receiver ≤ 1 point |
| Frames delivered | 0 | not yet measured: needs one approved camera start |

**Stress test of my own claim:** ~73% against a 75% limit leaves about 2 points of margin, while the parked baseline itself wanders between 62% and 67%. The fix removes the dominant spike, but it does **not** guarantee a pass on every attempt. If the guarded start still trips, the remaining lever is the baseline itself. Options for your decision are in section 13, and none is implemented.

## 5. Astra live-viewing status

**BLOCKED.** No real depth or RGB frame has reached the Dashboard; the camera was not opened in this stage.

Calibration remains invalid (factory intrinsics are NaN). Point cloud, XYZ and RGB-depth registration stay hard-disabled. The Vision Lab shows uncalibrated axial Z only.

## 6–8. Dashboard redesign, sensor presentation, desktop and mobile tests

See [`ATLAS_DASHBOARD_V2_UI_REDESIGN.md`](ATLAS_DASHBOARD_V2_UI_REDESIGN.md).

## 9. Safety and regression results

- Full repository suite: **979 passed, 5 skipped, 1 failed**. The one failure, `test_atlas_safety_status_camera_heartbeat`, is pre-existing and fails identically on `1cbc000`.
- New tests:
  - `tests/test_vision3d_stage31_domain.py` (10)
  - `tests/test_stage31_ui.py` (17)
  - `tests/test_stage31_package.py` (4)
- Three older stage tests compared the working Home against git `HEAD` line by line. They now skip when the Stage 31 layout is present; the invariants they protected are re-checked in `test_stage31_ui.py`.
- The Stage 27 package test now uses its own `4159f07` sources.
- Stage 27 `apply.sh` gained a guard that refuses to install any Home other than its own.
- Drive pad, camera pan and E-STOP were exercised in a headless browser against the old and new Home: the request bodies, paths and repeat counts are identical (only the random press nonce differs).
- Unchanged:
  - Thresholds: 75% CPU / 80% RAM / 70 °C (`test_policy_thresholds_unchanged`).
  - E-STOP priority, command mux and encoder 3-of-4 policy.
  - Pi camera, Motor Test Lab and FlySky Test Lab routes.

## 10. Deployment readiness

Package `stage31_pkg.tgz`, sha256 `168f6a7cbf7250284fa3d189d73e12952b42f4a8ecb1bc234826c96ec62f1f1f`. Script `project_atlas/tools/deploy/stage31/stage31.sh`.

| Step | What it changes | Restart |
|---|---|---|
| `apply-ui` | `index.html`, `vision3d.{html,js,css}` replaced; `home.css`, `home-cards.js`, `classic.html` added | **none** (static files) |
| `apply-astra` | `atlas_vision3d_runtime.py`, `atlas_vision3d_web.py` | **`rover-status-web` only** |

Each step:
- requires `OWNER_APPROVED=yes`, the exact live baseline hashes, a latched E-STOP and no running Astra driver or viewer worker;
- writes a checksummed backup;
- installs atomically (temp file plus `mv`);
- records the six protected service identities before and after `apply-astra`.

**Rehearsed on the Jetson** against a private copy of the live files (`/tmp/s31reh`, `NO_RESTART`):
- apply succeeded and a second apply was refused;
- the new modules imported under Humble (`RosTransport` in domain 77);
- both rollbacks restored all files **byte-identical**.

Production was untouched, and E-STOP stayed latched.

## 11. Rollback

- `OWNER_APPROVED=yes tools/deploy/stage31/stage31.sh rollback-ui` restores the static files and removes the three new ones. No restart.
- `OWNER_APPROVED=yes tools/deploy/stage31/stage31.sh rollback-astra` restores the two Python files and restarts only `rover-status-web`. It refuses while an Astra driver is running.
- Backups are written to `~/project_atlas/.pre_stage31_{ui,astra}_<stamp>/` and verified against their `SHA256SUMS` before restore.
- Even without rollback, `/v2/classic.html` keeps the old Home available.

## 12. GitHub commits

Listed in the CHANGELOG entry for this stage and in the final message of this task.

## 13. Owner approvals needed (each separately)

1. **Install the UI** (`apply-ui`): static files, no restart.
2. **Install the Astra private-domain fix** (`apply-astra`): restarts `rover-status-web` only.
3. **One guarded Depth-only start** through `/v2/vision3d` after step 2. Thresholds stay unchanged and there is no retry on failure. Expected peak is about 73%; record frame count, FPS, freshness, CPU, RAM, temperature and Pi camera status.
4. Only if step 3 still trips: a **measured policy decision**, which I will not make myself. Options:
   - Option a: make the 75% guard count only normal-priority CPU, excluding about 20 points of nice-10/15 background work that the scheduler already deprioritizes.
   - Option b: a "viewing quiet mode" that pauses named nice-10 AI services, such as voice companion, annotator and agents, during a session.
   - Option c: require two consecutive samples over 75%.
5. Still open from earlier stages:
   - FlySky receiver input (Stage 27);
   - physical E-STOP tests;
   - Jetson password rotation and temporary key removal;
   - encoder crosstalk.

Not done, and outside this stage: driving, E-STOP release, firmware, calibration, map, Nav2/EKF/AMCL, threshold changes, recording, autonomy.
