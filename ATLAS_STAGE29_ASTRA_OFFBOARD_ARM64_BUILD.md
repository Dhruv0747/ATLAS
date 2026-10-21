# Stage 29 — offboard ARM64 preparation, 21 October 2026

## Result

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
