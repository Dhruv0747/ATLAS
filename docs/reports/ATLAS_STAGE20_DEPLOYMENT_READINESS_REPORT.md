# Stage 20 deployment-readiness assessment — 14 October 2026

Later scope decision: [PUBLIC-only alternative](ATLAS_STAGE20_MINIMUM_SAFE_DEPLOYMENT.md)
is separately qualified and awaits owner approval. Private-checkpoint gaps below
are preserved, not declared fixed by public capture.

**NOT DEPLOYMENT READY. No production installation or restart approved/performed.**
This continuation builds on `cbe39269e29d23a9142c93fede5f1bacc73e7cc2`, not a
new localization investigation. GitHub had no newer working-branch commits at
both fetch checks. Source delivery SHA is identified in the final commit link.
Stage 21 was not started. Stage17B remains HOLD; B–E remain fidelity-blocked.

## Completed, with scope

- Known subscriptions created before synthetic producers; exclusive readiness
  marker distinguishes subscription creation from discovery/receipt/consumption.
- Real EKF consumption events before/after `processMeasurement`, actual relative
  reference creation, constructor and `reset()` events. Original mathematical
  expressions retained. Complete 15-state/225 covariance captured, not a full
  restart checkpoint.
- Separate version-pinned AMCL 1.1.20 overlay: actual initial-pose receipt,
  Gaussian particle initialization, accepted scan/TF, motion updates, pre-resample
  weights, resampling before/after, both sets, clusters, covariance, convergence
  and recovery averages. Full particles omitted from no-update/summary events;
  snapshot detail/truncation is explicit. No likelihood/RNG/selection changes.
- DDS startup races were demonstrated, not assumed away. Bounded event buffering
  and a read-only EKF bootstrap Trigger service retain its actual constructor
  event. Getter does not initialize/reset the filter. A late collector is still
  rejected by original monotonic creation time; other sequence gaps still fail.
- Consumer names are parameter aliases (`odom0_pose`, `imu0_twist`), not ROS topic
  names. Audit now resolves them using the actual captured parameter snapshot.
- Correct private shutdown order: stop producer, drain consumers, terminate
  private consumers, drain recorder, close/flush. Earlier interrupted pairs remain
  in preserved failed records.
- Deterministic comparator, predeclared statistical summary margins, missing-state
  rejection, checksums/crash audit, strict install identity guard, atomic file
  transaction and rollback rehearsal, one-shot future-boot approval gate.

## Native demonstration

Verified result directory:
`/tmp/atlas-stage20-complete-EW8kVA07/demo_f57afacb/`.
Private network/PID/device namespaces; domain187/local-only; read-only host root;
one writable scratch directory; no serial or motor devices. Source clones pinned:
robot_localization `8696ee5a9e4f959fcaae37835dcf2ed12ead581b` (3.5.4),
navigation2 `a097086719c88f781aa59788eca29ac6ca5e56db` (1.1.20).

Synthetic room, stationary wheel pose and gyro, separate original-library
observer with separate output TF, private simulated clock, wheel-first then gyro
after 0.5 s. These are declared fixture conditions, NOT production changes.

- Startup ledger audit: PASS, **2,734 consumed measurements**, no sequence gaps
  or unmatched consumed inputs, actual AMCL initialization/resampling phases.
- **609/609 unique reference samples matched**: maximum X/Y and yaw differences
  zero; maximum full covariance Frobenius-relative difference **0.089457%**.
  Gates 0.01 m/0.5°/1% unchanged. This is a stationary synthetic comparator pass,
  not full historical or moving replay fidelity. Comparator's TF-error argument
  was zero; full TF rejection/discard accounting remains unqualified.
- 914 wheel, 906 gyro, 407 scans; 12,636 recorded events plus receipt ledger.
- Native serialization/SQLite read-back and Stage19 bag-audit loader PASS. SQLite
  integrity OK, all five Stage19 input topics present; no backwards/duplicate
  source headers or stored receipt regressions. Bag SHA256:
  `4eaeef2b7a05912448ac198d80f31cc2df1da0fa25502e2df0888e13e0f16ec1`.
