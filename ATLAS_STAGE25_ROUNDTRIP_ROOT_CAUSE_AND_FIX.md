# Stage 25 — round-trip root cause, targeted fix and deployment readiness

15 October 2026 · branch `agent/sync-developer-20261011` · baseline commit `113b9aa`.

## Verdict

**Root cause of the failed slow return: two independent encoder-channel faults removed the three-of-four consensus,
so the base failed closed and integrated nothing. This is not a Stage 21 or estimator-logic bug.**
Nothing was deployed, moved, restarted or recalibrated. One display bug is fixed offline and packaged.

- **M3 (front-left) is near-dead today.** It registered 44 counts while M1/M2/M4 registered ~25,000 on the outbound leg.
- **M2 (rear-right) failed mid-run.** At 21:40:24.2 IST its raw count froze at −40584 for 4.5 s while M1/M4 kept
  counting, then it resumed counting the **opposite direction** for the rest of the drive.
- **With M3 dead and M2 contradicting, no three wheels agree.** Consensus went UNAVAILABLE; the base reported
  `feedback_unavailable` for 313 of 3,635 intervals. Those intervals held **3.47 m of 9.33 m (37%)** of the M1/M4 wheel travel.
- **The Dashboard "Stopped" chip was a separate, real defect.** It reads `/odom` velocity only, so it said "Stopped"
  while wheels were counting. Fixed offline; tested against recorded frames.
- **The final AMCL pose is not verified.** AMCL (4.56, −0.96) fits the map at 0.34 (start 0.98, Hall 0.92). It is
  about 4.3 m from the start and outside the Dhruv Room search box. The owner's "back in Dhruv Room" is not reproduced
  by AMCL or by independent LiDAR odometry. Physical confirmation is needed.

## 0. Protocol deviations (operator and agent)

- **E-STOP was never latched** during the recorded loop: `stop_latched` was false in all 3,665 policy messages
  (21:36:54–21:44:25). The Hall and final latch checkpoints were not performed.
- **I did not issue RECORDER READY / GO / RETURN GO.** The owner drove at 21:36 after I reported Phase 0 blocked
  (localization not VERIFIED, E-STOP released). I armed the recorder at 21:36:39 as a passive safeguard and said so.
  The start pose is therefore not a verified baseline; the stationary scans do support it (section 8).
- The earlier recorder session (21:24–21:34) expired with 0 captures: no motion occurred inside its 600 s window.

## 1. Safety-state verification (read-only, 21:52 and again 22:00 and 22:16)

| Check | Result |
|---|---|
| E-STOP | latched, "REMOTE STOP: B pressed" |
| Manual-only / commissioning | true / disarmed |
| `/cmd_vel` | 0.0, 0.0 |
| Navigation | `atlas-nav2`, `atlas-explore` inactive; no goal |
| Recorder | exited at the 600 s cap (21:46:45) |
| Production services | EKF pid 3242 unchanged; no restart, reboot or deployment |
| Old direct-serial steering script | not run |

The offline replay used isolated ROS domain 178, localhost-only DDS, `nice 19`, no actuator nodes and no `/cmd_vel`
publisher. Afterwards only production processes remained; E-STOP was still latched.

## 2. Evidence: five bags, hashes and coverage

Originals are unchanged (SHA-256 re-checked after copying). All analysis used read-only copies. Raw bags stay on the
Jetson (`~/project_atlas/data/diagnostics/stage25_20261015/` and `.../motion_capture/`) and the PC
(`~/Downloads/atlas_stage25_bags/`). They are not committed.

| Bag | Start–end (IST = Jetson clock) | s | Msgs | MiB | SHA-256 (db3) |
|---|---|---|---|---|---|
| `capture_20261015T160704Z_5d3cfaf5` | 21:36:54.99–21:37:54.24 | 59.2 | 16,329 | 18.9 | `7f93c57577ff42901696b3846b6c6a8d65a097ffdb3c0a6d7a55b7f3fa3e28da` |
| `capture_20261015T160910Z_5f8d9440` | 21:39:00.02–21:39:46.23 | 46.2 | 12,365 | 11.6 | `12a5268a950e5d8d21973a3740a8697527025b5a5971f96615037d023f243ec4` |
| `capture_20261015T161020Z_d0b2d703` | 21:40:10.23–21:40:50.23 | 40.0 | 10,371 | 9.1 | `92e06b08cc9411e05850f03175b8de453644e956dec14d25dd0770d6c05afc81` |
| `capture_20261015T161057Z_5a598338` | 21:40:47.33–21:42:20.24 | 92.9 | 23,450 | 16.7 | `af05d046f137f3270c29325ec42d8d5487e5f9f1ed040de448cbb355824d4b99` |
| `capture_20261015T161222Z_fe0d4344` | 21:42:12.99–21:44:25.24 | 132.3 | 34,395 | 24.7 | `bb208e6851a6068df9857f0a9a41497c02d7d0f5ade61f72413a747ac5d17b9f` |

