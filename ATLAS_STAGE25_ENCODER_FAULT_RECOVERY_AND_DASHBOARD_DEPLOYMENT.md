# Stage 25b — encoder fault recovery and Dashboard Motion Chip deployment

16 October 2026 · branch `agent/sync-developer-20261011` · builds on `596bfdc` / `c53f017`.

## Status at a glance

| State | Item | Result |
|---|---|---|
| SOURCE FIXED | Motion Chip classifier (`web/v2/motion-status.js`) | done in Stage 25 (`596bfdc`) |
| TESTED OFFLINE | 35 chip/web/safety tests, 40 encoder/diagnostic tests, 6 new hand-test tests | all pass |
| **DEPLOYED** | Three static Dashboard files, 09:03:38 IST | **yes**, hashes match, no restart |
| **DASHBOARD VERIFIED** | Loads, `AtlasMotion` present, chip "Stopped" at rest, no console errors, warning path exercised on live data | **yes** (section 4) |
| ENCODER HARDWARE CHECK PENDING | M2 and M3 physical inspection and lifted hand test | **pending, your action** |
| MOVING VALIDATION PENDING | any drive, Candidate B, fallback estimator | **pending, nothing requested** |

Nothing was moved, energized, restarted, recalibrated or flashed. Candidate B is not deployed. The 3-of-4 fail-closed policy, Stage 21, Stage 22 and Stage 24 are untouched.

## 1. Current Jetson safety state (read-only)

Checked at 09:00 (Phase A), immediately before install (09:03) and after (09:26).

| Check | Result |
|---|---|
| E-STOP | **latched**, reason "REMOTE STOP: joystick unavailable" (normal after a boot) |
| Manual-only / commissioning | true / disarmed (`commission_remaining_s` 0) |
| `/cmd_vel` | 0.0 / 0.0 |
| `atlas-nav2`, `atlas-explore` services | inactive; no `/navigate_to_pose` action status published, so no goal |
| Encoders | READY, consensus AVAILABLE, packet_fresh, 0 checksum errors, wheels unchanged for ~12 min |
| Resources | RAM 2.4 GB available of 7.6 GB, disk 368 GB free (17% used), temps 57–58 °C, load 12–16 |
| Dashboard | HTTP 200 on `:8088/v2/`, also reachable at `192.168.1.15:8088` |

Observations you should know about (none touched):
- **The Jetson was power-cycled overnight** (uptime 11 min at 09:00). Its saved-clock quirk makes `last`/`dmesg` show 22:17 Oct 15 as the boot time; the real boot was ~08:49. Odometry reset to the origin, as expected.
- **A localization and Nav2 stack is running outside the `atlas-nav2` service**: `atlas_localization.launch.py` (AMCL, map server, Nav2 controller/planner/BT) and an RPLIDAR driver started with `ros2 run` at ~08:56; their parent is the user session. I did not start them. The mux is manual-only and E-STOP is latched, so nothing can drive, but please tell me whether you started it.
- `/dev/yahboom` does not exist; the base runs on `/dev/ttyUSB1` via the `usb-1a86_USB_Serial` by-id path. One `serial_write_errors: 1` ("Write timeout") since boot. Neither affects encoder reading (24.6 Hz, 0 errors); noted only.

Deployed hashes before and after the install (first 16 hex; all unchanged):

| File | sha256 |
|---|---|
| Stage 21 `scripts/yahboom_base.py` | `c551be0053a43755` |
| Stage 22 `scripts/atlas_motion_recorder.py` | `7110961ca9692f6b` |
| Stage 24 `seed_atlas_localization.py` | `273989b23e9ee023` |
| Stage 24 `atlas_localization_verify_core.py` | `d95828a09b174d10` |
| Stage 24 `config/place_regions.json` | `325df94a7cade0cc` |
| `config/encoder_calibration.yaml` | `21badbadee0aaa7a` (= repo; unchanged since 25 Sep) |
| `config/encoder_selection.yaml` | `1260c4633efebf94` (= repo) |
| `web/v2/estop.js`, `atlas_status_web.py` | unchanged; status-web PID 2006, base PID 3198, EKF PID 2841 never restarted |

## 2. Dashboard patch deployment outcome

**Deployed 09:03:38 IST** with the prepared package (`tools/deploy/stage25_motion_chip/`), static files only.

