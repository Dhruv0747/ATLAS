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

## 4. Test environment (isolated; cannot reach ATLAS)

- x86-64 cloud workstation, 2 cores. RoboStack Humble: **Python 3.12 + rclpy 3.3.21** (the Jetson's exact rclpy;
  authoritative for correctness) and **Python 3.10 + rclpy 3.3.7** (the Jetson's interpreter version, for timing; a
  one-class `TimerCancelledError` shim is applied identically to every variant).
- Every ROS run is in a private network namespace with only a loopback interface (the wrapper refuses to start
  otherwise), ROS domain 216 (213 for the reused repository suite). No Jetson connection during any test.
- Not the Jetson: ARM64 cores are slower and the absolute numbers below are x86 numbers.

## 5. Measured CPU-time and wall-time comparison

### 5.1 Operation level — one executor wait cycle (`bench_cycle.py`)

Node shaped like `atlas_web_status` (84 String subscriptions + their 86 QoS-event waitables). Executor-thread CPU
(`thread_time`) per cycle; 10 alternating AB/BA pairs × 1,500 cycles per cell. All pairs reported.

| Interpreter | Cycle | Live CPU/cycle | V1 CPU saving, median [range] | Pairs better | V1 wall saving, median |
|---|---|---:|---|---:|---:|
| 3.10 | idle (full rebuild, timeout) | 622 µs | **8.5%** [−2.6 … 18.9] | 9/10 | 8.0% |
| 3.10 | one message dispatched | 684 µs | **6.6%** [−0.5 … 21.6] | 9/10 | 9.8% |
| 3.12 | idle | 445 µs | **6.9%** [−10.3 … 17.7] | 7/10 | 7.5% |
| 3.12 | one message dispatched | 498 µs | **10.3%** [−8.0 … 22.6] | 9/10 | 9.7% |

Rejected in the same runs: V2 (identity-set membership) −2.6 … +6.3% median, 4–8/10 pairs — not robust, dropped.

### 5.2 Application level — the exact live `atlas_status_web.py` (`bench_dashboard_app.py`)

The live Dashboard file (`acb9fe18`) and its byte-identical sibling modules are imported, which starts the real
two-node ROS layer (HTTP server not started); only the executor overlay differs (live `543e4112` vs V1 `4f5c1cc9`,
adapter integrity check active). The existing `bench_status_executor.py` replays the Dashboard's topics at the
rates measured live on 2026-10-11 plus `/tf` at 10 Hz. Fidelity: **68 keys at 252 messages/s**, matching the
audit's live 67 keys / 250 Hz. Each run is a fresh process: 5 s warm-up, 30 s measured; 12 alternating pairs per
interpreter; the publisher is shared and identical for both arms.

| Interpreter | Measure (% of one x86 core) | Live mean | V1 mean | Paired saving, median [range] | Pairs better |
|---|---|---:|---:|---|---:|
| 3.10 | both executor threads | 19.61 | 18.44 | **5.6%** [1.2 … 11.1] (1.11 pts) | **12/12** |
| 3.10 | control thread / status thread | 15.20 / 4.41 | 14.38 / 4.05 | 4.5% / 8.5% | 12/12, 12/12 |
| 3.10 | whole process (incl. DDS threads) | 21.54 | 20.43 | **5.1%** (1.08 pts) | 12/12 |
| 3.12 | both executor threads | 17.96 | 16.84 | **6.4%** [2.6 … 9.2] (1.18 pts) | **12/12** |
| 3.12 | control thread / status thread | 14.01 / 3.96 | 13.15 / 3.69 | 6.6% / 6.5% | 12/12, 12/12 |
| 3.12 | whole process | 20.03 | 18.94 | **5.1%** (1.03 pts) | 12/12 |

Behaviour, same runs (both arms):