- Metadata and manifest hashes are in `SHA256SUMS.original` next to the bags. Total 96,910 messages, ~85 MB.
- **Coverage:** 21:36:55–21:44:25 (450.2 s) with **two uncovered intervals: 21:37:54–21:39:00 (65.9 s) and
  21:39:46–21:40:10 (24.1 s)**. Bags 3→4 and 4→5 overlap by 3.0 s and 7.3 s (pre-roll). All five closed with reason
  `stopped`; `dropped` is `{}` on every bag; `missing` is `[]`.
- **Topics:** 32 per bag, all 20 required topics present. `/particle_cloud` is present (482 messages) but its type
  (`nav2_msgs/ParticleCloud`) could not be decoded in my sandbox; it was not analysed.
- **Continuity inside bags:** `/yahboom/odom` median 0.100 s, max 0.61 s; `/atlas/encoder_update` max 0.43 s; `/scan`
  median 0.132 s, max 0.41 s; `/amcl_pose` median 0.91 s. Odometry stayed above the 8 Hz abort line.
- **Not recovered from the gaps:** nothing was interpolated. AMCL poses bracketing both gaps are consistent with a
  stationary rover (Hall: (6.55,−2.42) → (6.53,−2.44); second: (5.86,−2.59) → (5.86,−2.52)), but that is not a recording.

## 3. Reconstructed timeline (same Jetson clock; owner times are message times)

| Time | Event | Source |
|---|---|---|
| 21:36:39 | recorder armed | event log |
| 21:37:05 | **outbound wheel motion starts** (first REMOTE command 21:37:04) | sensors |
| 21:37:33 | outbound motion ends; ATLAS stationary at Hall | sensors |
| 21:37:54 | bag 1 closes (20 s post-roll) | recorder |
| ~21:38 | owner "reach at hall" (my receipt 21:38:11, ~38 s after the sensors stopped) | owner |
| 21:39:11 | **return motion starts** (turn-around ≈ −153°); owner message ~21:39 | sensors / owner |
| 21:39:26–21:40:20 | pause 54 s (bag gap 2) | sensors |
| **21:40:24.2** | **M2 raw count freezes, later reverses** | encoders |
| 21:40:20–21:44:05 | ~15 slow pulses of ~1–1.7 s, two ~14–17 s drives (21:43:31–21:44:05) | sensors |
| 21:44:05 | last motion; owner "reach dhruv room" at 21:44 | sensors / owner |
| 21:44:25 | bag 5 closes | recorder |
| 21:46:45 | recorder exits at its cap | recorder |

**Distance, total versus net (LiDAR odometry, independent but not tape-verified):**
- Outbound: path 7.3 m, net 6.8 m. AMCL path 7.9 m, net 6.5 m.
- Return (turn-around plus slow pulses): path ≈ 6.9 m, net Hall→end ≈ 2.0 m (LiDAR) to 2.5 m (AMCL).
- Start→end: ≈ 4.3 m (AMCL) / 4.8 m (LiDAR odometry propagated from the start).

## 4. Raw and accepted encoder behaviour

Link health is clean: 24.6 Hz encoder packets, 98 Hz valid packets, 0 checksum errors, 0 stale events, 0 recoveries,
packet age ≤ 0.058 s, packets never stale. **The faults are at channel level, not in the serial link.**

Signed wheel distance per phase (M1 rear-left, M2 rear-right, M3 front-left, M4 front-right):

| Phase | M1 | M2 | M3 | M4 |
|---|---|---|---|---|
| Outbound 21:37:05–21:37:33 | +4.44 | +5.04 | **+0.01** | +4.48 |
| Hall turn-around 21:39:11–21:39:46 | +0.47 | +1.02 | +0.01 | +0.93 |
| Return 21:40:10–21:44:25 | +3.57 | **−2.20** | −0.29 | +4.78 |