1. Package files copied to a staging directory **outside** the web tree (`~/stage25_pkg_staging`), checked against `MANIFEST.sha256` (full SHA-256) on the PC and again on the Jetson.
2. **Rehearsal on an exact copy of the live `web/v2`**: apply, second apply refused ("live shell.js is not the expected pre-state"), rollback; the copy was byte-identical to live afterward.
3. Safety preconditions re-read immediately before install (latched, manual-only, disarmed, cmd 0).
4. `apply.sh` run against the live directory. No service was restarted (status-web PID 2006 and elapsed time unchanged).

### Confirmed display-only
- Diff versus the previous live code: one `<script>` line in `index.html`; in `shell.js` a three-line delegation to `window.AtlasMotion` with the original logic kept as fallback.
- `motion-status.js` contains no `fetch`, `XMLHttpRequest`, `cmd_vel`, `estop`, `e_stop`, `localStorage` or POST (test-enforced).
- E-STOP code (`estop.js`, status-web) hashes unchanged; encoder selection and Stage 21 untouched.

## 3. Exact before / after hashes

| File | Before | After (full sha256) |
|---|---|---|
| `web/v2/shell.js` | `6a843ec277c2f8bd0c28079202bcf2b48e176c1b2c73595c5304440baf135d70` | `f05f6b8103af638edfaef230d0f0dcde576249aa55e673012e9dc2d896bc95ba` |
| `web/v2/index.html` | `e0291f844ea16474868a83ad76f7126a125b07dbe8a4063909d9617758be1f6c` | `61f3a12e59bf123753a5e675d7f8247cb82905fd34403bc5e34ec3718e9d3109` |
| `web/v2/motion-status.js` | absent | `592daa6942011bfeba1134cada1fc5aee332ecab86741f593515bee75c0c3163` |

Matches the prepared values (`f05f6b81…`, `61f3a12e…`, `592daa69…`). `apply.sh` 00a35217…, `rollback.sh` 6039c32e….

## 4. Regression tests and post-install verification

| Suite | Result |
|---|---|
| `test_motion_status` (7, recorded Stage 25 frames) + `test_atlas_web_v2` + `test_status_web_estop_safety` + `test_encoder_packet_timing` + `test_status_web_smart_panels` | **35 pass** |
| `scripts/test_encoder_selection`, `test_web_diagnostics` | **40 pass** |
| New `tests/test_encoder_hand_test.py` | **6 pass** |

Post-install checks on the live system:

| Check | Result |
|---|---|
| Files match expected SHA-256 | yes (section 3) |
| Served over HTTP | all three 200 (2917 / 7906 / 17263 bytes) |
| Rendered in a real browser (built-in browser pane, `192.168.1.15:8088/v2/`) | `AtlasMotion` loaded; script list includes `motion-status.js`; chip "Stopped"; **no console errors** |
| Headless Chromium on the Jetson (`localhost:8088/v2/`) | DOM dump shows "Stopped"; only a pre-existing harmless "password field not in a form" notice |
| Genuine rest | **Stopped** (live frame, wheels unchanged ~12 min) |
| ≥2 wheels counting, odom zero (synthetic from the live frame) | **"Moving · odometry not tracking"** (warn), with the "do not trust the position" text |
| 1 wheel only | Stopped (no false alarm) |
| Health data 9 s old | Stopped (old behaviour; no certainty claimed) |
| `packet_fresh` false | Stopped (old behaviour) |
| Odometry moving | Moving (never downgraded) |
| No status | Motion unknown |
| E-STOP status/controls, Stage 21 | unchanged (hashes, section 1) |

No screenshot file is attached: the headless screenshot did not write on the Jetson and the browser-pane image is not saved to disk. Rendered verification is the DOM/JS evidence above. The warning path was exercised on the real classifier with live frames, not by moving the rover.

## 5. Dashboard rollback

- Backup: `/home/jetson/project_atlas/web/v2/.pre_stage25_motion_chip_20261016_090338/` (original `shell.js` and `index.html`, hashes `6a843ec2…` / `e0291f84…`). Pointer: `.stage25_last_backup`.
- Roll back (static files, no restart): `TARGET=~/project_atlas/web/v2 ~/stage25_pkg_staging/tools/rollback.sh`
- Rehearsed on a live copy before install (identical afterward). **Not executed live**, because verification passed.

## 6. M2 (rear-right) fault analysis

All numbers are from the five Stage 25 bags (raw counts, sign-corrected so forward is positive) and the history scan below. Raw bags untouched.

