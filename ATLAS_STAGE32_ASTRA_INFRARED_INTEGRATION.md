# ATLAS Stage 32: Astra Pro Infrared, Calibration and XYZ Point Cloud

Branch `agent/sync-developer-20261011`. Baseline `2c4adbf` (Stage 31B live). Stage 32 and its addendum are one assignment, and this is the single report for both.

**21 October handover reconciliation:** A1 deployment, one A2 IR attempt and A4 read-only metadata queries had already occurred on the Jetson, although they were missing from Git. Section 15 records recovered evidence and supersedes the original offline-only status below. No camera session or deployment was repeated during this reconciliation.

## Status

| Label | Status | Basis |
|---|---|---|
| IR CAPABILITY VERIFIED | PARTIAL | Driver logged IR 320x240@30 started; Dashboard delivery remains unverified. |
| IR DRIVER IMPLEMENTED | YES (launch arguments only) | The pinned driver already publishes IR. The runtime now requests it per mode. No driver rebuild. |
| IR IMPLEMENTED | YES (offline) | Receiver, raw route, viewer and mode matrix are in place. |
| IR OFFLINE TESTED | YES | 14 unit tests and a synthetic browser test. |
| IR LIVE VERIFIED | **FAILED delivery revalidation** | Separately approved instrumented attempt received zero IR frames before Stop; section 16. |
| IR DASHBOARD DEPLOYED | **YES** | A1 recovered installation and ten live package hashes verified. |
| DEPTH REGRESSION PASSED | Offline only | Depth and Depth+RGB launch arguments are byte-identical to `abf375b` (test). No live rerun. |
| CALIBRATION PREPARED | YES | Guided checkerboard and physical-validation tooling, gate and procedure. |
| CALIBRATION VALIDATED | **NO** | Factory parameters read as NaN. No calibration file exists. |
| DEPTH ACCURACY VERIFIED | **NO** | No physical targets measured. The 2.721 m reading is uncalibrated and single-point. |
| XYZ CLOUD IMPLEMENTED | YES (offline) | Back-projection, PointCloud2 node, viewer panel, gate. |
| XYZ CLOUD LIVE VERIFIED | **BLOCKED** | Calibration invalid. The node refuses to start, by design. |
| RGB REGISTRATION VERIFIED | **NO** | Not attempted. XYZRGB stays off. |
| 3D VIEWER READY | YES (offline, gated) | Orbit, pan, zoom, reset, axes, point count, FPS, measurement, calibration status, Cloud ON/OFF. Disabled until calibration is VALIDATED. |
| 3D VIEWER DEPLOYED | **YES, gated** | Installed by A1; stays disabled until validated calibration. |

## 1. IR stream compatibility

**Source facts** come from the pinned driver `ros2_astra_camera` f7e71d9, already deployed:

- IR is opened as OpenNI `PIXEL_FORMAT_GRAY8` and published as `mono8` on `/astra/ir/image_raw`, with `/astra/ir/camera_info`.
- IR and OpenNI colour exclude each other only when `use_uvc_camera` is false. The Astra Pro uses UVC colour, so RGB+IR is not excluded by the driver. It may still be refused by the firmware or the USB bus.
- Mode negotiation tries three things in order:
  1. the exact mode;
  2. otherwise, the same resolution and format at another frame rate;
  3. otherwise, the stream is disabled and the driver logs "Supported video modes".

  A bad IR request therefore produces no IR. It never produces substituted data.
- The vendor `astra_pro` launch enables depth, IR and colour together at 640x480@30. That shows the driver allows the combination. It does not show that this camera, firmware and Jetson USB bus sustain it.

**What was built:**

- **Runtime** (`atlas_vision3d_runtime.py`) has these modes:

  | Mode | Streams | State |
  |---|---|---|
  | `depth` | depth | verified (Stage 31B) |
  | `concurrent` | depth + RGB | untested |
  | `ir` | IR | untested |
  | `ir_depth` | IR + depth | untested |
  | `rgb_ir` | RGB + IR | untested |
  | `depth_cloud` | depth + XYZ node | blocked until calibration |

- **IR arguments** are added only when IR is requested: 320x240@30. Depth and Depth+RGB argument lists are byte-identical to Stage 31B, and a test proves it.
- **Driver output** goes to a bounded log (2 MB cap). After each session the runtime stores only the mode-negotiation lines as `driver_negotiation`. The first live IR session therefore records the camera's real supported-mode list, even if IR fails.
- **RGB+IR+Depth** is not offered. Nothing demonstrates it, and the owner asked not to promise it.
- **Receiver** (`atlas_vision3d_web.py`, domain 77):
  - subscribes IR only while a session runs;
  - accepts only native intensity encodings (`mono8`, `mono16`, `16UC1`) and rejects anything else (test);
  - serves `GET /api/vision3d/raw?kind=ir` with the camera's bytes unchanged plus width, height, encoding, step, endianness, stamp and frame headers. It offers no raw route for any other stream (test).
- **Display:**
  - The browser draws the IR frame in grayscale, stretching between the 2nd and 98th percentile of that frame.
  - The page states the stretch: "Display stretched from raw *lo* (black) to *hi* (white); the camera's values are not changed".
  - Clicking a pixel shows its raw value.
  - IR is never derived from RGB or depth. There is no code path that could do so, and if IR is absent the panel says so.

**Live result: not run.** Approval A2 covers it.

## 2. Factory calibration investigation

Earlier work, Stage 30 and `ATLAS_ASTRA_PRO_CALIBRATION_AND_POINTCLOUD_VALIDATION.md`:

- The driver's `OBEXTENSION_ID_CAM_PARAMS` (property 14, 120 bytes) returned rc 0 and all NaN.
- `.ros/camera_info` holds no calibration file.
- The driver's FOV-derived default CameraInfo is **not** a calibration, and the gate rejects it.

Stage 32 adds three findings from source review:

- The driver caches property results without checking the return status.
- `isValidCameraParams()` checks only four intrinsics.
- Neither finding proves why the device returns NaN.

Methods still open, all read-only and none run in this stage:

| Method | Needs | Risk |
|---|---|---|
| Device serial + firmware version query (OpenNI device properties) | camera powered, no streams; approval A4 | read-only |
| Supported-property enumeration for this USB PID (0x0403) | same session as A4 | read-only; no other model's structures |
| Vendor calibration file shipped with this exact serial | owner check of any Orbbec download or box media | none |

Not done, deliberately: other models' parameter structures, repeated property-14 requests, firmware upgrade or flash, any property write.

**Conclusion:** factory recovery is unlikely but not exhausted. The guided route below does not depend on it.

## 3. Guided calibration procedure (prepared, not run)

### Tooling

