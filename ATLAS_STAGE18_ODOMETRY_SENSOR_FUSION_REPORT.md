# Stage 18 — wheel model and independent motion evidence

14 October 2026 · `agent/sync-developer-20261011` · baseline `46ff15f`.
**TESTED OFFLINE; NOT DEPLOYED; NOT PHYSICALLY VALIDATED.**
Stage 17B is on **HOLD**, with no deployment or physical execution authorized.
No actuator, service, steering calibration, map, EKF or safety policy changed.
Owner observations of working steering are accepted. This report does not diagnose
a defective servo, bracket, motor or individual encoder.

## New findings and decision

- **CONFIRMED:** the production model inserts commanded PWM deflections directly
  into a road-wheel-angle equation. No physical axle-angle feedback exists.
- **CONFIRMED mathematical limitation:** zero midpoint lateral motion and current
  path normalization are valid for symmetric counter-steering, not general 4WS.
- **TESTED OFFLINE:** adding the general lateral term under the *same command-angle
  assumption* does not repair the wrong-sign yaw. Commands are nearly symmetric;
  maximum lateral/longitudinal ratio is only 0.02125 in the two detailed drives.
- **New coverage correction:** the separately located
  `atlas_amcl_roundtrip_20261009_final` directory contains **4,591 exact updates**.
  The earlier inventory's statement that only the Hall return had exact snapshots
  was incomplete. The Hall return has 2,919. Neither implies perfect encoders.
- **TESTED OFFLINE:** gyro-heading/wheel-translation shadow reduces median relative
  yaw error in both detailed recordings, but translation is not consistently
  improved. It is **not an EKF replay or proven AMCL fix**.
- **UNPROVEN:** servo lag, wheel slip, CPR/radius scale, steering conversion and
  residual time alignment are not uniquely separated. Do not deploy a fitted
  steering multiplier, global sign flip, distance scale or relaxed encoder policy.

## 1. Verified equations and frame assumptions

For a no-slip single-track 4WS model, let `vx` be longitudinal midpoint velocity,
`vy` lateral midpoint velocity, `w` yaw rate, `L` axle spacing, and `δf/δr`
physical virtual-axle road-wheel angles. At axle centres:

`vy + w L/2 = vx tan(δf)`

`vy - w L/2 = vx tan(δr)`

Therefore `k = w/vx = (tan(δf)-tan(δr))/L` and
`vy/vx = b = (tan(δf)+tan(δr))/2`.
For wheel position `(x,y)`, signed longitudinal-distance/path normalization is
`scale = hypot(1-k y, b+k x)`. Track affects individual paths, not the axle-centre
curvature equation. If using total body speed instead of longitudinal `vx`, the
sideslip cosine must also be accounted for. Reverse changes signed distance and
yaw together; it does not require globally inverting steering geometry.

The existing model is the `b=0` subset. Equal same-direction axle angles instead
produce crab translation: at 20°, 1 m longitudinal travel implies 0.364 m lateral
travel and zero yaw. The old model omits that displacement. The isolated general
model reproduces this case and exact forward/reverse SE(2) inverses.

