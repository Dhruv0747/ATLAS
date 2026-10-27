# Stage 28 Stage A, attempt 2 (transient 10 s, commit f7bf93f): FAIL, fail-closed abort, rollback verified — 2026-10-27

Owner-approved single attempt. Package: `git archive` of GitHub `f7bf93f717f581dfe8471df6344118056db16636`, archive sha256
`d7a01d401f96f8499d26f723b65bd09f815b9f35e52c88da9a87a47fd6273bb0`. Run as transient unit `atlas-stage28-A2`. No retry.

## Sequence (Jetson time)
| Time | Step | Result |
|---|---|---|
| 21:53:21 | read-only preflight | GO: 14/14 ×3; CPU mean 66.01 / max 69.08; RAM 62.3; 64.19 C; status API 5–29 ms |
| 21:54:08 | A-pre safety | 14/14 ×3; encoders constant; packets 283625→283725 |
| 21:54:38 | A-pre resources (30 × 1 s strict) | mean 65.52, max 67.72, RAM 62.75, 64.41 C |
| 21:54:40.9 | install, restart atlas-sensor-recovery ONLY | patched recovery: `coordination: loaded` 44.34, READY 44.53 |
| 21:54:45.4 | safety snapshot +4.52 s | `/api/status` **TimeoutError (2 s)**: no data, so all 13 status predicates false; snapshot gap 3.9 s > 3.5 s |
| 21:54:46 | **IMMEDIATE ABORT** (fail-closed: safety monitoring not reliable during the spike) | rollback started |
| 21:54:46–52 | rollback | original recovery restored (c6b5ac79), module removed, one recovery restart, READY 21:54:50.9 |
| 21:55:56 | read-only post-rollback check | GO: 14/14 ×3; CPU mean 65.74 / max 68.11; RAM 63.37; 64.25 C; E-STOP latched |

## CPU timeline (every sample, seconds after the restart, whole-machine %)
| Restart | Samples |
|---|---|
| Install restart (patched recovery) | -1.5 64.62 · -0.5 67.39 · 0.51 71.31 · 1.51 73.60 · **2.52 98.51 · 3.54 99.83 · 4.57 99.67** → aborted |
| Rollback restart (original recovery) | 0.5 **91.65** · 1.51 72.11 · 2.52 **78.22** · 3.59 **99.50** · 4.59 **99.33** · 5.62 **99.83** · 6.63 **97.18** · 7.64 **94.52** · 8.65 **94.12** · 9.66 71.50 · 10.66 65.19 · then 64.2–66.7 |

The rollback restart was not CPU-gated, by design; it was recorded and reported. Its last over-limit sample was at +8.65 s,
consistent with the first measurement (+8.5 s) and the 10 s bound.

## Safety-monitoring intervals
| Snapshot | Interval | State |
|---|---|---|
| -2.47 s | — | ok |
| -0.94 s | 1.53 s | ok |
| +0.61 s | 1.55 s | ok |
| +4.52 s | **3.91 s** | `/api/status` timed out |

## Exact failure
During the discovery-driven CPU saturation (98.5–99.8 %), `rover-status-web`, the deployer's independent safety data
source, could not answer `/api/status` within the 2 s client timeout; the web logged the matching `BrokenPipeError`.
The snapshot therefore carried no data. The fail-closed rule aborted.

This is **not** evidence that E-STOP, commands or telemetry changed: every snapshot before and after was 14/14, and no
other unit logged warnings. But safety could not be **verified** during the spike, which is exactly the
owner's abort condition.

## State after rollback
- Files: recovery c6b5ac79, module absent, `atlas_flysky_core.py` 3e4b379e.
- No lease, no drop-in.
- PIDs: base 1921 (NRestarts 0, never restarted); recovery 64464 → 95634 (install + rollback restarts). Unchanged:
  mux 1917, safety 1939, web 2068, camera-joystick 1937, camera 1924, EKF 3406, localization 4289, LiDAR 1919,
  voice 2137, mode-manager 1944, tight-recovery 1958.
- Xbox still unavailable.

Evidence: `/home/jetson/project-atlas-migration/stage28-recovery-coordination-20261027_215403-738388714/`.

## Implication
Any service restart saturates the CPU for ~6–7 s. During that window the dashboard and status API cannot be relied on
for safety evidence. The base's own CPU priority (`CPUWeight=1000`) is not enforced, because the user manager has no cpu
controller. A further attempt needs a decision that changes this condition. No attempt is authorised.
