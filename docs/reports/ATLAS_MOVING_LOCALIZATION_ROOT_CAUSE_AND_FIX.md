# ATLAS moving localization: upstream yaw evidence and fix gate

14 October 2026 · branch `agent/sync-developer-20261011` · continuation of
`7ea5174`. This is an **offline diagnostic change, not a deployed motion fix**.
No motors, steering, AMCL, Nav2, EKF, map or live service were changed.

## Answer and confidence

The earliest newly isolated yaw discrepancy in the recorded Hall→Dhruv turn
sequence is the 160–162 s window: the wheel model accumulated +0.02° while
the bias-corrected IM10A accumulated +6.39°, with 20 fresh encoder updates.
The first opposite-sign 2 s window is 174–176 s (+4.26° wheel versus −15.11°
gyro). A second is 186–188 s (+4.26° versus −17.84°). The previously audited
185.23–189.58 s interval has independent scan-ICP support for a negative turn:
+7.42° wheel, −18.96° gyro, −16.09° ICP. Thus the **wheel command-based yaw
model disagrees with measured motion before AMCL's parked hypothesis switches**
(high confidence). This is an upstream estimator failure, not a dashboard
rendering delay.

The **physical reason** the wheel model is wrong in those particular turns is
**not verified**. Its commanded PWM angles are not measured road-wheel angles.
Servo/linkage lag, road-wheel hysteresis, traction, centre-distance loss and
mixed steering/traction remain candidates. No global encoder polarity or
heading sign error is supported: in the same recording 162–164 s produced
−52.83° wheel versus −48.72° gyro, 176–178 s produced +30.62° versus
+30.26°, and 198–200 s produced −27.23° versus −24.57°. A global sign
inversion would break those turns. M3 is not proven faulty: all four channels
were accepted in 16/20 updates during the 186–188 s wrong-sign window.

The exact AMCL failure chain remains a **strong hypothesis**, not a proven
single-root-cause repair: wrong/short wheel-integrated X/Y pose is fused in
the EKF, weakens particle tracking during movement, and AMCL later switches
between map hypotheses while parked. The saved bag confirms five parked
AMCL steps >0.5 m (maximum 2.206 m) with zero coincident wheel or gyro
motion and pre-jump XY uncertainty >1 m. It does not prove what fraction of
those switches was caused by wheel yaw versus ambiguous map/scan geometry.

## Exact raw-to-odom and EKF trace

The production source maps M1 rear-left and M3 front-left to positive-forward
counts, M2 rear-right and M4 front-right to negative-forward counts.
`encoder_calibration.yaml` uses signed metres = `(raw count − origin) ×
encoder_sign × 0.392699 m / CPR`, with provisional CPRs 2238.4, 2215.0,
2199.1 and 2230.5. The driver computes
`k = (tan(front_command − 90°) − tan(rear_command − 90°)) / 0.367 m`,
normalizes each wheel for its 0.26 m track position, selects a coherent
three-or-four-wheel median body-distance increment, and publishes wheel yaw
increment `distance × k`. Both steering values are **commanded targets**;
there is no physical steering-angle feedback. Wheel X/Y integrate this yaw.
The EKF fuses `/yahboom/odom` X/Y pose and X/Y velocity, plus corrected IM10A
gyro Z; wheel yaw/yaw-rate are **not** direct EKF inputs. Wheel pose can still
pull EKF translation along a wrong commanded-yaw trajectory.

Example, 186–188 s: raw changes M1 +2604, M2 −2974, M3 +1575, M4 −2645;
signed wheel-distance changes +0.4568, +0.5273, +0.2813, +0.4657 m;
accepted median body distance +0.4726 m; wheel yaw +4.259°, gyro −17.837°.
All 20 encoder packets were fresh and at least three channels accepted; four
were accepted in 16. The front command ranged 90–109° and rear 71–90°,
so this is a steering-transition interval, **not** a measured wheel-angle
trajectory. The diagnostic replay does not infer a new steering calibration.
At 204–206 s the accepted body distance was ~−0.0005 m and wheel yaw ~0°
while gyro integrated −13.25°; 10/20 updates had three-or-more channels.
`distance × commanded curvature` cannot represent such rotation when centre
distance is rejected or nearly zero. IM10A covers yaw in the EKF, but the
wheel-integrated X/Y pose remains a potentially inconsistent fusion input.

## IM10A, LiDAR, TF and time

The observer converts raw WIT gyro units using ±2000°/s and publishes Z as
`raw_z − bias_z` in `base_link`; its X/Y sign rotation does not invert Z.
The Oct 9 bag records 2,920 corrected IMU samples and 2,919 exact encoder
snapshots. It does **not** contain raw `/im10a/imu/unvalidated`, so an
in-bag raw-versus-bias correction comparison is unavailable. The Oct 10 fast
drive had no motion bag. Its −97.5° inferred physical turn versus −44.9° EKF
and +15.4° wheel endpoint is concerning, but IMU saturation, sample loss,
bias, slip and commanded-steering error cannot be distinguished from that
endpoint alone. No gyro scale or bias change is justified.

