# ATLAS core localization fix: deployment plan (2026-10-15)

Branch `agent/sync-developer-20261011`. It continues `ATLAS_SINGLE_DEVELOPER_RECOVERY_HANDOFF.md`
and repeats nothing from it.

**Nothing below is deployed.** Every live step needs the owner approval listed in §11.

## 1. Driver stop anchor (stage 21): safety assessment

**`3eff519` was too weak and is superseded by `a2ad1c9` / `46424ff`.**
- **Old rule:** trust zero velocity after a single unchanged tick.
- **Why that fails:** the driver samples the *last* encoder packet on a timer, and the board
  reports counts in bursts. In the exact `/atlas/encoder_update` snapshots of the 9 Oct drives,
  LiDAR-ICP shows motion while all four counts stay unchanged for up to **0.79 s**.
- **Tool:** `tools/diagnostics/encoder_still_runs.py`.

**New rule (`WheelStillnessDetector`).** Zero-velocity twist keeps its normal covariance only
after **1.0 s** of continuous:
- a fresh packet stream;
- all applied motor outputs exactly 0;
- all four raw distances identical;
- at least one packet newer than the start of the interval.

Any change, stale stream or non-zero output resets it.

| Owner audit item | Result |
|---|---|
| 1. Fresh, valid packets only | Stale stream → reset, never qualifies (test) |
| 2. Unchanged counts vs frozen communication | Re-reading one packet (stamp not advancing) never qualifies (test) |
| 3. Reversals and slow motion | A 0.7 s reversal pause and 0.8 s count bursts never qualify (tests). The 1.0 s hold exceeds the 0.79 s worst case recorded while moving |
| 4. 3-of-4 policy | Unchanged. `EncoderDeltaEstimator` and `fewer_than_3=stop` are untouched |
| 5. Safety status / `odom_source` | Label unchanged (test asserts `feedback_unavailable`); `atlas_safety_status.py` unaffected |
| 6. Pose covariance | Still ×1000 / ×4 |
| 7. Velocity covariance | Normal 0.10 is the same value already used whenever 4/4 encoders agree on zero |
| 8. No independent motion → no false confidence | Driven motors with frozen counts never qualify (test). **Residual:** a counter freezing while ATLAS is pushed by hand, motors off, looks like rest. Only the covariance is affected; AMCL scans still correct |
| 9. Manual control | No motor, steering, mux or command path changed. The diff is odometry covariance only |

**Regression:**
- 46/46 encoder and odometry tests.
- All 138 repository test modules have **identical pass/fail status** to `0107b5f`: 103 pass; the
  same 35 fail on missing hardware/ROS/bag dependencies in the cloud workspace.
- Pre-existing, unrelated failures noted for the owner:
  - `test_status_web_estop_reset::test_wrong_pin_then_lockout_even_for_the_right_pin` (409 ≠ 403);
  - `test_atlas_safety_status_camera_heartbeat`.

**Calibration-sign test (`875cb1c`).**
- The test still pinned the **original motors'** signs and CPRs (`5f3e309`). The same day,
  `b2f7668` / `338242b` replaced them for the new motors.
- The current signs are independently supported: raw M1, M2 and M4 read positive against
  LiDAR-ICP forward motion.
- The test now pins the current values. **No YAML or polarity change.** M3's sign is unverified
  because it reads about 0.

**Packaging.**
- `make_package.py stage21-driver-stop-anchor 1de2962 46424ff`.
- The live `yahboom_base.py` is the **`0872973` version**. Stage 17 commits `46ff15f` / `1de2962`
  (steering measurement, on HOLD) were never deployed, so the package ships **only this
  change's diff**, applied to the live file.

| File | Live now | After install |
|---|---|---|
| `scripts/yahboom_base.py` | `0464a3a10d07…` | `c551be0053a4…` (patch onto live, offset −10) |
| `scripts/atlas_encoder_selection.py` | `b52d2a408c74…` | `7d457c9f9293…` (MATCH) |