- Accepted map not used/replaced by the synthetic map. Original failure not
  reproduced; no correction candidate executed. All private children exited.

Earlier wall-time native fixtures intentionally remain FAILED: lost constructor/
initialization events, parameter-alias mismatch, shutdown-cut consumption pair;
parallel wall-time filters had identical X/Y/yaw but **3.223% covariance difference**
with only 81.9% matched reference coverage. Fixed input order AND controlled clock
were subsequently used together. This does not prove which caused the earlier
difference, and is not a before/after localization repair.

## New RNG finding — correct the earlier incomplete audit

`pf_alloc()` calls `srand48(time(NULL))`, but the same pinned version's
`src/pf/pf_pdf.c` has **static `pf_pdf_seed` and `srand48(++pf_pdf_seed)` in
Gaussian allocation**. Gaussian initialization therefore reseeds the shared stream
again. The earlier wall-seed-only explanation was incomplete. Do not assume each
cold start yields independent random particles.

Twenty separate synthetic AMCL process-start cases produced valid current poses
with max_particles=2000. Maximum observed step was **0.009146 m in every case**;
final-X standard deviation 0.000442 m, final-Y 0.001216 m, final-yaw 0.000301 rad,
published XY-standard-deviation mean 0.076634 m. Recorded run variation includes
scheduling and initialization effects; it is **not twenty independent RNG trials**
or evidence about the old five jumps. Gaussian allocation events and verified
process birth can constrain a future from-startup seed sequence; current RNG
state/draw progression and old allocation history are not exported/restored.
No seed was changed to manufacture stochastic variability.

Statistical comparator requires ≥20 runs per ensemble and predeclared margins:
mean jump count 1; maximum jump 0.10 m; parked drift/particle XY spread/published
XY uncertainty 0.05 m; heading span 2°; competing-hypothesis weight 0.05;
scan-fit proxy 0.02. Conservative approximate Welch mean-difference intervals
are tested on fixtures, not asserted valid for independent RNG samples here.
Jump-time equivalence, metric extraction and distribution/independence qualification
remain pending. Summary comparison always returns fidelity_verified=false.

## Measured resources — not full production overhead

66.58 s recorder runtime; 71.56 s whole demonstration:

- Collector including worker: 21.789 CPU s, **32.7% one core**, peak **74.88 MiB**.
- All child processes, including reference EKF/map server: 28.767 CPU s,
  about **40.2% one core / 6.7% six-core capacity**. This is total test-process
  CPU, not incremental observer overhead against an identical uninstrumented stack.
- Sum of individual child RSS peaks **197.04 MiB**: conservative upper bound,
  not a sampled simultaneous peak. No GPU benchmark claimed.
- Logical recording **22.19 MB**, approximately 0.333 MB/s; physical NVMe
  throughput/fsync latency unmeasured. Writer reports SQLite call time separately.
- Callback mean 0.421 ms, max42.04 ms; histogram p99 upper bound10 ms.
- Queue-to-SQLite-call mean7.291 ms, max121.80 ms; p99 upper bound50 ms.
- SQLite-write-call mean0.211 ms, max40.75 ms. Peak queue89,659 bytes, no
  application-reported drops. DDS loss is not thereby proven zero.
- Free storage395.15 GB. Host postflight CPU70.3%, RAM5473/7620 MB,
  temperature60°C. These snapshots are not attributable overhead measurements.

20-start AMCL test used 2000-particle configuration but did not collect a full
2000-particle sustained pipeline CPU/latency/retention benchmark. No claim otherwise.

## Failure and regression results

**46 current offline checks pass**, including 7 retained Stage20 contract checks;
39 new checks. The original 21 hook/recorder/writer checks remain prior successful
evidence: **67 unique scoped checks across both milestones**, not 67 newly run.
Native failure tests PASS: missing sensors remain incomplete; 64MiB quota rejects
70MiB retained logical evidence without deleting it; SIGKILL leaves an incomplete
capture; restart creates a new session and preserves the interrupted directory.
No physical disk was filled. Existing worker disk-full/queue-error tests are reused.

