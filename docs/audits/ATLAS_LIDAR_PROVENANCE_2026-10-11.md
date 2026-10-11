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

## Owner-approved stage 10 deployment — 17:11–17:15 IST

The preceding non-deployment status describes the original investigation;
it is superseded for the three diagnostic files by this approved deployment.
Source `1a9f077ad3781b4479b7142c3aded06880de8b48` installed with matching hashes,
rehearsal and byte-identical rollback. Only dashboard restarted. See the
[deployment record](../ATLAS_MASTER_DEPLOYMENT_2026-10-11.md) for measurements,
paths and rollback. Browser visibly shows actual scan points, four highlighted
minima and raw beam provenance. 60/60 parked samples LIVE; no HTTP failures.

### New owner observation: hand occlusion

Owner reports side-hand placement changed FRONT about 0.51 to 1.19 m while
forward wall stayed near 2 m, then removal restored 0.51. No synchronized
annotation or raw capture of that event is available. Earlier variable-density
capture cannot be relabelled as this event. Therefore a before/after beam index,
timestamp, valid-point distribution and causal physical identity cannot honestly
be assigned. Occlusion removing the former minimum and exposing the next valid
minimum is a hypothesis, not proof of reflection or defective LiDAR.

New browser sample: front 0.528 m, ray 318, raw 0.565 m at laser angle 139.0
degrees, base bearing -44.6 degrees. Main forward wall remains about 1.98 m.
This is a new stationary sample, not a reproduction of the owner's hand test.
The raw-to-filtered equality already established remains the evidence against
dashboard fabrication; physical range accuracy is not independently proven.

The previously verified `/scan` subscribers receive full scans, not dashboard
quadrant minima. A finite close ray can participate in obstacle marking and
AMCL likelihood calculations. Whether this particular return causes adverse
marking/clearing or historic localization jumps has NOT been measured. No
control/filter scaling or map change is justified by the display improvement.

### Combined view and candidate-map workflow: explicit unfinished scope

Saved map is still on `/v2/mapping`; live scan is on `/v2/lidar`. They are not
yet overlaid. Quadrant minima have raw provenance; arbitrary clicked points
still show transformed distance/bearing only. Do not claim those requirements
complete. Combined overlay needs scan-time map TF, map-image identity matching,
visible localization disagreement and stale-data tests before deployment.

Existing `tools/local_map_audit/candidate.py` builds separate candidate files
from recorded evidence, with parked-hit protection and later no-new-reachability
checks. `validate_location.py` compares active/candidate residuals, ambiguity
and through-wall rays. These are historical offline tools with dataset-specific
paths/regions, not a production automatic map updater. Reuse their validation
ideas/tools against an explicitly frozen map and evidence set, review the diff,
retain the accepted map and require separate acceptance before promotion. No
candidate generation/promotion was run in this deployment. Live scan viewing
already operates while `atlas-slam-fast` is inactive; map writing is unnecessary.

### One parked target session (not another driving loop)

Keep E-STOP latched. Put a flat board squarely facing the LiDAR, with its face
0.5 m from the LiDAR optical centre at front-centre; then front-right (~45
degrees) and one side. Repeat at 1 m and 2 m only where available. The selected
target ray's raw range should approximately match that measured distance within
sensor/placement tolerance. Base-link distance can differ because of sensor
translation; the quadrant minimum may still be another nearer object. Do not
use the cluster median as ground truth. Keep hands/cables outside the scanning
plane and do not touch a spinning unit. A labelled before/target/removed capture
is the missing evidence needed to identify which rays actually change.

BMS passive monitor attempt: bounded `btmon -i hci0` denied with `Operation not
permitted`, so no HCI evidence captured. Existing single retry owner still
reports connection deadline exceeded; valid battery percentage is not restored.

## Navigation decision-path audit — 11 October, parked, no control changes

### Separate consumers and actual runtime settings

The dashboard's `atlas_lidar_view` is imported only by the web server; no
navigation subscriber consumes its quadrant summary. AMCL receives `/scan`
and uses up to 60 beams with likelihood-field matching. Local/global obstacle
layers also consume `/scan`, with marking and clearing enabled; marking range
2.5 m, raytrace range 3 m. Both footprints are the configured rectangle
0.50 m long by 0.36 m wide, padding zero, resolution 0.05 m. Inflation radius
0.28 m, scaling 15. Physical loaded/swept steering envelope is not measured
by this audit; commanded steering is not angle feedback.

Runtime parameter reads confirmed RPP collision detection, 0.8 s projection
horizon, 0.15 m/s desired speed, reversing enabled. Smac uses REEDS_SHEPP,
minimum turning radius 0.35 m, allow_unknown true. These are current settings,
not the older DUBIN/forward-only generation. Local track_unknown_space false;
global true. Local scan expected_update_rate 0.0 and inf_is_valid false.
Unknown/default-free local cells must not be described as observed clear.
The zero update-rate setting does not provide a scan-age expiry gate.

The `atlas-localization` launch starts Nav2 components even when the separate
atlas-nav2 unit is inactive. Service inactivity alone was not evidence that
the controller was absent. This audit observed no `/cmd_vel_nav` messages,
E-STOP latched, final output zero, and no new recovery journal entries.
No node activation, goal, motor publication or service restart was performed.

### Fresh parked evidence

Bounded read-only subscriber/parameter probe, approximately 18 seconds:
128 scans (7.09 Hz), 30 local raw costmaps (1.67 Hz), 11 global raw costmaps
(0.72 Hz), 18 AMCL messages (1.01 Hz). Sampled source-age ranges: scan
0.130–0.448 s; local grid 0.001–0.695 s; global grid 0.119–1.959 s; AMCL
0.254–1.152 s. These are observed delivery/publication rates, not update-loop
rates or DDS loss counts. Initial TF warmup produced missing samples.

