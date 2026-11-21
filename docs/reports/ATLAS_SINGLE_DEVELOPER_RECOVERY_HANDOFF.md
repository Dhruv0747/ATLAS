# ATLAS single-developer recovery handoff, 2026-10-15

Branch `agent/sync-developer-20261011`. Started from GitHub HEAD `0107b5f`: 40 new commits since the
11 Oct handoff, all fetched and read. The commit adding this file is the new baseline.

**Status words used here:**
- BUILT: committed.
- TESTED: automated tests pass.
- DEPLOYED: installed on the Jetson.
- PHYSICALLY VALIDATED: proven in supervised motion.

**Nothing in this file is DEPLOYED or PHYSICALLY VALIDATED.**

## 1. Baseline

**GitHub:** HEAD `0107b5f` before this work. Working tree clean; not merged to `main` (`a6f044d`).

**Jetson** (read-only audit, 10:33 IST, up 1 h 56 min):

| Check | State |
|---|---|
| E-STOP / mode | `stop_latched: true`, `manual_only: true`, `commission_armed: false` |
| Motor command | `/cmd_vel` silent for 6 s (the mux publishes only on change) |
| Recorders | Stage 20 recorder and motion recorder **inactive**, PID 0 |
| Sensor topics present | `/scan`, `/im10a/imu/{unvalidated,bias_corrected_candidate}`, `/atlas/encoder_update`, `/yahboom/odom`, `/odom`, `/amcl_pose`, `/particle_cloud`, `/lidar/odom` |
| Accepted map / EKF config | YAML `d957f0fe…`, PGM `4beb26d5…`, `atlas_ekf.yaml` `69dd4479…`: unchanged |
| Localization | Monitor `PARKED_SETTLING`. AMCL (−0.32, −1.10) is 0.6–0.8 m from the last startup verdict (0.275, −1.835). **Not navigation-valid** |
| Restarts this boot | `atlas-lidar` 8, `atlas-localization` 8. Recurring LiDAR start fault, ATLAS-015 |
| Resources | Load average 9.9 / 12.2 / 13.4 (1/5/15 min); RAM 5.1/7.6 GB; all thermal zones 59–60 °C |
| Network | Wi-Fi default (metric 50), cellular standby (600); PC `desktop-8sbj6cr` reachable over direct Tailscale |

**Stage 16 startup evidence works.** It has captured 6 boots:
- 2 refused correctly:
  - best fit 0.91–0.92 < 0.93;
  - ambiguous: 0.94 vs 0.91, 0.95 vs 0.93.
- 4 VERIFIED in Dhruv Room, at y −1.535 to −1.835.

That evidence is replayable offline. It has not been analysed yet.

## 2. Working subsystems (preserve)

All untouched by this work:
- CYS S8218 steering and manual remote;
- E-STOP latch priority;
- LiDAR, ultrasonic and radar;
- IM10A fusion and encoder health;
- camera and AI detection (preview pacing deployed 15 Oct);
- Glass UI V2, BMS and the Wi-Fi → cellular → hotspot fallback;
- the startup verify-before-seed (0.93 / 0.06) and CHECK MY LOCATION.

Stage 17B stays on HOLD.

## 3. Confirmed localization failures, with new measurements

Measured offline on the four usable 9 Oct drives:
- 933 LiDAR scan-to-scan ICP pairs;
- 52 chains of ten consecutive pairs (about 1.4 m each).

ICP is an independent relative-motion reference, not surveyed truth.

**1. The production EKF's translation does not follow its own heading. (New, confirmed.)**
- **Cause:** the EKF takes yaw from the gyro but X/Y from wheel *position*, which is integrated
  along the wheel model's commanded-steering heading. The wheel position has a fixed
  0.05 m² covariance, so X/Y is effectively pinned to it.
- **Measured:** recorded `/odom` travel direction relative to its own heading has a 90th
  percentile of **22°**, and 40% of pairs are above 10°. LiDAR gives 9° and 7%.
- **Effect on AMCL:** its `DifferentialMotionModel` turns that sideways motion into spurious
  rotation.

**2. Fusing wheel position also degrades EKF heading. (New, confirmed.)**
Over about 1.4 m chains, the heading error against ICP is:

| Drive | Recorded/production EKF | Without wheel position (Candidate B) |
|---|---|---|
| Outbound | 4.8° | 0.5° |
| Return | 7.4° | 2.3° |
| Hall → Dhruv | 23.6° | 3.4° |

**3. A constant 5.5° offset between LiDAR travel direction and body heading. (New, confirmed;
cause unknown.)**
- Per drive: +6.5 / +4.5 / +5.0 / +5.8°.
- It has the same sign forwards and in reverse.
- It is either a LiDAR mounting-yaw error (the TF says exactly 180.00°) or a steering-trim crab.
- AMCL works in the LiDAR frame, so either cause looks like about 10 cm of sideways error per metre.

**4. The wheel distance under-read is unchanged.**
- Raw M1/M4 read 0.64–0.72× and M2 0.51–0.64× of the true distance (11 Oct analysis).
- Chain end-point errors of 55–110 cm per 1.4 m are dominated by it. No EKF variant fixes it.

