# ATLAS sensing and localization reliability investigation

11 October 2026, Asia/Calcutta. Branch `agent/sync-developer-20261011`,
starting at `2feefd5`. This is a bounded Priority 1 diagnostic milestone,
not completion of all seven priorities or permission for autonomous movement.

## Confirmed cause of the displayed distance difference

The FRONT summary means the nearest valid return in a 90-degree quadrant,
not the wall on the forward centreline. A captured 0.509072 m minimum is at
44.695 degrees to the right of forward. Its `base_link` coordinates are
x=0.361883 m, y=-0.358044 m. This point lies near the quadrant boundary.
Forward geometry near 1.90 m and a closer off-axis return can coexist.

The exact sample has scan timestamp 1791718090.3272607, frame `laser_frame`,
ray index 318, original range 0.545750 m, original angle 2.426008 radians,
and ray offset 0.113097 seconds. The transform to `base_link` has translation
(-0.05, 0, 0.18) metres and approximately 180-degree yaw. Thus the raw sensor
range and the base-origin radial distance legitimately differ. No multiplier
is applied. Neither value is bumper clearance.

All 64 successfully projected samples across two short captures had matched
raw/filtered timestamps, zero changed finite ranges and zero minimum-to-raw
mismatches. The nearest points are already present in `/scan_raw`, not created
by dashboard arithmetic or the chassis filter. This establishes provenance,
not whether the physical return is an object, reflection, cable or occlusion.
Do not discard it or enlarge the self-filter without physical evidence.

## Current implementation and data flow

Live ROS graph and service commands confirmed:

`rplidar_node → /scan_raw → atlas_scan_self_filter → /scan`

The filtered `/scan` feeds AMCL, both costmaps, LiDAR odometry and other
existing safety/perception consumers. The dashboard independently projects
the same scan into `base_link` at its header timestamp and calculates quadrants.
Its `/api/lidar-view` result is not an AMCL or Nav2 input. An erroneous dashboard
summary would not itself alter localization; bad sensor returns can affect
all consumers of the shared scan.

The self-filter preserves timestamps, angles and surviving ranges, replacing
returns inside x=±0.30 m, y=±0.23 m with infinity using its fixed mounting model.
Its mounting constants agree with the observed TF, but physical mount accuracy
and self-exclusion dimensions remain unmeasured in this session.

Live AMCL parameters are `scan_topic=scan` and `DifferentialMotionModel`.
Local and global obstacle layers report `observation_sources=scan`; local
marking and clearing are true. The local plugin is `obstacle_layer`, not
`voxel_layer` (querying the latter returned unset). Matching deployed/repository
Nav2 YAML sets marking/clearing for both costmaps, obstacle maximum 2.5 m and
raytracing maximum 3 m. Semantic-camera parameters exist but are not selected
as observation sources. These checks do not prove dynamic clearing or stopping
performance; no costmap obstacle injection or motor test was run.

The deployed scan filter, Nav2 YAML and EKF YAML hashes match the repository.
EKF still selects wheel x/y pose plus x/y velocity and corrected IM10A gyro Z;
the velocity-only candidate has NOT been deployed. No new evidence here resolves
the historic heading disagreement or five stationary AMCL jumps. Prior replay
limitations and recorded results remain authoritative; those tests were not repeated.

## Measurements and their limits

| Measurement | Initial 20 second capture | Payload preserving 15 second capture |
| --- | --- | --- |
| Samples projected | 38 of 39 | 26 of 26 |
| Valid points per sampled scan | 1–215 of 360 | 204–212 of 360 |
| Source timestamp age | 0.148–0.394 s | 0.158–0.390 s |
| Raw pairs matched | 38 | 26 |
| Finite ranges changed by filter | 0 | 0 |
| Minimum raw mismatch | 0 | 0 |
| Front minimum | 0.507–1.977 m | 0.506–0.515 m |

The first probe's initial TF lookup failed before its local TF buffer discovered
`laser_frame`; later exact-time transforms succeeded. This is not proof of a
production TF outage. Probes sample at up to 2 Hz, not every scan. Their density
changes must not be described as DDS message loss. Source data age includes
scan acquisition time and processing; it is not exclusively network latency.

In the second capture, all 26 front minima remain near bearing -44.685 degrees.
Other sampled minimum ranges: left 0.422–0.423 m, rear 0.557–0.568 m, right
0.414–0.417 m. Initial capture had a sparse/dense/sparse transition already in
raw returns. Its physical cause is unverified. Persistence alone does not prove
that a return is a real obstacle or a reflection.

## Software changes and tests

- `atlas_lidar_view.project`: retains the existing points and minima values;
  adds raw ray index/range/angle, base bearing/coordinates, ray time offset and
  a separately labelled dominant-cluster estimate. Nonfinite geometry is rejected.
- Cluster estimate: largest contiguous group with endpoint gaps ≤0.15 m,
  at least five rays and at least five degrees span; median radial distance.
  This diagnostic heuristic is not a fitted wall, navigation input or filter.
  Insufficient support produces no estimate. Close isolated returns remain.
- `web/v2/lidar.js` and `lidar.html`: mark each quadrant minimum in orange;
  show provenance, source timestamp/age and cluster support independently.
- `tools/diagnostics/lidar_provenance_probe.py`: finite read-only paired scan/TF
  capture, graph discovery and explicit IEEE invalid-value encoding. No publishers.
- `tools/diagnostics/replay_lidar_provenance.py`: replay saved raw geometry and
  verify points, minimum identity and distances; report sampled temporal variation.