**What happened**
- Outbound and the Hall turn: M2 tracks M1/M4 cleanly. Correlation 0.95, slope 1.0–1.45 (M2 reads ~12–20% high, its known scale), **0% opposite, 0% zero**. In reverse (33 intervals) it follows correctly.
- **21:40:24.15–21:40:28.35 (4.2 s): raw count frozen at −40584** while M1/M4 advanced 2,940/2,982 counts (M2 +135). This began **3 s after a 0.52 m/s drive started from rest**; commanded steering and mode were unchanged; battery 12.9–13.1 V, no sag.
- Afterwards, with M1/M4 driving forward (269 intervals): M2 **negative in 75%, zero in 20%, positive in 5%**. Slope **−0.64 to −0.68**, correlation **−0.38 to −0.46**. In reverse (73 intervals): **zero in 63%, negative in 36%, positive 1%**. It never follows real direction.

**What it is not (evidence against)**
- **Not a clean sign inversion** (wiring swap, config or driver sign). That predicts slope ≈ −1.1 and correlation ≈ −0.95 with M2 following reverse as positive. Observed −0.65 and −0.4, and reverse does not flip it.
- **Not a configuration change.** `encoder_calibration.yaml` is byte-identical to the repo and unchanged since 25 Sep; the base code is the Stage 21 hash.
- **Not the serial link.** 24.6 Hz packets, 0 checksum errors, 0 stale, packet age ≤ 0.058 s; M1 and M4 stayed perfect through the same packets.
- **Not a power sag.** BMS 12.9–13.1 V, 1.9–5.9 A through the whole run (5 s resolution; fast noise is not visible at that rate).

**Consistent with, and not separable from, the bag data**
| Candidate | Fit to evidence |
|---|---|
| Intermittent or marginal A/B signal (loose pin, cold joint, damaged cable) | **Fits**: freeze, reduced gain, fixed bias toward negative, no tracking of real direction, onset after a start-up jolt |
| Loose connector | **Fits**, same signature; the jolt at start-up supports it but does not prove it |
| Faulty encoder or sensor | **Fits**; indistinguishable from the above without a hand test |
| Electrical noise | Weak: the pattern persisted for 4 minutes at all speeds and at rest |
| Mechanical coupling (magnet or disc slipping on the shaft) | Weak: does not explain direction bias |
| Unexpected driver interpretation | **Not supported** (no config change; a decoder sign fault gives slope ≈ −1.1) |

**Do not conclude which component is faulty without the lifted hand test (section 9).**

## 7. M3 (front-left) fault analysis

- **Direction-dependent loss.** Counted as a fraction of the M1/M4 reference:

| Period | M3 going forward | M3 in reverse |
|---|---|---|
| Outbound (245 intervals) | **0.00** (zero in 98%, small ±1 dither) | — |
| Hall turn | 0.13 | 0.36 |
| After the M2 fault (forward 269 / reverse 73) | **0.11** | **0.96** (99% of intervals correct sign) |

  The polarity is right (positive forward, negative reverse) and it can count at full rate, but mostly **only in reverse**. That is not a dead encoder and not a wiring sign; it points at a marginal quadrature phase or sensor margin that fails in one direction.
- **Alternating ±1 counts while M1/M4 move** (e.g. 21:37:05–08: −1, +1, −1, +1 …) is the signature of an input chattering on a single edge rather than counting.
- **Not new.** `encoder_calibration.yaml` already labels M3 `intermittent_measured_provisional` and M4 likewise; `encoder_selection.yaml` says the weak channel "can move between M2, M3 and M4" and that M4 "returned coherent counts after repair".

### Previous sessions (read-only scan of 41 Jetson bags, Aug–Oct)
Counted/reference ratio, forward / reverse (`tools/diagnostics/stage25_roundtrip/s25b_history_scan.py`; reference is the median of the four wheels, so read rows rather than single numbers):