- `tools/vision3d/checkerboard_calibration.py` handles the maths, offline:
  - `CornerSet` keeps checkerboard **corner coordinates only**. No images are kept.
  - `calibrate()` runs OpenCV `calibrateCamera` on the training views and then checks reprojection on held-out views.
  - It returns `CANDIDATE` only if training RMS ≤ 0.5 px, held-out RMS ≤ 0.8 px, image coverage ≥ 60%, and there are at least 12 training + 3 held-out views. Otherwise it returns `REJECTED` with the reasons.
  - `derive_resolution()` maps IR intrinsics to the 160x120 depth image by explicit pixel-centre scaling, plus an optional measured offset. The result stays unvalidated.
  - `attach_validation()` sets `VALIDATED` only when all of these hold:
    - at least 2 distinct distances pass, each with median axial error ≤ max(10 mm, 1%) and invalid pixels ≤ 10%;
    - a plane fit on the calibrated cloud passes, with RMS ≤ max(5 mm, 0.5%) and distance within the same limit.
- `scripts/atlas_vision3d_geometry.calibration_state()` is the only gate for metric XYZ. It requires all of the following:
  - a file at `config/astra_calibration/depth_160x120.json`;
  - `tools/vision3d/calibration_validation` passes, meaning: matching device serial, source `measured_target` or `factory_verified`, `independently_validated`, exact 160x120 resolution and `astra_depth_optical_frame`, `plumb_bob` model, and finite K and D;
  - files of at most 16 KB.
- The manifest currently has no `device_serial`. Even a well-formed file is therefore rejected until approval A4 records the real serial. This is fail-closed by intent.
- Tested offline:
  - a synthetic checkerboard recovers known K within 0.2%;
  - a poor-coverage set (0.52) is rejected;
  - the validation rules are tested.
- The same tests pass on the Jetson under Python 3.10 with OpenCV 4.5.4 and NumPy 1.21.5.

### What the owner supplies

1. **Checkerboard:** printed flat on A3 or A4, mounted rigid (foam board or glass), matte paper.
   - Report the **inner-corner count** (for example 9x6).
   - Report the **square size measured with a ruler across 5 squares**, divided by 5, to 0.1 mm.
2. **Flat matte target:** a wall or large board, roughly perpendicular to the camera.
   - Tape-measure **from the Astra front face** to the target at **1.00, 1.50 and 2.00 m**, and optionally **2.72 m**.
   - Report each measured value to the millimetre.
3. During capture, the owner moves the board through about 20 poses. Cover the corners and edges of the image, tilt ±30°, and use distances of 0.5 to 1.5 m. The rover stays still with E-STOP latched.

### Capture sessions

Each session needs approval A5.

- **IR-only viewer session.** Corners are extracted live and only corner coordinates are kept. If the IR image is too dark for corner detection, the procedure stops and reports. The IR projector (laser) speckle can defeat detection, but the driver's `set_laser_enable` service exists. Turning the laser off for capture would be a separate, explicit request; it is not part of A5 as written.
- **Depth-only session** at each tape-measured distance. Only per-distance statistics are kept: median, bias, median absolute error, spread (IQR) and invalid rate over a central region of interest. Plane-fit statistics come from the candidate calibration.
- **Result:** a calibration JSON with the full validation record, committed for owner review **before** it is installed on the Jetson.

## 4. Depth accuracy

**Not measured.** The Stage 31B reading of 2.721 m is an uncalibrated single click. It says nothing about intrinsics, distortion or 3D accuracy. The procedure in section 3 reports bias, median absolute error, spread and invalid-pixel rate per distance.

## 5. Intrinsics and extrinsics validity

| Item | State |
|---|---|
| Depth intrinsics (fx, fy, cx, cy) | invalid (NaN factory; none measured) |
| Depth distortion | invalid |
| Resolution and frame | 160x120 `astra_depth_optical_frame` (observed live in Stage 31B); the gate requires an exact match, with no implicit scaling |
| Depth scale | driver publishes `16UC1` millimetres (observed); accuracy unverified |
| RGB intrinsics | not measured; needs a separate RGB checkerboard pass (same tool, RGB frame) |
| RGB-to-depth extrinsics | not measured; needs a stereo pass or a verified driver registration |

## 6. XYZ PointCloud2

**Implemented offline in `scripts/atlas_vision3d_geometry.py`:**

- Pinhole back-projection with iterative `plumb_bob` undistortion. Undistorted rays are computed once per calibration and cached for one calibration only (see section 9).
- X right, Y down, Z forward, in metres, in `astra_depth_optical_frame`.
- Accepts `16UC1` millimetres or `32FC1` metres.
- Discards 0, 65535, NaN, values ≤ 0 and values beyond 8 m.
- Uniform stride sampling to at most 6,000 points.
- Rejects a resolution or frame mismatch.
- PointCloud2 layout: x/y/z float32, little-endian, `point_step` 12, dense, unorganized. A plane-fit helper supports validation.

**Node** `scripts/atlas_vision3d_cloud_node.py`:

- It runs only as a child of the viewer worker in `depth_cloud` mode.
- It exits with "CALIBRATION BLOCKED" unless `ROS_DOMAIN_ID=77` and the calibration is VALIDATED.
- It subscribes to `/astra/depth/image_raw` and publishes `/astra/points` (best effort, depth 1), at most 5 Hz.
- It reuses the depth image's own header, so stamp and frame are those of the source depth image.
- No other publishers, services or files.

The worker also refuses `depth_cloud` before admission while the calibration is invalid, and kills the node on stop or failure. The receiver's `cloud()` and `pixel()` XYZ require the same VALIDATED calibration.

**Uncertainty:** the error will be documented from the validation record of the measured targets. None exists yet.

**Tests** (synthetic; they prove the maths, not the camera):

- a wall at 2 m gives a plane at 2 m with the correct axes;
- pixel-to-point association;
- invalid filtering;
- tilted-plane recovery;
- distortion round-trip;
- cached rays equal direct undistortion;
- resolution and frame mismatch rejected;
- PointCloud2 layout.

**Live: BLOCKED** until calibration is VALIDATED.

## 7. XYZRGB

Not started, by the rule in the addendum. Prerequisites:

1. a validated XYZ cloud;
2. RGB intrinsics;
3. RGB-to-depth extrinsics, verified by reprojecting checkerboard corners across both cameras with a stated pixel error.

The driver's `enable_colored_point_cloud` stays `false`.

## 8. Vision Lab viewer (synthetic results)

The `/v2/vision3d` changes are additive, and the Home layout is untouched.

