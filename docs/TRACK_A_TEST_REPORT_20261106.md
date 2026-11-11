# Track A test report — 2026-11-06 (software only)

Environment: Jetson Orin Nano Super (100.87.208.71), ROS 2 Humble, Python 3.10, NumPy 1.21.5, OpenCV 4.5.4.
Tests ran in throw-away folders under /tmp (removed afterwards). The production ROS domains 0 and 77 were not
used; the end-to-end test ran in isolated, localhost-only domain 91. No camera, motor, actuator or service was
started. The production `nav2_params.yaml` was byte-identical before and after (sha256 prefix `2411371c89751eba`).

## Automated tests: `tests/test_track_a.py`, 25 / 25 PASS

| Group | Tests | Result |
|---|---|---|
| Config gate: shipped config refuses unmeasured mount; implausible / NaN / bool / string values; height band, ranges, frame, resolution, stale and valid-fraction bounds | 4 | PASS |
| Calibration gate (real `tools/vision3d/calibration_validation.py`): missing file; not validated; no evidence; serial, size, frame, source mismatch; malformed K; valid doc accepted | 3 | PASS |
| Geometry (ray-cast synthetic depth): wall at 1.5 m within 2 cm; floor only gives no obstacles; ceiling above rover ignored; 10 cm box detected; < 0.35 m and > 3 m ignored; 15° tilt; side offset + yaw; optical rotation equals the launch file's static TF chain | 8 | PASS |
| Invalid data: NaN / ±inf / 0 never become obstacles; mixed valid and invalid; blinded camera gives BLINDED (no scan); stale, NaN, inf and negative ages give STALE; wrong shape / encoding raise | 5 | PASS |
| Nav2 merge against the LIVE `nav2_params.yaml` copy: all 13 checks pass (LiDAR layer byte-identical, separate astra_layer, inflation last, global costmap unchanged); validator rejects `inf_is_valid:true` and a dropped LiDAR layer | 2 | PASS |
| ROS end-to-end (real node, synthetic publisher, domain 91): fresh frames give scans (base_link, 1.5 m); 10 Hz cap; blinded gives no scan + BLINDED; 2 s-old frames give no scan + STALE; publisher stopped (camera loss) gives no scan + STALE; preflight exits 78 on the shipped config, 0 on a valid one | 3 | PASS |

Extra checks: the launch file refuses domain 0 and builds (4 actions, not executed) in domain 77 with a valid
config; refuses on unmeasured mount. Shell syntax OK for all deploy scripts. Python compile OK.

## Performance on the real Jetson (scanner core, synthetic 160x120 frames, 10 Hz, nice 10, 30 s)

| Metric | Value |
|---|---|
| Per frame | median 7.2 ms, p95 15.1 ms, max 25.4 ms |
| Scanner CPU | 5.6 % of one core = **0.94 % of the Jetson** |
| Whole Jetson during run | 60.3 % (limit 75 %) |
| RAM | 36 MB RSS, **0.0 MB growth** over 3,000 further frames |
| Astra depth driver (measured 5 Nov) | about 1 % of the Jetson |

NOT TESTED on hardware: the real Astra driver in this pipeline, the domain_bridge (not installed), the bridge's
domain-0 join spike (gate G3), and the Nav2 costmap behaviour with the real layer (gates G4/G5).

## Deployment run (2026-11-06 16:36)

- Owner installed `ros-humble-domain-bridge` (apt).
- `install.sh` run from bundle `~/ATLAS-track-a`: files in place, units registered as *static* (no [Install]), NOT enabled, NOT started. Backup `track-a-backup-20261106-163609`.
- `verify.sh`: files PASS, domain_bridge PASS, Nav2 merge dry-run PASS, nav2_params.yaml unchanged; G1/G2 BLOCKED (no calibration, mount unmeasured).
- Early-start test found a defect: `ExecStartPre` refusal was retried by `Restart=on-failure` (RestartPreventExitStatus only covers the main process). Fixed with `ExecCondition`; retest: unit skipped, 0 restarts, inactive.

## Factory-calibration integration run (2026-11-06 evening)

