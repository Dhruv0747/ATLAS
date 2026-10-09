# Stationary AMCL update-policy experiment

Continuation from `7a6bff7`. No production ROS node, actuator, calibration,
parameter, initial pose or service was changed. The separate executable
initializes no ROS context and only reads exported recording data.

## Outcome

Repeated stationary scan assimilation can reproduce large hypothesis
switches and severe particle impoverishment using the installed AMCL core.
Resampling less often does not reliably eliminate either problem. Scoring
each scan against a fixed prior preserves diversity and reduces apparent
movement, but freezes an already wrong prior. **None of these candidates is
approved for deployment or establishes accurate localization.**

## Experiment and provenance

Source bag: `amcl_roundtrip_20261009_final`. The exporter automatically found
three intervals in which recorded EKF pose stayed within 2 mm and 0.2 degrees
of the interval anchor, with no odometry gap exceeding 1 second:

| Window | Bag offsets (s) | Selected scans | Initial distinct support |
| --- | --- | ---: | ---: |
| 0 | 1.673–120.946 | 111 | 29 |
| 1 | 171.442–280.943 | 103 | 1,232 |
| 2 | 351.239–464.442 | 106 | 1,268 |

Each run restores the same first published particle cloud inside its window,
uses the recorded occupancy grid and laser extrinsics, and evaluates scans
approximately once per second. Scans are chosen after the seed cloud and
after the interval begins. AMCL's likelihood-field range preprocessing and
base-frame beam bearings are preserved. For this controlled stationary
experiment, the motion delta is set to zero rather than injecting the small
recorded odometry fluctuations. This is not a full TF/timing replay.

The executable uses actual Nav2 AMCL 1.1.20 particle-filter, map, clustering,
resampling and laser-model libraries. Dynamic loader verification showed
the installed `/opt/ros/humble/lib` libraries were loaded. The independently
built trace workspace supplies matching 1.1.20 headers. No library was replaced.
Installed package: `1.1.20-1jammy.20260607.130817`.

- sensors library SHA-256: `dc48e3c5993c54ab329a699d18aa17e2382ceb5a2d954629defcd511292f6531`
- particle filter SHA-256: `c94e7373711347fb98ac9da8ddb4fb8048d3c6d86bef543e7db2835b7205749c`
- map library SHA-256: `a65bf0bad565bdcad042418b62adfef5961412c7673ac766fe3e51621dfcf2e2`

Four policies were compared at RNG seeds 1, 7 and 42 (36 runs):

1. `baseline`: recursively update weights and resample every scan.
2. `ess_half`: recursively update, resampling only below 50% weight ESS.
3. `no_resample`: recursively update weights but never resample.
4. `fixed_prior`: restore the window's initial cloud and weights before each
   scan; score once without resampling. This prevents accumulating repeated
   evidence but does not create missing pose alternatives.

During harness verification, `pf_alloc` was found to reset `srand48` from
wall time. The controlled seed is now applied **after** allocation. Preliminary
results from the earlier seeding order are excluded. A repeated full window
with the corrected order matched all 12 result trajectories exactly.

## Measurements

Ranges below span the three seeds. Geometric ESS aggregates weights at
rounded x/y/yaw support points, so repeated copies do not inflate confidence.

| Window/policy | Final distinct support | Final geometric ESS | Steps >0.5 m | Largest step (m) | Max heading change from initial |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 baseline | 1–3 | 1.00–1.27 | 0 | 0.008–0.013 | 0.80–1.15° |
| 0 fixed prior | 29 | 9.98 | 0 | 0.003 | 0.07° |
| 1 baseline | 3–4 | 1.41–2.77 | 1 | 3.766–3.859 | 54.77–55.98° |
| 1 ESS-half | 37–41 | 3.55–4.12 | 1 | 3.873–3.918 | 55.01–56.05° |
| 1 no resampling | 1,232 | 3.99 | 1 | 3.920 | 55.53° |
| 1 fixed prior | 1,232 | 930.95 | 0 | 0.024 | 1.88° |
| 2 baseline | 3–4 | 1.22–2.13 | 5–11 | 1.198–1.596 | 162.71–174.63° |
| 2 ESS-half | 69–83 | 5.73–8.01 | 3–11 | 1.272–1.332 | 158.94–160.54° |
| 2 no resampling | 1,268 | 8.84 | 0 | 0.488 | 130.71° |
| 2 fixed prior | 1,268 | 968.09 | 0 | 0.029 | 1.43° |

