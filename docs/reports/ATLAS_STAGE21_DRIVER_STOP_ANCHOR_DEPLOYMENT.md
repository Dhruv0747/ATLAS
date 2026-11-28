# Stage 21: driver stop anchor deployment, 2026-10-15

**Status: BUILT → TESTED OFFLINE → DEPLOYED (12:53:45 IST) → PARKED VERIFIED → MOVING VALIDATION
PENDING.**

The new zero-velocity branch was **NOT LIVE EXERCISED**: it applies only when fewer than 3
encoders agree, and that never happened while parked.

Approved scope: Stage 21 only, with a restart of `rover-base-telemetry` only. Nothing else was
changed or restarted: no Candidate B, Foxglove, calibration, map, steering or autonomy change.

## 1. Preflight (12:51–12:53, read-only)

**GitHub:** HEAD `242270e`, matching the remote. No newer commits; working tree clean.

**Safety:** `stop_latched: true`, `manual_only: true`, `commission_armed: false`. `/cmd_vel` all
zero. No Nav2 goal status: the `navigate_to_pose` status topic showed no goals.

**Sensors:**
- encoder packets fresh (age 10–38 ms), accepted channels [1, 2, 3, 4], no faults, source
  `stopped`, raw counts [0, 0, 0, 0];
- steering commanded at 90/90, equal to the calibrated centres, so the restart could not move the
  servos;
- `/scan` 6.9 Hz, IM10A 9.8 Hz, `/yahboom/odom` 9.3 Hz (normal covariance), `/odom` 10 Hz.

**Resources:** CPU 63–68% (five 1 s samples), RAM 4.9/7.6 GB, all thermal zones 59–60 °C,
369 GB free.

**Live hashes, full, matching the manifest baseline:**

| File | sha256 |
|---|---|
| `yahboom_base.py` | `0464a3a10d070b0a4df83ca3b068c37f5d1a54863a6986ebd818b5100a8fa3b4` |
| `atlas_encoder_selection.py` | `b52d2a408c7421f2a0862ad201c8672a2baebd337d1c91f761ec389cecf3f7b2` |

**Service identities:**

| Service | PID |
|---|---|
| `rover-base-telemetry` | 3162 |
| mux | 1788 |
| EKF | 2802 |
| localization | 4521 |
| web | 1956 |
| IM10A | 1802 |
| LiDAR | 1790 |
| Foxglove | 1947 |

The Jetson had been up since 11:17:31; that restart was not part of this work.

## 2. Source and package

**Source:** `a2ad1c9`, the 1.0 s `WheelStillnessDetector`, with the comment fix `46424ff`. Not
the superseded `3eff519`.

**Detector contract.** Zero-velocity twist keeps normal covariance only after 1.0 s of
continuous:
- a fresh stream;
- all applied motor outputs exactly zero;
- four identical raw distances;
- at least one packet newer than the interval start.

Any change, stale stream or non-zero output resets it.

**Unchanged:**
- 3-of-4 consensus and `fewer_than_3=stop`;
- `odom_source` labels;
- pose covariance;
- calibration and polarity;
- steering.

**Package:** `stage21-driver-stop-anchor`, built by `make_package.py` with base `1de2962` and head
`46424ff`. Archive sha256 `8e9da4e755755aa4c6aa76fa9605ecf356a0f9b6ac157557778e612296852292`,
identical in the container, on the PC and on the Jetson.
- Patch-only onto the **live** files.
- Stage 17 commits `46ff15f` / `1de2962` (on HOLD) are **not** shipped.

## 3. Hashes

| File | Before | After (live, verified) |
|---|---|---|
| `scripts/yahboom_base.py` | `0464a3a10d07…a8fa3b4` | `c551be0053a43755578fc8e60b534338818a690411322c63a293376e6e560141` |
| `scripts/atlas_encoder_selection.py` | `b52d2a408c74…cf3f7b2` | `7d457c9f929387ba8ef9ad1837cdfee3ab620b2548206b30d488a52bb3a41375` (installer MATCH) |

## 4. Regressions

**Container, at HEAD:**
- encoder, odometry and calibration suites OK;
- driver, mux and E-STOP safety suites OK (`test_yahboom_diagnostic_cadence`,
  `test_encoder_packet_timing`, `test_yahboom_lifted_owner`, `test_atlas_cmd_vel_mux_stop_hold`,
  `test_atlas_cmd_vel_mux_mapping_limit`, `test_status_web_estop_safety`);
