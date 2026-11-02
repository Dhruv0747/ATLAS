# Jetson-local RGB-D recording completion — 2026-11-02

Repository-only implementation; no deployment, camera activation or real capture.
Continues be99d87. No Windows, WSL, Grafana or cloud runtime dependency.

## Implemented

- Existing ViewerSession now accepts an optional recording owner and absolute
  monotonic deadline. The camera worker counts admission/startup in the same
  maximum 60 seconds; ordinary browser heartbeats cannot renew a recording lease.
  A stalled recorder loses its existing four-second lease. Existing normal viewer
  calls retain their behavior. Capture worker rejects CPU >=75%, RAM >=80% and
  temperature >=70 C; the recorder's strict safety predicate is unchanged.
- Optional ATLAS_RGBD_EVIDENCE_CACHE=1 retains original TFMessage batches,
  odometry and scan references in the existing web-node callbacks/listener.
  Default is disabled. No additional subscriber, ROS node, TF publisher or camera
  driver. Dynamic cache: <=128 batches of <=64 transforms over 0.5 seconds;
  static cache: <=128 transforms. Overflow/missing/stale evidence fails closed.
- rgbd_recording.host_binding(host) wires the existing camera cache/controller,
  host.snapshot() and existing local resource guard. No route or UI control is
  enabled. CPU admission is measured for one second; its time remains inside
  the total capture budget. The first recording heartbeat starts after admission.
- Original RGB/depth/CameraInfo CDR, source stamps, receipt stamps and original TF
  batch CDR reach the bounded evidence DB and standard rosbag2 SQLite conversion.
  Native Humble rosbag2 reader and existing replay admission are used in tests.
- Mapping cleanup no longer interprets OFF text alone as proof of shutdown. It
  requires matching ownership plus both driver_stopped/cloud_stopped evidence;
  ambiguous cleanup retains the owner receipt for investigation.

## Verification scope

70 focused tests PASS: 18 recorder/replay tests and 52 cache, lease, worker,
startup/shutdown and mapping cleanup tests. Native ROS 2 Humble tests use
synthetic messages and mocked hardware. Independent safety review PASS after
correcting the admission/first-heartbeat timing defect. Changed Python files
compile successfully.
They test original CDR compatibility, cache bounds, lease ownership, deadline,
strict boundary values, startup admission, missing evidence and cleanup.
No synthetic fixture is real Astra evidence or physical geometry acceptance.
Existing mapping/storage/viewer tests and evidence are reused where unchanged.
No RTAB-Map map generation or Jetson resource measurement is claimed here.

## Deployment and rollback preparation — NOT EXECUTED

1. Review the branch diff against fresh live hashes. Back up exact live files
   and service environment before any separately approved installation.
2. Install the new atlas_rgbd_context.py plus reviewed changes to
   atlas_vision3d_runtime.py and vision3d recording/supervisor helpers. Apply only
   the small callback/listener patch to the current atlas_status_web.py; never
   overwrite a newer live Dashboard with the repository copy.
3. Keep ATLAS_RGBD_EVIDENCE_CACHE absent, camera OFF and UI controls disabled.
   A separately approved web reload/restart is needed to load the optional host
   cache; this sprint does not authorize it. It must not restart ROS/Recovery.
4. Before any capture approval, provide real validated per-camera calibration,
   correct physical serial/dimensions/frame IDs and a valid camera-to-base TF.
   Call host_binding only in the existing host; a reviewed owner-authorized call
   to Recording.run is required. No generic public Start endpoint is added.
5. Capture is <=60 seconds including admission. Existing bounded owned-process
   shutdown follows (up to 11 seconds worker escalation, not extra recording).
   Keep at least 1 GiB free; capture DB <=128 MiB plus bounded journal, converted
   bag <=128 MiB. Archive failed result/DB checksums; do not retry automatically.
6. Convert only a COMPLETE, shutdown-verified capture with export_bag(directory).
   Replay remains isolated and calibration-gated. Jetson-local map DB/viewer
   paths and production SLAM/EKF/AMCL/Nav2 TF ownership are unchanged.
7. Rollback: stop only an approved owned capture using its existing controller,
   verify shutdown, preserve evidence, restore exact backed-up changed files and
   original environment. A web restart requires separate approval; do not
   automatically restart anything. Never delete maps or calibration evidence.

## Remaining gates

NO-GO for live capture/mapping now. Existing evidence inventory found no original
RGB+depth+CameraInfo recording suitable for replay; factory calibration contained
NaNs, registration and camera mounting TF remain unverified. These cannot be
replaced by distance preview, synthetic fixtures or guessed intrinsics.
The optional callback cache and host binding require reviewed installation and
stationary hardware validation. Real RTAB-Map memory/CPU headroom and map geometry
remain unmeasured. Existing local database quotas, integrity/quarantine and the
Jetson-hosted /v2/map3d viewer are implemented, not physically accepted.