**M2 failure (the discriminating evidence).** Raw counts, bag `5a…`/`d0…` (t = seconds after 21:36:55):
- t = 209.17: M2 −40584, still counting (−40449 → −40584).
- t = 209.25 to 213.67 (4.5 s): M2 **frozen at −40584** while M1 advances 37,600 → 40,657 (about 0.5 m).
- t = 213.75 onward: M2 counts **upward** (−40554, −40464, …) for forward motion, opposite to its outbound sign.
- No steering, mode or joystick change coincides (steering centred, mode `four_wheel_opposite`, buttons unchanged).
- When M1 and M4 both advance: outbound M2 same direction 231/231; Hall turn 57/58; **after the flip 40 of 290**
  (opposite 178, zero 72). It does not depend on speed (opposite at all four speed bands).
- Older bags (4–9 Oct, 8 bags, 2,715 such intervals): M2 opposite only **12** times (0.4%). **New today.**

**M3.** Near zero in 229 of 231 outbound intervals when M1/M4 advanced (99%); in the 8 older bags it was near zero
in 30% of those intervals. It is worse today than its known weakness.

**Consensus decisions** (per update interval, 3,635 total):

| Base `source` | Intervals | M1/M4 travel proxy |
|---|---|---|
| `wheel_encoder_consensus_3of4` | 342 | 5.69 m (61%) |
| `wheel_encoder_delta_4ws` | 264 | 0.17 m (2%) |
| **`feedback_unavailable`** | **313** | **3.47 m (37%)** |
| `stopped` | 2,713 | −0.01 m |

Accepted-channel sets while wheels counted: {1,2,4} 294, {1,2,3,4} 285, **∅ 313**, {1,3,4} 20, {2,3,4} 17, {1,2,3} 12.
Invalid intervals are rebased, not integrated later (by design), so the 3.47 m is permanently lost to the EKF.

**Low-speed quantization.** One count is 0.18 mm, so 0.05 m/s is ~28 counts per 0.1 s; the 4 mm tolerance floor is
not the limiting factor. Burst cadence was normal. The failure is direction and dropout, not resolution.

## 5. STOPPED / MOVING: three different layers, evaluated separately

1. **Stage 21 stillness anchor (base) — behaved correctly.** It needs 1 s of unchanged four-wheel counts and zero
   outputs. `stopped`-source intervals with any wheel count change: 52 of 2,713, carrying **−0.01 m** of travel, 42 within
   0.6 s of the last command (settling), max 1.42 s. It never hid real travel and was never "wrong while moving".
2. **Control-policy `source` (`REMOTE`/`STOPPED`) — not a motion classifier.** It is the command mux state
   ("no active command"). 217 of 740 wheel-moving intervals read STOPPED (coasting after the stick was released).
3. **Dashboard Motion chip — defective.** It used `/odom` velocity only. On the 10 Hz samples, 668 of 898 wheel-moving
   samples (74%) read Moving; 374 of 740 wheel-moving intervals had |vx| < 0.02 m/s. When consensus fails closed, `/odom`
   is zero and the chip said "Stopped · Odometry reports zero speed" on a moving rover.

The localization monitor's MOVING flag also reads `/odom` twist and has the same blind spot. **Not changed** (outside
the approved scope and it affects diagnostic scheduling only).

## 6. Wheel-distance error and yaw consistency

**Distance.** LiDAR odometry is the reference. It has not been checked against a tape, so these are ratios, not accuracy.
- Outbound: M1/M2/M4 4.44/5.04/4.48 m versus LiDAR path 7.29 m, so wheel/LiDAR ≈ 0.61 / 0.69 / 0.61. Base `/yahboom/odom`
  path 4.30 m (0.59).
- Over 16 near-straight 4 s windows (|gyro| < 0.3 rad/s): median M1/M4 ÷ LiDAR path **0.60**, range 0.46–1.01, no speed
  trend (v < 0.15: 0.66, 0.15–0.30: 0.51, ≥ 0.30: 0.62). This is the known under-reading; it is not caused by today's
  faults and is **not** addressed here. No scale or CPR was changed.

**Yaw** (Δyaw over each phase; IM10A gyro integral is the heading reference):

| Phase | Wheel odom | EKF A | LiDAR odom | AMCL | IM10A gyro |
|---|---|---|---|---|---|
| Outbound | −69° | −78° | −127° | −153° | −146° |
| Hall turn-around | −126° | −123° | −145° | −153° | −146° |
| Slow return (blind) | −2° | −7° | −31° | −17° | −29° |

EKF A under-reads outbound heading by **68°** (53%) against the gyro. Travel-direction offset: only 2 usable windows
(+3.4°, +8.9°) — too few to re-measure the known ≈5.5°; not changed. In the last 130 s the gyro (−80°) and LiDAR odometry
(−30°) disagree by 50°; unresolved.

