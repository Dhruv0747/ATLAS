# Encoder distance against LiDAR, by speed (offline), 2026-10-11 20:40 IST

Read-only analysis of saved Oct 9 bags. Nothing on ATLAS was changed, driven or recalibrated.
Tool: `project_atlas/tools/diagnostics/encoder_scale_by_speed.py`.

## Question

The known ~0.6× encoder distance (ATLAS-001) could be:
- a constant scale error (CPR, wheel size or gearing after the motor replacement), or
- counts lost at speed (slip, or encoder/firmware count loss).

A constant error would justify a measured calibration change; lost counts would not.

## Method

- **Pairs:** scan pairs 3 scans apart (0.2–0.8 s), aligned by LiDAR scan-to-scan ICP. ICP is
  independent of the wheels and the map.
- **Pair filter:** kept only pairs with rmse < 0.05 m, inliers ≥ 60% and |yaw| < 3°, i.e. near-straight
  motion.
- **Compared over the same interval:**
  - `raw_mN`: Δcounts × sign / CPR × circumference, from `config/encoder_calibration.yaml`;
  - `/yahboom/odom`: the output of the 3-of-4 consensus estimator;
  - `/odom`: the EKF.
- **Timing:** every series uses bag receipt time.
- **Bags:** 4 Oct 9 bags with usable pairs (898 pairs). `amcl_hall_outbound_20261009_1636` gave 0
  pairs.

**Bias check:** binning by one noisy speed estimate biases the ratio (regression to the mean), so
results are binned twice, by ICP speed and by encoder speed. Only a trend seen in both binnings
counts.

## Result (all bags)

**Distance ratio over ICP, binned by ICP speed:**

| ICP speed (m/s) | n | raw median | M1 | M2 | M4 | EKF |
|---|---|---|---|---|---|---|
| 0.03–0.10 | 129 | 0.98 | 0.98 | 0.90 | 0.95 | 0.71 |
| 0.10–0.20 | 205 | 0.72 | 0.72 | 0.64 | 0.72 | 0.60 |
| 0.20–0.30 | 149 | 0.65 | 0.66 | 0.51 | 0.65 | 0.53 |
| 0.30–0.45 | 119 | 0.65 | 0.65 | 0.57 | 0.65 | 0.58 |
| 0.45–1.00 | 66 | 0.60 | 0.59 | 0.56 | 0.59 | 0.51 |

**Distance ratio over ICP, binned by encoder speed:**

| Encoder speed (m/s) | n | raw median | M1 | M2 | M4 | EKF |
|---|---|---|---|---|---|---|
| 0.03–0.10 | 210 | 0.53 | 0.53 | 0.46 | 0.52 | 0.64 |
| 0.10–0.20 | 266 | 0.66 | 0.66 | 0.54 | 0.66 | 0.55 |
| 0.20–0.30 | 129 | 0.64 | 0.64 | 0.55 | 0.64 | 0.52 |
| 0.30–0.45 | 54 | 0.65 | 0.65 | 0.62 | 0.65 | 0.56 |

Other figures:
- **Consensus estimator over raw median:** 0.975–0.997 in every bin.
- **M3:** about 0 or negative throughout.

## Interpretation

**Confirmed:**
- **0.10–0.45 m/s:** both binnings agree. M1 and M4 read **0.64–0.72** of the LiDAR distance;
  M2 reads **0.51–0.64**.
- **Slow end:** the two binnings move in **opposite** directions, which is the signature of
  binning bias. Neither slow-end number is evidence.
- **Consensus estimator:** it is not the main loss. It removes 1–3%, apart from isolated intervals
  (the round trip above 0.45 m/s; 122252 at 0.10–0.20 m/s).
- **M1/M4 versus M2:** M1 and M4 agree with each other, and M2 is consistently lower. That is a
  per-wheel difference, not one global scale.

**Retracted:** an earlier reading in this session took the ICP-binned table alone as showing
"raw ≈ 0.95 at low speed, falling with speed", i.e. speed-dependent loss. The encoder-binned table
does not support that, so it is withdrawn.

**Not separable from bags:**
- A ratio that is roughly flat across 0.1–0.45 m/s fits a constant CPR/scale error.
- It also fits a constant slip fraction. With skid steering, wheels on one side can slip
  steadily even in straight motion.

**Next step:** tape-measured straight runs with raw counts (already listed under ATLAS-001), at two
speeds. A tape is the only reference that has neither binning bias nor ICP corridor degeneracy.

**No calibration change is proposed.** A ×1.5 CPR change would be an arbitrary scaling factor
until the tape test separates scale from slip.

## Limits

- ICP in long corridors can be degenerate along the corridor axis. That would make ICP
  **under**-estimate motion and the ratio read **high**, so it cannot explain a low ratio.
- Scan motion distortion is not corrected; at 0.5 m/s it is about ±5 cm per scan and largely
  cancels between scans of the same motion.
- Bag receipt timestamps contain transport latency. A constant latency does not bias steady-state
  ratios but adds noise during acceleration.