**5. The five parked AMCL jumps (maximum 2.206 m) remain unexplained and unreproduced.** No AMCL
claim is made here.

## 4. Recorder and network blockers (Phase B)

**Blocker 1: admission policy.** The safeguard refuses any 1 s CPU sample above 75%, but the
parked baseline is about 70% mean with 1 s peaks of 77–80% (Oct 15 reports). It will fail
intermittently by construction. Owner decision needed:
- keep it as is; or
- change it to a sustained rule. For example: 10 s mean ≤ 75%, no sample > 90%, and abort on
  control-policy or command staleness.

I did not change it.

**Blocker 2: the production bridge is not receive-only.** `atlas-foxglove.service` (PID 4363,
4.5% CPU, 80 MB) runs with:
- address `0.0.0.0:8765`, no TLS, no token;
- capabilities `clientPublish, parameters, parametersSubscribe, services`;
- topic, service, parameter and client-publish whitelists all `.*`.

So any device on the home Wi-Fi or the tailnet can publish any topic, call any service and set
parameters. The E-STOP latch still has priority over velocity, but parameter and service access
is wider than the receive-only contract (`offboard_bridge_contract.py`) assumes.

**Smallest safe fix** (needs approval, restarts only the bridge):
- capabilities `[connectionGraph]`;
- `topic_whitelist` limited to the five qualification topics;
- `client_topic_whitelist`, `service_whitelist` and `param_whitelist` set to `[]`;
- address set to the Tailscale IP.

**Blocker 3: clock.** The PC–Jetson offset is unknown. Use source header stamps only; treat
receive times as host-local.

**Alternative that avoids a live recorder entirely:** the startup and drive evidence already on
the Jetson (Stage 16 history, the Oct 14 Stage 17 parked bag) can be copied off with `scp` and
analysed here.

## 5. Exact next software correction candidate

**Candidate B-safe = Candidate B + fresh-zero-count stop anchoring.** BUILT and TESTED offline;
**not deployed.**

**Part 1: EKF config (Candidate B, unchanged from `fixtures/minimal_wheel_pose_candidate.json`).**
`odom0_config` selects indices 6, 7 (Vx, Vy; the driver always publishes Vy = 0) instead of
0, 1, 6, 7. The gyro, topics, covariances, frequency and TF offset are unchanged.

**Part 2: driver (`yahboom_base.py`, +15 lines; helper `all_counts_unchanged` in
`atlas_encoder_selection.py`).**
- **When it applies:** fewer than 3 encoders agree, *and* a fresh packet shows all four raw wheel
  distances exactly unchanged (including excluded channels).
- **What changes:** the zero-velocity twist keeps its normal covariance instead of ×1000.
- **What stays the same:** pose covariance stays inflated. The `odom_source` label (read by
  `atlas_safety_status.py`), the consensus rule and the `fewer_than_3=stop` motor policy are
  untouched.
- **Why it is needed:** without it, B coasts **2.01 m during a 20 s parked stop** with encoder
  consensus lost (native EKF, synthetic). With it: 0.003 m. Production A improves too
  (−0.115 → −0.037 m).

**Native replay** (robot_localization 3.8.x on ROS Jazzy in the cloud workspace; Jetson untouched):
- **Fidelity:** native A reproduces the recorded EKF's *relative* motion per pair to 0.04–0.11 cm
  lateral, 0.2–0.6 cm forward, 0.12–0.30° heading and 0.2–0.75° sideslip (medians).
- **Validity:** a relative A/B is therefore valid even though a cold start cannot reproduce
  absolute pose or AMCL state. Stage 19's finding that it cannot stays correct for AMCL; it is
  refined here, not overturned.

**A versus B on the same inputs.** 90th-percentile per pair; lower is better.
- "corrected" = the LiDAR yaw offset estimated leave-one-drive-out (−5.09 / −5.77 / −5.58 /
  −5.33°), never from the scored drive.
- Drive order: outbound, return, Hall→Dhruv, round trip.

| Metric | A (production) | B |
|---|---|---|
| Heading error (°) | 1.66 / 2.83 / 3.74 / 2.32 | 1.83 / 2.06 / 1.99 / 1.88 |
| Heading drift per 1.4 m chain (°, median) | 4.8 / 7.4 / 23.6 / – | **0.5 / 2.3 / 3.4** / – |
| Sideslip vs LiDAR (°), uncorrected | 9.1 / 15.8 / 16.2 / 26.1 | 12.8 / 12.6 / 12.0 / 11.5 |
| Sideslip vs LiDAR (°), corrected | 10.8 / 21.1 / 21.5 / 31.4 | **8.2 / 10.3 / 9.6 / 9.5** |
| Lateral error (cm), corrected | 1.86 / 4.03 / 4.52 / 3.88 | **1.65 / 2.50 / 2.36 / 1.84** |
| Forward error (cm, median) | −4.8 / −4.7 / −5.7 / −4.6 | −6.0 / −5.9 / −6.1 / −5.6 |
| Parked drift, 6 real stops (max) | 4.34 cm | 1.77 cm |

