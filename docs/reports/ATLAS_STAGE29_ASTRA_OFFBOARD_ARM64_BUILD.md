# Stage 29 — offboard ARM64 preparation, 21 October 2026

Calibration continuation: [new evidence and gates](ATLAS_ASTRA_PRO_CALIBRATION_AND_POINTCLOUD_VALIDATION.md).
120-byte layout matches pinned SDK; vendor validity check is incomplete, but
NaN root cause remains unresolved. Fresh458 hashes match; stationary admission
passed at CPU67.055%, RAM66%, hottest63.187C. No stream/rebuild/live change.
94 targeted tests pass including six new offline calibration/statistics tests.
Metric cloud remains blocked; physical accuracy needs separately approved targets.

## Continuation — current verified checkpoint, 21 October 2026

**Driver cross-built, isolated target loader verified, and concurrent real ROS
RGB + depth received. Metric PointCloud2 is blocked by invalid factory calibration.**
All test processes are now OFF. No production Dashboard/autostart deployment,
motion, recording, map, steering, encoder, EKF/AMCL/Nav2 or Pi-camera change.
The historical incomplete-sysroot report below is preserved, superseded here.

### Architecture / dependency resolution

PC is build-only. The runtime binaries, private libraries and ROS streams run
locally on Jetson using its native Humble; Windows/WSL/PC ROS/internet are not
runtime dependencies. No PC camera feed, DDS server or remote control path was added.

The transfer blocker was bypassed rather than retried: PC verified 18,091 complete
ROS files against their complete entries in the earlier partial tar, reused that
subtree, and extracted 504 ARM64/all dependency debs into a NEW private sysroot.
No incomplete archive was declared complete. No large target tree was retransferred.

Crucial new evidence: target `libcv_bridge.so` actually needs OpenCV
`libopencv_{core,imgproc,imgcodecs}.so.4.5d`, despite custom OpenCV4.8 also being
installed under `/usr/lib`. Private signed Ubuntu Jammy ARM64 OpenCV4.5.4 packages
match that ABI. Actual target `ldd -r` then verified resolution. This is not an
assumption that 4.8 and 4.5 are interchangeable.

Ubuntu target packages were downloaded using separate apt lists/cache/status and
the Ubuntu archive key, not installed into host or target. Total cached deb bytes
282,422,610. Three prior private ROS packages were fetched from the official apt
endpoint and matched their previously recorded SHA256 exactly (camera-info-manager,
camera-calibration-parsers, image-publisher). HTTPS on packages.ros.org presented
a hostname-mismatched certificate; no TLS check or trust policy was disabled.
Its standard HTTP apt endpoint was used with the pre-established pinned hashes.

PC provenance: `/root/atlas-stage29/cross-sysroot-manifest.json` records reused-file
hashes and all dependency versions/hashes; SHA256
`224ea3f96de3ff3a54b052ece496e485b54bec4e8d3b423a292756a6cff5668e`.
Absolute links and exported CMake paths were relocated only inside the private
copy. Native host Python/code generators were separated from target Python headers,
libraries and `cpython-310-aarch64-linux-gnu` extension suffix. The temporary
pkg-config manual-install marker was restored to its original automatic state;
no new host package was needed in this continuation.

### Build / package / installed hashes

Pinned source remains `f7e71d9ce806e788cb48d8580aac2c778fba4214`.
Reviewed isolated source patch: use target processor rather than host uname,
respect Release selection, and request the OpenCV modules used by this driver.
Patch is `project_atlas/tools/vision3d/vendor_arm64.patch`; SHA256
`1e1b5b132cf98a85a13f1c6c500ac8dd6d14c7652505dc043d9a7763f130cc1a`.
`build_arm64_pc.sh` builds sequential packages with at most two compiler jobs.
Both `astra_camera_msgs` and `astra_camera` completed successfully, including
OpenNI, UVC, CameraInfo and compiled XYZ/XYZRGB implementation. Unused RPATH
and cross-host Python suffix artifacts were rejected/removed from the candidate.
Initial dependency/configuration/link failures are retained in PC cross-log;
they were resolved, not erased or labeled successful.

Observed PC compile window (three 1-second samples): whole-WSL CPU12.76–12.82%,
two compiler processes up to roughly1.2 GiB RSS each, >12 GiB available.
This is not a full Windows utilization benchmark or full-build peak certification.