Atomic capsule tests verify checksum preflight, no approval/no writes, idempotence,
timestamped backup, rollback after injected failure, and refusal to overwrite later
user edits. These are scratch whole-file tests, not a complete Jetson live-package
activation/rollback rehearsal. No safety service was restarted.

## Package and live drift

Prepared tools: `stage20_package_manifest.py`, `stage20_install_guard.py`,
`stage20_package_transaction.py`, `stage20_production_gate.py`, and disabled
`stage20_capture.service.in`. No unit installed/enabled. Production capture path
defaults OFF, checks separate owner approval/readiness, exact map/config identities,
finite current-boot or one-shot future-normal-boot scope. Simulated-clock mode is
rejected for production. It never creates owner approval.

Actual built identity:

| Artifact | SHA256 |
|---|---|
| EKF r3 executable | `04868e817513373e7f33e61d62a33c0e27fd16c12d83141b7ff7a1bee161d1e3` |
| EKF r3 library | `7ffabcb2f3a5eb1ea02cefb7cbd622333c5d33a11ca4050d928b99e3ca97a4dc` |
| AMCL r3 executable | `fe4088f3044b8d7d2bce5490f2673a1e1fcd0b184e9682df909ea52aa43f625a` |
| AMCL r3 core | `d9ab64e639257f16c66b9127780119c5da429c64b5362d44a32dda5cb67857a2` |

Live EKF/nav/map SHA256 still equals Stage19 (full hashes in checkpoint report).
Live mission script SHA256 `0da12027fe1c0fcab79e19bb95b3e3d8e29868d2b285e5aafe51761a7205f86f`;
live seeder `db634ff08b6c8c0af4df16829bbf0047269afd31505f866c7a7e45345f6082ae`.
Neither contains this milestone's installed instrumentation. Mission drift predates
Stage20; do not replace it wholesale with GitHub's different implementation.
The final full source/binary/dependency/drop-in capsule is not yet assembled.

Future affected scope: optional collector unit; scoped EKF/AMCL diagnostic binaries
and their launch selection; seeder/mission default-OFF event hooks. Never globally
replace `/opt/ros` libraries or override motor/mux/E-STOP units. A future approved
boot can exercise capture; no reboot/restart should be done just to create evidence.

## Remaining gates — do not silently waive

1. Complete native reset/set-pose reinitialization, backward-clock, parameter-change
   and diagnostic-publication-failure coverage. `reset()` hook does not yet cover
   every internal/manual reinitialization path such as `setPoseCallback`.
2. Verify complete real user-unit ordering graph with systemd, including collector
   startup failure. Synthetic DAG tests are not actual systemd-cycle validation.
   Template has no Requires/Wants from E-STOP/base/mux; do not add such dependencies.
3. Qualify uncontrolled/moving native equivalence and full-config rates/2000-particle
   latency, sustained RSS and retention. Controlled static fixture is insufficient.
4. Finish statistical timing/distribution contract accounting for Gaussian reseeding;
   do not use the 20 cases as independent stochastic fidelity evidence.
5. Assemble exact live-based hooks/drop-ins and all required libraries, hashes,
   dependency pins, executable installation/activation/rollback packet; rehearse it
   in isolation, including partial writes/permissions/unit startup failures.
6. Revalidate latest collector endpoint-history/known encoder/control subscriptions
   natively; they were added after the successful full demonstration.

**BUILT / TESTED OFFLINE / NATIVE ROS VALIDATED: scoped tools and fixtures above.
DEPLOYMENT READY: NO. DEPLOYED: NO. LIVE CAPTURE VERIFIED: NO.
REPLAY FIDELITY VERIFIED: NO. LOCALIZATION FIX VERIFIED: NO.**

E-STOP postflight remained latched, final velocity zero, Nav2/explore inactive.
No production install/restart/reboot/seed/steering/motor operation occurred.
No new drive is requested. No installation approval is requested while these
gates remain open. Continue Stage20, not Stage21, from this verified checkpoint.
