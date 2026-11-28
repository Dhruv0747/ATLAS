# Mandatory standalone ATLAS mapping architecture

Owner requirement supersedes any suggestion that the PC is required for normal
mapping. Jetson hosts camera processing, RGB-D admission, RTAB-Map, localization,
Nav2, supervision, database storage and dashboard map serving. Windows/WSL/Grafana
are optional development/visualization/backup tools only. No deployment performed.

## Existing evidence and implementation status

Jetson Astra driver and diagnostic distance/preview implementation already work;
no replacement driver is introduced. Existing depth decoding uses original
16UC1 millimetres or 32FC1 metres. Preview geometry is explicitly uncalibrated;
finite fallback CameraInfo is not independent calibration. RGB alignment and
camera mounting TF remain unverified. Existing EKF, LiDAR, IMU, encoders, SLAM
Toolbox and Nav2 remain unchanged.

PC RTAB-Map0.23.13 native synthetic test previously passed:17 nodes, SQLite
integrity OK, native CPU2.125%onecore/202.17MiB peak RSS. Not Jetson performance.
Latest measured parked Jetson samples:CPU60.34–63.31%, RAM<=64%, temp<=63.16C.
No onboard RTAB-Map installation or mapping benchmark has occurred.

Recorded data search this turn: all .db3 topic inventories under the existing PC
ATLAS-github/artifacts tree contained no Image/CameraInfo topics; known Astra
stationary/concurrent artifact folders had no raw/npy/npz/cdr/mcap payloads. The
known Jetson astra-20261021 folder (depth3) similarly had no matching image bags
or raw payload candidates. This is a scoped search, not proof no recording exists
anywhere. Existing reports/screenshots/scalars cannot be converted back to raw
RGB-D. Therefore real Astra depth entering RTAB-Map is NOT demonstrated.

## New repository-side work

- calibration_capture.py: single-use60s state machine, 10s missing-stream timeout,
  one-second safety observation/window checks, stale/unknown rejection, original
  integer source timestamps and CDR payload checksums in bounded SQLite storage.
- astra_bag_adapter.py: read-only extraction of the four existing Astra topics;
  no camera driver, activation, invented intrinsics, RGB or TF. Unknown depth units
  rejected. Recorded messages preserved byte-for-byte. Up to60s/7200messages.
- astra_replay.py: isolated localhostDomain179, topic-allowlisted native rosbag
  replay to existing RTAB-Map inputs. Full prevalidation rejects stale/skewed,
  malformed or unpaired image/CameraInfo bundles. No command topics. Requires
  evidence-backed registration/calibration manifest and recorded odometry/scan/TF.
- 7 focused new test methods pass, including native Humble CDR round-trip,
  payload hashes/nanosecond timestamps, no-data rejection, safety/timeout/write
  failure/cleanup and topic allowlisting. No repeated camera or mapping benchmark.

The supervisor is an offline-tested CORE, not a complete live activation package.
The nonblocking local observation/ROS capture adapter, independent process-death
shutdown enforcement, free-space reserve and actual shutdown acknowledgment still
need integration and tests. A callback or tick alone cannot guarantee physical
camera shutdown after a supervisor crash. No camera-session readiness claim.

Existing IR/depth scalar capture tools are reused as references; no need to
repeat passed camera tests or require a checkerboard before ingesting usable
existing recorded evidence. However missing recordings currently block real replay.
The calibrated replay path deliberately stays strict. An UNCALIBRATED depth-only
reconstruction using ORIGINAL finite driver CameraInfo can be added independently;
it must not manufacture colour alignment/odometry or relax calibrated map gates.
That provisional native path is not yet implemented or demonstrated.

## Exact onboard changes still needed (approval-gated)

1. Pin compatible Humble ARM64 RTAB-Map packages in an isolated Jetson prefix,
   audit dependencies and produce hashes/rollback before installation approval.
2. Implement local RGB-D adapter using the existing Astra streams in Domain77.
   Carry allowlisted odometry/LiDAR/TF from production through a local-only bridge;
   no command/goal interfaces. Reuse external EKF rather than another VO/EKF.
3. Integrate independently supervised one-shot capture with existing camera owner;
   no duplicate driver. For persistent mapping, a separately reviewed local lease
   must replace dependence on a remote viewer; do not bypass existing viewer guards.
4. Add optional disabled-by-default mapping service and local safety supervisor.
   Keep EKF sole odom->base_link owner. SLAM Toolbox OR AMCL owns map->odom.
   RTAB-Map publishes no production TF; its optimized map is separately named.
5. Local session directories: bounded SQLite growth plus journal allowance,
   initial2GiB session target and measured free-space reserve. Flush/close on stop;
   never overwrite last verified map. After interruption validate a preserved copy,
   quarantine corruption, and require explicit resume. Disk full must stop mapping.
6. Add read-only dashboard map/status endpoints and lazy-loaded, decimated cloud
   chunks to the existing white-glass UI. No continuous full-cloud regeneration;
   serve from Jetson. Browser closes/disconnects without stopping the future local
   mapper. This UI is DESIGN ONLY; current preview is not a stored-map viewer.

## Resource feasibility and autonomy

No defensible measured minimum exists yet. Initial targets:1Hz map processing,
bounded queues, limited working memory, supported reduced capture resolution/FPS,
512MiB additional RAM target; up to768MiB only if total headroom permits. Camera
driver and registration costs must be included. No GPU acceleration assumption:
inspect the exact ARM64/OpenCV CUDA build before enabling any supported operation.
RAM80%, CPU75%, temperature70C limits and one-second local guard unchanged.
Do not average away spikes or disable useful voice/reporting/control services.

On sensor loss/resource overload/invalid localization, cancel exploration through
existing safety arbitration, stop movement, close mapping and retain evidence.
No mission auto-resume after reboot. Initial mapping remains parallel/read-only
relative to navigation. Future 3D costmap integration requires separate evidence
for overhangs, floor hazards, full footprint and independently safe reverse.

Validation gates: offline adapter/supervisor -> calibration/stationary depth ->
bounded onboard camera+mapper -> supervised manual-drive geometry/loop closure ->
supervised exploration -> whole-home/return-home acceptance. Each hardware phase
needs separate approval. PC-disconnection independence is an explicit future
stationary acceptance test; NOT tested, no PC/network disconnected this turn.

GO: further offline adapter/local-supervisor preparation. NO-GO: camera activation,
onboard deployment, accurate metric map claim or autonomous mapping. No PR merged.