The previous synchronized audit measured wheel-header receipt p95 ~8 ms,
corrected-IMU p95 ~6 ms, EKF p95 ~94 ms; the main bag's encoder driver
packet age p95 was 41.1 ms, with no diagnostic sequence gaps. The Oct 9
filtered scans are source-monotonic, and scan/raw receipt lag near the largest
jump had p95 11.5 ms. Recorded `/odom` and `odom→base_link` TF agree after
accounting for EKF's configured +0.2 s future TF offset, but they are the
same estimator, not independent physical truth. A 0.10–0.18 s best-fit timing
shift remains a hypothesis. No TF offset was changed. The first disagreement
measured here is upstream of the parked AMCL steps; no single timestamp fault
has been demonstrated.

## Cross-recording coverage and map integrity

`moving_yaw_evidence.py` reads all six locally available bag directories.
Only `hall_to_dhruv_20261009-20261009-122252` contains the exact
`/atlas/encoder_update` snapshots needed to replay accepted wheel increments
with command angles. Its 20 nontrivial 2 s gyro-covered turn windows contain
two opposite-sign wheel/gyro estimates. The other Oct 9 bags contain corrected
IMU but no exact per-update encoder snapshot; the August bag lacks both.
Prior independent audits reported cross-bag wheel/gyro integrated-yaw errors
ranging from near-zero to tens of degrees in either direction. These data do
not support a transferable sign or scale correction.

The accepted map archive in the 11 Oct backup was rehashed read-only:
YAML `d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4`,
PGM `4beb26d5a9990db537df53ba71404d549f88f717d72ca59fc03e0b72a3684a1e`.
The differing repository `atlas_latest` was not substituted. No new AMCL
replay was attempted because there is no physically justified candidate yaw
or EKF correction to compare and prior replay did not reproduce the five
live jumps. **Before/after AMCL jump result: unavailable; live baseline stays
5 jumps, maximum 2.206 m. Localization is unresolved.**

## Adaptive encoder feasibility

The existing driver already monitors per-wheel eligibility/faults and uses
dynamic three-of-four coherent increments. A fresh packet is not proof of
physically accurate distance: the Oct 9 M1/M4 and M2 channels under-reported
LiDAR distance in selected motion segments despite regular receipt. A
wrong-direction classification needs *independent* motion evidence; opposing
count signs between left/right are normal because of per-motor inversion.
No static M3 exclusion is warranted by this audit.

Two encoders can provide a **shadow translation estimate** if both directions,
freshness and normalized distances agree; they cannot by themselves make a
safe steering-aware body-yaw estimate on this rover without validated
road-wheel angles or independent motion constraints. In the 186–188 s
window M1/M4 agreed within 0.009 m while M2 differed by ~0.07 m and M3 by
~0.18 m. Selecting a convenient pair would conceal that disagreement.
The live fewer-than-three fail-closed policy remains unchanged. A future
adaptive authority model must validate per-wheel residuals against LiDAR
odometry/gyro over multiple *independent* runs, require sustained recovery,
publish covariance/observability, and stop when yaw or translation cannot be
observed; it cannot be commissioned from these bags alone.

## Changes, tests, deployment, rollback and next gate

Added only the offline, standard-library-only diagnostic
`project_atlas/tools/diagnostics/moving_yaw_evidence.py` and three tests in
`test_moving_yaw_evidence.py`. It reads SQLite bag files read-only, decodes
CDR source timestamps, refuses implausible IMU payloads, clips integration at
the window bounds, and reports raw/signed per-wheel changes, accepted channel
counts and gyro coverage. It does not publish ROS messages or command hardware.
All **3/3 focused tests passed**, plus 23/23 existing encoder-selection and
6/6 IM10A fusion tests; `git diff --check` passed. The six-bag
inventory was run, with one diagnostically complete bag and five explicitly
reported missing exact snapshots. No production source, config or services
were modified. This is a diagnostic improvement, **not a physically validated
localization fix**. The source commit is identified by the GitHub link in the
delivery message; it cannot be self-referential inside this committed report.

Read-only Jetson check on 14 Oct reached `jetsan-desktop`, uptime ~6 min,
with `rover-base-telemetry.service`, `atlas-ekf.service` and
`atlas-im10a.service` active; its 1 min load average was 34.12. The live EKF
config hash `69dd4479…` matched the preserved source baseline.
This check does **not** certify E-STOP, navigation authorization, sensor
freshness or operating health. Nothing was installed or restarted on Jetson.
Rollback is simply to stop using the offline script or revert this diagnostic
commit; no live rollback package is needed. The accepted map, startup gates
0.93/0.06, and existing motor/steering settings remain untouched.

The minimum **future operator-approved** physical gate is one tightly
instrumented low-speed left/right and forward/reverse turn sequence on a
measured clear floor, with opt-in recorder capturing raw and corrected IM10A,
all four counts and exact encoder updates, commanded steering **plus a fixed
view of physical front/rear road-wheel angle**, LiDAR scans, EKF/TF and AMCL
particles. Measure loaded wheel-angle arrival/hysteresis and actual heading
against LiDAR or an external reference. Only then fit and cross-validate an
offline steering/odometry candidate against *all* recorded turns, requiring
correct signed yaw, distance, scan fit and post-stop AMCL stability without
regressing remote steering. This test is **not authorized or run** here.