This derivation is consistent with the physical-angle 4WS formulation in
[Optimal Control Method of Path Tracking for Four-Wheel Steering Vehicles](https://www.mdpi.com/2076-0825/11/2/61)
and the individual wheel-angle relationships in
[configuration/control review](https://www.mdpi.com/2076-0825/10/8/184).
These models assume physical angles and rolling constraints, not servo PWM units.

## 2. ATLAS geometry and conversion

Preserved source dimensions: wheelbase 0.367 m, track 0.26 m; both command centres
90. Dimensions are configured values, not newly remeasured physical dimensions.
Current wheel mapping is M1 rear-left, M2 rear-right, M3 front-left, M4 front-right.
Saved front endpoints 121/50 and rear 134/59 are asymmetric command envelopes,
not calibrated road angles. Inner/outer physical wheel angles also differ under
Ackermann geometry. An axle's command cannot silently serve as both wheel angles.

The formula's positive-left sign and reverse mathematics are internally coherent.
The wrong sign is not demonstrated to be an arithmetic sign bug. The driver uses
instantaneous applied commands with accumulated encoder deltas covering a previous
interval. That creates a transition-time model assumption, not evidence of actual
servo lag. The configured body midpoint/reference and loaded rolling radius still
need independent physical validation. No steering or dimension value was changed.

## 3. Exact wrong-yaw trace

Existing event evidence is retained, not restarted:

| Hall return interval, relative to first exact update | Accepted distance | Wheel yaw | IM10A yaw |
|---|---:|---:|---:|
| 174–176 s | +0.32847 m | +4.2595° | −15.1050° |
| 185.23–189.58 s | +0.53058 m | +7.4194° | previously −18.96° |
| 186–188 s | +0.47265 m | +4.2590° | −17.8372° |
| 204–206 s | −0.00052 m | −0.0368° | −13.2458° |

The earlier independent ICP estimate −16.09° for 185.23–189.58 s is retained as
prior evidence; the new neutral-seed screening does not falsely claim it recreated
that result. Long 2-second registrations for 174 and 186 s fail the stricter new
quality gate and remain UNKNOWN. No wheel/EKF seed is used to force agreement.

New per-update trace: at **175.183 s, sequence 57563**, command `[92,90]`,
accepted distance +0.01356 m, curvature +0.095/m, accepted M1/M2/M4; the matching
gyro interval is −0.710°. At **187.071 s, sequence 57682**, `[92,88]`,
+0.02891 m, +0.190/m, **all four accepted**, gyro −1.526°.
The algebra outputs positive yaw because positive accepted travel is multiplied
by positive command-derived curvature. The first independent inconsistency is
there, upstream of EKF and AMCL—not a dashboard error. Physical angle versus
actual body motion remains unobserved. Earlier 160–162 s near-zero wheel yaw versus
+6.39° gyro remains the earliest audited nontrivial discrepancy.

In 186–188 s raw changes were `[+2604,−2974,+1575,−2645]`; signed wheel distances
were `[0.4568,0.5273,0.2813,0.4657]` m. Opposing raw signs reflect commissioned
motor inversion. Twenty packets were fresh, at least three channels accepted, all
four accepted in 16 updates. This is not proof of an M3-only fault. Rejection near
204–206 s can erase centre translation while real yaw persists; IM10A/LiDAR agree
there under the new screening, so the wheel observation is suspect, not evidence
that ATLAS physically stopped.

## 4. Distance under-reading

Reuse the Oct 11 dual-binning evidence: 898 near-straight ICP pairs; M1/M4 roughly
0.64–0.72× and M2 0.51–0.64× in the interpretable 0.10–0.45 m/s range. Consensus
removed only about 1–3%. Slow-bin bias prevented a count-loss conclusion.
Configured circumference 0.392699 m and per-channel CPR 2238.4/2215.0/2199.1/2230.5
are not verified absolute calibration. Constant slip and constant scale remain
confounded. A fresh 10 Hz packet/no sequence gap is not proof of correct metres.
No arbitrary rescale or channel replacement was performed.

## 5. Independent evaluator and uncertainty

`stage18_motion_consistency.py` opens each SQLite bag read-only and hashes it.
It reuses the existing CDR decoder, clipped source-time gyro integration and ICP
kernel. It explicitly composes the recorded laser→base_footprint→base_link static
chain (including laser's π orientation), refuses missing/nonplanar chains,
uses header times, rejects pose extrapolation and >0.5 s pose gaps, and records
receipt lag separately. Five available relevant drive directories were evaluated.

Non-overlapping 2-second motion windows use neutral ICP seeds −0.15/0/+0.15 rad,
not odometry. All three must converge with RMSE ≤0.05 m, inlier fraction ≥0.6,
yaw spread ≤2°, and reciprocal closure ≤0.04 m/2°. Sparse/time-misaligned scans
are rejected. Repeated geometry can still fool reciprocal/multi-seed registration;
these checks are NOT guaranteed truth, global map matching or absolute accuracy.
Within-scan distortion and independently calibrated ICP covariance are missing.

Screening assumes 2° gyro, 2° LiDAR, 3° wheel uncertainty plus 0.1 s endpoint timing
uncertainty multiplied by measured maximum gyro rate. These are explicit analysis
bounds, **not measured error guarantees or production thresholds**. The reusable
gate requires supplied bounds; missing/stale evidence yields UNKNOWN. Disagreeing
independent references yield REFERENCES_DISAGREE with no winner. All outputs have
`authority=NONE`; a consistent result is not navigation qualification.

| Recording | Motion windows | ICP-screened windows | Wheel-suspect screens | Unknown |
|---|---:|---:|---:|---:|
| Hall→Dhruv exact | 26 | 12 | 1 | 14 |
| Return retry2 | 29 | 11 | 0 | 18 |
| Outbound retry2 | 19 | 4 | 0 | 15 |
| Final roundtrip exact | 52 | 26 | 6 | 26 |
| Outbound 16:36 | 0 eligible | 0 | 0 | no comparison |

Zero screens on other drives do not prove accuracy. Gyro coverage/pose availability
exclude the last recording; no synthetic zero-motion pass is invented.

## 6. Before/after isolated shadow measurements

Median *relative* error versus screened neutral ICP, over 2-second intervals:

| Detailed bag / candidate | n | XY error | Yaw error |
|---|---:|---:|---:|
| Hall return recorded wheel | 12 | 8.33 cm | 3.052° |
| Hall return general model, same commands | 12 | 8.21 cm | 3.066° |
| Hall return gyro-heading/wheel-distance shadow | 12 | 8.28 cm | 1.080° |
| Hall return recorded EKF | 12 | 10.88 cm | 1.190° |
| Final roundtrip recorded wheel | 26 | 11.02 cm | 3.406° |
| Final roundtrip general model, same commands | 26 | 11.42 cm | 3.466° |
| Final roundtrip gyro-heading/wheel-distance shadow | 26 | 11.37 cm | 0.944° |
| Final roundtrip recorded EKF | 26 | 12.27 cm | 1.794° |

Shadow uses exact accepted distance and interval gyro without replacing it with
LiDAR translation. It keeps zero lateral motion and existing distance uncertainty.
Recorded poses interpolate endpoints; exact-update candidates sum discrete packet
intervals, so boundary/cadence differences are additional uncertainty. The general
model's small error changes are not proof of improvement. Gyro heading improves yaw
as expected but fails a consistent translation-improvement gate. **Rejected for
deployment pending further evidence.** This is deterministic motion re-integration,
not a robot_localization/AMCL closed-loop replay or a new velocity-only EKF result.

## 7. EKF vulnerability and AMCL integrity

Production fuses wheel X/Y pose plus X/Y velocity from the same encoders with IM10A
gyro Z. Wheel yaw is excluded directly but still rotates integrated wheel X/Y;
those pose errors can oppose gyro-oriented EKF translation. This is a **CONFIRMED
input dependence**, not proof of the sole localization root cause. Correlated pose
and velocity and fixed covariance do not provide independent evidence.

Existing velocity-only comparison's 23.1→50.2% map-fit median remains promising
but does not prove fewer AMCL jumps. Do not repeat the fidelity-invalid AMCL replay
and call zero jumps a repair. Native ROS 2 EKF/AMCL replay was not run on this
Windows offline runtime. No new covariance or EKF configuration was deployed.

The original bag still contains five >0.5 m pose switches: 0.565, 2.206, 1.549,
1.549 and 1.481 m. Prior particle/map-alias and parked covariance evidence is
retained. **Before/after AMCL jumps: 5 / unavailable**, not 5→0. Post-stop confidence,
map fit and heading stability after a new candidate remain unvalidated.
Accepted archive hashes stay YAML `d957f0fe…`, PGM `4beb26d5…`; this relative-motion
evaluation needs no map and substitutes none. Startup 0.93 fit/0.06 margin, AMCL
initialization and production frames remain untouched.

Analyzed `.db3` SHA-256 identities (same order as the five-row table):

```text
c890f4d18e3fb1de11d3d432c5fe47a66de75bd309efe59c39da1594b7f64a93
e34111bd45a2572059cae85386abc9a8150d918d39a120da9392b91a65538671
0ca6424649838ab88c62a9e9ea566e1dbb0b07a4585392ad9df2d5e6cc4612d2
5576d93839abb935b011e4a149ce6d0669319a4cd192712af0e9e49712c5a945
99e1ed799fdcddde315119184682c8e1059cc5187fadad887a99aad914ba97d3
```

## 8. Adaptive observability, not permission to drive

Reuse existing freshness, fault qualification and dynamic three-of-four consensus.
Do not require equal raw counts: signed increments must be interpreted with geometry.

| Usable encoders | Potential offline observability | Production authority |
|---|---|---|
| 4 or 3 | Wheel rolling constraints; with measured angles and residuals can estimate motion. Shared scale/slip still unobservable without reference. | Existing qualified 3-of-4 gate only |
| 2 | With valid independent yaw and nonparallel measured directions, translation can be solved; parallel pair leaves lateral motion unobserved. | Stop; no relaxation approved |
| 1 | One rolling projection only; even gyro leaves a translation component missing unless an independently validated no-slip constraint is imposed. | Stop |
| 0 | No wheel translation; gyro observes heading only. LiDAR may offer shadow relative motion, not commissioned replacement. | Stop |

Per-wheel future quality should separately retain packet age, counter continuity,
direction residual, rolling/slip residual, independent-reference quality and
sustained fault recovery. Do not reintroduce a channel from one good packet or
select the convenient pair after seeing the desired answer. MCU acquisition times,
actual road angles and calibrated residual bounds are missing; no calibrated
per-wheel score or lower-count navigation authority was invented here.
The existing measured-angle rolling harness is reused conceptually, not duplicated.

## 9. Source, tests, resource impact and rollback

**FIXED IN SOURCE (isolated model only):** complete lateral/path geometry and exact
constant-twist integration are implemented in `stage18_motion_model.py`, tested
against symmetric legacy behavior, asymmetric no-slip constraints, crab motion and
reverse. Neither module is imported by the live driver. The driver's only edit
corrects misleading comments about measured geometry and permanent M4 exclusion.
`stage18_motion_consistency.py` provides explicit quality/uncertainty/missing-data
gates and shadow comparison. No active diagnostic/background service is added.

**56 tests passed:** 12 new tests plus 23 encoder-selection, 6 existing IM10A bias,
6 stop-hold, 6 measured-angle/rolling-model and 3 prior yaw-evidence tests.
New coverage: geometry, reverse, finite-input validation, reference disagreement,
missing/stale evidence, heading wrapping, no extrapolation and synthetic independent
ICP. Native `test_atlas_fusion_replay.py` could not import `rosbag2_py` in the Windows
runtime; it is an environment-blocked test, NOT a passed native replay. Compilation
and diff checks passed. The delivery commit is linked in the final handoff.
Five-bag final replay used ~4.98 CPU seconds / 5.06 wall seconds; lifetime sampled peak
working set 147.55 MiB on the **Windows PC**, not Jetson. ROS/control CPU impact is
zero because nothing was installed. This is not a Jetson resource benchmark.
Generated detailed evidence remains local in `artifacts/stage18_motion_comparison_20261014_verified.json`;
source hashes and summarized results are in this report. Logs/bags are not committed.

Rollback is stop using the isolated tools or revert the Stage 18 source commit;
production remains intact. Source commit is linked in the delivery message (a
committed report cannot contain its own commit hash). Base `46ff15f` is preserved.
An AST comparison against that base confirms the motor driver's executable code
is identical; only comments changed.

Reproduce without ROS using a Python environment with NumPy/SciPy/rosbags:
`python project_atlas/tools/diagnostics/stage18_motion_consistency.py BAG1 BAG2 ... --output NEW_OUTPUT.json`.
The tool refuses an existing output path and never overwrites input bags.

## 10. Minimum next evidence — no test authorized here

No repeated whole-house route is requested. First validate any future candidate
through native isolated EKF replay with preserved source/header times and accepted
map/AMCL initialization, reporting parked jumps rather than map-fit percentages.
The saved-data motion comparison already rules out a blind lateral-term or global
sign fix. It cannot identify CPR versus slip or actual angle-versus-command motion.
Minimum later owner-approved physical reference is a tape-measured short straight
forward/reverse leg at two speeds and one independently measured loaded body turn,
capturing exact updates, raw/corrected gyro, scans/TF and particles. If fitting a
steering conversion remains necessary, actual road-wheel angles are indispensable;
working servo observation alone does not measure that conversion. Stage 17B remains
on HOLD; no sweep or physical test is requested or executed by this report.

**Final state: moving localization UNRESOLVED; isolated diagnostics improved;
motion-model candidates NOT DEPLOYED; autonomous authority unchanged.**