**Honest trade-offs:**
- B removes the heading contamination outright.
- B's sideways benefit appears only once the 5.5° offset is resolved; uncorrected, B is mixed.
- B reads about 1 cm (2–3%) *less* forward distance per pair than A.
- **No AMCL improvement is claimed.**

## 6. Evidence

**Available:**
- the 4 Oct 9 drives (on Dhruv's PC);
- the native A/B outputs (`~/Downloads/atlas_ab_evidence_20261015/ab_20261015.tar.gz`, sha256
  `0bfbe4ab…`);
- Stage 16 boot history (6 boots, on the Jetson);
- the accepted map backup (11 Oct).

**Missing:**

| What | Why it matters |
|---|---|
| Physical cause of the 5.5° offset (LiDAR mount vs crab) | Decides whether to fix it in TF or in steering trim |
| Taped distance at two speeds | Separates CPR error from slip |
| A moving bag with raw IM10A and `/yahboom/odom_source` | Neither is in any Oct 9 bag |
| AMCL filter state | Needed for any AMCL claim |

## 7. Tests

| Tests | Result |
|---|---|
| `test_encoder_selection` (5 new), `test_encoder_update_snapshot` (2 new), `test_encoder_observer` | **38/38 pass** |
| Driver suites `test_yahboom_diagnostic_cadence`, `test_encoder_packet_timing`, `test_yahboom_lifted_owner` | 18/18 pass |
| `tools/diagnostics/test_ekf_ab_compare.py` (sideslip folding, chaining, body frame) | 5/5 pass |
| `test_encoder_calibration` | **1 pre-existing failure, not caused by this change.** `test_repository_mapping_signs_and_values_are_canonical` expects signs (−1, 1, 1, 1); the repository YAML gives (1, −1, 1, −1). It fails identically on `0107b5f` without this change. Do not "fix" the YAML to match without physical sign evidence |

Native EKF A/B replay: 8 runs, with a guard against duplicate EKF publishers. The first batch was
**discarded**: `ros2 run` had left 5 EKFs publishing `/odom`.

## 8. Deployment and rollback (not authorized; for when approved)

- **Package as one stage, two files plus config:**
  - `scripts/yahboom_base.py` and `scripts/atlas_encoder_selection.py` (restart
    `rover-base-telemetry`);
  - `config/atlas_ekf.yaml` with `odom0_config` 6, 7 only (restart `atlas-ekf`).
- **Install conditions:** parked, latched, manual-only. Use the existing stage tooling
  (rehearsal, backup with `ROLLBACK.sh`, MATCH hashes).
- **Deploy the driver part first, on its own.** It is safe with the current EKF too (A improved
  in the synthetic test).
- **Rollback:** `ROLLBACK.sh`, then restart the same two services. No map, AMCL, Nav2, steering
  or threshold change.

## 9. Approval gates

**Needs Dhruv's explicit approval:**
- the bridge hardening (§4);
- the admission policy (§4);
- deploying the driver anchor;
- deploying the EKF Candidate B;
- the supervised test (§10);
- any LiDAR TF yaw or steering-trim change;
- any CPR change;
- reboot or E-STOP release.

None was done.

## 10. Prioritized plan

1. **Approve and deploy the driver stop-anchor** (low risk; it improves the current EKF too).
   Verify parked: the `/yahboom/odom` twist covariance stays normal when counts are frozen.
2. **One supervised 10-minute session**, latched between moves, recorder on:
   - **(a)** drive 2 m straight along a taped floor line and measure the sideways offset at the end.
     About 19 cm means steering crab; about 0 cm means LiDAR mounting yaw. Then check the LiDAR
     0° mark against the chassis axis.
   - **(b)** 2 m forward and back at about 0.15 and about 0.40 m/s against a tape (CPR vs slip).
   - **(c)** gentle left and right turns with 10 s stationary before and after.
3. **Correct the 5.5° offset at its measured cause:** laser TF yaw, or steering trim (Stage 17B is
   on hold; owner decision).
4. **Deploy Candidate B** (EKF config) after 1–3, then repeat 2(c) and compare live A/B heading and
   sideways error. That is the "measurable reduction" gate.
5. **Distance scale:** a measured CPR or slip correction from 2(b).
6. **Analyse the Stage 16 boot evidence** for the 0.91–0.92 refusals. Then the corridor/Hall map
   repair. Then the Dhruv Room → Hall → home route.

## 11. New tools (offline only; never run on the rover)

All in `project_atlas/tools/diagnostics/`:

| Tool | Purpose |
|---|---|
| `odom_heading_consistency.py` | sideslip and heading against ICP |
| `ekf_ab_replay.sh` | native EKF replay on a private domain with sim time; refuses if another EKF exists |
| `ekf_ab_compare.py` | fidelity, per-pair and chain metrics; optional leave-one-out laser-yaw hypothesis |
| `ekf_ab_stops.py` | parked drift |
| `ekf_consensus_loss_synthetic.py` | synthetic consensus-loss stop |
