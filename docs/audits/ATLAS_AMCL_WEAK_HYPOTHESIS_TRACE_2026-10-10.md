# Survival of the low-weight room hypothesis

Continuation of the 2026-10-09 next-week handoff from `cc5862a`.
Offline only: no ROS context, movement, motor activation, steering change,
service restart, initial-pose publication or production parameter change.
The Jetson was accessed read-only to copy the saved recording and to confirm
the deployed AMCL parameter file.

## Answer

The 15 room-near particles were lost through **resampling while parked**.
The scans did not reject them, and odometry did not push them away.

- **When:** support fell from 15 particles at +351.997 s to zero at
  +362.854 s, over 11 AMCL updates.
- **Odometry:** the total change across that window was 0.23 mm and
  0.0003°, below AMCL's 0.05 m / 0.05 rad motion-update thresholds. Every
  update in this window was a forced no-motion update.
- **Scan likelihood:** the scans favoured the room. The exact refined room
  pose scored above every particle in the cloud on every update. The 15
  room-near particles scored about average, because none sat on the peak.
- **What removed them:** multinomial resampling of frozen poses while
  KLD-adaptive sampling shrank the cloud from 2,000 to 1,098 particles.
  Simulated with AMCL's own sampler, this removes all room support within
  11 updates in about 1 run in 10. The observed loss is a plausible chance
  outcome; no likelihood disadvantage is needed to explain it.
- **What could have recovered it, and why it did not:** nothing could create
  a particle near the peak while parked. There is no motion-model spread at
  zero odometry, and `recovery_alpha_fast` / `recovery_alpha_slow` are 0.
  Even a particle placed exactly on the peak gains only about 1.55× weight per
  update, so it would still not take over in this window.

This is a mechanism finding on one recording. It is not a fix, and it does
not explain why AMCL's majority was already wrong before the rover stopped.

## Method and provenance

- **Source:** `data/demonstrations/amcl_roundtrip_20261009_final` on the
  Jetson. The copied `.db3` SHA-256 is
  `5576d93839abb935b011e4a149ce6d0669319a4cd192712af0e9e49712c5a945`,
  matching the Jetson file. The SQLite file is read with `mode=ro`, using the
  recorded map and laser transform.
- **Script:** `project_atlas/scripts/atlas_amcl_weak_hypothesis_trace.py`. It
  accepts only this bag name, because the hypotheses and offsets belong to
  this recording. Raw output remains outside Git.
- **Room candidate:** the locked refined room pose
  `(0.37479, -1.16681, 1.38742 rad)` from
  [competing-pose evidence](ATLAS_COMPETING_POSE_EVIDENCE_2026-10-09.md).
  Support uses the same rule as that report: within 0.5 m AND within 20°.
  The start cloud matches that report: 15 particles, nearest 0.198 m.
- **Likelihood model:** a reimplementation of nav2_amcl 1.1.20
  `LikelihoodFieldModel`, checked against the 1.1.20 source:
  - beam step `(360-1)//(60-1) = 6`, giving 60 beams;
  - ranges at or below `range_min` are treated as max range, and max-range
    beams are skipped;
  - off-map endpoints use `laser_likelihood_max_dist`;
  - weight factor `p = 1 + Σ pz³`.

  Parameters are the deployed ones: `likelihood_field`, `max_beams` 60,
  `sigma_hit` 0.2, `z_hit` 0.5, `z_rand` 0.5, `laser_likelihood_max_dist`
  2.0. The deployed file (SHA-256 `24620bf4…`) is identical to the
  repository copy apart from line endings.
- **Sampler:** nav2_amcl 1.1.20 `pf_update_resample` uses its "naive
  discrete event sampler", which is multinomial, with KLD-limited sample
  count. With both recovery alphas at 0, `w_diff` is 0, so no random poses
  are injected.

## Trace: +351.997 s to +362.854 s

Each update pairs a cloud with the latest `/scan` received before the next
cloud. All published clouds in this window carry uniform post-resample
weights, so the likelihoods below are recomputed rather than read from AMCL.

| Cloud | Offset (s) | Particles | Room support | Room support weight ÷ cloud mean | Cloud max likelihood | Exact room pose likelihood |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 497 | 351.997 | 2,000 | 15 | 1.03 | 4.78 | 5.57 |
| 498 | 352.785 | 2,000 | 13 | 1.11 | 4.87 | 6.03 |
| 499 | 353.834 | 2,000 | 13 | 1.13 | 5.07 | 6.18 |
| 500 | 354.874 | 2,000 | 18 | 0.99 | 4.67 | 5.57 |
| 501 | 355.791 | 2,000 | 15 | 1.01 | 5.15 | 6.03 |
| 502 | 356.844 | 2,000 | 18 | 1.04 | 4.96 | 6.01 |
| 503 | 357.765 | 2,000 | 17 | 0.93 | 5.08 | 6.18 |
| 504 | 358.938 | 1,915 | 8 | 0.93 | 5.43 | 6.34 |
| 505 | 359.863 | 1,641 | 5 | 0.94 | 5.14 | 6.51 |
| 506 | 360.776 | 1,429 | 5 | 0.95 | 5.02 | 5.70 |
| 507 | 361.829 | 1,290 | 2 | 0.88 | 5.32 | 6.44 |
| 508 | 362.854 | 1,098 | 0 | – | 4.93 | 5.87 |