| Check | Live | V1 |
|---|---|---|
| Delivered messages/s, py3.10 / py3.12 | 252.30 / 252.42 | 252.36 / 252.38 |
| Updating keys; identical key set every pair | 68; — | 68; yes (24/24 pairs) |
| `web_error` (executor failure flag) | none | none |
| Hot probe `/atlas/control_policy` latency, median p50 / median p95, py3.10 | 0.56 / 2.21 ms | 0.56 / 2.13 ms |
| Cold probe `/atlas/health` latency, median p50 / median p95, py3.10 | 1.39 / 4.16 ms | 1.32 / 3.99 ms |
| Same probes, py3.12 | 0.51 / 1.93; 1.14 / 2.60 ms | 0.47 / 1.83; 1.04 / 2.75 ms |
| Drive-watchdog / camera-tick timers (0.1 s), median period | 100.0 ms | 100.0 ms |
| Map-pose timer (0.5 s), median period | 500.0 ms | 500.0 ms |

Worst single observations (one sample in ~3,600) move in both directions between arms and interpreters (hot probe
max: 3.10 live 69.2 / V1 29.1 ms; 3.12 live 62.5 / V1 66.4 ms; timer max gap: 3.10 live 194.6 / V1 156.9 ms;
3.12 live 176.0 / V1 193.2 ms). They are dominated by the 2-core host and **no worst-case improvement or
regression is claimed**.

### 5.3 What this does and does not mean for the Jetson

- **Operation level:** ~7–10% less executor CPU per wait cycle. **Application level:** ~5–6% less executor-thread
  CPU for the real Dashboard ROS layer under live-rate traffic, consistent in 24/24 pairs on two interpreters.
- **Not measured on the Jetson.** If the same *relative* saving held there, the Dashboard's two executor threads
  (25.00% + 12.40% of one core in the ranked capture) would drop by roughly 2 points of one core, i.e. about
  **0.35–0.4 percentage points of whole-Jetson (6-core) CPU**. That is an extrapolation, not a result.
- **It does not by itself create Astra 3D-preview headroom.** Recorded whole-Jetson baselines are ~71–75% average
  with 1-s peaks above the unchanged 75% guard. This candidate removes one verified, avoidable cost; it is not a
  claim that the camera guard will now pass.

## 6. Correctness results (both overlays; V1 must behave like live)

| Suite | Environment | Live `543e4112` | V1 `4f5c1cc9` |
|---|---|---|---|
| `test_dashboard_exitstack_ros.py` (14): 84-sub ordered delivery; handle enter/exit balance across timeouts, dispatch, abandoned generators; callback exception propagation + recovery; subscription destroy/recreate while spinning in another thread; dynamic/cancelled timers; guard condition; service/client; incompatible-QoS events both sides; deadline-missed events; executor shutdown and context shutdown from another thread; cancelled task not executed; mutually-exclusive vs reentrant groups (MultiThreadedExecutor); ExitStack equivalence (3,000 random scenarios) and generator close | py3.12/rclpy 3.3.21 | 12 pass, 2 n/a | **14 pass** |
| same | py3.10/rclpy 3.3.7 | 12 pass, 2 n/a | **14 pass** |
| Repository native suite re-run on live vs candidate (`test_dashboard_exitstack_native.py` → `test_executor_qos_shutdown_native.exercise`): incompatible QoS, deadline, shutdown during callback, context shutdown while waiting, entity churn while spinning | py3.12/rclpy 3.3.21 | 5 pass | **5 pass** |
| same | py3.10/rclpy 3.3.7 | not runnable (suite has no `TimerCancelledError` shim for 3.3.7) | — |
| `test_dashboard_exitstack_package.py` (8): candidate == generator output; only `OVERLAY_SHA` changes in the adapter; originals byte-identical; checksums; deterministic build; wrong inputs fail closed; install script refuses without approval and refuses a changed `atlas_status_web.py`; ExitStack equivalence (4,000 scenarios, no ROS) | system Python 3.13 | — | **8 pass** |
| HTTP surface of the imported live module (`http_check.py`), GET only | py3.12 | `/api/status` 200, `/api/estop/state` 200, `/v2` 200 (23,654 B white-glass), `/` 200, `/api/diagnostics` 200 | **identical codes, sizes and key sets** |

Failures encountered and fixed during this work (none in the candidate): a test helper used the wrong
`NumberOfEntities` keyword (affected both overlays identically); the isolation wrapper initially lacked `ip`, so
the loopback stayed down and only single-process tests delivered; the benchmark tree initially lacked
`tools/vision3d` and `web/`. All re-run after fixing.

## 7. Features and safety behaviour preserved

