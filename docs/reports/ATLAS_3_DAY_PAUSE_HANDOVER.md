# ATLAS — 3-day pause handover

**Paused:** Wednesday 21 October 2026, 19:25 IST, by the owner. No development, production changes or hardware tests during the break.

**Branch:** `agent/sync-developer-20261011` (never `main`). The commit SHA is recorded in the final message of the session that wrote this file, and `git log -1` on the branch shows it.

**Resume:** from the verified checkpoint below. Re-verify the state read-only before doing anything else.

## 1. Verified state at pause (19:22 IST, read-only checks)

| Item | State |
|---|---|
| Motion | Stationary; `cmd_vel` 0 / 0; motor_speed 0 |
| E-STOP | **Latched** (REMOTE STOP: joystick unavailable) |
| Control policy | manual-only; `commission_armed` false |
| Recording | OFF; no `ros2 bag` or recorder process |
| Astra camera | **OFF**: Vision Lab runtime OFF; no `astra_camera_node`, worker or cloud node |
| Leftover units | none (`s32*` units all finished) |
| Guards | CPU 75% (1-s window), RAM 80%, 70 °C; viewer lease 4 s — unchanged |
| ROS domain | Vision Lab private domain 77 — unchanged |
| Sensors | LiDAR, odom, IMU and encoders fresh (≤ 0.3 s); Pi Camera 200 |

## 2. Deployed production (Jetson `~/project_atlas`)

| File | SHA256 (16) | Since |
|---|---|---|
| `scripts/atlas_vision3d_runtime.py` | `fc807489b06699d7` | 21 Oct 18:02 (IR 640x480@30 GRAY8) |
| `config/vision3d_live.json` | `7f9e5ff655fe3163` | U2+P, 21 Oct 19:17 |
| `scripts/atlas_vision3d_geometry.py` | `6eb23c251dc78fb2` | U2+P |
| `scripts/atlas_vision3d_web.py` | `10bdc9db35ab8b85` | U2+P |
| `web/v2/vision3d.js` | `d23fe88bf07ccffc` | U2+P |
| `web/v2/vision3d_state.js` | `bedbeed1a16a1a2d` | U2+P |
| `web/v2/vision3d.html` | `d6ebc4bee73f341b` | U2+P |
| `web/v2/vision3d.css` | `69af9900d408bdbc` | U2+P |

`rover-status-web` MainPID is 253946 (restarted once by U2+P). The protected services were not restarted.

**What the deployment provides:**
- **Infrared:** live IR at 640x480, marked "Tested".
- **Depth:** live depth.
- **Session states:** truthful Vision Lab session states (U1).
- **Calibration gate:** the device serial is in the manifest, and the gate is still **NOT VALIDATED**.
- **Uncalibrated preview:** the **UNCALIBRATED — DIAGNOSTIC ONLY 3D preview**, a browser-only checkbox that is active only while Depth is live. It has been deployed but **not yet viewed live**.

**Still blocked:** the calibrated cloud (route returns 409), metric XYZ, `/astra/points`, navigation use, recording and motor movement.

## 3. Backups and rollback (all preserved)

**Backups on the Jetson, under `~/project_atlas/`:**
- `.pre_stage32_config_u2p_20261021_191658`: the seven files before U2+P, SHA256SUMS verified.
- `.pre_stage32_ui_20261021_183816`: the files before U1.
- `.pre_stage32_20261021_155609`: the earlier Stage 32 backup.

**Rollback U2+P** (restarts `rover-status-web` once; owner approval needed):

```
OWNER_APPROVED=yes bash ~/project-atlas-migration/stage32-u2p/pkg_v4/tools/deploy/stage32_ui/stage32_ui.sh rollback-config
```

**Packages on the Jetson** (`~/project-atlas-migration/`):
- `stage32-u2p/pkg_v4`: the deployed one;
- `stage32-ui-continuation/pkg` and `pkg_v3`;
- `stage32-takeover-ir-diag-rehearsal/pkg`;
- `stage32-ir-640-final/tools`.