The exact room pose outscored the best existing particle on every update.
The late false anchor scored 4.5–5.3 on the same scans. The scans therefore
preferred the room location throughout. The cloud contained no particle close
enough to that peak to benefit.

Distinct support collapsed alongside the room loss: 1,268 unique poses at
+351.997 s fell to 7 by +449.851 s. This matches the impoverishment already
recorded in [particle collapse](ATLAS_AMCL_PARTICLE_COLLAPSE_2026-10-09.md).

## Why the room particles gained no advantage

The 15 particles sat 0.198–0.312 m and 1.6–19.2° from the refined room pose.
On the first update's scan, likelihood falls quickly away from the peak:

| XY offset | 0° | 5° | 12° |
| ---: | ---: | ---: | ---: |
| 0.00 m | 5.57 | 5.41 | 4.68 |
| 0.10 m | 4.80 | 4.58 | 3.69 |
| 0.20 m | 3.72 | 3.58 | 3.12 |
| 0.30 m | 3.06 | 3.07 | 2.85 |

At 0.2–0.3 m and around 10°, the likelihood is about 3.1–3.7. The cloud mean
on that scan was 3.60, so the room particles were neutral in practice.

## Resampling experiment

Setup: the start cloud's 2,000 poses are held fixed, which matches zero
odometry. Each update draws multinomially with the observed KLD counts
(2,000 ×6, then 1,915, 1,641, 1,429, 1,290, 1,098). There were 4,000 trials
per case, with seed 20261010.

| Case | P(all room support lost within 11 updates) | Median room particles remaining |
| --- | ---: | ---: |
| Equal weights (pure drift) | 14.2% | 7 |
| Recomputed likelihood-field weights | 9.6% | 10 |
| Observed | lost | 0 |

The recomputed weights slightly *favour* the room set: 1.03–1.13× the cloud
mean on every update, because these trials keep the original poses. They do
not explain the loss. Drift alone is sufficient. The observed outcome is a
roughly 1-in-7 to 1-in-10 event, not a certainty, and a small disadvantage
from effects this model does not capture cannot be excluded.

Counterfactual: add ONE particle exactly at the refined room pose. It scores
1.50–1.64× the cloud mean per update. It survives 11 updates in 59% of trials,
with a median of 13 copies out of 1,098 particles at the end. With this
sensor model's flat weights, even a correct minority hypothesis grows slowly
while parked, and it can still be lost by chance.

## What this does and does not establish

**Established for this recording:**

- The loss happened entirely while parked.
- The odometry and heading prior had no effect during the loss.
- The scans did not reject the room set.

**Not established:**

- Why AMCL's majority was already on the wrong side before stopping. Earlier
  audits point to wheel-derived heading divergence during motion; this trace
  does not test that.
- AMCL's internal pre-resample weights. The published clouds are
  post-resample.
- Behaviour on other drives.

No candidate fix was evaluated. The handoff's comparison metrics (AMCL jump
count, maximum jump, stopped-position stability, heading and held-out scan
fit) therefore have no candidate to report yet.

## Implications for the next experiments

These directions follow from the mechanism. Each needs AMCL replay on the
saved drives, scored with the handoff metrics, before any deployment
decision:

1. **Stop forced no-motion updates while parked.** This is the repository's
   existing fresh-odometry request gate (`ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md`).
   This trace shows it would remove the drift that erased the room set. It
   would not, by itself, move the cloud onto the better pose.
2. **Controlled diversity while parked.** Bounded pose jitter or bounded
   recovery injection would let the scan pull particles onto the room peak,
   which scores about 5.6–6.5 against a cloud best of 4.7–5.4. Any such
   change must keep the existing stale-pose, jump and covariance rejections.
3. **Sensor-model sharpness.** With `z_rand` 0.5, a pose on the peak earns
   only about 1.55× per update. This explains the slow takeover. It is not
   evidence that a different value is safe. Earlier rejected tuning must not
   be repeated without discriminating replay evidence.

The production configuration is unchanged. This handoff does not authorize
any rover movement, motor activation, steering change or autonomous
navigation.

## Validation

- 13 unit tests pass in
  `project_atlas/scripts/test_atlas_amcl_weak_hypothesis_trace.py`. They
  cover wrap and joint support, non-finite rejection, AMCL beam step,
  capped distance field, empty-map rejection, correct-pose preference,
  short and max-range skipping, off-map maximum distance, laser offset and
  yaw direction, neutral full membership, seed reproducibility, takeover by
  a strongly favoured particle, and invalid-weight rejection.
- The neighbouring particle-diversity tests still pass.
- The complete script ran on the saved bag.