At the historical beam endpoint transformed at each grid timestamp, 27/27
valid local queries and 27/27 global queries returned lethal cost 254. This
establishes that the surrounding cell is occupied, not that this beam alone
caused the cost; existing/static surfaces may contribute. It is not a matched
scan-to-grid attribution. Whether it is physically false remains unknown.

Parked independent localization monitor: VERIFIED, fit 1.0, disagreement
0.053 m / 5.4 degrees, check age 12 s. AMCL covariance was small, but covariance
alone is not accuracy. The old start-verdict age was about 35,143 s, so it is
not a fresh navigation authorization. Motion confidence/freshness was NOT
validated: no movement was authorized or performed.

### Offline native Nav2 footprint tests (not a controller action replay)

Compiled and used the installed Humble 1.1.20 `FootprintCollisionChecker`,
without calling rclcpp init, creating a ROS node or publishing commands.
Constant-twist trajectories use the configured rectangle and 0.35 m turn
radius, sampled every 20 ms over 4 s. This tests grid/footprint intersections,
not the actual RPP controller's discrete sampling, path choice, speed regulation,
steering dynamics, observation clearing or braking distance.

| Frozen test geometry | Straight | Left arc | Right arc | Straight reverse |
| --- | --- | --- | --- | --- |
| 2 m wall + front-right point, other cells ASSUMED free | No lethal hit in 0.60 m | No lethal hit in 4 s | Lethal at 2.04 s | No lethal hit in 0.48 m |
| Captured live local grid | No lethal hit in 0.60 m | Lethal at 1.58 s | Lethal at 1.26 s | No lethal hit in 0.48 m |
| 26 saved scans rasterized into known-free fixture | 0/26 lethal hits | 26/26 at 1.80 s | 26/26 at 1.40 s | 0/26 lethal hits |

The synthetic fixtures use explicit configured inflation arithmetic; they do
NOT replay the obstacle-layer marking/clearing implementation. Saved scan
projection uses each retained TF and preserves all valid points. Unobserved
fixture cells are deliberately free only to isolate geometry: never interpret
these results as authorization to enter unknown space. The frozen live grid
uses the final nearby parked TF sample; it is not a moving synchronized replay.

In the corner-only fixture, straight maximum footprint cost was 186, left 170,
right 254. Thus the corner does not geometrically block the whole forward
direction. Other observed surroundings make both sustained turns intersect
obstacles. A separate rear obstacle produced a reverse collision at 0.84 s;
all-unknown grid returned 255 immediately. No reverse permission follows from
a blocked front. Inflation cost 253 is not a lethal hit under the Humble RPP
threshold; it is also not a clearance guarantee. The 0.8 s live horizon checks
only about 0.12 m at desired speed, and requires repeated fresh checks plus
adequate stopping response; the 4-second fixture is not its current horizon.

RPP follows the supplied path and collision-checks it; it does not itself
select a left detour simply because the right is blocked. Smac plans the route,
and failure can invoke the BT's bounded clear/back-up/wait sequence (six outer
retries, 0.18 m backup at 0.12 m/s). We did not reproduce a replan/recovery loop
caused by this point, so unnecessary looping remains unproven.

### Confirmed defects versus unresolved safety gaps

1. Separate `atlas_tight_space_recovery` uses sectors, not the Nav2 full-footprint
   checker. Its front half-width is 35 degrees (not dashboard 45); the disputed
   beam is a right-side input there. Empty sectors returned infinity. Actual
   extracted production methods selected forward with all rays absent, reverse
   with blocked front/unknown rear, and allowed continuing reverse with missing
   rear data. Values above range_max also granted clearance. Four tests failed
   before the fix; after changing unavailable clearance to zero and enforcing
   range_max, all six pass. The original LaserScan is unchanged. This narrow
   fix does NOT establish dense swept-footprint coverage or odometry freshness.
2. Runtime RPP `inflation_cost_scaling_factor=3.0` disagrees with local inflation
   `cost_scaling_factor=15.0`. The Humble documented contract requires equality.
   This overestimates inferred obstacle distance and weakens proximity slowing;
   it is not evidence of false stopping. A separate candidate correction follows.
3. Local unknown-space handling, source-age gating, reporter no-return semantics
   and recovery full swept-body checks remain gaps. Do not blindly enable
   track_unknown_space as a fix: Humble RPP has version-specific unknown handling.
   No live calibration, inflation radius, scan suppression or control setting
   was changed. Stop is currently the only authorized action.

Humble sources: [RPP parameter contract](https://api.nav2.org/nav2-humble/html/md_nav2_regulated_pure_pursuit_controller_README.html)
and [RPP collision implementation](https://api.nav2.org/nav2-humble/html/regulated__pure__pursuit__controller_8cpp_source.html).

### Tests, approval and next necessary work

Recovery regressions 6/6; mux E-STOP hold 6/6; scan-frame helpers 3/3;
native checker compiled; 26 retained scan geometries evaluated. Source compiles.
Private evidence: `nav_geometry_20261011.json`, `collision_sweeps_20261011.json`
in the existing Jetson scratch directory; do not publish indoor geometry.

Prepare separate patch/backup/rollback stages, do not install them. Recovery
fix would require only the recovery service restart under separately approved
parked conditions. The controller conversion correction requires its own
isolated RPP regression and approved Nav2 restart/configuration procedure.
Next engineering gate is actual isolated controller + obstacle-layer replay,
including missing rear data, stale scans, clearing and candidate paths. No
physical drive is needed to close those software questions. Final loaded
stopping/turn validation needs separate permission afterward.