Unchanged files: `atlas_status_web.py` (still `acb9fe18`), voice and its executor overlay, white-glass assets,
E-STOP/reset logic, motor/steering/STM32, maps, EKF/AMCL/Nav2, Pi Camera, Vision Lab, Test Labs. Unchanged
behaviour (tested): QoS-event delivery and failure reporting, callback delivery/order, lifecycle (add/remove/
destroy), cancellation and shutdown, callback-group exclusivity, timer cadence (drive watchdog), HTTP/control
surface. Production guards (CPU 75% / RAM 80% / 70 °C, 4-s viewer lease, ROS domain 77, depth/IR settings,
calibrated-cloud restriction) are untouched — this change is inside the Dashboard process only.

## 8. Package and rollback

Builder: `tools/diagnostics/dashboard_executor_bookkeeping/build_package.py` (offline; hash-pinned inputs).
Package directory `project_atlas/tools/deploy/dashboard_exitstack_pkg/` (SHA256SUMS file `934a236e5fd856980033ff7ee8b9cc60f7d9f943091cc748076cd68aec26039d`, script `c02326cb…`, manifest `03359786…`): `install/` (2 files), `original/` (2 live files), `manifest.json`,
`SHA256SUMS`, `dashboard_exitstack.sh`.

`dashboard_exitstack.sh`
- `check` — read-only: package checksums, live pre-hashes, `atlas_status_web.py` unchanged.
- `apply` (`OWNER_APPROVED=yes` only) — refuses unless E-STOP latched, no Astra/Vision Lab camera process and exact
  pre-hashes; verified backup `~/project_atlas/.pre_dashboard_exitstack_<stamp>`; passive 1 Hz `/proc` recorder
  20 s before; atomic install of the 2 files; restart **rover-status-web only**; settle (5 consecutive 1-s samples
  ≤ 75% within 120 s; the known restart transient is recorded, not hidden); then checks installed hashes, E-STOP,
  manual-only + stop latched, LiDAR/odom/IMU/encoder/cmd_vel freshness, no `web_error`, ≥ 40 fresh status keys,
  9 protected service identities unchanged, Pi Camera / `/v2` / `/v2/vision3d` / `/api/vision3d/summary` 200,
  static white-glass assets hash unchanged, `atlas_status_web.py` unchanged. **Any failure → automatic rollback**
  (originals restored, one more web restart).
- `rollback` (`OWNER_APPROVED=yes`) — restores the 2 files from the recorded, checksum-verified backup and restarts
  rover-status-web once.

Manual rollback (equivalent): copy `original/atlas_dashboard_executor_impl.py` and `original/atlas_dashboard_executor.py`
over `/home/jetson/project_atlas/scripts/`, verify `543e4112…` / `2b6ceeae…`, restart rover-status-web.

## 9. Remaining evidence gaps

1. No ARM64/Jetson measurement: the relative saving on the Jetson's Python 3.10 + rclpy 3.3.21 + Cortex-A78AE is
   expected but not shown. The only way to show it is the approved deployment's matched before/after window.
2. Python 3.10 timing used rclpy 3.3.7 natives (3.3.21 is not packaged for 3.10); 3.12 used the exact rclpy.
3. The workload is the 2026-10-11 rate table (validated then against the live process); current rates may differ.
4. Telemetry (`yahboom_base.py`) has the same bookkeeping pattern on the stock executor; not addressed (motor
   keep-alive path; would need its own overlay adoption and validation).
5. Whole-Jetson headroom for the Astra preview remains unresolved; this candidate is worth ~0.4 points at most by
   extrapolation.

## 10. Approval request (separate; nothing is installed)

Requested decision: deploy this 2-file package with ONE monitored `rover-status-web` restart and automatic
rollback, followed by a matched parked before/after Dashboard CPU window — ATLAS stationary, E-STOP latched, no
camera start, no recording, no motion, no other service touched. Not requested: any camera session, guard
change, telemetry change or retry.

Reproduction (workstation only): see `tools/diagnostics/dashboard_executor_bookkeeping/` — `prepare_variants.py`
(variants from the live overlay), `run_iso.sh <env> bench_cycle.py '<json>'`, `make_tree.sh` +
`run_iso.sh <env> bench_dashboard_app.py driver …`, `sum_op.py`, `sum_app.py`. Raw result JSON is kept privately,
not committed.
