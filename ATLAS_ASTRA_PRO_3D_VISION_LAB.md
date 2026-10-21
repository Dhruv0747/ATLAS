# ATLAS Astra Pro 3D Vision Lab — 21 October 2026

## Approved stationary setup follow-up — latest checkpoint

The owner subsequently approved isolated driver setup and stationary RGB/depth
testing, including targeted USB permissions. **Preparation progressed, but the
build and live stream tests are BLOCKED. No Astra streams were started.**
This supersedes the earlier pending-approval text below for the stationary test
only. The production dashboard deployment is still NOT approved or performed.

Confirmed completed preparation:

- Cloned the pinned vendor wrapper revision
  `f7e71d9ce806e788cb48d8580aac2c778fba4214` into
  `/home/jetson/project-atlas-migration/astra-20261021/ws/src/ros2_astra_camera`.
  Its OpenNI2 core and Orbbec plugin are ELF64 AArch64; their `ldd` dependency
  checks resolve. This does not prove a working Humble driver or valid depth data.
- Downloaded/extracted seven ARM64 dependency packages into this staging folder,
  **not installed system-wide**: libuvc-dev/libuvc0 0.0.6-1.1,
  libusb-1.0-0[-dev] 2:1.0.25-1ubuntu2, Humble camera-info-manager and
  camera-calibration-parsers 3.1.13, image-publisher 3.0.9. Exact build suffixes,
  package hashes and metadata are preserved in `dependency_manifest.json`.
- Relocated only the private pkg-config paths and configured a separate
  CMake/AMENT/library prefix. No `/etc`, `/usr`, `/usr/local`, production ROS
  workspace, system package database or shell startup files were modified.
- The vendor CMake hard-coded Debug; the isolated checkout now respects explicit
  Release selection. No driver runtime logic, calibration or camera setting was
  changed. Source is not redistributed here (upstream package has TODO license).
- Added opt-in build tooling with one job, requested CPUQuota35% (0.35 core),
  800MiB memory cap and 900s hard deadline. Live safety/resource supervisor stops
  only this new build job; it never calls robot control APIs.

Preserved failures, in order:

1. Initial preflight used assumed `CPU-therm` names. Read-only sysfs inspection
   found `cpu-thermal`, `gpu-thermal`, `soc0/1/2-thermal`, `tj-thermal`; the guard
   was corrected to require these exact sources. Nano CV read failures are not
   treated as temperatures or silently substituted with zero. No build started
   under the failed preflight.
2. First transient build exited immediately because Humble `setup.bash` reads an
   optional unset `AMENT_TRACE_SETUP_FILES` under nounset. The isolated wrapper
   now temporarily disables nounset while sourcing and restores it afterwards.
   Evidence: `build_supervised_result.json` and its retained journal. No camera
   was opened. Essential service identities before/after matched.
3. Second build passed fresh preflight and began astra_camera_msgs configuration.
   Total CPU reached **75.88424437299035%**, exceeding75%; the supervisor stopped
   the build immediately. RAM at rejection **66.08189202890861%**, maximum required
   temperature **60.093°C**. Thresholds were not relaxed. Evidence:
   `build_supervised_result_2.json`, which retains the exact failed readings in
   its failure text. Its sample list contains only admitted samples (peak73.71%);
   do NOT misreport that admitted-only peak as the total peak. Future source
   tooling also retains a structured rejected sample. That later enhancement
   is offline-tested, not a fresh live retry.

The stopped transient unit can report systemd `Result=success` / ExecMainStatus0
after an intentional stop. That is **not compilation success**: the supervisor's
overall result remains BLOCKED. No retry followed the CPU rejection. Both build
units have MainPID0; no Astra driver, build or recording process remains running.
CPU quota was requested, not independently profiled for sustained enforcement
before this short abort. No claim that the Astra workload caused the CPU spike;
it was total-system admission failure and prior baseline spikes already exist.

USB permission blocker:

- Fresh `/dev/bus/usb/001/014` depth and `001/011` RGB remain root:root0664,
  without an ACL for jetson. The operator's initial “Done” was not accepted as
  evidence of a permission change; direct checks still fail write access.