Candidate `astra-arm64-stage29-v2.tar.gz`: **2,498,814 bytes**, 458 hashed files,
28 ELF64/AArch64 objects, no unexpected X86-64 ELF or runtime search paths.
SHA256 **`8d840fb9166212ea707392e76e74cfd07aba2b4c049f6bc6608ca228118f553c`**.
v1 packaging rejection (cross-build RPATH in generated Python library) is preserved;
v2 uses explicit no-RPATH linking. No large binary is committed to GitHub.

One rate-limited 2048-kbit/s candidate upload passed 20 independent guard samples:
whole-Jetson CPUmean65.91%, peak68.59%, all required service identities unchanged.
Installed ONLY under:
`/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2`.
Archive hash and all458 installed file hashes verified. `ldd -r` on executable,
driver library and Orbbec plugin returned0, no missing libraries/undefined symbols.

| Installed file | SHA256 |
| --- | --- |
| `lib/astra_camera/astra_camera_node` | `2f7a58f9b409ee98aa38dde8966fbd661f0c532c589eead32207a58964635aa9` |
| `lib/libastra_camera.so` | `6ae876010c824be97d2545996f897e40e07e0c97fa7a45694f96f342cf6e22a6` |
| `lib/libOpenNI2.so` | `d7231df09a6a242990507fce4eb75329a67c8f298bd8f110baa8dddc344f6bda` |
| `lib/OpenNI2/Drivers/liborbbec.so` | `b6511b00891360bda20f452847db5f25d67d588597bad5991a9756ef5dffa95b` |

Do NOT source cross-generated package `setup.bash`: its development prefix chain
mentions PC paths. `astra_runtime_env.sh` instead sources native `/opt/ros/humble`
and sets only isolated Jetson library/message prefixes. It launches nothing.
The tested guardian set those native paths directly; no PC path was needed at runtime.

### Explicit owner CPU exception and failure history

Original75% CPU stop remained active for upload and initial baseline. A new ROS
observer baseline stopped at93.87%. The owner then explicitly directed
"dont stop ignore cpu load". Subsequent BOUNDED stationary tests required an
explicit `--cpu-report-only-owner-approved` flag. Production policy/default
guard thresholds were NOT changed. RAM80%, thermal70 C, stop latch, manual-only,
commissioning disarmed, zero command/output and freshness protections remained enforced.

New-DDS observer plus driver startup timed out the Dashboard status API; a
staggered observer also hit that timeout. No timeout/freshness bypass was applied.
The observer was replaced by a Jetson-local receive-only connection to the ALREADY
running Foxglove bridge, without creating another ROS participant. Fresh source
timestamps, control-policy, cmd_vel, four wheel outputs, mission state, LiDAR,
IM10A, encoders and Pi camera were checked directly. Actual resources came from
proc/sysfs instead of depending on the busy noncritical Dashboard HTTP handler.
Only subscribe/unsubscribe operations exist; no publish/service/parameter path.