Changes:
* Intrinsics now come from the driver's runtime CameraInfo; see `TRACK_A_FACTORY_CALIBRATION.md` (device stored
  calibration reads all-NaN; the driver's nominal model is used and labelled as such).
* Mount values from owner records:
  * x = 0.13 (candidate);
  * y = 0.0 (prior);
  * z = 0.30;
  * pitch = +0.8 nose-down;
  * max_height = 1.0 m (engineering bound, not a rover height).
* Range-growing floor cut: 4 cm + r·tan(1°).
* Driver respawn in the launch.
* Bridge: parked interlock, Restart=no, binary run directly.
* Nav2 snippet: `expected_update_rate: 0.0`, so the LiDAR stays independent of the Astra.

### Automated: 32 / 32 PASS on the Jetson (isolated domain 91; live nav2_params read-only, hash unchanged)

New tests:
* Runtime calibration:
  * the recorded driver CameraInfo is accepted;
  * IR inf, all-NaN (as the device params), wrong size, wrong frame, implausible fx, fx/fy mismatch, off-centre
    principal point, skew, and large or unsupported distortion are all rejected;
  * the scanner refuses to run without a calibration.
* Shipped config values and their provenance labels.
* Null mount values are refused.
* No phantom floor with depth noise (σ = 1.5e-3·z²) and a configured-vs-true pitch error of −2.6°, 0°, +1.0° and
  +1.5° (5 seeds each).
* Detection limits.
* End to end:
  * no CameraInfo gives no scans;
  * a valid CameraInfo gives scans;
  * a NaN CameraInfo mid-run stops scans;
  * a valid CameraInfo again recovers;
  * ranges are only finite or +inf.
* Bridge interlock: parked, moving, stale and missing telemetry.
* Nav2 validator rejects a currency check on the Astra source.

Measured detection limits with the configured pitch (10 noise seeds each):
* 10 cm objects: 10/10 out to 2.4 m, 2/10 at 2.6 m, 0/10 at 2.8 m.
* 15 cm objects: 10/10 out to 3.0 m.

If the camera really pitches 1.8° up (the old depth hint), a 15 cm object at 1.0 m is still seen, but a 10 cm object
at 2.0 m is missed.

### Parked shadow run on the real Astra (domain 77, no bridge, nothing consuming the scan)

Preconditions:
* cmd_vel 0/0, motor speed 0;
* Nav2 inactive;
* Track A units inactive;
* camera free.

| Check | Result |
|---|---|
| Calibration loaded at runtime | FACTORY_DRIVER_CAMERAINFO, fx = fy = 142.586, cx 79.5, cy 59.5, D = 0, nominal = true |
| Scans | 192 in 30 s (6.4 Hz; the driver delivers about 6-7 fps at this setting), frame base_link, 120 bins |
| Timestamps | scan age vs ROS clock: median 11 ms, max 155 ms (stale limit 500 ms) |
| Data validity | 0 NaN or negative ranges, 0 ranges outside 0.35-3.0 m; centre-bin jitter 3.3 mm std |
| TF | base_link->astra_link (0.130, 0.000, 0.300), pitch 0.8 deg; astra_link->astra_depth_optical_frame standard optical rotation |
| Scene | Structures at 0.89 m (left, 0.38-0.44 m high) and 1.9-2.5 m (0.12-0.97 m high); a horizontal surface about 0.42 m above the floor (furniture underside). No points lie on a floor plane. No floor was visible (only 1 % of the bottom rows had depth), so the pitch/height cross-check is NOT done. |
| Driver killed (SIGKILL) | Scans stopped at once, status STALE; launch respawned the driver; OK again with scans at 6.1 Hz |
| CPU / RAM | Whole Jetson 62.4 % (baseline 62.5 %); driver 0.63 % and node 1.34 % of the Jetson; RSS driver 84 MB, node 62 MB; growth over 30 s under 0.6 MB |
| Production services | 34 active atlas units: identical PIDs and restart counts before and after; nav2_params hash unchanged |

### Bridge, domain-0 join (gate G3) with the rover parked