**Rehearsal** on a byte-identical copy of the live files:
- the installer's scope check passed;
- the snapshot/odometry tests pass against the patched live driver;
- `ROLLBACK.sh` restored both live hashes exactly.

## 2. Native Humble verification

**Environment:** Ubuntu 22.04 + ROS 2 Humble, built as a chroot in the cloud workspace.
- **Versions:** robot_localization **3.5.4** (the Jetson runs 3.5.4); rosbag2 0.15.17 (Jetson
  0.15.16).
- **PC WSL:** not used. It is not reachable from this session, and it was not needed.

**Same inputs as before:**
- the same 4 bags;
- unmodified `/yahboom/odom`, `/im10a/imu/bias_corrected_candidate` and `/tf_static`;
- bag-receipt `/clock`;
- a guard against duplicate EKFs (it caught and voided one transient run, which was re-run).

**Fidelity (native A against the recorded EKF, median per pair):**

| Measure | Range across the 4 drives |
|---|---|
| Lateral | 0.07–0.16 cm |
| Forward | 0.17–0.90 cm |
| Heading | 0.10–0.32° |

**Transfer: yes.**

| Drive | Heading drift per ~1.4 m chain, A, Humble (Jazzy) | B, Humble (Jazzy) |
|---|---|---|
| Outbound (3 chains) | 5.11° (4.82°) | 0.56° (0.51°) |
| Return (31 chains) | 7.39° (7.41°) | 2.26° (2.28°) |
| Hall → Dhruv (18 chains) | 23.58° (23.62°) | 3.48° (3.43°) |

## 3. Candidate B metrics (Humble) and limitations

90th percentile per pair unless marked. Drives in order: outbound / return / Hall→Dhruv / round
trip. "LOO" = the 5.5° LiDAR travel offset estimated from the *other* drives.

| Metric | A (production) | B |
|---|---|---|
| Heading error per pair (°) | 1.72 / 2.96 / 3.78 / 2.41 | 1.72 / 2.15 / 1.79 / 1.92 |
| Sideslip vs ICP (°), uncorrected | 9.0 / 15.0 / 16.1 / 25.9 | 14.0 / 12.7 / 13.1 / 11.7 |
| Sideslip vs ICP (°), LOO-corrected | 10.7 / 20.4 / 20.9 / 31.2 | **9.0 / 10.2 / 10.6 / 9.5** |
| Lateral error (cm), LOO-corrected | 1.86 / 3.95 / 4.69 / 3.84 | **1.65 / 2.53 / 2.38 / 1.81** |
| Real parked stops, max drift | 4.42 cm (outbound), 2.43 cm (round trip) | 1.55 cm, 1.76 cm |

**Synthetic encoder-consensus loss at the instant of stopping from 0.3 m/s (Humble):**

| Variant | Coast during a 20 s stop |
|---|---|
| A, unchanged driver | −0.11 m |
| A + stage 21 | −0.11 m |
| B, unchanged driver | **+1.61 m** |
| B + stage 21 (1 s hold) | **+0.135 m past the wheel stop, then held** |

**Limitations:**
- Forward error is about 1 cm per pair worse with B (2–3%).
- B's lateral benefit needs the 5.5° offset resolved; uncorrected, B is mixed.
- ICP is a proxy, not ground truth.
- **No AMCL claim:** there is no faithful AMCL replay, and the five parked jumps remain
  unexplained.
- **B depends on stage 21** and must not be deployed without it.

**Prepared:** `config/atlas_ekf_candidate_b.yaml`. It differs from `atlas_ekf.yaml` only in
`odom0_config` X/Y, plus a header. Production `atlas_ekf.yaml` (`69dd4479…`) is unchanged.

## 4. Foxglove bridge hardening