- **Mode selector:** Depth (Tested), Depth + RGB, Infrared, Infrared + Depth, Infrared + RGB (all "Not yet tested"), and Depth + 3D cloud (disabled, "Needs calibration"). A mode becomes "Not supported" automatically when the manifest marks it so after a failed live test.
- **Infrared panel:** live chip, FPS and age, native-resolution canvas, stretch statement, raw-value probe.
- **Controls:** Start, **Pause preview** (keeps the last picture while the camera runs) and **Stop camera**.
- **3D point cloud panel**, now in the main view:
  - calibration status line;
  - chip shows "Blocked" until VALIDATED;
  - Show cloud toggle stays disabled;
  - orbit (drag), pan (Shift or Pan mode), zoom (wheel or buttons), Reset view;
  - axes legend; points drawn of total, stride and frame; click a point for XYZ;
  - at most 6,000 points.

Headless Chromium against the local simulator (`tools/vision3d/stage32_browser_test.py`; evidence in `evidence/stage32_offline/`) passed every check:

- depth_cloud disabled;
- IR selectable;
- IR drawn at native 320x240;
- stretch spans 0–255;
- probe returns the raw value at a known pixel (252 at u=316, 0 at u=1);
- cloud gated ("Blocked", toggle disabled, reason shown);
- Pause preview holds the frame, which resumes after unpausing;
- no page errors;
- no horizontal scroll at 390 px.

Screenshots use synthetic gradients only; no room imagery.

## 9. CPU, RAM, thermal (profiled separately; camera off)

The Jetson figures come from a camera-off probe on the Jetson: nice 19, pure Python, two runs. Evidence is in `evidence/stage32_offline/jetson_compute_probe.json`.

| Workload | Per frame | At rate | Note |
|---|---|---|---|
| IR receive + raw serve (status-web Python) | 0.02 ms | negligible | stores a reference; excludes rclpy deserialization of 76.8 kB |
| Browser IR stretch 320x240 | 2.7–3.4 ms (PC Chromium) | ~6 ms/s at 2 Hz | not measured on the Jetson HMI browser |
| Back-projection, plumb_bob, **before** fix | 51.7–52.1 ms CPU | 26% of one core at 5 Hz | rejected |
| Back-projection, **after** ray table (steady) | 6.95–7.07 ms CPU | ~3.5% of one core at 5 Hz | first frame 60–62 ms (one-time) |
| PointCloud2 pack, 6,000 points | 2.25–2.3 ms | ~1.2% of one core | |
| Receiver cloud parse, 6,000 points | 7.4 ms (PC) | estimated ~4–5% of one core at 2 Hz on the Jetson | estimate, not measured |
| Probe RSS | 13–15 MB | | |

**Not measured:**

- driver CPU with IR enabled;
- USB bandwidth;
- the extra rclpy process for the cloud node (import and spin baseline);
- thermal under IR.

The Stage 31B baseline (depth only, guard 63.7–71.1% against a 75% limit) leaves about 4 points of headroom at the worst sample. **IR+Depth or Depth+cloud may be stopped by the guard. That is the guard working, not a fault to tune away.** Limits, the window and fail-closed behaviour are unchanged, and no grace period was added.

## 10. USB and stream stability

Not tested. The first live IR session reports the frame count, maximum gap, stamp regressions and the driver's negotiation lines.

## 11. Pi Camera 3 regression

No Pi Camera file, service or unit was changed. The `atlas-camera` identity is checked before and after apply by the deploy script.

The full suite collects 1,030 tests: 1,023 pass, 5 are skipped and 2 fail. Neither failure is caused by Stage 32:

- `test_atlas_safety_status_camera_heartbeat…same_success_path` fails identically at `2c4adbf` with Stage 32 changes stashed. It is a pre-existing Pi camera heartbeat test failure, not caused or touched here.
- `test_protected_safety_files_untouched` flags any uncommitted change under `config/` (here `vision3d_live.json`). It clears once committed.

The Vision Lab suites give 185 passed and 3 skipped.

## 12. Deployment package and rollback (prepared, not applied)

`project_atlas/tools/deploy/stage32/stage32.sh apply|rollback`, run with `OWNER_APPROVED=yes`.

**It refuses unless:**

- E-STOP is latched;
- no driver, worker or cloud node is running;
- every replaced file equals the live Stage 31B hash. The live hashes were checked read-only today and equal `2c4adbf`.

**Apply:**

1. Parse and import check of the candidate with the Jetson's Python.
2. Backup with SHA256SUMS to `.pre_stage32_<stamp>`.
3. Atomic installs.
4. Restart of **rover-status-web only**. The receiver code is loaded in-process, which is why this stage needs a restart while Stage 31B did not.
5. Protected service identity comparison.
6. Prints calibration state and mode states.

Apply installs **no calibration file**.

**Rollback** restores every file, removes the four new files, and restarts rover-status-web.

**Rehearsed** on a copy of `2c4adbf`:

- refused without approval;
- applied;
- refused re-apply;
- rolled back to byte-identical files with the new files removed.

| File | Stage 31B (live) | Stage 32 |
|---|---|---|
| scripts/atlas_vision3d_runtime.py | 077edc29… | 454dd25f… |
| scripts/atlas_vision3d_web.py | 6b9a28c5… | 889881c0… |
| web/v2/vision3d.html | 47380d1b… | a930af83… |
| web/v2/vision3d.js | 05b83020… | 76f9a202… |
| web/v2/vision3d.css | 339e8102… | 04f98c8c… |
| config/vision3d_live.json | d815940f… | e27bc0c0… |
| scripts/atlas_vision3d_geometry.py | — | 75d02012… |
| scripts/atlas_vision3d_cloud_node.py | — | d2bfad1c… |
| tools/vision3d/calibration_validation.py | — | 9ca7f52c… |
| tools/vision3d/checkerboard_calibration.py | — | 132522ba… |

No autostart, systemd unit, driver binary or production-domain change.

## 13. Commits

- `2f91a3c`: Stage 32 implementation, tests, package, evidence and this report (offline; not installed).
- Baseline: `2c4adbf` (Stage 31B live).

## 14. Approvals needed (minimum, in order)

| # | Step | What happens | Stops on |
|---|---|---|---|
| A1 | Deploy Stage 32 package | `stage32.sh apply`, rover-status-web restart only, camera stays off | any refusal; rollback ready |
| A2 | One **IR-only** 60 s session | first real IR frames; driver negotiation captured; guard unchanged | no frames, guard stop, USB error. No retry. |
| A3 | Then, only if A2 passes: one **IR+Depth** session, then one **Depth+RGB regression** session | combination support and CPU/USB stability | first failure. Mode marked "Not supported". |
| A4 | Read-only device serial, firmware and supported-property query (no streams) | serial into the manifest; factory-recovery paths closed or found | any non-read operation is refused by design |
| A5 | Guided calibration: IR checkerboard capture (corners only) + depth statistics at the tape-measured distances | candidate, then validation record; nothing installed until reviewed | REJECTED quality gates |
| A6 | Install the reviewed calibration file and one **Depth + 3D cloud** session | first live `/astra/points`; flat-wall check on the live cloud | guard stop or validation mismatch |
| — | RGB intrinsics, extrinsics and XYZRGB | later, after A6 | |