- `sudo -n -l` permits passwordless shutdown only, not permission changes. General
  sudo requires the operator's password. No credential retrieval, privilege
  workaround, broad chmod, udev reload, shared hub reset or unsolicited GUI
  authentication was attempted. The operator is busy; no further terminal prompt
  will be repeated during this attempt.
- `project_atlas/config/99-atlas-astra-pro.rules` is a **candidate, NOT installed**:
  exact USB IDs0403/0501, group video (jetson is already a member), mode0660.
  It does not match the Pi camera, UNO, modem or hubs. Applying/removing this rule
  and refreshing only the two camera devices needs administrator execution;
  current approval authorizes that scope but does not supply OS credentials.

No image/point-cloud/rosbag/snapshot was saved. Logs here are build/admission
metadata, not sensor recording. Real RGB/depth FPS, accuracy and simultaneous
modes remain NOT TESTED. No RGB-only experiment was started after the failed CPU
gate. Local private evidence copies: `artifacts/astra_stationary_20261021/`.
Remote preparation occupies approximately12MiB, preserved for continuation.

Final read-only checks: E-STOP latched, manual-only true, commissioning false,
commands zero, Stage20 recorder inactive/PID0. Essential PID/restart counts
matched: Pi camera1982/0, base3534/1, mux1975/0, EKF3260/0,
localization5713/1, LiDAR5523/5. Historical restarts were not caused, cleared or
certified by this work. No production service or Pi camera was restarted.

**Next necessary action:** obtain actual administrator execution for the two
targeted USB permissions and establish CPU headroom below the unchanged75% gate.
Then resume the isolated build under fresh checks using a new evidence ID;
the owner's stationary-test approval already exists. Do not repeat completed
inventory or start streams merely because permission has been granted.
No automatic retry, background driver, dashboard deployment or autonomy follows.

Rollback: there is no production installation to undo. Keep the stopped build
units stopped; do not source the private workspace into production processes.
Retain the12MiB staging folder and failure evidence instead of deleting it.
If a future administrator applies a camera ACL/rule, preserve its original mode/
ACL/rule first and restore exactly those values on rollback; no such permission
change was verified during this attempt.

Fourteen new offline stationary-guard tests pass, in addition to the72 targeted
Vision Lab/regression tests below (86 total). Full vendor build and live RGB/depth
tests did not pass and are not included in that count.

## Status and authorization boundary

**Read-only hardware identification COMPLETE. Offline viewer candidate TESTED.
Live depth integration NOT COMPLETE. Nothing from this candidate is deployed.**
No driver was started/installed, no recording made, no actuator command sent, no
production service restarted, and no Nav2/AMCL/EKF/calibration/map changed.
The owner permits read-only inspection and offline development; section 7 of the
request does not authorize a new live driver or production dashboard deployment.

Repository branch: `agent/sync-developer-20261011`. Baseline merge `8384343`
preserves developer stages 21–27 (`8351fc5`) and the UNO watchdog fix (`250afeb`).
Tested implementation commit: `13570fc12f5397d6d787c84a93a9136016bfb23d`.
Subsequent report-only provenance changes do not change the candidate code.
Local package: `artifacts/vision3d_20261021/candidate-13570fc.zip`, SHA256
`1521390ebcdc8ad94348265b3eab83c595cf4dd06c63242bcf3ff3e17a4cb504`.
Its eight file hashes were independently verified against the manifest. It has
empty topics, recording false and deployment_authorized false; no install scripts.

## 1. Confirmed hardware, live inspection

| Function | Confirmed identity | Interface / ownership |
| --- | --- | --- |
| Astra depth | `2bc5:0403`, USB product `ASTRA Pro` | `1-2.3.1.2`, vendor-specific depth + USB audio |
| Astra RGB | `2bc5:0501`, Astra Pro HD Camera | `1-2.3.1.1`, UVC; `/dev/video1` capture, `/dev/video2` companion interface |
| Existing Pi camera | `vi-output, imx708 9-001a` | `/dev/video0`; existing `atlas-camera.service` kept active |

Both Orbbec devices enumerate at **480 Mb/s USB 2.0** behind an internal Genesys
hub and additional hubs sharing Jetson's USB2 root. USB3 ports elsewhere do not
make this camera USB3. `authorized=1`, runtime status active; RGB power policy auto,
depth policy on. No settings were changed. No matching camera/USB error appeared
in the bounded current-boot kernel query. **Power integrity and sustained USB
bandwidth are unverified** without streaming/power measurement; enumeration is
not proof of stability. No physical unplug/replug test was performed this session.