**Findings (read-only):**
- `atlas-foxglove.service` runs `ros2 launch … address:=0.0.0.0` with the launch defaults:
  capabilities `clientPublish, parameters, parametersSubscribe, services, connectionGraph,
  assets`, and every whitelist `.*`.
- `atlas-foxglove-nav-goal` relays any `/goal_pose` to Nav2 `NavigateToPose`.
- **No client was connected,** and no successful sessions are logged this week. Only two failed
  handshakes (08:54, the recorder preflight).
- Dashboard V2 and camera viewing do not use port 8765.

**Isolated test** (Humble, bridge 3.6.0; the Jetson has 3.4.2), with
`tools/diagnostics/foxglove_bridge_privilege_test.py`:

| A remote client can… | Production defaults | Proposed `config/foxglove_bridge_readonly.yaml` |
|---|---|---|
| Read topics | all | all (unchanged) |
| Advertise `/goal_pose` (ROS publisher created) | **yes** | no |
| Read any node's parameters | **yes** | no |
| Write any node's parameters (value changed) | **yes** | no |
| Services exposed | **13**, including `set_parameters` | 0 |

**Subprotocol finding:** bridge 3.x accepts only the `foxglove.sdk.v1` WebSocket subprotocol and
rejects `foxglove.websocket.v1` with HTTP 400. That explains the 08:54 handshake failures. Any PC
client must offer `foxglove.sdk.v1`.

**Proposed change** (restarts only `atlas-foxglove`):
1. Back up the unit file.
2. Set `ExecStart=… /opt/ros/humble/lib/foxglove_bridge/foxglove_bridge --ros-args --params-file
   /home/jetson/project_atlas/config/foxglove_bridge_readonly.yaml`.
3. Run `daemon-reload` and restart.

**Access:** binds the Tailscale address `100.87.208.71` only. WireGuard and tailnet membership
provide encryption and access control; bridge TLS is not added. If Tailscale is down at boot, the
bridge fails and `Restart=on-failure` retries every 3 s until it is up. SSH and the dashboard are
unaffected.

**Verify:**
- `ss -ltn` shows `100.87.208.71:8765` only;
- a capabilities-only client handshake (serverInfo) shows `['connectionGraph']`. Never publish
  against live to "test".

**Rollback:** restore the unit file, `daemon-reload`, restart `atlas-foxglove`.

**Optional, separate decision:** disable `atlas-foxglove-nav-goal`. It becomes unreachable once
client publishing is off.

## 5. Physical measurement protocol (one supervised session, about 20 min)

**Preconditions:**
- E-STOP latched between every move; manual-only on; no autonomy.
- A clear 3 m floor; tape line and marks at 0, 1 and 2 m; a measuring tape.
- Recorder: the installed 6b `atlas_motion_recorder.py --record`. It captures scans, both
  odometries, the four raw counts, corrected IM10A, AMCL, TF, all `cmd_vel` sources and steering
  commands.
- **Optional (separate approval):** upgrade the recorder to the repository version for
  `--profile steering-validation`, which adds raw IM10A, `/atlas/encoder_update` and particles.
- Each test starts and ends with 10 s stationary.

**Test A, straight line (×2, then ×2 in reverse).**
- Centre ATLAS on the line, steering centred, and drive 2 m slowly (about 0.15 m/s).
- Measure the end lateral offset from the line, the end heading against the line, and the
  distance.
- **Interpretation, an indicator not proof:**
  - offset of about 19 cm with ICP heading constant → steering crab;
  - offset of about 0 while LiDAR still shows a 5.5° travel angle → LiDAR mounting yaw;
  - anything else → record it and do not correct.

**Test B, distance.** 2 m forward and back at about 0.15 m/s and about 0.40 m/s, two runs each.
Compare tape vs raw counts per wheel vs ICP. A constant ratio indicates CPR; a speed-dependent
one indicates slip.

**Test C, turns.** One gentle left and one gentle right arc of about 90°. Compare wheel yaw,
IM10A, ICP, EKF and AMCL.