The return-window baseline reproduces the stationary-jump **class**, not the
original five-event trajectory. Matching a count in one seed is not matching
the historical failure. Removing resampling alone still concentrates nearly
all weight on a few alternatives. Its return-window heading changes by
130.71 degrees even though no single translation exceeds 0.5 m; a zero
large-translation-jump count would therefore be misleading.

Fixed-prior maximum displacement is 0.005/0.029/0.040 m in windows 0/1/2.
However, window 1 remains around `(3.221, -0.510)` instead of approaching the
previously accepted Hall region around `(6.279, -2.199)`. Window 2 remains
around `(3.009, -0.316)`, incompatible with the earlier Dhruv Room candidate.
Suppressing the correction preserves an inaccurate starting hypothesis.

## Why a steady map marker is insufficient

The nearest initial return-window particle is 1.034 m from the earlier
scan-derived Dhruv Room candidate `(0.184, -2.034, 1.447 rad)`; none is within
0.5 m. That candidate is an approximate scan-derived reference, not surveyed
ground truth. No stationary reweighting/resampling policy can create a new
pose outside its existing support when random recovery and motion are absent.

On the same last return scan, the actual AMCL likelihood-field score was:

| Evaluated pose | Score |
| --- | ---: |
| Initial selected return-window hypothesis | 2.4442 |
| Baseline final hypothesis (seed 1) | 5.3019 |
| Earlier scan-derived Dhruv Room candidate | 4.8419 |

These are model scores, not calibrated probabilities or accuracy. The model
can favor the suspect location over the plausible room candidate. This
supports investigating scan/map ambiguity and the prior delivered by motion
integration; it does not prove which is the sole original root cause. True
position error cannot be measured from these internal estimates alone.

## Changes and verification

- Added `atlas_extract_stationary_pf.py`, a read-only SQLite exporter with
  stationary-window checks and explicit missing-checkpoint/ground-truth limits.
- Added `atlas_stationary_pf_experiment.cpp`, a standalone AMCL core harness.
- Added `validate_atlas_stationary_pf_results.py` to verify equal starting
  states, scan counts, finite poses, ESS bounds, particle-support invariants,
  policy behavior, RNG-independent policies and exact repeatability.
- Build passed on Jetson. All 36 runs passed the experiment checks, and the
  additional 12-run repeated window matched exactly. These are experiment
  validity checks, **not 48 autonomous tests**.
- Production AMCL retained PID 8075 and was not restarted. Raw result
  trajectories are saved in
  `/home/jetson/project_atlas/data/diagnostics/amcl_pf_policy_20261009/` and are
  excluded from Git. Input bundles are reproducible from the retained bag.

## Next necessary action

Reject these stationary-policy variants as complete navigation fixes. Test a
bounded method of retaining/reintroducing credible pose alternatives and
independently rejecting a wrong map match; investigate the moving odometry
prior using the existing recordings. Health reporting must eventually be
separated from unconditional repeated Bayesian updates without weakening the
motion watchdog. Existing steering calibration remains untouched. No new
manual route is requested from this experiment, and live pose correction is
separate from validating a permanent localization repair.

Reproduce by exporting a retained single-file SQLite bag and compiling the
standalone harness against AMCL 1.1.20. Run it on each exported JSON window,
then validate all three results and a repeated first-window result. Never
play actuator topics or replace the production AMCL node for this experiment.

## Follow-up: startup reset and bounded request-policy repair

Read-only post-reboot inspection verified startup at 21:39:42 IST explicitly
called the existing seed service with `(0.254, -1.539, 1.337 rad)`. A subsequent
AMCL sample was `(0.359, -1.215)` (about 0.34 m from saved home). The operator
reported the displayed room was correct. This is a seeded restart, not proof
of autonomous global recovery. The deployed Nav2 configuration SHA-256 remained
`24620bf4416a1a5b215353876b4fb63458e974a41425103c7b157fb03df80706`.