From the owner, before A5:

- the checkerboard inner-corner count;
- the square size (ruler over 5 squares);
- tape-measured distances, Astra front face to target, at about 1.00, 1.50 and 2.00 m (and 2.72 m if wanted);
- whether the IR laser may be switched off during checkerboard capture (separate yes or no).

## 15. Recovered live handover evidence — 21 October 2026

This section supersedes the original deployment/approval status above. The prior
developer's live evidence was recovered without repeating A1, A2 or A4. The local
branch was fast-forwarded seven commits to `92a2bc3`; unrelated untracked work was
preserved. This continuation changed documentation only, not running software.

### A1 — installed and verified

`apply.txt` records installation at 15:56:09. All ten live SHA256 values match the
extracted `s32_deploy_pkg_2f91a3c.tgz` package and the Stage32 column in section 12.
Package SHA256: `d10121c306e8dd21208ab7e18fa7d2501b83925c4610e145b8626804fa11c992`.
Only the web owner was restarted by A1. Backup
`/home/jetson/project_atlas/.pre_stage32_20261021_155609` passes its SHA256SUMS
verification. Use the existing section-12 rollback procedure; it would require
the documented web restart and was not executed during this audit.

### A2 — attempted, acceptance evidence incomplete

The retained driver log shows IR 320x240@30 starting, then stopping roughly 21 s
later. Runtime retained 24 successful samples over 24.47 s and the stop reason
`viewer paused or closed`. Active guard CPU was 64.25–69.32%, RAM last 67.88%,
temperature last 60.875 C; the 75% CPU guard did not cause this recorded stop.
Astra CPU peaked at 38.09% of one core and ended at 4.91%; final RSS 81,592 KiB.
These process percentages are not whole-machine CPU percentages.

Registration-enable error and USB-thread-priority warnings appear in the log.
They do not establish why the viewer stopped or prove that frames failed.
Crucially, `VisionService.stop()` clears frame statistics. The subsequently saved
zero counters therefore cannot establish zero frame delivery. No retained
Dashboard frame count, FPS, raw encoding or frame timestamps were found for A2.
Driver start alone is not a Dashboard pass. **IR live verification is UNVERIFIED,
not passed and not diagnosed as hardware failure.** A3 remains blocked; neither
combination test was repeated. Stage31B's 607-frame Depth pass remains historical
evidence, not a post-Stage32 live regression result.

### A4 — metadata read, calibration not recovered

Recovered read-only query: Astra Pro serial `17122120830`, firmware `5.8.22`,
platform `RD108C-009`, SDK `5.2.0.0`. Supported IR/depth modes were enumerated
without starting a stream. A calibration-support flag is not a calibration
payload. The zero-plane-distance field was decoded as an unsigned integer and
gave `4638777984935788544`; its type/units are unverified and it must not be used
for geometry. No validated calibration was recovered. No EEPROM, firmware,
laser/emitter, calibration or production setting was changed in this continuation.

### Fresh read-only health and protected identities

Three CPU samples: 64.08%, 66.88%, 64.80%; RAM 72.18–72.19%; hottest 60.06 C.
E-STOP latched, manual-only true, commissioning false, commands/wheel outputs
zero, recorder OFF, mission READY. Required freshness checks passed. No Astra
driver, worker or cloud process remained. Pi Camera returned HTTP200/JPEG.
Protected PID/restart-count pairs match the recovered post-A4 snapshot:
camera 1982/0, base 3534/1, mux 1975/0, EKF 3260/0, localization 5713/1,
LiDAR 5523/5, web 164593/0. No service was restarted during this reconciliation.

### Evidence preservation and next necessary action

Remote evidence directory:
`/home/jetson/project-atlas-migration/stage32-deploy-20261021/`.
A preserved PC copy is under `artifacts/astra_stationary_20261021/` (not committed;
generated logs/backups remain out of Git). New read-only verification is
`handover-readonly-verification.json` in both copies. Key evidence SHA256:

| File | SHA256 |
|---|---|
| apply.txt | 94e534aefb9f5f368abe0a6f04779ed25453b7cc5eaad58d3dd768950cf39981 |
| a2_trace.jsonl | 0eb45d41791233a9ce25f8f7123c4dbcc21d727df49b25e8ff1acf4bc3b76430 |
| a2_viewer_state.json | 197d65aa41b18a7a5bd1f152baa1009830cc727ba1948a71e18758141786a727 |
| a2_driver_log_filtered.txt | b16e1d3318b0500100da9d7ebc5c8c4fa9b9023d9ec29f649c418c11a35e4c89 |
| a4_devinfo2.txt | 0482430c65c90e51bb20dcf92316adecd8f66b21ce5277034838236831f9eb9c |

No completed offline suite was repeated: earlier section-11 results remain
historical, not new test runs. New checks were live/package hash equality,
backup integrity, resource/safety freshness and protected-service comparison.
Next: recover the previous A2 browser delivery evidence if available; otherwise
request approval for one instrumented IR-only revalidation retaining delivery
statistics before Stop. Do not consume A3 on an assumed A2 pass. A5 physical
checkerboard acquisition and A6 calibration installation/cloud test remain
separately unapproved and blocked. No new camera session is authorized by this
report.

## 16. One approved instrumented IR revalidation — 21 October 2026

**Result: real infrared frames did NOT reach the Dashboard receiver.** This is
now supported by statistics saved while the session was ACTIVE, rather than
cleared post-stop counters. No retry or IR+Depth session was performed.

### Scope and monitoring

Stage32 was not reinstalled. One Start action selected IR-only in the existing
Vision Lab, using private domain77 and unchanged CPU75%, RAM80%, temperature70C
guards. Preflight verified all ten live hashes, Astra/domain77 idle, recorder OFF,
E-STOP latched, manual-only true, commissioning false, zero velocity and wheel
commands, mission READY, required sensor freshness and active protected services.
Available disk was 394,608,717,824 bytes.

A single persistent monitor was established before Start. It sampled scalar
Vision Lab status and /proc/stat approximately once per second, retaining JSONL
before stop could clear statistics. It created no ROS participant/subscription,
stored no image payload, and issued no process listings or service queries while
streaming. The existing guardian continued its normal safety checks. No new SSH
session or ROS CLI command was executed while streaming. Monitor also enforced
the unchanged CPU limit and an explicit no-delivery timeout: stop if IR remained
unavailable more than10s after first observing ACTIVE. It never starts a camera.

