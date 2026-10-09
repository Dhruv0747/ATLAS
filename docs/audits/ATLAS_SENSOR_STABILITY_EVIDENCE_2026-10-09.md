# Sensor-based stationary position validation

## Result

Recorded sensors strongly support physical stationarity in the six examined
windows. They do NOT establish correct global position in every window.
The late return is a concrete counterexample: a steady pose with respectable
endpoint/map agreement can still be the previously identified wrong location.
Do not replace the mission pose-count gate with a stationary/fit-percentage
gate. No runtime safety check, calibration, parameter or service was changed.

## Source and reproducibility

Continues `b577a85609ba499871649e261453e926a55f0552`.
Read-only source: `data/demonstrations/amcl_roundtrip_20261009_final` on Jetson.
One SQLite segment, recorded map, recorded laser extrinsics, encoder scalars,
both odometry streams, both recorded IMU streams, scan and TF headers.
No live subscriptions, ROS nodes, motor publishers or services were started.
The script uses SQLite `mode=ro`, validates one immutable recorded map and
identity base_link/base_footprint transform, and preserves frame/timing details.

Command (source ROS Humble first; no ROS daemon required):

```sh
OPENBLAS_NUM_THREADS=1 nice -n 10 python3 atlas_stationary_sensor_evidence.py \
  /home/jetson/project_atlas/data/demonstrations/amcl_roundtrip_20261009_final \
  /tmp/atlas_stationary_sensor_evidence.json \
  --window 30 38 --window 110 118 --window 180 188 \
  --window 270 278 --window 360 368 --window 450 458
```

These six explicit eight-second windows are early/late sections of the three
previously identified stopped intervals. They are not an exhaustive audit of
every scan or every historical jump. All sensor samples within each window
are summarized; nine scans per window are scored, approximately 1 Hz, using
every fourth valid endpoint. The fixed anchor is the latest AMCL pose received
BEFORE the window. We never optimize that anchor on the same scans being scored.
This avoids a circular claim that matching each scan independently proves
stability. Scores still share the same map/LiDAR modality as AMCL.

## New measurements

| Bag offset, seconds | AMCL position span (m)* | AMCL heading span | Endpoints within 15 cm of map walls | Rays crossing mapped obstacles before endpoint |
| --- | ---: | ---: | ---: | ---: |
| 30–38, initial room | 0.00342 | 0.141° | 95.8–98.0% | 8.0–15.7% |
| 110–118, initial room late | <0.000001 | <0.000001° | 95.9–100% | 8.0–14.3% |
| 180–188, Hall early | 0.04623 | 1.221° | 32.5–39.0% | 51.2–56.1% |
| 270–278, Hall late | 0.0000344 | 0.0291° | 78.0–85.4% | 17.1–27.5% |
| 360–368, return early | 1.14770 | 76.478° | 57.4–64.7% | 53.7–57.7% |
| 450–458, return late | 0.00000191 | 0.00000404° | 77.4–82.7% | 15.1–22.2% |

*Position span is the XY bounding-box diagonal, not maximum individual jump
or measured physical travel. Heading is unwrapped yaw span.

- All four encoder counts remained unchanged in every selected window.
  That supports no detected wheel rotation; it does not prove encoder health.
- Wheel odometry stayed constant. EKF position span was at most 4.78 micrometres.
  These are correlated sources, not two independent physical measurements.
- `/imu/data` integrated signed gyro-Z change ranged -0.228° to +0.421°
  per window. The return-early window integrated +0.0642°, contradicting
  AMCL's 76.478° variation. Absolute gyro integration was 1.69–2.16°,
  which includes noise; signed cancellation alone is not a stillness proof.
- The separate `/im10a/imu/bias_corrected_candidate` gyro-Z was exactly zero
  in these windows. This is a processed stream; zero is not evidence of an
  independently measured perfect heading or of a faulty sensor.
- Maximum sampled median absolute range difference from each window's first
  scan was 0.004 m. Return-early maximum was 0.00250 m. Same-beam comparison
  requires identical scan geometry and common finite returns in 0.3–8 m.
  It is scene repeatability, NOT a six-axis or planar motion estimate.

## Data-quality and synchronization checks

338 scans and 480 samples each of `/odom` and `/imu/data` occurred in the six
windows. Corrected IMU had 481 samples. No duplicate or backward header stamps
in those streams/windows. Scan receipt gaps were about 0.27 s maximum;
odom about 0.11 s and IMU about 0.12 s. Scan receipt-minus-header age ranged
0.1198–0.2773 s; odometry 0.0144–0.1038 s, `/imu/data` 0.0008–0.0180 s.
Thus a rule assuming all scan headers are acquisition-at-receipt would be wrong.

Both odom→base_link and map→odom had timestamp brackets for all 54 sampled
scans, using transforms received by scan receipt plus 0.5 seconds and headers
within 0.5 seconds of scan time. This is an offline availability check, NOT
proof that AMCL consumed the transforms on time, nor proof that map→odom was
correct. No TF timeout was changed. No interpolated TF was used to falsify
sensor stationarity or score an alternative pose.

## What can and cannot be validated

The sensor cross-check can flag the early-return AMCL movement as inconsistent
with the stationary physical scene. The initial-room windows show both stable
local estimates and strong map agreement. However, the late return's wrong
anchor `(3.8404,-0.4824,2.7268 rad)` is extremely steady and its map/ray scores
overlap the late Hall range. A generic 75% endpoint threshold, pose stability,
or healthy TF alone would admit that counterexample. No such threshold was
installed. Room identity is based on prior operator evidence, not surveyed truth.

Next necessary action: compare competing global pose hypotheses and their
free-space/ray consistency with the recorded moving prior, so a locally steady
but globally wrong hypothesis can be rejected. That can continue on saved data.
There is no validated independent global-position acceptance rule yet; no new
drive is needed now. Historical localization jumping remains unresolved.

## Tests and delivery

Six helper regressions passed: missing data stays unknown; duplicate/backward
stamps exposed; boundary gaps retained; no future anchor chosen; yaw wrapping;
separate heading/translation spans. The Windows default Python lacked NumPy;
tests passed with bundled Python/NumPy. The full analyzer completed on Jetson
against the saved bag. Results are retained outside Git; only code, tests and
this aggregate report are committed. This data-quality workflow deliberately
kept physical stillness, estimator stability and global correctness separate.
