# ATLAS RTAB-Map isolated PC preparation

## Scope and architecture

Development branch: agent/rtabmap-offline-20261030, based on the existing approved
development branch. No Jetson installation, camera activation, production ROS
participant, TF modification or control command. No Build Your Own X dependency.

Ubuntu 22.04 WSL2 uses Humble binary RTAB-Map packages. The runner forcibly sets
ROS_DOMAIN_ID=179 and ROS_LOCALHOST_ONLY=1; it does not use production or Astra
Domain 77. No ROS daemon is needed. Existing SLAM Toolbox, EKF, Nav2 and their
map->odom/odom->base_link ownership remain unchanged. Mapping is namespaced
/atlas_offline, publish_tf=false, map frame map_3d_offline. External odometry and
LaserScan input are supported; no visual odometry replacement is launched.

Only approved offline replay publishers should use these inputs:

| Input | Local topic |
|---|---|
| Rectified RGB | /atlas_offline/input/rgb |
| Depth registered into RGB camera geometry | /atlas_offline/input/depth |
| Matching RGB CameraInfo | /atlas_offline/input/camera_info |
| Continuous external odometry | /atlas_offline/input/odom |
| LiDAR scan | /atlas_offline/input/scan |

Replay must supply /clock, static camera/LiDAR transforms and any dynamic TF at
source timestamps. Do not replay command topics, goals, production map transforms
or entire unfiltered bags. No production network bridge is provided or authorized.

## Calibration evidence and requirements

Reuse tools/vision3d/calibration_validation.py and checkerboard_calibration.py.
Saved Stage 32 evidence reports factory property 14 all-NaN, fallback CameraInfo,
RGB registration disabled, low-resolution depth and working 640x480 IR. These are
not validated RGB-D calibration. No existing evidence establishes physical depth
scale, RGB-depth extrinsics or a synchronized calibrated RGB-D recording. Do not
fabricate calibration from FOV, declare NaNs repaired or silently resize K.

Before real replay or stationary geometry evaluation:

1. Record exact camera serial, stream resolution, frame names and driver version.
2. Use existing checkerboard procedure with measured square size, diverse poses,
   withheld validation views and independently reviewed reprojection residuals.
3. Measure a matte planar target's axial distance from the optical reference at
   several supported distances; reuse depth_statistics for bias/noise/invalids.
   Preserve raw units (16UC1 millimetres / 32FC1 metres); do not tune scale to hide
   incorrect reference measurement. Define accuracy tolerance before testing.
4. Establish depth intrinsics and distortion separately; RGB calibration alone
   cannot calibrate depth. Validate RGB-depth extrinsics and registered edges.
5. Measure base-to-camera mounting transform and verify optical-axis conventions.
6. Compare original source stamps, clock domains, CameraInfo and TF coverage.
   Initial offline policy: maximum skew 30ms, age 500ms, reject future/nonfinite
   stamps. These are proposed mapping input limits, not changes to rover limits.

The admission manifest calls the existing validator and rejects missing metadata,
invalid calibration, unverified scale/registration, unavailable TF and timing
errors. Manifest booleans refer to independently reviewed evidence; they do not
perform physical measurement. This is an offline admission tool, NOT a continuous
live safety supervisor. A real replay adapter must check every bundle before
publication; live integration is blocked until that adapter is independently tested.

## Bounded execution and visualization

Source /opt/ros/humble/setup.bash. From tools/vision3d, run the synthetic-only
benchmark with `python3 benchmark_offline.py`. It does not require a camera or
real calibration; synthetic evidence is explicitly labelled and never suitable
as a real-camera calibration document.

The runner defaults to 30s, permits at most 60s, uses a new output directory,
checks output growth every 100ms and stops at a 256MiB soft budget. This is a
bounded test budget, not a hard filesystem quota; writes may overshoot between
checks. SIGINT allows database closure, followed by bounded forced termination.
Never delete an existing database to rerun. 1Hz mapping, five-message queues,
two OpenMP threads and 5cm occupancy cells reduce initial PC load. They are
engineering starting points, not proven camera accuracy parameters.

RViz configuration map_offline.rviz displays /atlas_offline/cloud_map in
map_3d_offline. Start RViz only on localhost Domain179, or inspect the resulting
database with rtabmap-databaseViewer on the PC. Visualization is PC-only and
must never be labelled an accurate ATLAS map when displaying synthetic fixtures.

## Resource evidence

WSL inventory: 16 logical CPUs, 15,879MiB RAM, 4GiB swap; filesystem 943GiB free
before package installation. Budget two compute threads initially; do not assume
GPU acceleration. ROS packages installed on the PC do not start rover services.

Grafana proxy queried at Unix time 1793374855: exporter UP, Jetson CPU61.37%,
RAM61.68%, GPU0%, maximum63.531C. These are scrape observations, not synchronous
camera admission checks. CPU75%, RAM80%, temperature70C safeguards unchanged.
Neither this sample nor the previously measured monitoring overhead proves
camera startup headroom. PC benchmark results are reported separately below.

## Native validation results

Installed PC packages: ros-humble-rtabmap-ros 0.23.13-1jammy.20261011.115255,
rtabmap-slam 0.23.13-1jammy.20261011.111917. Binary package installation succeeded;
no source build was necessary. Its metapackage includes PC-only optional examples,
Nav2 and camera libraries; none of these drivers/services were launched.

Six new unittest methods (including nine rejection subcases) and six reused
calibration tests passed. Python compilation and git whitespace checks passed.
The first native fixture exposed zero covariance on unused odometry axes and
missing odometry TF. Corrected only the synthetic fixture, with positive diagonal
covariance and timestamped odom->base_link. No real odometry tuning occurred.

Corrected native run: 85 synthetic RGB-D/scan/odom bundles, 17 mapping updates,
clean exit0, 17 database nodes and SQLite integrity `ok`. Native RTAB-Map consumed
0.53 CPU-seconds over 24.943s sampled runtime (2.125% of one core), peak observed
RSS202.17MiB. Full fixture/runner/native child total CPU4.258s over26.846s,
largest-child peakRSS208112KiB. These results characterize a tiny stationary
synthetic scene; they are NOT real-camera reconstruction, loop-closure, GUI or
long-duration memory benchmarks. Camera startup and motion accuracy remain untested.

Database1355776bytes, SHA256
3eb9ab3df00d20a879f2b12cce5993965590581d56482096696320ab38b72a8b.
Evidence retained under /opt/atlas-rtabmap-evidence/20261030 on WSL2, including
the initial failed fixture and corrected run, resource samples and native logs.
No lingering benchmark/RTAB-Map process found after completion. RViz configuration
is prepared; actual interactive GUI rendering remains PENDING.

## Next approval and rollback

No live map accuracy claim. Next separately approved operation is a bounded
stationary camera/calibration evidence session, after fresh E-STOP/zero-command,
sensor/resource/USB/hash checks, using existing guards and no automatic retry.
It must establish actual paired images/CameraInfo/TF, depth-scale references and
calibration quality before any metric mapping claim. No motion is requested.

Rollback: stop only the local runner/fixture/RViz processes, retain evidence and
database, and revert this isolated development commit if required. No Jetson
rollback is necessary because nothing was deployed. PC apt additions can remain
idle; if removal is desired inspect apt history and simulate removal first.
Do not indiscriminately autoremove shared ROS/monitoring dependencies.