Read-only UVC ENUM_FMT/ENUM_FRAMESIZES ioctls (no STREAMON) advertised:
YUYV and MJPEG, each at 1280×720, 640×480, 352×288, 320×240, 176×144 and 160×120.
Advertised sizes are not measured FPS or verified concurrent modes.

## 2. Software compatibility and blockers

Live system: aarch64 Ubuntu **22.04.5**, ROS **Humble**, L4T **R36.4.3**,
kernel **5.15.148-tegra**, installed `nvidia-jetpack` **6.2.1+b38** (not the
request's assumed 6.2.2). Do not upgrade JetPack for this feature.

`libopenni2-0:arm64` 2.2.0.33+dfsg-15 is present, with generic PS1080/PSLink/
OniFile/DummyDevice plugins. Neither `astra_camera` nor `openni2_camera` ROS
package was found; no Astra/OpenNI process was running. Depth USB device is
root:root `0664`; `jetson` currently has **no write access**. A targeted approved
permission change is required, not `chmod 777`, a global USB rule or hub reset.

Primary references checked:

- [Orbbec OpenNI SDK supported devices](https://github.com/orbbec/OpenNI_SDK):
  explicitly lists Astra Pro. This is the appropriate legacy protocol family.
- [Orbbec SDK version support](https://orbbec.github.io/OrbbecSDK/): v2 excludes
  legacy OpenNI devices. Do not install the newest SDK blindly; Astra Pro is not
  Astra Pro Plus, Mini Pro or Astra 2.
- [Vendor ROS2 wrapper](https://github.com/orbbec/ros2_astra_camera), inspected
  revision `f7e71d9ce806e788cb48d8580aac2c778fba4214`. Its README uses Galactic
  examples and separate OpenNI/libuvc dependencies. It is a candidate for an
  isolated ARM64/Humble build, **not proven compatible on this Jetson**. Do not run
  its global install/udev scripts unchanged or let its default `/camera` namespace
  collide with the Pi camera.

Read-only `ros2 topic list -t --no-daemon` works. Actual existing Pi topics are
`/camera/image_raw`, `/camera/image_raw/compressed`, `/camera/detections/json`.
**There are no live Astra RGB/depth/IR/PointCloud2 topics to report.** No names
were fabricated. Camera-internal TF and base_link extrinsics are not validated.
No dummy identity base_link transform has been installed.

## 3. Candidate functionality (offline only)

`/v2/vision3d` and one Home **3D Vision Lab** shortcut are additive repository
changes. They do not appear on the production dashboard until approved deployment.
The candidate provides:

- Separate RGB, colorized depth and IR panes with active/unavailable/stale/error
  states and real source timestamps, encodings, resolutions and observed rates.
- CPU Canvas 3D viewer on the browser: orbit, pan, zoom, XYZ optical axes, click
  selection with XYZ/range; receives real PointCloud2 when available, <=6,000
  sampled points. It rejects unverified non-optical clouds rather than relabeling
  arbitrary frames as camera axes. No camera extrinsics are guessed.
- Depth pixel inspection of the original buffer: 16UC1 mm and 32FC1 m, padded rows
  and either endianness; zero/non-finite/negative and uint16 sentinel invalidity.
  Axial Z and Euclidean range are explicitly different. XYZ requires matching
  CameraInfo dimensions/frame, positive finite intrinsics and zero distortion;
  otherwise Z remains available but XYZ/range are explicitly unavailable.
- PNG preview conversion only on request, <=240×180 display sampling; sample
  validity counts are labeled as sampled, **not full-frame counts**. Invalid pixels
  are black. No interpolation or false distance substitution.
- Mode selector reflects only owner-reviewed manifest modes and is disabled for
  hardware switching. All combinations currently UNVERIFIED. It cannot issue
  driver service calls. Pi detections are explicitly not registered to Astra;
  no false detection overlay or RGB point-cloud coloring is shown.
- Recording/snapshots OFF, no recording backend or autostart unit. USB inventory
  provenance is distinguished from live USB health; a connected indicator cannot
  be inferred merely from the historic manifest.

Implementation: `atlas_vision3d_core.py`, `atlas_vision3d_web.py`, V2 assets.
No publishers, service/action clients, motor/serial/device ownership or Nav2 output.
ROS imports are lazy. An explicit `ATLAS_VISION3D_MANIFEST` with exact discovered
topic names is required; the included example has **empty topics and modes**.
Production `/camera/`, control, IMU and motor namespaces are rejected. Graph types
are checked before subscribing and missing topics rediscovered at 2-second cadence
only while an approved viewer is active. There is no idle polling service.

## 4. Resource and fault isolation

Only latest messages retained (<=8 MiB per payload, five fixed keys), bounded
statistics deques, best-effort depth-one QoS, <=5 Hz callback retention, shared <=2 Hz
conversion caches. No conversion in ROS callbacks. Hidden/paused pages abort
requests, remove images/clouds; subscriber/executor context shuts down 15–30s
after last request. Driver lifetime is separate: stopping the viewer does not
claim to stop the hardware driver. ROS failures back off 30 seconds; a separate
ROS context prevents shutdown of the production ROS context.

Local receipt and source timestamp freshness are checked **before cached data can
be returned**. Source-clock mismatch is rejected, not hidden. Backward/duplicate
stamps, malformed buffers, viewer throttling and observed gaps are counted.
Exact transport drop count remains UNKNOWN (Image has no sequence number);
frame-rate gaps are not mislabeled as exact dropped frames.

Read-only Jetson baseline, no Astra streams (10 one-second CPU samples):

| Measurement | Result |
| --- | --- |
| Aggregate CPU | mean 65.927%, peak 67.40% |
| RAM dashboard endpoint | 4,786 / 7,620 MB, 63% |
| Temperature dashboard endpoint | 59°C |
| GPU activity | unavailable in existing telemetry; not assumed zero |
| Available disk | 368 GiB (`df -h`); no recording space consumed |
| Astra USB traffic under streaming | NOT MEASURED |
| Astra driver/viewer CPU/RAM/GPU overhead on Jetson | NOT MEASURED |

Windows synthetic 640×480 constant-depth decoder microbenchmark: 40.625 ms CPU
per sampled PNG conversion (10 iterations), tracemalloc peak 514,360 bytes,
842-byte PNG for this highly compressible fixture. **Not a prediction of real
frame size, Jetson speed or total system memory.** Browser rendering runs on the
viewer's device, not Jetson GPU. No live performance acceptance is claimed.

Final read-only checks preserved the observed essential service identities since
the baseline: Pi camera PID1982/restarts0, base3534/1, mux1975/0, EKF3260/0,
localization5713/1 and LiDAR5523/5. Non-zero historical restart counts predate
this comparison and are not cleared or declared healthy by this feature.
Recorder PID0/inactive; manual-only true, stop latched, commissioning false,
commands zero. Dashboard PID2149/restarts0 active. No restart was issued.

## 5. Test results and screenshots

**72 targeted offline tests passed**:

- 37 new decoder/service tests: valid/invalid depth, units, bounds, truncation,
  byte order, padded rows, XYZ/range, missing/distorted calibration, PointCloud2
  bounds/fields/NaN/optical frame, shadow-only ROI, stale/cached data, clock mismatch,
  throttling, ROS failure backoff, idle teardown, reconnect cache reset and
  clicked-image timestamp matching (reject changed frames instead of measuring a
  different image from the one displayed).
- 2 native ROS2 Humble serialization tests on WSL Ubuntu 22.04, actual Image and
  PointCloud2 messages. No DDS subscriptions or hardware were used.
- 7 existing V2 route tests, 8 existing default-route tests, 18 FlySky web tests.
- JavaScript syntax and affected Python compilation passed.

Headless Edge/Playwright synthetic browser checks passed at 1440×1000 and 390×844:
no horizontal overflow, page exceptions or non-GET requests; real PNG rendering,
source-pixel click response, cloud interaction controls, stale image clearing,
unavailable-to-live recovery and no requests after Pause. Simulator responses and
screenshots prominently say **SIMULATED UI TEST — NOT JETSON DATA**. They do not
prove live camera FPS, calibration or concurrent RGB/depth/IR capability.

Local screenshots: `artifacts/vision3d_20261021/desktop.png`, `mobile.png`;
browser result in `result.json`. Reproduce with local `tools/vision3d/sim_server.py`
and `browser_test.cjs`; no dependency on Windows for eventual Jetson operation.

Additional old stage-specific static suites were attempted, **not counted as
passing**: FlySky's uncommitted-diff assertion assumes every new link is FlySky;
old git-status assertions see CRLF checkout differences under WSL; the legacy
stage26 apply.sh test fails on CRLF `pipefail`. Windows default-codepage/cv2 issues
were avoided by UTF-8/native WSL runs. These were not hidden or fixed by changing
unrelated files. This is not a claim of a full repository test-suite pass.

## 6. Depth obstacles — isolated prototype only

Core exposes a bounded camera-optical-frame ROI candidate count/nearest Z, labeled
shadow-only. This is **not obstacle avoidance**: floors/walls can enter the ROI;
no ground segmentation, base_link transform, robot footprint, LiDAR comparison or
motion compensation is commissioned. RPLIDAR remains primary. Next experimental
work needs measured camera/LiDAR extrinsics and synchronized real data. There is
no Nav2 publisher, costmap layer, slow/stop authority or through-wall/body inference.

## 7. Minimal deployment and rollback plan (NOT executed)

1. Separate owner approval for an isolated ARM64 OpenNI/Humble driver build and
   stationary stream test. Recheck stopped/latched/zero-command/manual-only and
   recorder OFF. Preserve existing resource guards (CPU75%, RAM80%,70°C); abort
   rather than relax them. Inventory camera service PIDs/hashes and USB errors.
2. Inspect pinned driver source, ARM64 binaries, dependencies and USB permissions.
   Stage in a NEW isolated workspace; no global driver/SDK overwrite, default
   `/camera` namespace, shared hub reset or production-service restart. Start
   depth-only conservatively (candidate 320×240 at5Hz **if device supports it**),
   then separate RGB test. Probe IR/depth exclusion from actual device modes.
   No assumption that all three run together. Permission rule requires approval.
3. Measure real per-stream FPS, source age, invalid counts, TF, USB errors, CPU,
   RAM/GPU, Pi-camera behavior and sensor deadlines. Verify measured plane distances
   against a physical reference; do not call synthetic unit tests accuracy tests.
4. Obtain approval before any unplug/replug, bounded recording or production page
   deployment. Discover actual topics and store exact verified manifest; unknown
   streams/modes stay unavailable. Do not insert dummy calibration.
5. `python3 project_atlas/tools/vision3d/package_candidate.py --output <new.zip>`
   creates eight candidate files and SHA256 manifest; no installation action.
   Source commit and package SHA must be verified. Reconcile **live** dashboard
   hashes against the reviewed base first; never overwrite newer live work.
6. Back up the three existing files (atlas_status_web.py, atlas_web_v2.py,
   web/v2/index.html) plus any pre-existing new-name asset, and record nonexistent
   paths. Actual candidate includes two new Python files/three assets and three
   existing files, eight total. Store backup outside served directories with
   timestamp, hashes, original modes and exact service state. Changing the backend
   requires a separately approved restart of only the dashboard service. No
   camera/motor/localization/Nav2 restart is part of page installation.
7. Install candidate to staging, compare hashes, then approved atomic deployment.
   Verify `/v2/vision3d`, one Home link, API no-source state, existing UI/camera,
   E-STOP/manual policy, resources and unchanged essential service identities.
8. Rollback: stop only the isolated new driver/viewer session if started; unset
   the Vision manifest; restore **backed-up live** existing files with modes;
   remove only paths marked newly created by this deployment; restart only the
   dashboard if separately authorized, then verify its original hash/routes.
   Do NOT restore old Git versions over newer live changes or reset shared USB.

No live backup/rollback directory exists because nothing was installed. The ZIP
is a review candidate, not an unattended installer. If hardware driver permission
changes are approved later, record their own reversible exact-file plan separately.

## Single next owner approval

Approve **isolated Astra/OpenNI driver preparation and one stationary depth/RGB
stream validation**, including review of any required targeted USB permission
change. Keep motors stopped, recorder OFF and production dashboard untouched.
After that evidence, request separate approval for the page deployment. Live
integration, calibration, USB replug reliability and resource commissioning remain
open; this report must not be used as an autonomy pass.