## 7. EKF versus LiDAR comparison

| Phase | Wheel odom path / net | EKF A path / net | LiDAR odom path / net | AMCL path / net |
|---|---|---|---|---|
| Outbound | 4.30 / 4.22 m | 4.56 / 4.22 m | 7.29 / 6.79 m | 7.86 / 6.47 m |
| Hall turn-around | 1.22 / 0.76 m | 1.30 / 0.76 m | 2.75 / 0.66 m | 2.03 / 0.69 m |
| Slow return | **0.95** / 0.67 m | **1.43** / 0.67 m | **4.12** / 1.64 m | 3.24 / 2.02 m |

On the slow return the EKF integrated 23–35% of the LiDAR path. Propagated from the start pose, the end-of-loop
estimates are: LiDAR odometry (5.10, −0.85), AMCL (4.57, −0.97) (0.55 m apart, heading within 3°), EKF A (3.42, 0.72)
(2.0 m from AMCL), wheel odometry (3.64, 0.12) (1.4 m).

## 8. AMCL behaviour and uncertainty

- **No jump above 0.5 m** between consecutive poses (rate 1.08 Hz; largest step 0.33 m). But there is a second failure
  mode: pose motion while stopped. At Hall, **AMCL moved 1.25 m in the 15 s after the rover stopped** (LiDAR odometry and
  wheels both 0.00), as the covariance collapsed from **1.41 m / 75° at 21:37:33** to 0.01 m. Steps of 0.19–0.24 m between
  consecutive poses occurred at standstill. The Dashboard marker moved while ATLAS was parked.
- **Cause of the outbound uncertainty:** fast driving (0.5 m/s) with hard turns, wheel odometry under-reading by ~40%
  and heading by 50%, so the motion model and the scans disagreed. It re-converged; Hall fits the map at 0.92.
- **The 0.55 m / 38° rise at 21:40:25–45 (return):** it follows the M2 failure at 21:40:24. The rover moved 0.45 m
  (M1/M4) while the EKF saw ~0 motion, so the particles lagged the true pose. AMCL then caught up while stopped
  (a 0.33 m / −21° step at 21:40:39 with wheels and LiDAR odometry both at 0.00).
- **Scan-to-map fit at stationary windows** (fraction of beams within 0.07 m of an occupied cell):

| Window | AMCL fit | Best local fit | Shift |
|---|---|---|---|
| Start (before moving) | 0.58 | **0.98** | 0.11 m, −4° |
| Hall stop | 0.92 | 0.94 | 0.05 m |
| Return pause 1 | 0.84 | 0.93 | 0.05 m |
| Return pause 2 | 0.71 | 0.83 | 0.20 m |
| **Final** | **0.34** | 0.55 (±0.8 m, ±20°); 0.63 in a ±2 m, ±90° search at several different poses | — |

- **The final pose is unverified.** Its fit is poor and at least three other poses fit no worse ((5.06,−2.36,78°),
  (3.96,−0.66,156°), (2.56,0.14,159°)): an aliased corridor. AMCL is not proven wrong either: LiDAR odometry, which
  inherits its own drift, agrees within 0.55 m. I do not call it correct.
- **Map and EKF model:** the accepted map fits well at three of five stationary windows, so it is not what misled AMCL.
  The proximate cause is the odometry that fed the motion model (blind, then 40% short).
- **Parked jumps (five known):** none occurred in this recording's parked intervals; not revisited further.

### Front-wall distortion

- **Stationary at the start:** median scan-to-map residual 0.05 m, 84% within 0.10 m, **0% beyond 0.20 m**; the best
  local fit is 0.98. `/scan` and `/scan_raw` give identical statistics, so the scan filter is not responsible.
- **Moving outbound (pose from interpolated 1 Hz AMCL):** median 0.10 m, 22% beyond 0.20 m. A 1 Hz pose with
  0.4–1.4 m uncertainty smears a live overlay without any map or TF defect.
- **Conclusion:** the recording shows no LiDAR TF, timestamp or saved-map defect. The apparent crookedness while moving is
  consistent with overlay pose lag. **Not proven for the saved map itself and I do not know which wall the owner means.**
  The accepted map and LiDAR TF were not touched. A screenshot of the wall would settle it.

## 9. Candidate B offline A/B (EKF only, native Humble, isolated)