* **Join spike:** 0.5 s samples went 72, 99, 100 … 96, 85, then back to 62 % baseline. That is about 7 s near 100 %
  with `ros2 run`; with the binary run directly it is about 4.5 s.
* **Any new participant causes it:** a minimal rclpy node joining domain 0 caused about 3.5 s at 100 %. Fast DDS
  simple discovery runs among all production nodes, so this cost is not specific to Track A.
* **LiDAR rate:** observed rate dipped from 1.86 to 1.58 Hz in the window that included the spike.
* **Delivery into domain 0:** 6.9 Hz, median age 12 ms, max 0.98 s, 0 NaN; bridge RSS 43 MB.
* **Production services:** unchanged.
* **Result:** the original G3 criterion (CPU < 75 % through the join) is **not met**.
* **Mitigation implemented:** the bridge unit starts only when `atlas_astra_bridge_parked_check.py` confirms that
  cmd_vel, motor speed and odom are zero and fresh, and it has `Restart=no`. So it can never join, or rejoin, while
  driving.

### Not done (needs separate authorization or physical access)

* G4: floor-plane pitch/height check (needs open floor in view).
* G4: tape-measured box position check.
* G4: 10-minute empty-view phantom check.
* G5: live Nav2 integration and supervised driving.

## G4 shadow checks on the parked rover (2026-11-11, owner present)

The installed unit `atlas-astra-obstacles` was started by hand in domain 77 only, and stopped after each check.
* Not touched: the bridge, Nav2 and boot settings.
* Every run: ExecCondition preflight OK, calibration FACTORY_DRIVER_CAMERAINFO (nominal), 0 restarts, clean stop.
* Tool: `tools/track_a/g4_shadow_check.py`.

| Check | Result |
|---|---|
| Floor-plane pitch/height | **NOT POSSIBLE here.** The floor returns no depth: the bottom 15 % of the image is empty, and the far wall appears mirrored up to 0.39 m below floor level (glossy floor). A matte sheet laid in front made no difference. The constrained fit was unreliable (265 inliers, impossible camera height), so no pitch or height value is claimed. |
| ~~Supporting evidence~~ RETRACTED | Table legs' lowest *visible* points measured z = -0.9 cm. The box test below shows the bottom of the view is cut off, so these were not the floor contact. This is not evidence for z or pitch. |
| Box at a tape-measured spot | **NOT DONE** (no box placed). |
| 10-min empty view (22:22-22:33, owner confirmed nobody entered) | 4036 scans, 6.73 Hz, status OK 600/600 (no STALE/BLINDED), stable-scene jitter 7.4 mm median. Hits nearer than the stable scene in 191 scans (4.7 %), in two clusters: (1) about -14 deg at 1.30 m: the table edge flickering at a bin boundary (real object). (2) +5 to +12 deg at 0.70-0.72 m, 44 hits, intermittent: a straight line at about 0.45 m in front of the bumper, where the sheet's near edge lies. Probably the sheet edge or near-range noise; **unexplained, so not a clean PASS.** |
| Resources (10 min) | Whole Jetson 62.6 % CPU (baseline 61-62 %), Tj 63.5 -> 63.9 C |
| Production | 34 units: identical PIDs and restart counts; nav2_params hash 2411371c89751eba unchanged; Astra and bridge off afterwards, nothing left running |
| 10-min empty view, RERUN without the sheet (22:35-22:45) | 4075 scans, 6.79 Hz, status OK 600/600, stable-scene jitter 1.8 mm median. **The 0.70 m line is gone, so it was the sheet's edge.** Hits nearer than the bin median, max 3 bins per scan, only at the edges of real objects already in the stable scene: -15/-14 deg at 1.25-1.31 m (table edge; stable scene -14 deg 1.30, -16 deg 1.15) and +27/+28 deg at 1.72/2.44 m (object at the left FOV edge; stable scene +26 deg 1.69). These are edge bins switching between the object and the wall behind it. **No detections anywhere without a real object: PASS (no phantom obstacles).** CPU 62.8 %, Tj 63.8 -> 64.0 C, 0 restarts, 34 production units identical, nav2_params unchanged, Astra and bridge off afterwards. |