**Repeat:** run the identical protocol after each deployment step (§6) for before/after.

## 6. Deployment scope and order (never two at once)

| Step | Change | Restart |
|---|---|---|
| 1 | Stage 21 driver stop anchor | `rover-base-telemetry` |
| 2 | Parked verification (§7) | — |
| 3 | Foxglove hardening (independent of localization; any time after approval) | `atlas-foxglove` |
| 4 | Baseline session (§5) with production EKF A | — |
| 5 | Resolve the 5.5° offset from Test A. Any TF or trim change is a separate approval | — |
| 6 | Candidate B: copy `atlas_ekf_candidate_b.yaml` over `atlas_ekf.yaml` (backup first) | `atlas-ekf` |
| 7 | Repeat §5 and compare | — |
| 8 | Encoder distance correction, from the Test B measurements only | — |
| 9 | AMCL and map reassessment, then supervised navigation | — |

## 7. Acceptance criteria

**Stage 21, parked and latched:**
- `/yahboom/odom` twist cov[0] reads 0.10 with all four fresh.
- After induced or observed consensus loss while parked, it becomes 0.10 again after ≥1 s.
- `odom_source` labels, the `encoder_health` policy string, and the mux / E-STOP / EKF PIDs are
  unchanged.
- `/odom` drift ≤ 1 cm over 10 min parked.
- No new errors in `rover-base-telemetry`.

**Candidate B,** same protocol, against step 4:
- median heading drift against ICP per ~1.4 m ≤ 50% of baseline;
- forward distance error no more than 5% worse;
- after each stop, AMCL moves < 0.10 m within 30 s and makes no jump > 0.5 m;
- `/odom` TF continuous: no backwards stamps, no jumps.

Failing any criterion means roll back.

## 8. Rollback

| Change | Rollback |
|---|---|
| Stage 21 | `bash ~/project_atlas/data/backups/<stamp>-stage21-driver-stop-anchor/ROLLBACK.sh`, then restart `rover-base-telemetry` (latched). Rehearsed: restores live hashes `0464a3a1…` / `b52d2a40…` |
| Bridge | Restore the backed-up unit file, `daemon-reload`, restart `atlas-foxglove` |
| Candidate B | Restore the backed-up `atlas_ekf.yaml` (`69dd4479…`), restart `atlas-ekf` |

## 9. Remaining blockers

1. **5.5° travel offset:** needs Test A.
2. **Encoder distance about 0.65×:** needs Test B.
3. **Five parked AMCL jumps:** no faithful replay.
4. **Startup ambiguity:** this boot (11:17:31) refused, correctly, with "1.00 vs 1.00". 7 boots are
   now in the Stage 16 history, not yet analysed.
5. **Corridor/Hall map aliasing.**
6. **Recorder admission CPU rule:** the Stage 20 recorder only; the 6b recorder is separate.

ATLAS restarted twice today, at about 11:02 and 11:17. Neither restart came from this work.

## 10. Commits

| Commit | Content |
|---|---|
| `3636ab6` | Offline A/B and heading tools |
| `3eff519` | First stop anchor (superseded) |
| `a2ad1c9` | 1 s stillness detector |
| `875cb1c` | Calibration test pinned to current calibration |
| `46424ff` | Comment fix and stage 21 readme |
| (this commit) | Candidate B config, bridge config and test, Humble-compatible tools, this plan |

## 11. Owner approval requests (each separate)

1. **Install stage 21** (driver stop anchor) and restart `rover-base-telemetry` while latched.
   Then the §7 parked checks.
2. **Foxglove hardening** (§4): restart `atlas-foxglove`. Optionally, also disable
   `atlas-foxglove-nav-goal`.
3. **The §5 supervised session**, with the 6b recorder active. Optionally, the recorder upgrade for
   raw IM10A and particles.
4. **Candidate B**, only after 1–3 and only if §7 is met.