### Delivery and rendering evidence

| Measurement | Result |
|---|---|
| Driver negotiated/requested mode | Log reports IR320x240@30Hz; depth and colour disabled |
| IR delivery | 0 received, 0 rejected, 0 stamp regressions across11 saved ACTIVE samples |
| Actual delivered dimensions/encoding | Unavailable: no message; cannot claim mono8 based only on requested mode |
| Actual source timestamps/FPS/freshness | Null/unavailable; no actual frame stamps or measured frame rate |
| CameraInfo | Empty during saved ACTIVE samples |
| Dashboard | Runtime briefly said Camera streaming, but IR stayed unavailable; no IR image rendering verified |
| Stop | Monitor recorded `IR delivery absent/stale after startup`, then stop endpoint HTTP202 |

The driver logged `ir is started` at1792580132.327448 and received SIGINT at
1792580142.937659: approximately10.61s of nominal IR stream operation. It logged
`Stopped stream ir` at1792580144.330008. The worker's generic final reason is
`viewer paused or closed`, because the monitor called the ordinary Stop endpoint;
**the preserved monitor row identifies the actual no-delivery trigger.**
Source timestamp provenance cannot be assessed without frames. Transport loss is
UNKNOWN, not zero; zero callbacks do not identify whether publication, discovery,
subscription or the sensor stream failed. The visible runtime label proves only
the child process was running, not that images were delivered.

### Resource and shutdown evidence

| Measurement | Before | During ACTIVE | After |
|---|---|---|---|
| Whole-machine CPU | 63.07–66.92% | guardian peak69.78%; monitor peak69.24% | 62.83–66.36% |
| RAM | 69.18–69.24% | peak70.09% | 69.35–69.40% |
| Hottest temperature | peak59.47C | peak59.47C | peak59.50C |

Astra peak sampled CPU39.96% of one core; peak RSS85,180KiB. Neither is the
whole-machine CPU percentage. No resource limit tripped. No calibration/emitter
setting, navigation, motor, threshold, PointCloud2 or production file changed.

Postflight rechecked identical deployed hashes and protected PID/restart counts
(including web), fresh required sensors, E-STOP/manual-only, commands zero and
recorder OFF. Driver_stopped=true, no Astra/worker/cloud processes or domain77
owner remained. Pi camera JPEG endpoint returned HTTP200. Driver teardown logged
parameter-undeclare errors, so shutdown was clean in the sense of no remaining
processes/production impact, **not an error-free vendor log**.

### Findings and next step

Confirmed: this attempt failed IR delivery despite adequate resource headroom.
Driver reports a registration property5 error and USB-thread-priority warning;
neither is proved causal. No inference of defective hardware or permanent mode
incompatibility is justified. Next engineering action is an offline review of
the exact IR publication/topic/receiver path using these retained logs and pinned
source. Any further camera activation needs separate approval. A3 is blocked;
calibration/cloud remain unvalidated. No request to drive or redo completed work.

Scalar evidence and driver text are preserved on Jetson at
`/home/jetson/project-atlas-migration/stage32-ir-revalidation-20261021/`, with a PC
copy in `artifacts/astra_stationary_20261021/stage32-ir-revalidation-20261021/`.
Monitor source is preserved in the parent migration directory and PC artifacts.
Raw evidence is intentionally not committed. No video, rosbag, frame file or
screenshot was needed to document the zero-delivery result.

| Evidence | SHA256 |
|---|---|
| telemetry.jsonl | 217ba8d461ee87f77e62918e25582ab2ef99021247cb88620d47a542005c2139 |
| driver.log | 861a8be7ebe7f0c622d5840e181dd135f98403bc0302b8a522398d207370254f |
| final-runtime.json | 5124947404b0230597732d97db86a10c70e0faaec111243f494f3ca9953422a3 |
| pre.json | 9d8d5345a53746990f6fa7fbd9c91bb02b5b8344af2c1adbef8b4a92ea71e6be |
| post.json | a1853ec3a016f5ddedd3734a132f40bfc4e88b93394c84d36ff7b9858f6f8133 |

## 17. Zero-frame offline investigation — 21 October 2026

Continued from d9e23bf; no camera start, deployment, production restart, recording,
movement, calibration or safety-policy change. **DIAGNOSTIC FIX CANDIDATE READY;
real IR frame delivery remains UNRESOLVED.**

### Verified path and remaining boundary

Pinned vendor source f7e71d9ce806e788cb48d8580aac2c778fba4214:
`astra_camera/src/ob_camera_node.cpp` checks stream creation/start return codes.
The `ir is started` message follows successful OpenNI start, not a frame callback.
`pollFrame` silently continues when `waitForAnyStream` fails/times out (2000 ms).
It then reads a frame, invokes the callback, publishes Image and CameraInfo.
Neither readiness nor publication has a saved counter. Thus the exact unresolved
boundary is **OpenNI frame readiness/read → ROS publication → live discovery**.
No evidence yet proves which of these failed; zero received messages cannot do so.

- Saved A4 capabilities advertise IR320x240@30 GRAY8 and GRAY16. Stream-object
  creation succeeded; this does not establish hardware frame production.
- Current IR setup uses GRAY8, CV_8UC1, mono8, step1. Namespace/topic resolves to
  `/astra/ir/image_raw`, sensor_msgs/Image; CameraInfo is published separately.
- Default reliable/volatile publisher is compatible with the best-effort/volatile
  receiver. Driver environment and receiver context select Domain77. Read-only
  web-owner environment showed ROS_LOCALHOST_ONLY=0, no explicit RMW/domain or
  vendor DDS-profile override. This is not proof of live discovery or matching
  runtime RMW identities.
- Vision Lab consumes ROS directly through rclpy, not via Foxglove; changing
  Foxglove subscriptions would not repair this path.
- Vendor callback stamps messages with node current time, not sensor hardware
  capture time. Preserve those stamps but do not label them hardware timestamps.

### Vendor warnings: evidence versus hypotheses

Registration property5: setup calls registration OFF even when registration is
disabled. Its error text says 'Enabling' for both states. Failure logs but does
not abort startup; the later start succeeds. This establishes nonfatal control
flow, NOT that the property failure has no hardware effect. No setting changed.

USB thread-priority warning: bundled OpenNI implementation source is unavailable
in the pinned driver checkout. Exact failing call and effect remain unverified;
neither permissions nor real-time privileges should be changed speculatively.