Tests: 15 projection/freshness tests, seven V2 route tests, Node UI logic test
(marker, ray timestamp, unsupported surface and stale hiding), JavaScript syntax,
and 12 unchanged E-STOP regressions in the isolated Jetson test tree passed.
The Windows E-STOP test import lacked `cv2`; the isolated Jetson run passed.
The UI logic test is not a browser visual-layout acceptance test.

All 26 payload-preserving samples replayed successfully. On the Jetson the
maximum distance difference was zero; Windows differed by at most 1.11e-16 m
from floating-point library rounding, within the explicit 1e-12 tolerance.
Jetson replay used 0.082 s wall time, 0.054 CPU seconds and 13.6 MiB peak RSS.
This is a short offline replay measurement, NOT continuous dashboard overhead.
No before/after physical accuracy improvement is claimed: the fix explains
the measurement rather than altering it.

## Live mapping and recorder

Live obstacle visualization, localization and persistent map updates are distinct.
The live scan view does not require a camera. The existing map page separately
renders the accepted occupancy map, pose estimate and localization confidence.
The observed `/map` publisher was `map_server`, not active SLAM. No trusted map
was overwritten and no mapping mode was started. Combined map/live-scan overlay
and movement-time update acceptance remain unfinished.

Candidate map validation and transactional promotion already exist in
`atlas_map_acceptance_core.py` and `atlas_mission_control.py`, including accepted
backups and metadata binding. Do not duplicate these. Automatic structural-change
accumulation and its acceptance are not established by this audit.

Recorder/core/writer hashes still match the tested `0c1d520` deployment.
No recorder process is running; opt-in behavior remains. The topic list includes
raw/filtered scans, TF, wheel/fused odometry, corrected IMU, AMCL, individual
encoders, steering commands and control policy. Dedicated localization-diagnostic
and costmap topics are not currently in that list. Decide a bounded budget before
adding costmaps. Previous queue, preroll, bag-integrity and resource tests were not
repeated. Free storage was 369 GiB available on the live filesystem (`df -h`).

Offline diagnostic replay, without ROS or motors:

```bash
python3 project_atlas/tools/diagnostics/replay_lidar_provenance.py PATH_TO_CAPTURE.json
```

This is a scan-projection replay, not a reproduction of AMCL particle evolution.

## BMS and network

BMS PID 268412 and recovery PID 268405 retain zero service restarts. Repeated
errors explicitly say `response deadline exceeded during connect`, about every
130 seconds including bounded backoff. No successful telemetry appeared in this
inspection. Failure is before GATT/protocol decoding; the precise radio/peripheral
cause is unknown. BlueZ adapter is powered and not discovering; pairable=false
is an observation, not proof that pairing is required or the fault cause.
Do not change protection parameters, manufacture SOC or start a competing client.

The completed power-save trial did not restore BMS, and power saving remains ON.
Wi-Fi → cellular → rescue hotspot priority is preserved. No network experiment
was repeated. Next BLE evidence should be a passive HCI trace covering one
existing retry (subject to OS privilege), to distinguish connection request,
controller timeout and peripheral rejection. If the device is not advertising,
request a supervised peripheral power/phone comparison, keeping the Jetson retry
owner isolated for that comparison; do not infer a decoding fault.

## Deployment and rollback

No production file, service, motor calibration, EKF, map, network setting or
safety authority was changed in this investigation. E-STOP remained latched.
Motor owner PID 1878 and mux PID 1872 stayed at zero restarts. Only finite
read-only probes and isolated tests ran. New provenance UI/core are committed
candidates, NOT installed on the production dashboard. The previous deployed
stage 9b/9c and stage 8 rollback paths remain in
[the deployment record](../ATLAS_MASTER_DEPLOYMENT_2026-10-11.md).

For a subsequent authorized UI deployment: back up the projection module and
two static files, verify hashes, rehearse byte-identical restoration, install
only those files and restart only the dashboard while parked. Verify the new
API fields and visible markers; restore those three files and restart only
the dashboard if regression occurs. Do not restart navigation or motor owners.

Private captures remain in `/home/jetson/atlas_recorder_smoke_KWJkzy/` as
`lidar_provenance_20261011.json` and `lidar_provenance_payloads_20261011.json`.
Raw indoor geometry is not published in Git.

## Remaining work and one supervised validation session

The next necessary physical observation is identifying the persistent front-right
return, not another room-driving loop. After the diagnostic UI is deployed:

1. Keep parked, stop latched. Place a flat measured target at centre-front,
   front-right and one rear/side position, measuring from the LiDAR centre;
   record target dimensions/bearing and compare the exact sensor ray separately
   from base-origin range. Include 0.5, 1 and 2 m where space permits. Use the
   installed sensor's documented tolerance, not an invented pass threshold.
2. Remove the target and inspect the 44.7-degree front-right beam path for an
   object, cable, chassis part or reflective surface. Capture before/after scans.
   Do not reach into moving hardware or adjust calibration.
3. Verify scan display remains live when the camera is unavailable, and stale
   scans never imply free space. Dynamic costmap marking/clearing and physical
   scan-density consistency remain to be qualified.
4. Only under separate movement permission and normal safety gates, append one
   short manual segment to evaluate pose/TF lag and live map overlay. Do not
   start a route while localization or fresh battery gates fail.

Unfinished engineering: physical LiDAR alignment/tolerance and sparse-return
cause; combined scan/map view and candidate change accumulation; historical
AMCL/gyro-wheel instability; dynamic obstacle acceptance; recorder diagnostic
topic extension if justified; successful BLE reconnection and decoded SOC.
Stationary results do not resolve localization jumping or authorize autonomy.