**PC copies:** `Downloads\atlas_deploy\` (tarballs, viewer scripts, `u2p_evidence_20261021b\`).

## 4. Evidence and test results

**Evidence in the repository:**
- `evidence/stage32_u2p_deploy/`: `log.txt`, `trace.jsonl` (1 Hz CPU) and `post_checks.txt`.
  - The restart settled in 30.6 s.
  - The peak was 98.9% with the camera off, the known transient (ATLAS-WEB-RESTART-CPU-TRANSIENT-20261021).
  - Every post-check passed, and no rollback was needed.
- `evidence/stage32_preview/`: synthetic preview screenshots and the test script.
- Earlier Stage 32 evidence: `evidence/stage32_live`, `stage32_d1`, `stage32_d2`, `stage32_ir640`, `stage32_ir640_final` and `stage32_u1`.

**Offline tests:** `tests/test_vision3d*.py` + `test_stage31_ui.py` → **236 passed, 8 skipped**. Run them with `pytest -s`, because the guard tests need a real stdin.

**Live tests to date:**
- IR-only acceptance passed (29.7 fps, 640x480).
- **IR+Depth: not tested.**
- **Live 3D preview: not tested.**

**Full record:** `ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md` sections 21–29, plus `docs/audits/ATLAS_STAGE32_DEPLOYMENT_REGISTRY.json`, `ATLAS_ROOT_CAUSE_REGISTRY.json` and `ATLAS_CURRENT_BLOCKERS.md`.

## 5. Pending approvals (each separate; none carried over)

1. **One Depth-only 60-s live 3D preview session.**
   - The owner approved it at 19:16, but the pause arrived before Start, so it **must be re-confirmed**.
   - Tool: `project_atlas/tools/vision3d/stage32_preview_live.py`, dry-run verified. It runs from the PC VM (`LD_LIBRARY_PATH=/tmp/libx/ex/usr/lib/x86_64-linux-gnu`) with a 60-s heartbeat pre-check, one Start, no repeat on failure, and no API requests of its own.
   - It records point count, preview update rate, depth freshness, CPU/RAM/temperature, and orbit/zoom/pan/click; screenshots carry the canvas label.
2. **One IR+Depth 60-s session** (P1; also measures the IR-to-depth pixel offset). Prepared: `stage32_ir_acceptance.py` with `MODE=ir_depth`.
3. **A5 calibration captures,** after the owner supplies measurements:
   - the printed A4 board (`atlas_astra_checkerboard_9x6_25mm_A4.pdf`): both 100 mm bars, 9 squares on the long edge (≈ 225 mm) and 6 on the short edge (≈ 150 mm);
   - IR poses at about 0.40 / 0.60 / 0.85 m;
   - a ≥ 1 × 1 m flat depth target with its measured size and tape distances of about 1.0 / 1.5 / 2.0 m from the Astra front face.
4. **A6:** install the reviewed calibration file, then one Depth + 3D cloud session (first calibrated `/astra/points`).

## 6. Next steps on resume (priority order fixed by the owner)

- **P0:** a real interactive 3D point-cloud preview. Run the live check (approval 1). Then accurate calibration (A5, offline validation, owner review), then a calibrated XYZ PointCloud2 (A6).
- **P1:** IR + Depth integration (approval 2).
- **P2:** object detection + depth + radar human-detection fusion.
- **P3:** gesture recognition, person tracking and other AI features.

**First actions on resume:**
1. Read-only re-verification of section 1 and the section 2 hashes.
2. Pull the branch and confirm HEAD.
3. Ask the owner for approval 1.

## 7. Standing rules (unchanged)

- E-STOP latched, manual-only, commissioning disarmed, zero motor commands, recording OFF.
- Guards 75% / 80% / 70 °C with the 1-s CPU window; fail closed; 4-s lease, never faked, bypassed or extended.
- No intrusive SSH or ROS CLI during streaming; no retries without approval; no firmware or IR-emitter changes.
- Keep IR at 640x480 (never 320x240).
- No restarts or production deployment without separate approval.
- Never commit credentials, keys, `.env` files, models, raw bags or logs with secrets.
- Blur room imagery in committed screenshots.
- Do not change E-STOP, motor control, STM32, maps, EKF/AMCL, Nav2, Pi Camera, the Home layout or Test Labs.
