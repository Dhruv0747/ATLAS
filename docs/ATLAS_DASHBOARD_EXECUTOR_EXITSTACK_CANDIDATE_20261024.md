# Dashboard executor: per-cycle ExitStack removal — offline candidate

**Status: OFFLINE CANDIDATE, NOT DEPLOYED.** No production file, service, camera, motor, steering, map,
navigation or safety setting was touched. Live access in this work was read-only file copies (hash-verified).
Deployment needs a separate owner approval (section 9).

## 1. Starting point (saved evidence only; nothing re-profiled)

| Evidence | SHA256 | Re-verified |
|---|---|---|
| Dashboard GIL profile `evidence-qd0qjjcr/python-gil.json` (107 samples) | `bec0cdfb…16d7ab` | yes |
| Telemetry GIL profile `evidence-r8sg2x3q/python-gil.json` (52 samples) | `0b42ad72…7075c` | yes |
| Live `scripts/atlas_status_web.py` | `acb9fe18…55d7439` | yes (read-only copy) |
| Live `scripts/atlas_dashboard_executor_impl.py` | `543e4112…81b5c1` | yes |
| Live `scripts/atlas_dashboard_executor.py` | `2b6ceeae…de4eed389f11ab` (≡ repository) | yes |
| Live `scripts/yahboom_base.py` | `c551be00…e560141` | yes |
| Live rclpy | `ros-humble-rclpy 3.3.21` (`executors.py` `e8545919…`) | yes |

py-spy ran at 20 Hz for 10 s (200 opportunities) recording only GIL-holding samples, so 107 Dashboard samples
≈ 53% of one core of GIL-held Python and 52 telemetry samples ≈ 26% — consistent with the ranked native capture
(41.75% / 26.91% of one core). This is a consistency check, not a new measurement.

## 2. Verified cause versus remaining hypotheses

**Verified (profile + exact source + offline measurement):**

1. The Dashboard's Python time is dominated by executor wait-set bookkeeping, not callbacks.
   `atlas-web-status-spin`: 37 of 38 samples inside `_wait_for_ready_callbacks`, ~1 in a callback.
   Control `_spin`: 38 of 61 in bookkeeping, 15 in callbacks (TF, joystick, odometry).
2. The deployed overlay is stock Humble `rclpy/executors.py` plus two small earlier changes (task-cancellation guard,
   direct count sums). Every wake rebuilds a wait set over every entity of the node. The status node has ~84
   subscriptions and, because Humble attaches a default incompatible-QoS event handler to every publisher and
   subscription, ~86 QoS-event waitables: ~170 entities walked per wake for (typically) one small message.
3. Within that cycle, **`contextlib.ExitStack` is pure Python bookkeeping around cheap native `__enter__/__exit__`
   calls** (contextlib frames: ~13 of 38 status-thread samples and ~11 of 61 control-thread samples, inclusive;
   ~30% of the cycle in an offline cProfile ranking). The native enter/exit calls themselves are necessary (they stop a
   handle being destroyed while it is in the wait set); the ExitStack wrapper (per-entity `enter_context`,
   `_push_cm_exit`, closure creation, deque, Python-level unwinding) is not.

**Remaining hypotheses (NOT established):**

- The post-wait `wt in waitables` list scan is O(W²). Replacing it with a per-cycle identity set (V2) gave
  inconsistent results (median −2.6% … +6.3%, 4–8 of 10 pairs better): **not supported; dropped**.
- QoS-event per-cycle work (`add_to_wait_set`, `is_ready`, `get_num_entities`) is real cost but necessary for QoS
  failure reporting; not removed (owner constraint and correctness).
- Telemetry (`yahboom_base.py`) shows the same pattern on the **stock** executor (32/51 bookkeeping samples,
  QoS `add_to_wait_set` 7, `NumberOfEntities.__add__` 5, `publish` 8 real work). It does not use the Dashboard
  overlay; applying the same change there would touch the motor keep-alive path and needs its own validation.
  Not part of this candidate.

## 3. The change (smallest evidence-based candidate)

Only `atlas_dashboard_executor_impl.py` changes, inside `_wait_for_ready_callbacks`:

- `with ExitStack() as context_stack:` → `entered_handles = []` + `with _EnteredHandles(entered_handles):`
- each of the 7 `context_stack.enter_context(X)` → `_h = X; _h.__enter__(); entered_handles.append(_h)`
- new 30-line `_EnteredHandles` class: on leaving the block, exits every entered handle LIFO with ExitStack's
  exception semantics (all exits run; an exception raised by an exit replaces the active one; a true return
  suppresses). Plus `import sys`.

Unchanged: which entities are entered, their order, `InvalidHandle` skipping, wait-set construction and contents,
QoS events, readiness checks, yield order, timeouts, shutdown exceptions, callback groups, task cancellation.
**No state is kept between wait cycles** (unlike the rejected static-cache approaches). The adapter
(`atlas_dashboard_executor.py`) changes only its `OVERLAY_SHA` line, so its integrity check stays active.
`atlas_status_web.py`, voice, white-glass assets and every other file are untouched.

| File | Live SHA256 | Candidate SHA256 |
|---|---|---|
| `atlas_dashboard_executor_impl.py` | `543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1` | `4f5c1cc92c3ed156d68e0663639396be0c01f3d8b71c15f4fb4a98ea6521d9a8` |
| `atlas_dashboard_executor.py` | `2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab` | `6c82a00d3453334348a542da32115525d79ef77bc2cd8cec516d7edc45289a1c` |

RESULTS_PLACEHOLDER
