# Real Astra RGB-D capture readiness — 2026-11-02

NO-GO for live capture with the current package. No camera start, service restart,
monitoring recovery, deployment or robot motion was performed.

## Read-only evidence

At approximately 09:52 IST, inspected SQLite topic tables from 123 Jetson bags
under project_atlas/data, .local/share/atlas and project-atlas-migration. No
sensor_msgs/msg/Image or CameraInfo topics found in readable databases. One old
navigation database (dhruv_room_to_hall_house_teach-20260824-162312) is malformed;
its contents are UNKNOWN and were not repaired. No MCAP or capture.sqlite/NPY/NPZ
recording was found in those searched roots. This is a scoped search, not a claim
about every filesystem. Previous local search inspected ten bags without image
or CameraInfo topics.

Existing Vision Lab status reports camera OFF, USB connected/access available,
CameraInfo empty, calibration NOT VALIDATED with factory NaNs, RGB registration
DISABLED and base_link extrinsics unverified. Concurrent RGB/depth is marked
untested through Dashboard. No current RGB-D frames were obtained. Status claims
are not a new physical accuracy test.

## Existing reusable components and remaining wiring

calibration_capture.py already provides a 60-second single-use policy, original
serialized CDR storage with integer source stamps and SHA256, 128 MiB SQLite page
limit and integrity checks. Its header explicitly requires a separately reviewed
live adapter; no production caller connects this Supervisor to the camera session
controller. The existing pixel/IR capture tools do not preserve synchronized
original RGB/depth plus CameraInfo and cannot substitute for it.

astra_bag_adapter extracts originals from ROS bags; astra_replay consumes ROS bags,
not capture.sqlite. Therefore a capture.sqlite result alone is NOT ready for
existing bag replay. Do not silently reinterpret or restamp recordings. The
smallest missing implementation is the live evidence binding using the current
controller and existing recorder, including TF/odom/scan recording and a compatible
bag output; alternatively an explicit tested conversion is required. This must
be verified offline before asking for camera execution approval.

## Proposed single stationary session (not executable yet)

- Duration: hard maximum 60 seconds from admission, including startup, no retry.
- Existing controller only; concurrent RGB/depth requested once after approval.
- Local one-second safety observations; CPU <75%, RAM <80%, temperature <70 C,
  E-STOP latched, manual-only, commissioning disabled, zero commands, stationary
  encoders, fresh telemetry. Missing/malformed observations abort.
- Original RGB/depth/Image and CameraInfo CDR and integer stamps, actual dimensions,
  encoding, step and endian metadata. Preserve receipt times separately.
- Missing complete bundle at 10 seconds, frame age >500 ms, skew >30 ms, regressing
  stamps, delivery gap >1 second, malformed image/calibration or missing required
  timestamped TF abort valid-bundle admission. Never fabricate intrinsics or TF.
- Depth 16UC1 millimetres / 32FC1 metres is an encoding convention, not physical
  scale validation. Use an owner-measured stationary planar target distance and
  measured camera-to-base offsets/orientation before claiming metric geometry.
- Expected artifacts: original message recording, topic/encoding inventory,
  source/receipt timestamps, measured TF evidence, admission/abort reason,
  resource timeline, checksums and shutdown result. Invalid data is not map input.
- Recording budget: current Evidence DB 128 MiB; rollback journal can add another
  DB-sized allocation. Require at least 1 GiB free, enforce whole-session quota in
  the missing binding. Stop early on storage limit; never delete old maps.
- Cleanup: stop only the owned capture child and owned camera session via existing
  controller; verify OFF and driver termination, retain evidence, no automatic
  restart. Existing 4-second lease is the crash fallback but must be tested with
  the actual binding; Python finally alone is insufficient. Do not claim a proven
  total shutdown latency until that integration is tested.

## Replay and viewer gate

Replay only after valid calibration, registered geometry, synchronization and TF
pass. Retain separate mapping domain and publish_tf=false; SLAM Toolbox/EKF/AMCL/
Nav2 ownership unchanged. No production initial pose, transform or command output.
Jetson map storage and /v2/map3d viewer remain the runtime destination. Existing
local DB integrity/quarantine and 20,000-point viewer export tests passed in the
previous commit; no real new map/database/cloud was produced here.

Focused validation: test_calibration_capture.py — 4 tests PASS (including safety,
full simulated duration, missing/stale inputs, write/cleanup/poll failures and
bundle rejection subcases). Prior 21 adapter/storage/viewer tests reused unchanged.
No new Jetson resource/headroom claim. Fresh admission is required before any
future approved capture.

Next step: complete only the missing controller-to-recorder/TF binding and its
failure cleanup offline, then request one stationary capture approval. Monitoring
recovery remains separate and does not block this development.