Repository-only candidate repair: mission control now bounds its periodic
forced updates by fresh `/odom` progress (5 mm or 0.005 rad cumulatively),
allows only one in-flight request, and rejects missing/stale/nonfinite input,
invalid quaternions, duplicate timestamps and backward clock steps. These
are request-scheduling bounds, **not wheel or steering calibration**. Natural
AMCL updates, explicit pre-motion refresh, and the mux freshness timeout are
unchanged. This prevents gratuitous parked updates; it cannot restore a
missing correct hypothesis or certify the accuracy of wheel odometry.

`atlas_replay_amcl_update_gate.py` simulated the 1 Hz timer using recorded
receipt/header times, without running a ROS node or changing any service:

| Oct 9 recording | Timer ticks | Candidate requests | Unchanged-pose ticks | Requests on unchanged pose |
| --- | ---: | ---: | ---: | ---: |
| outbound 1636 | 349 | 0 | 300 | 0 |
| outbound retry2 | 173 | 40 | 81 | 0 |
| return retry2 | 242 | 55 | 143 | 0 |
| final roundtrip | 462 | 110 | 258 | 0 |
| original Hall return 122252 | 290 | 52 | 193 | 0 |

Total: 1,516 timer ticks, 257 candidate requests, and zero forced requests
on 975 fresh exactly unchanged-pose ticks. The first recording had 33 stale
ticks; the others had none at sampled timer times. This is a scheduling
check, **not** an AMCL jump-reduction or navigation pass. Ten gate/callback
tests, four particle-diversity tests and five display regressions passed.

**Not deployed.** Before deployment, validate the complete AMCL/mux interaction
offline: slow-motion freshness, start-from-rest and stopped goal handling.
The unchanged 2.5 s mux timeout may reject slow/stationary operation with this
candidate. Do not loosen it to make the experiment pass. A localization-health
contract must distinguish event-driven pose updates from loss of localization.
Preserve the pre-change production system until this is verified. Source
rollback is to restore only the mission-control change from parent revision;
the additional diagnostic modules have no running processes.

Permanent localization remains unresolved: earlier hypotheses already lacked
the correct return pose and the motion model still disagrees with gyro/scan
turn evidence. No new physical test, reseed, motor command or steering change
was performed for this follow-up.

## Deployment validation: REJECTED (follow-up to 4a4ea9a)

The candidate fails the existing localization freshness contract. Five new
non-actuating tests execute the actual repository `localization_guard` method
with controlled clocks, rather than implementing a substitute guard:

- A confident sample at t=100 permits t=102.5 but returns LOCALIZATION STALE
  at t=102.51. The candidate sends no update for unchanged fresh odometry.
- At 1 mm/s for three seconds the candidate's cumulative 5 mm bound is not
  reached. AMCL's configured natural 5 cm/0.05 rad update thresholds are also
  not reached. The guard blocks at three seconds despite fresh motion input.
- One pre-motion refresh does not cover a subsequent stationary pause.
- Fresh timestamps do not bypass a latched jump or excessive covariance.

The inspected AMCL 1.1.20 source checks odometry displacement thresholds OR
`force_update_`; continuing scan delivery alone does not guarantee a fresh
pose publication. These are deterministic contract counterexamples, not a
full ROS timing replay or physical navigation result. They are sufficient to
reject deployment without another route test or expensive AMCL replay.
All five rejection-regression tests and ten gate/callback tests passed.
Production localization retained MainPID 4371, NRestarts=0 during read-only
inspection. No production settings or services were changed.

Next necessary engineering change: design an independently verified health
signal for AMCL's processed scans/TF and estimate validity, distinct from pose
publication and from repeated particle assimilation. A timer that republishes
an old pose is NOT such a signal. Validate real scan/TF loss and wrong-pose
rejection as well as healthy stationary operation before changing the mux
contract. Keep its current fail-closed timeout intact meanwhile. The source
candidate in 4a4ea9a remains experimental and MUST NOT be deployed alone.
This does not resolve the separate moving-prior/heading disagreement.
