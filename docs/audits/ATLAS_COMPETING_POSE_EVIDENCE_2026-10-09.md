# Competing map locations versus scans and travel history

Continuation from `334cf1e2f799945004fa01c0e27932744c1038ee`.
Offline only: no ROS context, movement, service restart, production parameter
change, calibration change or initial-pose publication.

## New conclusion

This recording contains enough evidence to distinguish a refined Dhruv Room
hypothesis from the false return region. The combination of independently
integrated corrected gyro history, scan/map endpoint residuals and free-ray
consistency favours the room region. It is not a deployed correction or proof
of reliable recovery across other recordings.

The earlier locked room coordinate was not an adequate comparison point:
manual return need not end at the exact initial parking coordinate. Equal
bounded refinement materially changes the result. Do not conclude that the
map itself is uninformative merely because a fixed approximate room point
scored worse than AMCL's already-optimized false point.

## Method and provenance

Source: `data/demonstrations/amcl_roundtrip_20261009_final` on Jetson. Read
SQLite in `mode=ro`; use recorded map and laser transform, not current map.
Script: `project_atlas/scripts/atlas_competing_pose_evidence.py`.
It explicitly rejects other bag names because offsets and hypotheses belong
to this recording. Raw outputs remain outside Git under `/tmp/atlas_competing_pose*`.

Four locked seeds, from previous reports, in map metres/radians:

- Initial room: `(0.2070126, -1.5453962, 1.40799436)`.
- Prior approximate scan-room candidate: `(0.184, -2.034, 1.447)`.
- Late Hall: `(6.4680112, -2.7635224, -1.66138551)`.
- Late false return: `(3.84039193, -0.48244301, 2.72681390)`.

First compare each seed against the identical scans at offsets 110–118,
270–278, 360–368 and 450–458 seconds (nine per window). Then fit each seed's
region using ONLY one early-return scan at +352.107 s: identical ±0.6 m XY,
±30° yaw bounds, 27 starting points, robust nearest-wall least squares,
soft-L1 scale 0.1 m, maximum 60 function evaluations per start. The optimizer
does not use gyro or ray penalties. These are diagnostic search settings,
not changes to navigation tuning or calibrated acceptance thresholds.

Training uses even ORIGINAL beam indices before invalid-range filtering;
test results below use odd indices on nine later scans at +450–458 s.
The scanner geometry is explicitly checked unchanged. Restrict finite ranges
to 0.3–8 m. This tests different beams and later scans, but NOT a different
journey. Seeds include retrospective findings from the same bag, so there is
selection leakage; do not call this independent operational validation.
Preliminary filtered-array-parity results are superseded by this original-
beam-parity version, which cannot shift beam assignment when ranges go invalid.

## Fair same-scan comparison

On the late-return even-index scans, before refinement, median endpoint fits
were 65.8% initial room, 67.0% approximate room, 49.5% Hall and 80.2% false
return. This is why comparing only the old coordinates could be misleading.

After equal bounded refinement, held-out odd-index late-return results:

| Region | Endpoint fit within 15 cm (median; range) | Median premature-obstacle ray fraction | Median endpoint-to-wall distance | Corrected gyro heading residual |
| --- | ---: | ---: | ---: | ---: |
| Initial-room region | 100%; 99–100% | 0% | 0.021 m | 0.214° |
| Prior approximate room region | 77.6%; 74.3–78.4% | 14.3% | 0.028 m | 9.548° |
| Hall region | 22.3%; 20.6–25.7% | 100% | 0.268 m | 176.949° |
| False-return region | 82.2%; 78.9–85.6% | 19.4% | 0.054 m | 98.229° |

The best room pose is `(0.37479, -1.16681, 1.38742 rad)`. It is about
0.41 m from the initial parking anchor, not an assumed exact loop closure.
The refined false pose is `(4.05178, -0.56237, 3.09811 rad)`.
Neither fit touches its search boundary. The older approximate room region
does touch its Y boundary; its weaker score must not reject the whole room.
Hall's endpoint-only optimizer selected a ray-inconsistent pose, illustrating
why an optimizer's success flag alone is not evidence of a valid location.

100% here means sampled endpoints within a 15 cm wall-distance tolerance,
NOT 100% localization certainty or centimetre-accurate surveyed position.
Nearby beams/scans are correlated; no binomial confidence claim is made.

## Travel history provides a discriminating cross-check

Use header-time interpolation for odometry, refusing boundary extrapolation
and gaps over 0.5 s. Integrate gyro with interpolated exact boundaries;
reject duplicate, backward or missing timestamps. Outbound endpoints are
offsets 118–278 s; return is 278–450 s, both spanning stationary endpoints.

Return gyro integrals:

- `/im10a/imu/bias_corrected_candidate`: **-185.530°**.
- `/imu/data`: **+188.464°**.

The signs disagree. These streams must not be counted as interchangeable
frame/sign-validated witnesses; this comparison does not recalibrate either.
The corrected stream is evaluated as the existing candidate body-Z input,
not promoted to production authority by this report. Drift/bias and the Hall
anchor uncertainty remain limitations. Its outbound heading residual at the
Hall anchor is 11.588°, so near-perfect return agreement is not a blanket IMU
accuracy claim.

With locked (unrefined) return poses, corrected gyro residual is 1.392° for
the initial-room candidate, 3.627° for the approximate room candidate, versus
76.955° for the false location. Conversely wheel-odometry heading is only
0.538° from the false location, but 72.790–75.024° from the room candidates.
This is a verified conflict in the recorded motion prior, not proof of an
individual faulty encoder or actual measured steering angle.

Wheel-only predicted return position is 3.50–3.88 m from the locked room
points; EKF predicted position is 8.07–8.39 m away. Do not use those translations
as ground truth to veto the scan/gyro-supported room candidate. No full
scan-to-scan trajectory or collision-free route has been reconstructed here.

## Particle support revises the earlier missing-support interpretation

The published cloud immediately before training (+351.997 s) has 2,000
particles. **15 particles (0.75% of normalized published weight)** lie within
0.5 m AND 20° of the newly refined room candidate. Nearest XY distance is
0.198 m and that particle's heading error is 11.981°.

Therefore the better room hypothesis was weakly represented in this cloud;
it was not entirely absent. Earlier absence measurements concerned a different
approximate room point and an earlier seed cloud. They must not be generalized
to say no plausible room hypothesis ever existed. This report does not yet
trace the precise update where support was lost or prove why it was rejected.
Published resampled weights are not an internal pre-resampling likelihood trace.

## Validation and next necessary action

Ten helper tests passed: transform inverse; wrapped residual; pose interpolation;
no extrapolation/gap bridging; exact gyro boundaries; missing/duplicate/nonfinite
gyro rejection; fixed beam holdout parity; joint XY/heading particle support.
The complete read-only comparison ran on the saved bag. Search solutions and
scores are diagnostic outputs, not runtime code or configuration changes.

Next: trace survival of that low-weight room hypothesis through subsequent
recorded clouds and compare actual AMCL likelihood with gyro-consistent
candidate selection. Then validate any proposed safeguard on other saved
drives. No new driving is necessary for that analysis. The original failure
is better constrained, but localization is NOT declared fixed.