Parameter undeclare errors: `dynamic_params.cpp` performs undeclaration in its
destructor. These teardown errors follow stream stop and do not explain the
preceding zero-frame interval. No vendor patch or binary replacement made.

### Verified software correction and tests

`atlas_vision3d_web.py`: retain scalar last-session counts after Stop (no images),
expose domain/RMW and existing 2-second discovery results, executor errors and
explicit unknown sensor/publication boundaries. Metadata capture failure cannot
prevent Stop. No additional DDS participant, subscription or polling timer.

`web/v2/vision3d.js`: driver-running status no longer implies viewing; zero
callbacks show IR NO FRAMES RECEIVED, stale is distinct, and Rendered is set only
after canvas conversion. Preserve final no-frame evidence. Enforce mono8,
mono16/16UC1 dimensions/stride/byte layout; browser render evidence remains local.

Added `test_vision3d_ir_delivery.py`, `test_vision3d_ir_browser_logic.py`,
`tools/vision3d/ir_receiver_smoke.py` and package preparation utility.

Native PC ROS Humble synthetic smoke, localhost Domain77, delayed publisher:
180 callbacks, 0 rejected, 0 stamp regressions, latest-window25.215Hz,
maximum gap0.04394s, receive age0.08007s, source age0.08776s; CameraInfo received,
76800-byte320x240mono8 payload identical; rmw_fastrtps_cpp. No hardware, video,
rosbag or image-file output. This rules out unconditional receiver failure, NOT
Jetson-specific discovery/driver failures. It does not reproduce the hardware fault.

Final focused regression: **93 passed, 1 skipped** (Playwright unavailable).
Includes unchanged Depth/Depth+RGB launch arguments, guards, Domain isolation,
IR and calibration-gated geometry. Run pytest with `-s` because guard fixtures
use stdin fileno; default pytest capture causes fixture-level fileno errors.
Separate Windows Node execution of actual production canvas/banner functions
passed: mono8, big-endian mono16, padded little-endian16UC1, invalid stride and
encoding rejection, no-frame/stale/resource-blocked/final-stop banners. This is
not a full browser or live Depth regression. No live Depth test was repeated.

Resource impact: discovery metadata reuses the existing graph poll; retained
evidence is scalar and bounded, not image history. Actual incremental Jetson CPU,
RSS and render latency are **unmeasured** because nothing was deployed. Previous
live IR failure stayed within guards (section16); CPU is not established causal.

### Candidate package, installation boundary and rollback

Offline preparation script:
`project_atlas/tools/vision3d/prepare_ir_diagnostics_package.py`.
Local output `artifacts/astra_stationary_20261021/ir-diagnostics-candidate/`:
manifest plus candidate.tar.gz. Only two application files, no driver/runtime/
guard/service-unit changes. Script has no live deployment actions. Temporary
target apply/restore rehearsal verified byte-identical baseline restoration.

| File | Candidate SHA256 | Expected existing SHA256 |
|---|---|---|
| scripts/atlas_vision3d_web.py | ab056cf735a876d083822d783a312fd994c1cf7b6a19e38050476c26199e37c5 | 889881c062717d076430414f57825b14f7f0de36ba4cf8c20b0c74fbff9ec1bf |
| web/v2/vision3d.js | ee64d7d6625e0b135eef1a79b3575e5128a68257a580333e36ceb2c228aa056b | 76f9a20267e7d90a9d4b0a3be7f75a6c0e0ca594ddc1254e337e618215cf3fba |

Tar SHA256: 69fd7dd31d75553d4c68e8998a689f1d61e1eb9555bedbd91e562a107965f58e.
Package records baseline d9e23bf, not a claim that uncommitted bytes were deployed.
The Git commit containing this section and these files identifies the candidate.

Proposed installation requires separate approval, fresh safety/resource/hash
checks, backup of exactly both files, atomic replacement and a separately approved
Vision Lab web-owner restart. Abort on baseline mismatch; do not overwrite newer
developer work. Verify candidate hashes, stopped-camera and protected identities.
Rollback: restore both verified backups and restart only that web owner under
the same approval. No live backup/install path exists yet; package is PC-only.

### Single next necessary action

Do not repeat an unchanged camera start. Prepare read-only, low-rate vendor
instrumentation counting OpenNI wait result/timeouts, read success/failure,
actual first-frame mode/format/size and Image/CameraInfo publish totals. No image
payload retention. Review/build this separately before requesting deployment.
Together with receiver discovery/callback counters it can distinguish no sensor
frames from ROS delivery failure in ONE bounded IR-only session. The current
two-file package fixes misleading diagnostics, not that missing driver evidence.

Owner approval needed for installation/restart; additional explicit approval is
needed for an instrumented driver and one guarded IR-only verification after its
package is tested. Keep Domain77, 75% CPU/80% RAM/70C, persistent low-overhead
monitoring, maximum60s and early no-frame stop; no retry, combinations, emitter
changes or recording. IR acceptance requires real frames on Dashboard. No
hardware-delivery fix or combined-mode test is ready for approval yet.

## 18. Driver instrumentation candidate — 21 October 2026

Continued from 3e914657857143a682f9f82fdc85334d61d92e94. **DRIVER INSTRUMENTED;
OFFLINE VERIFIED; DEPLOYMENT READY subject to fresh preflight and approval.**
**LIVE IR DELIVERY NOT VERIFIED; ROOT CAUSE NOT IDENTIFIED; STILL BLOCKED** on
one instrumented hardware observation. No deployment, camera start, recording,
service restart, motor command or setting change performed this turn.

### Source and live identity verification

Read-only Jetson inspection matched all ten Stage32 files to section16's preflight
hashes. Existing shared library SHA256 is
`6ae876010c824be97d2545996f897e40e07e0c97fa7a45694f96f342cf6e22a6`;
unchanged executable is
`2f7a58f9b409ee98aa38dde8966fbd661f0c532c589eead32207a58964635aa9`.
No Astra driver/worker process was found. This hash/process inspection is not a
fresh safety/resource admission; repeat the complete gate before any installation.
Existing backups were not touched.

Pinned source is unchanged f7e71d9ce806e788cb48d8580aac2c778fba4214 plus existing
ARM64 build patch. `instrument_ir_driver.py` applies exact, count-checked anchors
and refuses a second application. Adds `ir_counters.hpp` and changes only vendor
`ob_camera_node.h/.cpp`. No launch, mode, registration, emitter or firmware changes.
Existing cross-build environment reused; only astra_camera target rebuilt. Its
dependent translation units recompiled for the private class layout; message and
unrelated ROS packages were not rebuilt. Candidate is a verified ARM aarch64 ELF,
with no RPATH/RUNPATH entry. Cross-install baseline library remains untouched.

### What the instrumentation measures