- all 138 modules have pass/fail status identical to `0107b5f`;
- known pre-existing failures, unchanged: `test_status_web_estop_reset` (wrong-PIN lockout,
  409 ≠ 403) and `test_atlas_safety_status_camera_heartbeat`.

**Jetson, on the patched scratch copy:** 42/42 repository encoder and odometry tests pass with the
Jetson's own Python, and both files compile.

## 5. Rehearsals

| Where | Result |
|---|---|
| Container, byte-identical copies of the live files | Install: scope check passed, expected hashes. Rollback restored both original hashes |
| Jetson, `/tmp` copy of the live `scripts/` | Install: scope check passed (only the 2 files), same hashes. Rollback restored `0464a3a1…` / `b52d2a40…` exactly |

Scratch copies were removed afterwards.

## 6–7. Deployment and restart

- **12:53:45:** live install (patch dry-run, backup, apply, byte-compile, scope check). Installed
  hashes as in §3.
- **12:53:58:** `systemctl --user restart rover-base-telemetry.service`, the only restart.
- **New PID:** 45674, active/running, NRestarts 0.
- **Startup log:**
  - "Resuming same-boot odometry after driver restart: x=0.000 y=0.000 yaw=0.0deg";
  - "encoder packet stream recovered; requalifying before use".
- **Errors:** zero error or traceback lines since the restart (checked at 13:05).

## 8–9. Parked observation, 600 s from 12:54:45

Read-only subscriber at nice 15, no publishers. Evidence:
`~/project_atlas/data/diagnostics/stage21_20261015/stage21_parked_600s.json` (sha256
`2edbaa75…`).

| Item | Result |
|---|---|
| Encoder packets | 5,986 snapshots, all fresh, max age 55 ms, counts constant, accepted [1, 2, 3, 4], no faults, source `stopped` |
| Motor output / commands | `/yahboom/odom` vx = 0, wz = 0. `/cmd_vel`: 2,788 messages, 0 non-zero. Steering command 90/90 throughout |
| `/yahboom/odom` covariance | 9.98 Hz; pose (0.05, 0.10) and twist (0.10, 0.20) only. **No inflated-pose samples occurred**, so the new branch was not exercised. Pose covariance was never reduced |
| Safety labels / policy | `odom_source` `stopped`; policy latched, manual-only, disarmed throughout |
| `/odom` (EKF, production config A) | 10.0 Hz; **drift 0.0 cm, 0.0° over 600 s**; max step 0.0 cm; 0 backwards stamps |
| EKF continuity across the restart | Odometry resumed at the saved pose (0, 0, 0). `/odom` started at (0.0, 0.0, 0.0001°), against (0.0, 0.0, 0.007°) before |
| Receive gap | One 0.82 s gap between `/odom` receptions in the nice-15 observer. Not attributed; there is no matched pre-deployment measurement of that metric |

## 10. Resources (13:05)

- **System:** load average 6.73 / 9.86 / 11.51 (1/5/15 min); RAM 4.7/7.6 GB; thermal zones
  59–60 °C.
- **`rover-base-telemetry`:** 29.6% of one core, averaged over its 11.5 min life including
  startup; RSS 79 MB. No pre-deployment per-process figure was captured for comparison.

## 11. Protected services

After the restart:

| Service | PID |
|---|---|
| mux | 1788 |
| EKF | 2802 |
| localization | 4521 |
| web | 1956 |
| IM10A | 1802 |
| LiDAR | 1790 |
| Foxglove | 1947 |

All unchanged. None was restarted.

## 12. Backup and rollback

**Backup:** `~/project_atlas/data/backups/2026-10-15-125345-601344477-stage21-driver-stop-anchor/`.
`orig/` holds the exact originals (`0464a3a1…`, `b52d2a40…`).

**Rollback** (rover latched):
1. `bash <backup>/ROLLBACK.sh`
2. `systemctl --user restart rover-base-telemetry.service`
3. Check both original hashes.

The rollback was rehearsed on the Jetson, not run live.

## 13. Unverified conditions

- **NOT LIVE EXERCISED:**
  - the fewer-than-3 branch and the 1 s hold;
  - reset on stale packets or non-zero motor output.

  These are covered only by offline tests (46 in the container, 42 on the Jetson). No fault was
  induced.
- **MOVING VALIDATION PENDING:** behaviour during driving, reversals and stops after motion.
- Candidate B, and any localization improvement, are not deployed and not claimed.
- The 0.82 s observer receive gap is unexplained (§8–9).

## 14. Commit

This report, the blockers file, the registry and CHANGELOG are in the commit after `242270e` on
`agent/sync-developer-20261011`.