The bridge rejected the legacy `foxglove.websocket.v1` protocol with HTTP400.
An Origin-header hypothesis was rejected. Offering `foxglove.sdk.v1` fixed the
client handshake and was verified by negotiated protocol. No bridge restart or
capability/network change occurred. This matches the official SDK's
[handshake implementation](https://docs.rs/foxglove/latest/src/foxglove/websocket/handshake.rs.html).
A hash-pinned 82-kB pure-Python websocket-client wheel is private staging only,
not a global installation or permanent PC dependency.

### Real ROS evidence / performance

Driver namespace `/astra`; external TF publication, registration, IR, colored
cloud and point-cloud enablement were OFF. No identity/body transform was inserted.

| Verified topic | Type / observed mode | Concurrent count / receive rate |
| --- | --- | --- |
| `/astra/depth/image_raw` | `sensor_msgs/msg/Image`,160x120,16UC1,mm; `astra_depth_optical_frame` | 97 /10.53 Hz |
| `/astra/depth/camera_info` | `sensor_msgs/msg/CameraInfo`,same size/frame; fallback K | 97 /10.53 Hz |
| `/astra/color/image_raw` | `sensor_msgs/msg/Image`,320x240,rgb8; `astra_color_optical_frame` | 139 /15.10 Hz |
| `/astra/color/camera_info` | `sensor_msgs/msg/CameraInfo`,320x240,same color frame; fallback K | 138 /15.02 Hz |

Depth-only short test received7 images/6 CameraInfo messages; this proves real
ROS messages, not duration stability. The first RGB-only test received2 images/
1 CameraInfo near the end of its startup-limited window and did NOT pass sustained
acceptance. An extended RGB-only attempt stopped on mission-status age>2 seconds;
it was NOT continued merely because CPU had report-only approval. The distinct
concurrent test subsequently passed an8-second observation window after first data,
with all required direct statuses fresh. Earlier failed ledgers remain failed.

| Window | Whole Jetson CPU mean/peak | RAM peak | Thermal peak | Astra CPU mean/peak (100%=one core) | Driver RSS peak |
| --- | --- | --- | --- | --- | --- |
| Astra OFF, ROS-observer baseline |76.16/99.56%|65.00%|63.31 C|not applicable|not applicable|
| Depth-only, bridge observer |90.23/100%|66.77%|63.50 C|14.70/29.91%|93,300 KiB|
| Concurrent RGB+Depth, bridge observer |82.59/99.86%|67.97%|64.06 C|14.34/40.02%|98,116 KiB|

These windows include startup and different observer paths; they are NOT matched
steady-state A/B benchmarks and do not prove concurrent mode costs less CPU.
Do not attribute whole-system90% to the camera: its own process was measured
separately. Sampled GPU peak was0% concurrent,59.5% in depth window; other GPU
workloads were not controlled, so no camera GPU attribution is established.

Pi camera delivered215 original compressed frames at9.20 Hz concurrently (baseline
9.90 Hz); service PID/restarts unchanged. LiDAR received6.62 Hz, IMU9.33 Hz,
encoders9.02 Hz in the concurrent observer. Maximum observed receive gaps:
Pi0.583 s, LiDAR0.707 s, IMU0.617 s, encoders0.467 s,
control-policy0.707 s, cmd_vel0.850 s, mission1.177 s. No required freshness gate
failed in that successful window. This is NOT a guarantee of unchanged long-run
timing or moving localization. USB electrical bandwidth/endurance/errors were not
instrumented;43,260,346 received bridge bytes include decoded ROS/Pi data and
must NOT be called USB-wire throughput. Source-frame losses remain UNKNOWN:
published images omit hardware frame indices and hardware acquisition timestamps.
Nominal depth mode30 FPS is not the observed ROS/bridge receive rate10.53 Hz.

Image headers use ROS processing time (`node_->now()` in vendor code), not SDK
capture timestamps. Last concurrent receipt-minus-header samples were about
10.8 ms depth /7.0 ms RGB; these are not exposure/capture latency guarantees.

### Calibration / PointCloud2 hard blocker

A separate bounded READ-ONLY OpenNI property14 query used the vendor120-byte
`OBCameraParams` ABI, without starting a stream. SDK returned success/120 bytes,
but ALL factory fields were NaN. `valid_factory_intrinsics=false`.
This proves this installed API path does not supply usable calibration; it does
NOT prove damaged hardware or that all alternative calibration access is impossible.

Driver falls back to SDK-FOV-derived intrinsics: depth fx=fy142.58555,
cx79.5/cy59.5 at160x120; RGB fx=fy285.17110,cx159.5/cy119.5 at320x240.
Those are observed fallback values, not independently calibrated values. Physical
depth accuracy and RGB/depth registration remain unmeasured. No metric PointCloud2
was enabled. No XYZ/color registration/extrinsics were fabricated.

SDK priority warning persisted. Process context had CAP_SYS_NICE absent
(CapEff0) and RLIMIT_RTPRIO(0,0), consistent with inability to elevate real-time
USB scheduling. Exact syscall errno was not captured (strace unavailable); no
privileges/RT limits were changed and the warning is NOT certified harmless.
Vendor duplicate-component-factory warning and static-parameter undeclare errors
on shutdown were also retained; no production service was restarted to hide them.

### Dashboard preparation / rollback / remaining approval

Offline candidate `config/vision3d_stage29_depth_verified.json` lists ONLY actual
verified RGB/depth topics. CameraInfo is deliberately NOT fed to metric-XYZ UI
calculation while calibration is unverified. Cloud and IR are omitted. No redesign,
Home shortcut deployment, existing Camera-page replacement or Dashboard restart.

| Milestone | Current status |
| --- | --- |
| TOOLCHAIN READY | YES |
| SYSROOT READY | YES for the successful cross-build; hashes retained |
| DRIVER BUILT | YES, both ARM64 packages |
| ROS STREAM VERIFIED | YES, real RGB/depth/CameraInfo; short bounded tests |
| RGB + DEPTH VERIFIED | YES concurrently, CPU-exception smoke scope only |
| POINT CLOUD VERIFIED | NO — valid calibration required |
| DEPTH ACCURACY CHECKED | NO — physical reference measurements required |
| DASHBOARD READY | Partial offline topic manifest; metric 3D/resource endurance pending |
| DEPLOYED | Isolated files only; runtime OFF, no autostart/production deployment |
| NAV2 INTEGRATED | NO; expressly out of scope |

88 targeted offline/native-Humble tests pass without camera access or ROS nodes,
including real cross-compiler output, ABI, read-only protocol, direct stale/zero/
stop guards, explicit CPU-exception semantics and uncalibrated-XYZ exclusion.
No claim that the entire repository suite or physical autonomy passed.

Final six essential service PID/restart identities unchanged; recorder OFF, stop
latched, manual-only, commission disarmed, zero commands. No test driver/observer
remains. Rollback: leave the isolated runtime unused; production does not source it.
No uninstall/service restart needed. Preserve package/evidence; no cleanup deletion.
Target evidence is in the existing `astra-20261021` staging directory, notably
`stage29-runtime-loader-result.json`, `stage29-bridge-concurrent-steady-window.json`
and `stage29-factory-intrinsics-result.json`. PC manifests/build logs remain private.

Next necessary action: obtain valid camera calibration (a verified device-specific
file, or separately agreed guided live calibration with the minimum physical
targets). Do not enable metric clouds using fallback K just to finish a checklist.
No further drive test is required. Production 3D Dashboard deployment/autostart,
Nav2 integration and any recording remain separately unapproved. CPU exception
was per bounded test, not a permanent production policy change.

## Historical initial Stage 29 result

**PC ARM64 cross-compiler installed and verified. Astra driver NOT built.**
Target-library snapshot preparation was interrupted at the unchanged CPU guard;
partial archives are NOT a verified sysroot or deployable package. No camera or
production service was launched. This is a preparation milestone, not ROS integration.

## PC audit and actual changes

- Windows 11 Pro 10.0.26200, 64-bit; about 31.8 GiB RAM, 17.2 GiB free at audit.
- Existing Ubuntu-22.04 WSL2 reused, x86_64; 15,879 MiB RAM visible, about
  14,970 MiB available initially, 949 GiB free disk. Existing Humble, Python3,
  colcon, CMake3.22.1 and host GCC11.4 retained. WSL session already runs as root;
  no password, Windows elevation, restart, firewall or security change required.
- Installed only `apt-get install -y --no-install-recommends g++-aarch64-linux-gnu`:
  25 new compiler/runtime-development dependencies, 58.7 MB download, 206 MB installed;
  no package upgrades/removals. Transaction recorded in WSL `/var/log/apt/history.log`.
- Key versions: g++-aarch64-linux-gnu `4:11.2.0-1ubuntu1`,
  gcc-11-aarch64-linux-gnu `11.4.0-1ubuntu1~22.04.3cross1`,
  binutils-aarch64-linux-gnu `2.38-4ubuntu2.12`.
- No QEMU, Docker, Podman, ROS reinstall or new WSL distro. Native cross compilation
  avoids whole-platform emulation and reuses host Python/code-generation tooling.
- Private workspace `/root/atlas-stage29`, about 1.3 GiB including partial evidence.
  Existing `/home/jetson/project_atlas` and native ROS were not changed.

## Source, target libraries and reproducibility

Public vendor repository cloned on PC and detached at
`f7e71d9ce806e788cb48d8580aac2c778fba4214`; no latest-SDK substitution.
`/root/atlas-stage29/source/ros2_astra_camera` contains the pinned source.
The cross-toolchain candidate in this repository requires an explicit sysroot,
selects AArch64 compilers and rejects host library/include/package lookup.

Read-only target version query confirmed libc6 `2.35-0ubuntu3.8`, libstdc++6
`12.3.0-1ubuntu1~22.04`, OpenCV `4.8.0-1-g6371ee1`, glog
`0.5.0+really0.4.0-2`, rclcpp `16.0.19-1jammy.20260605.142447`,
cv_bridge `3.2.1-1jammy.20260605.142654`. Target OpenCV is NOT the ordinary
Jammy4.5 dependency: do not substitute host x86 OpenCV or assume its ABI matches.

Vendor CMake checks build-host `uname -m`, which would select its x64 OpenNI SDK
during cross compilation. A future isolated patch must use target
`CMAKE_SYSTEM_PROCESSOR` and record its hash; no such patch was deployed to Jetson.
Host code-generation tools and target libraries must remain distinguished.

## Snapshot attempt and CPU evidence

An initial uncompressed read-only copy selected ROS, headers and target libraries
while excluding CUDA/tegra directories. Its scope was found unnecessarily large
(target library directory 4.4 GiB, including irrelevant TensorRT archives); that
owned transfer was stopped and its partial file retained.

A smaller base/header/config/source transfer used low-priority gzip level1.
One observed whole-Jetson CPU sample reached **75.7983%**, RAM60%, hottest
thermal62.375 C. Transfer was stopped; no unchanged-condition retry followed.
A previous copy sample was CPU70.6954%, RAM63.459%, thermal61.906 C, with stop
latched, manual-only, commissioning disarmed, zero commands and recorder OFF.
These are sampled total-system observations, NOT compressor CPU attribution or
proof that copying caused the complete spike. Nice priority is not a CPU quota.

Preserved PC evidence: `target-input.tar`, `target-base.tar.gz`,
`partial-extraction.txt`, `base-extraction-status.txt` under the private workspace.
Extraction reported unexpected EOF. Completed entries can assist further
preparation but the overall snapshot MUST NOT be used as a verified target or
packaged for deployment. Raw libraries/archives are not committed to GitHub.

## Offline tests and performance

Two new PC-only tests passed:
1. Compile/link a small shared object with the installed ARM64 C++ compiler and
   verify ELF64/AArch64 (not X86-64) using ARM64 readelf.
2. Check the toolchain prohibits implicit host-library/include/package lookup
   and requires an explicit sysroot.

This is a real compiler-output check, NOT compilation of Astra or its messages.
Test command wall0.31 s, user0.04 s, system0.03 s, process CPU25%, maximum RSS
25,120 KiB reported by `/usr/bin/time -v`; not whole-PC utilization or a full-build
resource estimate. WSL afterward had 14,891 MiB available, swap unused.

## Milestone separation / package

| Milestone | Result |
| --- | --- |
| ARM64 toolchain | INSTALLED, compiler probe VERIFIED |
| Compatible sysroot | INCOMPLETE, not validated |
| Astra driver/messages build | NOT RUN on PC pending complete target dependencies |
| Binary dependency compatibility | NOT VERIFIED for Astra |
| Deployment package / SHA256 | NONE — no driver package created |
| ROS RGB/depth/CameraInfo/IR topics | NOT VERIFIED |
| Concurrent RGB+Depth | NOT VERIFIED |
| PointCloud2 | NOT VERIFIED |
| Physical depth accuracy | NOT CHECKED |
| Dashboard / autostart / Nav2 deployment | NONE |

Previous separate 15-frame native camera smoke evidence remains valid but is not
repeated or promoted to a ROS/concurrent test. Pi camera remains the primary RGB/AI
camera; RPLIDAR/localization/control configurations are unchanged. No dummy
intrinsics, transforms or topic manifest were inserted.

## Rollback and next action

No Jetson installation/production rollback is needed: only read-only version/copy
operations, no service restarts, no control changes, no recording or motion.
PC artifacts can remain unused; preserve interrupted evidence. To remove compiler
tools later, first review `apt-get -s remove g++-aarch64-linux-gnu`; remove only this
transaction's unused packages after dependency review. Do not blindly autoremove
existing ROS packages or delete the WSL distro. No automatic rollback/removal run.

Next prerequisite is a complete compatible target dependency set, not another
Jetson compile. Prefer existing ARM64 package artifacts; for target-custom OpenCV,
design a narrow, **measurably CPU-bounded** snapshot export rather than another
unbounded tar/gzip transfer. Current approval covers isolated preparation but not
raising75%, stopping essential services, dashboard deployment or autostart. No
additional drive test or operator action is needed now; do not activate live
streams until the package, library linkage and fresh full safety gate pass.

Final read-only check: stop latched, manual-only, commission disarmed, commands
zero, recorder OFF; essential six service PID/restart identities still match
Stage28. No owned transfer/build/Astra-node activity remains. RAM60%, hottest
thermal62.937 C. This final check did not sample CPU, so it is NOT a fresh full
resource admission pass and authorizes no activation.
