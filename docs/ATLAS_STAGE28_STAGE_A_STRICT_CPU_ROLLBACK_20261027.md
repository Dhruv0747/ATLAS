# Stage 28 Stage A (recovery coordination): FAIL on strict CPU, rollback verified — 2026-10-27

One owner-approved attempt, `--cpu-rule strict`, package `git archive` of GitHub commit `df34205` (archive sha256
`2810d1c9a7e523cebc5d4bc64d0aa29ce838fbde2a9101a523f1c657ff3e33e2`), run detached as transient unit `atlas-stage28-A`.
No retry.

## Sequence (Jetson time)
| Time | Step | Result |
|---|---|---|
| 20:56:08 | read-only preflight | GO: live hashes = reviewed baselines; candidates A+B rebuilt, all hashes match; 14/14 safety ×3; CPU mean 65.53 / max 68.87; RAM 62.86; 64.09 C |
| 20:57:02 | A-pre safety | 14/14 ×3; encoders constant; packets 200080→200180 |
| 20:57:32 | A-pre resources (30 × 1 s, strict) | mean 65.3, max 67.51, RAM 63.07, 63.97 C |
| 20:57:33 | backup | recovery c6b5ac79 + absent module; backup.tar; verified |
| 20:57:35 | install 2 files, restart atlas-sensor-recovery ONLY | patched recovery logged `coordination: loaded` and `READY` |
| 20:58:06 | strict post-restart gate (every sample from restart) | **FAIL**: 7 of 30 samples > 75 % |
| 20:58:06–09 | reviewed rollback | original recovery restored (c6b5ac79), module removed, one recovery restart, READY |
| 20:58:28 | read-only post-rollback check | GO: 14/14 ×3; CPU mean 65.11 / max 67.06; RAM 60.89; 64.13 C |

Continuous recorder, seconds after the restart → whole-machine CPU %:
-1.5 64.1 · -0.5 64.6 · 0.5 71.1 · 1.5 71.6 · **2.5 95.3 · 3.5 99.8 · 4.5 99.5 · 5.5 96.0 · 6.5 90.8 · 7.5 90.4 · 8.5 80.7** ·
9.5 66.5 · then 64.5–69.5 to 29.6 s.

## Exact failure
The strict single-sample 75 % rule was exceeded for about 7 s by the start-up of the recovery process itself
(Python + rclpy init + subscriptions), beginning about 2.5 s after the restart, with a peak of 99.8 %. Steady state
returned to 64–69 % within 10 s. This is the same mechanism as the d1d13a3 rejection (98.8 %). It is not a
coordination-logic failure: the lease/ack/release proof never ran because the CPU gate precedes it.

## State after rollback
- Files: `atlas_sensor_recovery.py` c6b5ac79 (original); `atlas_base_maintenance.py` absent; `atlas_flysky_core.py` 3e4b379e unchanged.
- PIDs: base 1921 (NRestarts 0, never restarted); recovery 1947 → 64464 (two restarts: install + rollback);
  mux 1917, safety 1939, web 2068, camera-joystick 1937, camera 1924, EKF 3406, localization 4289, LiDAR 1919,
  voice 2137, mode-manager 1944, tight-recovery 1958, all unchanged and active.
- No lease, no drop-in. E-STOP latched ("REMOTE STOP: joystick unavailable"); Xbox remains unavailable, so coexistence is untested.
- The rollback restart has no CPU gate of its own; its transient was not separately measured.

Evidence: `/home/jetson/project-atlas-migration/stage28-recovery-coordination-20261027_205658-578206610/`
(safety snapshots, resources, recorder, result, backup, SHA256SUMS.all).

## Next gate (no attempt authorised)
With a 65–67 % baseline on 6 cores, any restarted rclpy node that briefly uses more than ~0.5 core breaches the strict
single-sample rule. Owner options:
1. **Accept a transient rule** for service restarts (`settle`: ≤120 s, 5 × 1 s ≤ 75 %, then 30 s strict). The limits stay unchanged.
2. **Cap the start-up** with a reviewed temporary `CPUQuota` on the restarted unit. This is a safety-service config
   change; it lengthens start-up and is only marginal at a 65 % baseline (+0.5 core ≈ +8 points).
3. **Lower the baseline first** (separate investigation; Stage 32 found no safe dominant fix yet).
Stage B stays blocked behind Stage A.