G4 status after 2026-11-11:
* Empty view: **PASS**.
* Box at a tape-measured spot: **open**.
* Floor-plane pitch/height: **not possible on this glossy floor** (needs a matte floor area, e.g. a rug, in view). Table-leg evidence supports z and pitch near range.
* G5 (Nav2 integration) not applied.

### Box test (2026-11-11 23:06, owner-placed box: front face 1.00 m from the front bumper, centred; 23.5 x 19.3 x 10 cm)

Expected front face x = 1.25 m in base_link (front edge +0.25 m from the axle midpoint, owner record).

| Measure | Result |
|---|---|
| Detection | **101 / 101 scans (100 %)**, steady: range std 0.3 mm |
| Range (scan, centre bins) | **1.140 m vs 1.25 expected: -11.0 cm. FAIL** (limit 3 cm) |
| Range (depth points, front face) | 1.136 m (-11.4 cm) |
| Width | 0.189 m in scan, 0.184 m in depth vs 0.193 true (good: lateral geometry and nominal intrinsics consistent) |
| Lateral position | bins -3.9 to +5.1 deg, face centre y +1.7 cm (centred within placement accuracy) |
| Height | box face computes at z -0.055..+0.069 m; the true top is 0.235 m. Top computed **16.6 cm too low** at 1.01 m from the lens |

**Diagnosis: the configured pitch (+0.8 deg nose-down) is wrong by about 8-9 deg; the camera actually points nose-UP.**
Three independent measurements agree:

| Measurement | Implied pitch error |
|---|---|
| Box top 16.6 cm low at 1.01 m | 9.3 deg |
| Far wall leans back in computed coordinates (dx/dz 0.14) | 7.9 deg |
| Wall base appears 0.39 m below the floor at 2.55 m | 8.7 deg |

The "wall below the floor" seen earlier was this pitch error, not only floor gloss. The pitch error alone explains about -3 to -4 cm of the box range error. The remaining about -7 cm points to the x = 0.13 m candidate (or the front-edge record) being off.

Safety effect of the current config: points compute too low by about 15 cm at 1 m and 31 cm at 2 m. So:
* Low obstacles are MISSED. The box was seen only because its upper part cleared the floor cut.
* The floor never turns into phantoms, which matches the empty-view PASS.

**The current config is NOT acceptable for G5.** No config was changed; Astra and bridge OFF; 34 production units identical; nav2_params unchanged.

### Re-test after the owner re-levelled the camera (2026-11-11 23:16; box turned so a side shows)

| Measure | Result |
|---|---|
| Pitch from the far wall's lean (independent of the box) | lean dx/dz 0.019, so the configured pitch is off by 1.1 deg. **Estimated true pitch -0.3 deg (level within about 1 deg)**, matching the owner's "set to 0". Before: about 8-9 deg nose-up. |
| Wall bottom | lowest computed point -0.14 m (was -0.39 m); remaining part is consistent with floor mirroring |
| Box (turned) | detected in **70 / 70 scans**, range 1.14 m (nearest corner) to 1.20 m across -4..+4 deg |
| Distance | still **about 11 cm short** of 1.25 m expected. With pitch now about right, this is an **x offset**: the Astra puts the box 1.01 m from its lens, so the lens is about 1 cm behind the bumper point the owner measured from. Config assumes 12 cm (x = 0.13, derived). Box-derived x is about 0.24 m. |
| Extra object | something at 0.73 m, 17-31 cm left, 18-43 cm high (not in the centre bins) |

Config NOT changed (pitch 0.8 and x 0.13 still in `astra_obstacles.yaml`). Astra and bridge OFF; nav2_params unchanged.

### Forward-position change withdrawn; geometry review (2026-11-11 23:22)

* `x_m` 0.24 was installed at 23:21 and **reverted to 0.13** after the owner asked for geometry verification first.
* `pitch_deg` stays 0.0 (owner re-levelled; wall lean -0.5 deg).
* Backup of the pre-change file: `track-a-backup-20261111-232112-mount`.
* 32/32 tests pass on the installed copy.