Method: production `atlas_ekf.yaml` (69dd4479…) versus the same file with `odom0_config` X/Y pose disabled — exactly
Candidate B (`atlas_ekf_candidate_b.yaml`, 856d82ce…) — fed the recorded `/yahboom/odom`, corrected IM10A and TF at 1.0×.
**Fidelity:** replay A reproduces the recorded production EKF's translation (net 4.22 m versus 4.22 m, path 4.66 versus
4.56 m) but its heading differs by 13° (−91° versus −78°) because the live EKF's earlier state was not recorded
(the same limit Stage 19 found). **There is no AMCL replay, so no AMCL claim is made.**

| Segment | Metric | Recorded A | Replay A | **Replay B** | Reference |
|---|---|---|---|---|---|
| Outbound (healthy, 59 s) | Δyaw | −78° | −91° | **−145°** | gyro −146°, AMCL −154°, LiDAR −127° |
| | path / net | 4.56 / 4.22 | 4.66 / 4.22 | 4.56 / 3.22 | LiDAR 7.29 / 6.79 |
| | end error vs LiDAR | 4.70 m | 3.94 m | 3.76 m | — |
| Slow stop-go (blind, 92 s) | path / net | 0.08 / 0.04 | 0.08 / 0.04 | 0.10 / 0.04 | LiDAR 0.33 / 0.31 |
| Last 132 s (blind) | Δyaw | −70° | −58° | −80° | gyro −80°, LiDAR −30°, AMCL −48° |
| | path / net | 0.78 / 0.18 | 0.81 / 0.18 | 0.76 / 0.12 | LiDAR 2.91 / 0.54 |

- **B tracks the gyro heading almost exactly while the wheels are good** (1° off versus 55–68° for A).
- **B does not fix distance.** Wheel under-reading dominates the end error (3.76 versus 3.94 m), and over the blind
  stretches A and B are identical: they receive the same blind wheel velocity.
- **B would not have prevented this failure.** It addresses heading, not encoder-consensus loss.
- **Not deployed.** Needs separate approval after the encoders are repaired. Forward distance, lateral deviation and
  stop behaviour were compared only as above; relative LiDAR agreement is as tabulated.

## 10. Recorder gaps: exact causes

All three gap-related effects are expected behaviour, not interruptions:
- **Post-roll rule:** a capture closes 20 s after the last motion, and the next opens with 10 s of pre-roll. A stop of
  *S* seconds therefore leaves *S − 30 s* uncovered. Hall: stationary 21:37:34→21:39:11 (97 s) → **66 s gap** (predicted 67).
  Second pause: 21:39:26→21:40:20 (54 s) → **24 s gap** (predicted 24).
- **Session expiry:** the 600 s cap includes waiting. This session would have stopped recording at 21:46:39; the drive
  ended at 21:44:05 so it was not binding. The earlier 21:24 session expired empty.
- **Owner milestone timing:** message times lag the sensors by 38 s (Hall) and ~50 s (return start).
- **Unexplained interruptions: none.** 0 dropped messages, 0 missing topics, all closes `stopped`. `/particle_cloud` flickers
  "stale" because AMCL publishes only on update (482 received). The session-wide `middleware reported_lost` counter reads
  936 but is not attributable to a topic; intra-bag gaps stay below 0.61 s.
- **Final stationary interval:** only the 20 s post-roll (21:44:05–21:44:25) was recorded; the later 140 s was not.
- **Load:** system load average 10–17 with the recorder at `nice 10`; odometry held 10 Hz. The existing recorder can cover
  a whole journey **without code changes**: arm it just before driving, re-arm at each stop longer than about 3 min, and
  use the existing `--stationary-probe` (E-STOP latched required) if a continuous stationary record is needed. Changing the
  post-roll would modify Stage 22 and is not proposed.

## 11. Confirmed code defects and targeted fixes

| # | Finding | Status |
|---|---|---|
| 1 | **Dashboard Motion chip shows "Stopped" when odometry fails closed while wheels count** — `motionText()` in `web/v2/shell.js` | **Fixed offline** (below) |
| 2 | M2 reversal/freeze and M3 dropout | **Hardware or wiring suspected; not a software bug.** No fix possible in software without weakening the fail-closed policy |
| 3 | Consensus fail-closed discards 37% of travel | **By design.** A degraded two-wheel mode would weaken it; **not implemented**, needs a separate owner decision |
| 4 | Localization monitor MOVING uses `/odom` | Same blind spot; **noted, not changed** |