| Session | M1 | M2 | M3 | M4 |
|---|---|---|---|---|
| 24 Aug teach/house bags (several) | 1.1/1.1 | 1.2/1.0 | 1.1/1.1 | 0.73/0.95 |
| 2 Oct `manual_dhruv_to_hall` | 0.98/1.15 | 1.09/1.08 | 0.99/1.14 | 0.96/**0.17** |
| 4 Oct `fresh_manual_mapping` | 1.03/1.1 | 1.12/1.16 | 0.86/1.11 | 1.03/**0.17** |
| 8 Oct `manual_mapping_*` | 1.1/1.2–1.4 | 1.2/1.2 | **0.24–0.47**/1.1 | 1.1/**0.18–0.20** |
| 9 Oct `hall_to_dhruv` | 1.11/1.65 | 1.2/1.44 | **0.40**/0.71 | 1.11/**0.24** |
| 9 Oct `amcl_hall_outbound` | 1.17/2.7 | 1.14/1.8 | **0.0**/0.0 (93% zero) | 1.15/**0.37** |
| **15 Oct, Stage 25 outbound** | 1.11 | 1.25 | **0.00** (98% zero) | 1.11 |

Reading: until 24 Aug the wheels are direction-symmetric. From 2 Oct M4 loses most counts **in reverse**; from 8 Oct M3 loses counts **going forward**; on 15 Oct M2 breaks. The weakness **moves from wheel to wheel over weeks**, always as direction-dependent loss, never as a stable single dead encoder. On 17 Sep M4 was excluded and the other three were symmetric within 0.7% (`THREE_ENCODER_GROUND_OBSERVATION`). That argues for a shared cause (harness, connectors, encoder supply or ground, or the board input stage) as at least as likely as three separate worn encoders. It does not prove it.

## 8. What I could not do without the hardware
Check wiring continuity, connector seating, cable damage, encoder supply voltage, or the signal shape on A/B. The manual states that the power branch topology and connector part numbers were not electrically traced.

## 9. Operator hardware test (rover lifted; nothing is driven)

Rules: do **not** energize the motors, do not command any wheel, do not change polarity/CPR/calibration, E-STOP stays latched. If anything feels unsafe, stop.

**A. Unpowered inspection (do this first)**
1. Power off. **Disconnect the battery. Wait several minutes for the rails to discharge. Verify 0 V at the motor-board input with a multimeter.**
2. Lift the rover on blocks so all four wheels are clear of the floor and cannot touch anything; check it cannot tip.
3. Label and photograph all four encoder connectors on the Yahboom board and at each motor (M1 rear-left, M2 rear-right, M3 front-left, M4 front-right). Send me the photos.
4. For **M2 and M3**, with the power off: look for bent or pushed-back pins, green or loose crimps, pinched, kinked or rubbed cable, strain at the connector, and connector latches not clicked. Gently wiggle each connector and cable along its length; note any that feels loose. Do not pull. Do not unplug unless you can reseat it identically and photographed.
5. Compare against M1 and M4 (which work): same connector type, routing and strain relief?

**B. Hand-rotation count test (needs the Jetson and the base node running; no motor drive)**
1. You need the encoders powered. **The manual does not say whether the encoder supply comes from the logic side or from the motor-board branch, and the branch topology was never traced.** Try the logic-power-only arrangement from the manual's safe sequence first (battery disconnected from the motor branch, Jetson/hubs powered the way you normally do for the "logic power only" step), with E-STOP latched. If you are unsure how to power logic without the motor branch, stop and tell me; do not improvise.
2. On the Jetson: `source /opt/ros/humble/setup.bash && python3 ~/project_atlas/tools/diagnostics/encoder_hand_test.py` (after this commit is pulled onto the Jetson; I will not copy it without your OK). It only listens to `/atlas/encoder_update`; it publishes and drives nothing.
3. Put a tape mark on each tyre. For each wheel the script asks for **one full turn forward and one backward, slowly (~5 s) and quickly (~1–2 s)**, 16 turns in all. Press Enter, turn, press Enter when the mark returns.
4. It reports per wheel: PASS (0.75–1.30 of one turn), PARTIAL, NO_COUNT, WRONG_DIRECTION, OVERCOUNT, **DIRECTION_ASYMMETRY**, **LOSS_AT_SLOW/FAST_PACE** and cross-talk onto other wheels. It writes a JSON log. Send me the output.
5. If the counts do not respond at all with the motor branch off, the encoder supply depends on it. **Do not turn the motor branch on yourself.** Tell me, and I will write the exact arrangement for separate approval. It would need the motor branch live with wheels lifted, E-STOP latched and a physical way to cut that branch, none of which I can specify from what is documented.
6. Reconnect only after all checks, restore the battery connection per the manual, and confirm E-STOP is still latched before leaving.

**Expected outcome if a connector/cable is at fault:** the failing wheel shows DIRECTION_ASYMMETRY or PARTIAL that changes when you wiggle its cable. If every wheel passes at rest but fails only under a motor load, the fault is intermittent, and the same test with a gentle wiggle will decide it.

The helper has not been run on the Jetson; its decision logic is unit-tested with the Stage 25 behaviours (M3 forward loss, M2 wrong direction).

## 10. Repair or replacement recommendation
1. **First, inspect and reseat connectors and harness** for all four channels (section 9A). The failure moving between M2, M3 and M4 over three weeks suggests a shared cause, and this costs nothing.
2. **Hand test (9B).** A wheel that fails on the bench is a candidate for replacement of its encoder/motor assembly or its cable; replace only the failing parts.
3. Do not change CPR, signs or the consensus policy to make the counts agree; none of the evidence calls for it.
4. After repair, a short **tape-measured** straight run with raw counts is needed to resolve the ~0.6× distance scale (ATLAS-001), separately from this.
5. I cannot say which part is faulty from software evidence.

## 11. Offline fallback analysis (investigation only; nothing deployed)

Question: could LiDAR ICP odometry with IM10A gyro heading provide useful observations while encoder consensus is unavailable?

Method: leg-by-leg between stationary anchors where AMCL fits the map (start 0.98 after a 0.11 m shift; Hall 0.92; pause 1 0.93; pause 2 0.83 after a 0.20 m shift). Error is displacement error versus the AMCL anchor displacement, which itself carries ~0.05–0.2 m of uncertainty. No tape truth exists.

| Leg | AMCL displacement | Wheel odom | Production EKF | LiDAR odometry | **LiDAR distance + gyro heading** |
|---|---|---|---|---|---|
| start→Hall (healthy encoders) | 6.46 m | 4.56 m off (71%) | 5.35 m off (83%) | 1.46 m off (23%), heading +27° | **0.34 m off (5%), heading +9°** |
| Hall→pause 1 | 0.65 m | 0.11 m (17%) | 0.29 m (44%) | 0.05 m (8%) | 0.16 m (24%) |
| pause 1→pause 2 (**blind**) | 1.57 m | 1.12 m (71%) | 1.13 m (72%) | 0.74 m (47%), heading −41° | 0.74 m (47%), heading 0° |

- Gyro heading fixes most of LiDAR odometry's heading drift (−41° → 0° on the blind leg), and on the long healthy leg it brings the error from 23% to 5%.
- On the blind leg the **position** error stayed at 0.74 m. That is more than the anchor uncertainty, so the LiDAR translation is not reliable at those low speeds, and no heading source fixes that.
- Three legs, one run, no tape truth: this is not enough to quantify performance.

**Requirements for any future fallback** (all kept, none implemented): a separate, non-actuating topic and node (e.g. `/atlas/odom_fallback_candidate`), never published as `/yahboom/odom` or wheel odometry, never gating or enabling motion, E-STOP priority and the 3-of-4 stop policy unchanged, explicit "estimated, not wheel-trusted" labelling on the Dashboard, and covariance that grows with distance (this evidence suggests an error of at least 0.5 m per leg and 25° if left unanchored) and resets only on a verified AMCL fit.

Conclusion: **worth a design note, not a deployment.** It is a candidate AMCL observation, not odometry. It does not justify driving on two encoders.

## 12. Candidate B readiness
**Not ready; remains undeployed.** Stage 25 showed it improves heading while the wheels are healthy (−145° versus gyro −146°; production −78°), and that it cannot recover movement lost when consensus fails. The M1/M4-only fix would not help either. Reassess after the encoders are repaired and a tape-measured baseline exists.

## 13. GitHub commit ID
See the commit recorded below after push.

## 14. Next action requiring your approval
**Do the unpowered inspection and the lifted hand test (section 9), starting with A.** Reply with: (1) photos of the M2 and M3 encoder connectors, (2) the hand-test output, and (3) how you normally power "logic only" (and whether the motor-board branch has its own switch/fuse). Also tell me whether you started the AMCL/Nav2 launch at ~08:56.

I am not asking for a drive, a reboot, a Candidate B deployment, or any change to the consensus policy.

## Evidence preserved
Stage 25 bags, their hashes and the audit trail are unchanged. New read-only outputs on the Jetson: `~/project_atlas/data/diagnostics/stage25b_history/` (scan script and JSON). Package staging: `~/stage25_pkg_staging/`. The PC has a leftover folder `Downloads/s25live/` (three small test files; I cannot delete in a connected folder without approval).

New in the repo: `tools/diagnostics/encoder_hand_test.py`, `tests/test_encoder_hand_test.py`, `tools/diagnostics/stage25_roundtrip/s25b_*.py`.