The 0.24 m estimate was wrong in method. It compared the turned box's nearest corner (1.139 m) and ignored the -3.7 cm
the old pitch error added in the square-face test. Corrected, the square-face test gives lens -> face about 1.04 m.
So the lens is about 4 cm behind the bumper, and x is about 0.21 m. That holds only if bumper -> face was 1.00 m and
the front edge is at +0.25 m. **Not adopted.**

Measurement at 23:22 (tilt 0 configured; box turned about 20-25 deg; same position):

| Measure | Result |
|---|---|
| Wall lean | 0.5 deg (pitch about level) |
| Box detection | 100/100 scans, range std 0.8 mm. The range sweeps 1.206 to 1.139 m across -4.4..+3.6 deg because the face is angled, so it is not comparable to a front-face distance. |
| Box face depth from the lens (optical) | 1.03-1.04 m |
| Box top surface | 0.163 m vs 0.235 m: **-7.2 cm** |
| Lowest visible box point | -5.6 cm (below the floor, impossible) |

Both height readings are offset by about -6 to -7 cm at 1.02 m. That means one of:
* the lens is about 0.23 m high rather than 0.30 (possibly changed by the re-level);
* the camera is tilted about 4 deg up.

The wall lean (0.5 deg) favours the height explanation. Not resolvable without a tape measurement.

Object at 0.73 m (23:16, 17-31 cm left, 18-43 cm high): **absent at 23:22**, so it was transient (most likely the owner
adjusting the box or camera at that moment). Unconfirmed.

**Needed from the owner (tape):**
* A: bumper -> box front face, with the box square-on and upright.
* B: Astra lens -> box front face.
* C: Astra lens centre height above the floor.

B - A gives the lens-behind-bumper offset (x_m = 0.25 - offset; +x forward, REP-103, origin = floor point at the axle
midpoint). B is also a direct check of the factory depth scale. C settles the height-vs-pitch question.

### Box retest with owner tape values (2026-11-11 23:41; config x 0.21, z 0.23, pitch 0.0)

Owner tape:
* A: bumper -> box face 1.00 m.
* B: lens -> box face 1.04 m.
* C: lens height 0.23 m.

Config backup: `track-a-backup-20261111-234037-tape`. 32/32 tests pass.

| Criterion | Before (0.13 / 0.30 / 0.8 deg) | After (0.21 / 0.23 / 0.0 deg) | Verdict |
|---|---|---|---|
| Distance, face centre (straight-ahead bins -0.9..+0.6 deg) vs 1.25 m | 1.14 m (-11 cm) | **1.238-1.250 m (-1.2..0.0 cm)** | PASS |
| Depth scale: Astra lens -> face centre vs tape B 1.04 | n/a | **1.034 m (-0.6 cm)**, independent of the config | PASS |
| Repeat stability | 101/101 | **205/205 scans over 2 runs, std <= 1.1 mm, runs identical to 1 mm** | PASS |
| Box top height | -16.6 cm (upright 0.235) | **0.101-0.103 m**: matches **0.10 m if the box lies flat**; would be -13 cm if upright | PASS if lying flat (owner to confirm) |
| Tilt (far-wall lean, independent of the box) | ~8-9 deg up | **0.0 deg** | PASS |
| Unexplained obstacles | object at 0.73 m (transient) | none. Every scan cluster is a known object: right table (-22..-13 deg, 0.97-1.39 m), wall (2.67-2.93 m), box (-3.9..+5.1 deg, 1.22-1.29 m), left table/stool (+13..+22 deg, 1.06-1.64 m) | PASS |

Notes:
* The box face is angled about 20 deg: range 1.289 m at -3.9 deg to 1.219 m at +3.1 deg. So the comparison uses the
  straight-ahead (face centre) bins, as the tape was taken straight ahead.
* Below the floor the depth image shows the box's mirror image (glossy floor). These points are below the floor cut
  and never become obstacles.
* The expected 1.25 m still relies on the +0.25 m front-edge record. x 0.21 is derived from A and B, so the distance
  PASS is partly circular. The truly independent checks are the depth scale (tape B vs Astra, -0.6 cm), the height
  and the tilt.

Production: 34 units identical, nav2_params unchanged, Astra and bridge off after the test.
