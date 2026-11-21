# Onboard mapping continuation — 2026-11-02

Offline preparation PASS; live mapping and deployment NO-GO.

## Existing implementation retained

Jetson-only onboard adapter uses original image stamps and rejects missing image/info,
frames older than 500 ms, RGB-D skew above 30 ms, mismatched dimensions or reviewed
CameraInfo. Requires registered depth, calibration, explicit separate domains and
TF edge allowlist. External odometry and LiDAR are copied only into the isolated
mapping domain. RTAB-Map publish_tf remains false; production map/odom TF ownership
is unchanged. No camera driver was rebuilt.

Local SQLite map storage, integrity checks, interruption quarantine, 2 GiB session
limit, 8 GiB retained-session admission limit and 1 GiB free reserve already exist.
The Jetson-hosted /v2/map3d viewer and read-only /api/map3d routes consume local
cloud.json snapshots capped at 20,000 points. No PC, cloud, CDN or Grafana runtime
is required. Actual current live route deployment was not checked this session.

## Small completed correction

onboard_adapter.py now validates original timestamp ranges and XYZ PointCloud2
layout before writing the existing local viewer artifact. Organized row padding,
big/little endian and finite-point filtering are retained. Invalid strides,
truncated data, overlapping/missing/duplicate fields fail before artifact writes.
Existing error handling stops optional mapping through the supervisor.

## Real evidence inventory

Read-only SQLite topic-table inspection of ten .db3 files in the existing
ATLAS-github/artifacts tree found zero sensor_msgs/msg/Image or
sensor_msgs/msg/CameraInfo topics and no database read errors. Available types
include LaserScan, Odometry, Imu and TFMessage; these alone cannot establish
RGB-depth registration, camera intrinsics, camera mounting TF or image skew.
No real Astra depth entered RTAB-Map in this work. Test fixtures are synthetic,
not calibration. No new geometry or calibration values were invented.

## Remaining gate and smallest next step

Existing onboard_mapping.json remains disabled with unset calibration files,
registered depth topic, registration evidence, production domain, odometry topic
and TF evidence. A stationary recorded RGB/depth/CameraInfo bundle with original
stamps plus measured/verified camera TF is required. First reuse such a recording
if supplied; otherwise separately approve the existing bounded stationary capture.
Do not enable mapping before that validation and Jetson package/resource preflight.
No camera activation, Jetson access, installs, restarts or movement occurred here.

Existing configuration targets 1 Hz RTAB-Map updates with bounded queues and two
OMP threads. This is configuration, not measured CPU/RAM demand. No new Jetson
performance measurement or proof of headroom is available. CPU <75%, RAM <80%,
temperature <70 C, E-STOP and existing safety checks remain unchanged.

Validation: focused native ROS Humble image admission, storage/quarantine, API
traversal, cleanup ownership plus new cloud/timestamp tests. No production TF
publisher or hardware session was started. Live mapping accuracy remains UNKNOWN.