This vendor uses waitForAnyStream/readFrame polling, **not an SDK listener
registration**. `callback` below means entry to vendor onNewFrameCallback after
readFrame returns, not an independent SDK interrupt. Distinguish readiness from
callback entry when interpreting Case A.

| Counter/field | Meaning |
|---|---|
| created / create_rc | Successful IR stream creation / actual return code |
| mode_rc / start_rc / started | Existing setVideoMode/start results, successful starts |
| ATLAS_IR_START | Requested and negotiated mode plus actual context domain |
| publisher / ATLAS_IR_PUBLISHER | Publisher creation, resolved topic, type and QoS |
| wait_ok / wait_failed / wait_rc | Global poll results; in IR-only mode these concern IR; do not attribute all waits to IR in combined modes |
| ready | IR stream selected by poller |
| read_ok / read_failed / read_rc | IR readFrame result |
| callback | IR conversion callback entered |
| width/height/pixel_format/fps/stride/bytes | Last actual OpenNI frame metadata, zero until a frame exists |
| hardware_timestamp_us / frame_index | Actual OpenNI timestamp/index; not substituted for ROS header time |
| converted | cv_bridge conversion returned a message |
| publish_attempt / publish_returned | ROS publish call entered / returned without exception; not remote receipt |
| info_returned | CameraInfo publish returned |
| exceptions | Exception escaped conversion/publication path; counted, logged and rethrown, vendor behavior preserved |
| subscribers | Publisher matched-subscription count, sampled with summary; not proof of delivery |

`ATLAS_IR_COUNTERS` summaries are at most once per second plus final/exception
summary, from the existing poller (no extra ROS timer/thread). A wait timeout can
make the summary interval approximately two seconds. Final summary occurs after
poller join; no image payload is stored. Saturating uint64 counters do not wrap.
ROS log timestamps provide summary time. Hard kill/power loss may lose final
summary; preserve earlier summaries in the existing driver log independently.

Receiver carries forward previous Domain77 discovery/RMW/callback/rejection
diagnostics. New `ir_api.responses_prepared` and unique stamps count raw responses
prepared, **not socket delivery**; retained in last_session after Stop. Browser
Developer Diagnostics separately counts complete response bodies, successful
canvas renders and failures, preserving scalar counts after Stop for the current
page lifetime. Browser reload loses those local counts: capture scalar evidence
before closing, without saving imagery. Counts may include repeats of one source
frame; use stamps and unique API stamps, not request counts as sensor FPS.

### Offline results and resource cost

- Native C++ simulation: six wait failures with zero callbacks; 180 read/callback/
  conversion/publication events; explicit attempt without successful return;
  exception, saturation, summary throttling and final-summary checks PASS.
  This tests instrumentation logic, not simulated proprietary USB firmware.
- Incremental ARM64 shared-library build PASS. No Jetson compilation/load.
- 94 existing/updated focused tests PASS, one Playwright dependency skip;
  three added instrumentation tests PASS. Separate Windows Node execution of
  production IR banner/canvas functions PASS.
- Fresh native PC ROS Domain77 smoke:179 received from180 synthetic publications,
  0 rejects/regressions, latest FPS24.822, maximum gap45.634ms, receive age71.193ms.
  CameraInfo arrived,320x240mono8 raw76800 bytes verified. One publication was not
  observed; exact transport/startup loss not attributed. No loss-free claim.
- Existing Depth launch/configuration, guard and calibration/geometry tests pass;
  no new live Depth test. Working Depth settings and Pi Camera remain unchanged.
- PC scalar counter microbenchmark:1,000,000 increments in0.00710509s; struct176
  bytes; example summary419 bytes. This excludes ROS logging, subscriber discovery
  and Jetson scheduling. Actual Jetson overhead UNKNOWN until approved test.
  Expect bounded metadata and roughly1 summary/s, not a resource-limit exemption.

Warning assessment remains section17: registration error is nonfatal in source
control flow, its hardware effect unproven; USB priority call's source unavailable;
undeclare errors occur during teardown. No evidence-based acquisition fix exists
yet. Instrumentation corrects the missing evidence, not the camera itself.

### Versioned package and rollback

Preparation tool `project_atlas/tools/vision3d/package_ir_instrumentation.py`.
PC output `artifacts/astra_stationary_20261021/ir-driver-instrumented-candidate/`:
manifest, exact vendor delta, candidate.tar.gz. Three payloads only; this supersedes
the previous two-file diagnostic candidate, do not install both sequentially.

| Payload | Candidate SHA256 |
|---|---|
| lib/libastra_camera.so | 8609f2641d181fb6fccda60e84f83d4c5d399b673dc65b27b723490a8b24cab9 |
| project_atlas/scripts/atlas_vision3d_web.py | a7b9f1f92ac4a9acd08954103df981d41dfea7ed613b01146669248ef9cd584c |
| project_atlas/web/v2/vision3d.js | 91460fcf775cd3517f19d050c86f1c55d9627e710d398b6e79dd456a696d99a5 |

Archive SHA256 `1e6704adb163747328b1a9f37dfd0053e713fb8d16aa09afbb1ae7744e5a3473`.
Vendor diff SHA256 `973eb10f839856406d03ce0c95d884b86f0f71cf7a9d41159a4613c5f11064f5`.
The Git commit containing this section pins scripts/header/tests; binaries and
generated artifacts stay outside Git. All three original payloads restored
byte-identically in an isolated temporary directory: rollback rehearsal PASS.

Live library target is
`/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2/lib/libastra_camera.so`.
App targets are `/home/jetson/project_atlas/scripts/atlas_vision3d_web.py` and
`/home/jetson/project_atlas/web/v2/vision3d.js`. Before approved install, verify
manifest baseline hashes, create a new backup directory (never reuse/overwrite
existing evidence), copy these exact three targets there and verify hashes.
Replace atomically only with Astra OFF; obtain approval for web-owner restart.
Do not restart any other production service. No live backup path exists yet.

Rollback procedure (NOT executed; `$backup` must be the validated new directory):
```sh
# Camera must be OFF; verify backup hashes against manifest before these copies.
cp -p "$backup/libastra_camera.so" /home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2/lib/libastra_camera.so
cp -p "$backup/atlas_vision3d_web.py" /home/jetson/project_atlas/scripts/atlas_vision3d_web.py
cp -p "$backup/vision3d.js" /home/jetson/project_atlas/web/v2/vision3d.js
# Restart only the freshly verified web-owner unit under explicit restart approval.
# Verify all restored hashes and protected service identities; no camera auto-start.
```

### Approval required and single live decision procedure