**Fix 1** adds `web/v2/motion-status.js` (pure classifier), a three-line delegation in `shell.js` (original logic kept as
fallback) and one `<script>` line in `index.html`. If `/odom` says moving it stays Moving. If `/odom` says zero but at least
two wheels counted within 0.6 s (fresh `encoder_health`, `packet_fresh`), the chip reads **"Moving · odometry not tracking"**
(warn). Stale, unreadable or single-wheel evidence leaves the old "Stopped". It can only turn "Stopped" into a warning.
It does not touch E-STOP, command gating, the Stage 21 detector, the consensus rule or any threshold.

**Measured on the recording (10 Hz samples):** wheel-moving samples flagged: current rule 668/898 (74%), new rule 898/898
(100%). False flags at true rest: 0 of 252 (start and end windows). About 6% of non-moving samples are flagged within 0.6 s
after motion ends (coasting tail).

## 12. Regression tests

| Suite | Result |
|---|---|
| New `tests/test_motion_status.py` (7 tests, node, recorded frames) | pass |
| `tests/test_atlas_web_v2.py` (+ `motion-status.js` servable) | pass (14 with the above) |
| `tests/test_status_web_estop_safety`, `test_encoder_packet_timing`, `test_status_web_smart_panels` | 21 pass |
| `scripts/test_encoder_selection`, `test_web_diagnostics` | 40 pass |

`test_defect_reproduced_by_legacy_logic` shows the pre-fix logic returns "Stopped" for the three recorded blind frames
(253.95 s, 304.67 s, 397.37 s). Fixtures are copied values (`tests/data/stage25_motion_frames.json`), not synthesised.
I did not run old direct-serial steering tests.

## 13. Minimal deployment package and rollback (NOT deployed)

`tools/deploy/stage25_motion_chip/`: `apply.sh`, `rollback.sh`. Three static files; no service restart (V2 files are read
per request with `Cache-Control: no-cache`; a page reload picks them up).

- Expected live pre-state **verified read-only on the Jetson:** `shell.js` `6a843ec2…`, `index.html` `e0291f84…`;
  `motion-status.js` absent. `apply.sh` refuses anything else and writes a timestamped backup.
- **Rehearsed in a scratch copy:** apply → second apply refused → rollback → both files byte-identical to the originals.
- Post-fix hashes: `motion-status.js` `592daa69…`, `shell.js` `f05f6b81…`, `index.html` `61f3a12e…`.
- Live deployment needs a separate owner approval. Rollback: `TARGET=~/project_atlas/web/v2 ./rollback.sh`.

## 14. Unknowns requiring physical measurement

1. **Where ATLAS is.** Is it back at the start spot? AMCL and LiDAR odometry say ~4.3–4.8 m east of it. A tape measure
   from the start mark would settle it.
2. **M2 and M3 encoders.** Lift the wheels and turn each by hand forward and backward while watching its sign and count
   rate. Check the M2 connector and the quadrature wires, and what changed between 9 October and today.
3. **True wheel scale.** A tape-measured straight run, with working encoders, against the ~0.6 ratio.
4. **Ground truth at Hall** and the identity of the "crooked" front wall.
5. **Physical E-STOP tests are still not passed;** this loop also skipped the latch checkpoints.

## 15. Exact next deployment recommendation

1. **Do not deploy Candidate B and do not change consensus, CPR, scale or thresholds.**
2. **Repair or replace the M2 and M3 encoder channels** (item 2 above), then re-baseline with one short tape-marked
   straight drive.
3. **Optional now, on approval:** deploy the dashboard chip package (static, rehearsed, no restart). It makes the next
   encoder failure visible to the operator instead of reading "Stopped".
4. Re-evaluate Candidate B against the new healthy-encoder baseline.
5. **Open owner decision:** a degraded two-wheel odometry mode with inflated covariance. It would weaken the fail-closed
   policy, so I propose it only after the evidence above and on the owner's explicit approval.

## 16. GitHub commit ID

(filled on push — see CHANGELOG)

## Files

- Offline source and tests: `project_atlas/web/v2/motion-status.js`, `shell.js`, `index.html`,
  `tests/test_motion_status.py`, `tests/data/stage25_motion_frames.json`, `tools/deploy/stage25_motion_chip/`.
- Analysis scripts (throwaway, paths fixed to the analysis sandbox, read-only): `tools/diagnostics/stage25_roundtrip/`.
- Jetson evidence (not committed): `~/project_atlas/data/diagnostics/stage25_20261015/` (event log, checksums, replay inputs
  and outputs, working copies).
