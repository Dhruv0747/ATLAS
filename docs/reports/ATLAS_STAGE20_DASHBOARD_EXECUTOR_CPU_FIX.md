# Stage 20 dashboard executor CPU decision — 2026-10-14

## Decision

**Targeted optimization rejected on present evidence.** Executor CPU consumption is measurable, but an avoidable executor defect is not confirmed. No runtime correction, deployment, restart, rate change, QoS suppression, or Stage 20 installation was performed. Stage 17B remains HOLD. Autonomy was not activated.

Status: diagnostic analyzer **TESTED OFFLINE**. Runtime **FIXED IN SOURCE**, **CPU IMPROVEMENT VERIFIED**, **DEPLOYMENT READY**, and **DEPLOYED** do not apply to this investigation.

## Exact evidence and interpretation

Used the owner's existing `/tmp/atlas_dashboard_cpu_30s.txt`, not another sampling run: 598 weighted samples; 299 status-executor call paths, 294 main-executor paths, 5 other. 566 samples include the wait generator; 457 end in it across all lines. Specifically 419 end at line 678 (70.1% of all samples).

Installed `rclpy/executors.py` SHA256:
`e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010`.
Line 677 calls native `wait_set.wait(timeout_nsec)`; line 678 checks shutdown. Thus the dominant line is a wait-return boundary, not evidence that rebuilding consumes 70.1% CPU. With the verified source mapping, inclusive samples comprise 107 construction, 420 wait-return boundary, 31 readiness, 8 other. These are samples, **not CPU-time proportions or rebuild counts**.

QoS event add/enter/exit operations appear in the samples. Their presence does not prove event storms. Default incompatible-QoS handlers provide useful warnings; removing them would change diagnostic behavior. Native waiting, GIL reacquisition and sampling line attribution remain competing explanations for the dominant boundary, not verified root causes.

The collapsed file has no Linux TID identifiers. `_spin` and `_spin_status` identify Python call paths; they cannot reliably be assigned to TID 5408/5580 from this file alone. Wait-set rebuild frequency, guard wakeup counts, useful-work/wakeup ratio, native CPU time and GIL contention cannot be recovered from these samples. No busy-loop claim is justified.

## Live architecture audit

Examined exact live dashboard SHA256:
`1be48aa972bdf79f66f22d1e2cd0da3da3f8e35ef58604e26e437be831bdc716`.
Main executor origin is live line 663; status executor line 437. There are 103 explicitly declared constant-topic subscriptions: 21 main and 82 status, with no duplicate topic names. This is not the complete runtime entity count: dynamic camera subscriptions, TF internals, automatic parameter services, clients, publishers and their waitables are additional. Three declared timers remain on main: drive watchdog, map pose, camera subscription management. No redundant subscription correction was found. Existing camera-idle management, caches and the two-executor isolation must be preserved.

## Bounded measurement, not lifetime ps percentages

One read-only `/proc` thread CPU interval over 30.0339 seconds for PID 2088, with process-start identity protection:

| Measurement | Result |
|---|---:|
| TID 5408 | 26.370% of one core |
| TID 5580 | 12.786% of one core |
| Sum of observed thread deltas | 42.552% of one core |
| End-snapshot whole Jetson CPU | 68.7% |
| End-snapshot RAM | 5401 / 7620 MB, 71% |
| End-snapshot temperature | 58 C |

Summed thread deltas are a process estimate, not a whole-machine percentage and not an independent process-counter benchmark. End snapshots are not interval means/p95/peaks. Prior unchanged 600-sample baseline remains mean 70.03%, p95 75.72%, max 81.93%, with 37/600 samples above 75%. A favorable endpoint does not clear admission.

At interval end, policy reported STOPPED, stop_latched=true, commissioning unarmed, age 0.1s and observed callback rate 10.01Hz. Command was zero linear/angular, age 0.2s, observed rate 4.71Hz. Encoder telemetry was approximately 10Hz, age 0.1s; dashboard LiDAR field 1.85Hz, age 0.4s; map-pose field 2Hz, age 0.2s. These are dashboard field observations, not certified source sensor rates or callback execution latency. No physical E-STOP latency test was performed.

Interval evidence retained at `/tmp/atlas-dashboard-cpu-ZWJhPgy7/dashboard_executor_interval.json` and local ignored artifacts. Raw logs are not committed.

## Changes and tests

Added a read-only collapsed-profile analyzer with source-hash-gated line classification; it refuses to infer CPU duration or TIDs from untagged samples. Five tests pass: weighted paths/leaf counts, source-identity gating, inclusive versus leaf distinction, invalid counts, empty input. Existing six executor-split regressions pass: **11 total**. These are offline/static tests, not live safety certification.

No runtime patch was justified. Before/after CPU, callback latency, HTTP response latency, RAM and temperature comparison is **N/A**, not zero-cost or improved. Measured production savings: **none demonstrated**. Prior JSON microbenchmark findings are separate and are not executor savings.

## Deployment and rollback

Live-source patch identity: none. Production file is preserved at the hash above; do not replace it with the repository version containing undeployed Stage 17B changes. No live backup or rollback directory was created because no production mutation occurred. No rollback is needed for this analysis-only commit. The analyzer runs only when explicitly invoked; it installs no service.

Any future justified patch needs an exact-live-source minimal diff, hash verification, timestamped backup, restoration command and dashboard-only restart approval. Existing production services, control authority, maps and calibration must remain protected. No such approval is implied here.

Stage 20 remains blocked with unchanged CPU 75%, RAM 80%, temperature 70 C and free-space 2 GiB limits. This investigation does not establish active-recording headroom.

## Next necessary action and commit provenance

Close the speculative executor rewrite: do not add sleeps, suppress QoS or repeat the same sampling experiment. The next optimization must target a demonstrated avoidable cost in existing whole-process evidence; if none exists, report insufficient headroom rather than force installation. Discriminating executor work would require per-wakeup work/native-time attribution, which this profile cannot supply; it is not evidence for a runtime fix now.

The exact analysis commit is obtainable with `git log -1 --format=%H -- ATLAS_STAGE20_DASHBOARD_EXECUTOR_CPU_FIX.md`; the delivery message supplies its immutable GitHub URL. This report cannot embed its own commit hash without changing that hash.