Request approval to install these three verified files, restart only the verified
Vision Lab web owner, then perform ONE stationary IR-only session, maximum60s,
early Stop after10s without frames. Before admission require fresh E-STOP latched,
manual-only, zero commands, recorder/Astra OFF, no goal, CPU<75%,RAM<80%,temp<70C,
correct hashes/rollback and healthy protected services. Preserve existing1s CPU
guard. No changes to navigation/steering/emitter/calibration/PointCloud2.

Reuse persistent Jetson-local monitoring from section16, launched before Start
and independent of SSH; preserve driver text and scalar samples. Add new API/
receiver/discovery counters to those samples. Keep Dashboard open for its existing
viewer lease; browser local counters provide render evidence. Do not introduce an
SSH heartbeat or intrusive ROS CLI sampling. No video, rosbag or raw image files.

Decision: read_ok=0 isolates before conversion (use wait/ready/read_rc); callback>0
and publish_returned=0 isolates conversion/publication (compare converted,
attempts, exceptions); publish_returned>0 but receiver=0 isolates ROS delivery
(domain/topic/QoS/discovery/subscribers); receiver>0 but API/browser=0 isolates web
transfer; received browser bodies>0 but rendered=0 isolates decoding. These are
decision rules, NOT observed conclusions. Respect missing final logs as unknown.
Stop on any guard/freshness/error failure; no retry. Verify no orphan Astra,
recorders OFF, protected identities unchanged and Pi Camera healthy afterward.
Do not proceed to combined modes or claim success until real IR frames render.

## 19. Approved conditional installation — aborted and rolled back, 21 October

Owner approved installing section18's three files, restarting only rover-status-web,
then ONE IR-only test **only after all deployment checks passed**. GitHub HEAD was
baa1f26e96b8976aed0785f62c0891558c5930f0; archive hash matched section18 exactly.

**Result: ROLLED BACK. IR TEST NOT STARTED. No automatic retry.**

### Sequence and exact failure

1. All ten deployed Stage32 hashes and three replacement baselines matched.
   Package members were individually hashed;1GiB free-space gate passed with
   394,550,407,168 bytes free. Existing backups untouched.
2. Fresh preflight passed: E-STOP latched, manual-only, commissioning disabled,
   source STOPPED, zero command/output targets, fresh required sensors, mission
   READY, motor speed0, recorder OFF, no Astra processes or Domain77 owner.
3. ARM64 candidate loaded with `ctypes.CDLL(..., RTLD_NOW)` on Jetson successfully.
   This resolves dependencies without constructing a ROS node or opening camera
   streams; it is not a stream test or complete driver-functionality qualification.
4. Exact three backups verified; safety checked again immediately before writes.
   Only reviewed three payloads replaced, each installed hash checked. Only
   rover-status-web restarted. Other active user-service identities matched.
5. Post-restart CPU sample was **95.63758389261746%**, exceeding75%. The unchanged
   guard raised AdmissionError before other resources were sampled in that window.
   No runtime Start request was sent. Browser page was opened, but Start was never
   pressed. No driver counters could be collected from a real camera session.
6. Restored all three original files atomically from verified backups and restarted
   only rover-status-web to load originals. Rollback hashes matched exactly.

The failure occurred during post-restart verification, before IR activation.
Neither the instrumented camera path nor IR acquisition can be blamed from this
sample. A web-startup/resource spike is a hypothesis; its exact attribution is
unverified. No resource threshold was changed and no lower later sample was used
to retry admission.

### Resource and final safety evidence

| Measurement | Initial preflight | Immediately before writes | After rollback (read-only) |
|---|---|---|---|
| CPU, 1-second samples |63.34–65.71%|62.03–65.66%|63.27% single sample|
| RAM |66.50–66.59%|66.70–66.75%|67.51%|
| Temperature |peak60.75C|within70C gate|peak60.25C|

Failed post-restart sample95.64% is preserved separately, not averaged away.
Final read-only checks: E-STOP latched, manual-only, commissioning disabled,
zero commands, fresh required telemetry, mission READY, recorder OFF, runtime OFF,
Domain77 unoccupied, no Astra/worker/cloud process. Pi Camera JPEG returned HTTP200,
26,179 bytes; image bytes were not retained. Ten original Stage32 hashes match.

All previously active user-service PID/restart/state tuples remained unchanged
except rover-status-web: PID164593 before,189500 candidate,189640 restored; automatic
NRestarts0 throughout. Explicit installation and rollback restarts are not counted
by systemd NRestarts. No other restart was issued. Protected sensor/motor/EKF/AMCL/
LiDAR identities matched. No movement, recording, emitter/calibration/firmware,
network, navigation or safety changes.

### Durable evidence and rollback

Jetson directory:
`/home/jetson/project-atlas-migration/stage32-instrumented-approved-20261021/`.
PC copy: `artifacts/astra_stationary_20261021/stage32-instrumented-approved-20261021/`.
Contains full terminal output, result/traceback, postrollback report, single-use
attempt marker, installer and read-only checker, package, rollback ledger and
`backup/` with all three original files. Raw evidence is not committed to Git.

| Evidence | SHA256 |
|---|---|
| result.json |0153ed3b6b99ff2455c07aaceb30cc3309ef833f3b4b3702ca85657531c151e0|
| postrollback.json |fa9d5ef970b1634686d821422c5b2872469cefde2d3f65ccbf15da6a2553e03b|
| terminal.txt |65d9d8028d1f79275f0abef6f1aaef16c96e4553f360bd2636e619bc5cccc9d9|
| rollback-ledger.json |bbc179cb0c68ae97678d80f1496b216feddbef9710c7b83181f440ef706a670a|

Restored library6ae87601…, web889881c0…, JS76f9a202… match full section18 baseline
hashes. Backup hashes independently rechecked after rollback.

Earliest failed boundary this attempt: **deployment resource admission**, NOT a
measured IR pipeline boundary. Real IR root cause remains unresolved; zero-frame
driver instrumentation is still offline-only. Next necessary action is a scoped
read-only diagnosis of the web-restart CPU spike and a reviewed deployment plan,
not another IR start. Fresh owner approval is required for another installation/
test attempt. This failed sequence cannot establish IR LIVE VERIFIED.

## 20. Documentation-only session handover

See `ATLAS_STAGE32_DEVELOPER_HANDOVER.md` for exact installed/candidate identities,
preserved WSL build tree, local/Jetson evidence, backups, hypotheses and next task.
Focused deployment ledger: `docs/audits/ATLAS_STAGE32_DEPLOYMENT_REGISTRY.json`.
No additional Jetson checks or technical execution performed for handover. Last
verified stopped state is section19's historical evidence, not fresh admission.
Incoming developer starts with passive restart-CPU analysis, not another install
or camera test. All operational approvals must be renewed. Current session ends.
