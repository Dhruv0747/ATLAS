# Stage 20 — minimum safe public capture option

14 October 2026, IST. Continuation from `ad2f1025d394ff0d14068522b829c52acbfef52e`.
Latest working-branch fetch contained no newer developer commits. Earlier evidence
and failed experiments remain preserved. No Stage21, dashboard, drive, calibration,
map, estimator restart, reseed, E-STOP release or autonomy change occurred.
Verified implementation commit: [`aa0bb06cde7cdabdbf80ae382024e8954173efb1`](https://github.com/Dhruv0747/ATLAS/commit/aa0bb06cde7cdabdbf80ae382024e8954173efb1).
Final report/manifest delivery commit is identified in the GitHub handoff.

## Decision and exact status

The **lower-fidelity PUBLIC-ONLY sidecar** is qualified for separately approved,
stationary, supervised installation/activation. This is the less-invasive option
per the owner's section4, **not completion of the full EKF/AMCL checkpoint objective**.
It reuses the existing recorder's topic list, SQLite sink and bounded worker.
Neither estimator binary overlay nor seeder/mission hook is in this capsule.

| Status | Public-only capsule | Private checkpoint / localization correction |
|---|---|---|
| BUILT | Yes | Earlier scoped prototypes only |
| TESTED OFFLINE | Yes | Earlier scoped tests only |
| NATIVE VALIDATED | Rates, raw CDR, bounded runtime, adapter and scratch transactions | Not complete production equivalence |
| DEPLOYMENT READY | **Yes, PUBLIC partial scope only; approval still required** | **No** |
| DEPLOYED | No | No |
| LIVE CAPTURE VERIFIED | No | No |
| REPLAY FIDELITY VERIFIED | No | No |
| LOCALIZATION FIX VERIFIED | No | No |

Do not use the public qualification to approve a private overlay or claim the old
five jumps were reproduced/fixed. If the owner requires the actual private
checkpoint now, do not deploy this substitute as though it supplies that evidence.

## A/B/C classification — no safety downgrade

| Remaining requirement | Class / justification | Disposition |
|---|---|---|
| Real startup ordering; safety independence; crash/failure isolation | A: collector must not delay or control safety/localization | Actual 530-unit graph checked; no reference to this collector. No Install section, Wants/Requires, consumer Before/After, restart or autostart. Native parser passes. |
| Finite CPU/RAM/tasks/disk/runtime; retention and termination | A: resource exhaustion can affect control | 120s capture, 150s service limit, 25s stop, kernel CPU75s lifetime, memory192MiB/tasks48, nice15; reserve/quota/crash tests pass. |
| Receipt/payload integrity, topic types, timestamp provenance, incomplete flags | A: do not misrepresent lost/incomplete evidence | Raw CDR path, SHA ledger, native audit and explicit missing/private-state flags pass. DDS loss remains unmeasured in live deployment. |
| Immutable live baseline, exact package, approval, atomic install/rollback | A: protect drifted live files and recover safely | Full hashes, pinned dependencies, new private payload directory, native scratch rehearsal and real transient failure -> rollback pass. |
| EKF/AMCL overlays' runtime/math/reset/setPose/backward-time/publication-failure coverage | **A if those overlays are deployed**; cannot call these merely research | **Not shipped. Still blocks overlay deployment.** |
| Actual full EKF state/cross-covariance/relative anchor and consumer order | B for this public-only alternative; otherwise essential private evidence | Explicitly unavailable; public odom blocks are not full 225-element covariance. |
| AMCL RNG/history/weighted clusters and deterministic/stochastic replay contracts | B: necessary for faithful historical comparison, not safe read-only receipt | Deferred, not waived; published particle clouds do not restore RNG. |
| Moving native equivalence | A for algorithm-changing/replacement binaries, B for unchanged public subscriber | No binary replacement. No moving-fidelity assertion. |
| Automatic future-boot ordering; dashboards; additional exports | C for this manual finite alternative | Deferred. Public-only package cannot guarantee before-first-source startup capture. |

The original remaining gates were not all made optional. They were removed from
the **deployment scope** where the risky overlays/hooks are absent, and remain
explicit blockers for those components. Safety thresholds and B–E fidelity gates
were not relaxed.

## New defect actually fixed

At conservative synthetic rates the old object subscription path received only
173–175 of 1500 messages on fast channels, and 170 of300 scans/clouds. Application
drop counters were empty. This demonstrated that empty counters do not prove
complete delivery; no production failure is attributed to this diagnostic defect.

The collector now subscribes with `raw=True`, preserves original serialized CDR
and hashes it without converting/re-serializing 2000 Python particle objects.
Standard Header/first-TF stamps are checked against native deserialization.
Unsupported/no-header types retain null source stamps; a first-TF stamp is not
misrepresented as the timestamp of the entire TF array. No scan range or sensor
payload is filtered or rewritten.

## Scope: what this first capture can and cannot answer

| Evidence | Public sidecar |
|---|---|
| Raw M1–M4 counts, exact encoder update, wheel odom, raw/corrected IM10A, EKF output, scans, TF, commands, policy, steering commands | Capture where published; missing channels explicit. Steering remains commanded, not measured. |
| Public initialpose/AMCL lifecycle events and parameter changes | Subscribe/read; absent history remains absent. Does not issue initial poses or call no-motion/update services. |
| Parameter snapshot, discovered publisher/QoS identity, receipt/source/monotonic times | Captured/read-only; discovery and receipt are not consumption proof. |
| Particle cloud output | Available when published, not pre-resampling/internal/RNG state. |
| Actual EKF initialization, relative wheel reference, full cross-covariance, measurement consumption | **Not available** without qualified internal instrumentation. |
| Complete startup/service history or reproducible historical checkpoint | **Not available. Flags remain false.** |

Public-only mode never requests the internal bootstrap service. List/GetParameters
are read-only; no SetParameters, ROS control publisher, serial/GPIO access or
control HTTP POST exists in this entrypoint. It cannot independently solve the
Stage19 missing-private-history barrier; its added value over prior bags is raw
receipt/payload proof, fresh parameter/publisher identity and bounded provenance.

## Native results and resources

Resource case: `/tmp/atlas-stage20-complete-EW8kVA07/public_dce7a496/`.
Private PID/network/device namespaces and synthetic sources; no production DDS,
controllers or actuator devices. Temporary test units, not production services,
were started and automatically collected. Their CPU includes fixture costs.

- Full120s collector test, 110s traffic. 50Hz wheel/EKF/IMU/raw encoder/control/TF,
  10Hz two1080-ray scans and 2000-particle clouds/poses.
- **97,901 synthetic source messages received exactly** (plus26 metadata events).
  Each fast channel5500/5500; each slow channel1100/1100; static TF1/1.
  195,854 sample+receipt SQLite writes; zero application drops/worker errors.
- Collector CPU63.8094s / wall120.06595s = **53.14% one core**, approximately
  **8.86% six-core capacity**. This is a deliberately conservative synthetic load,
  not a measured increment in production navigation CPU.
- Collector peakRSS **76.66MiB**; peak queue467,695bytes; logical output197.72MB
  (~1.65MB/s across120s). Free storage394.63GB after the run.
- Callback mean0.271ms/max55.57ms; histogram p99 upper5ms. No exact percentile
  beyond the histogram claimed. Physical NVMe/fsync throughput remains unmeasured
  because private `/proc/self/io` is unavailable; logical bytes are not physical writes.
- Native CDR audit on the 40s qualification case: **26,727 exact sample/receipt
  pairs**, **8,701 source headers/first-TF stamps** verified, no mismatched hash,
  sequence, or receive timestamp. That audit was not falsely labeled as auditing
  every message in the separate120s case.
- Current read-only parked check: E-STOP latched, command zero, CPU71.6%, RAM73%,
  temperature59°C. Those snapshots are not before/after attributable overhead.

**Important kernel/platform findings:** `CPUQuota=60%` is not enforced because
the user's cgroup lacks the CPU controller file. We do not claim a hard rate cap.
Actual memory.max201326592 and pids.max48 were read. The full native test inherited
actual kernel RLIMIT_CPU `[75,75]`. Runtime and total CPU are bounded; instantaneous
CPU is not guaranteed below60%. The service uses nice15 and headroom checks.

The requested PrivateDevices/ProtectSystem/ProtectHome user-service sandbox trial
failed before ROS with status218 (capability drop denied). Those unsupported
directives are **not** shipped or claimed. NoNewPrivileges and kernel resource
limits passed a native bounded process/capture test. The public collector is not
an OS-enforced read-only filesystem sandbox in production: trusted hash-verified
code/output-root/approval restrictions provide that scope. Private test sandboxes
remain namespace-isolated. This difference is an explicit remaining risk.

## Mandatory gate results

- Actual graph:530 loaded units, selected EKF/localization/base/mux/remote included.
  Reverse safety dependencies, consumer ordering edges and autostart are rejected.
  Native `systemd-analyze --user verify` passes the exact candidate unit. This is
  not a production boot test; no boot/order change is proposed.
- Native public production adapter ran against a namespace-bound **fake** project
  root and local HTTP safety fixture: single-use grant, fixed output root/profile,
  missing sensors, honest unavailable private state and graceful SIGTERM pass.
  A second use is refused before another session. No real approval was created.
  Final frozen v4 payload entrypoint passed in `adapter_fake_project_03`;
  runtime hashes cover all nine payload files.
- **65 current offline tests pass**, including retained Stage20 checks and new
  public gates, raw stamps, installation/qualification and fresh-headroom checks.
- Native missing-sensor, quota (64MiB root with retained70MiB), SIGKILL/incomplete
  detection and unique restart/evidence preservation regressions pass on raw code.
  No real disk was filled. Existing worker error tests are reused.
- Scratch capsule install/default-OFF and injected health failure rollback pass;
  exact unit is parsed natively. A real uniquely named transient `/bin/false`
  service failure also reaches the scratch installer's rollback branch. Manager
  daemon-reload and the scratch unit path remain mocked: production activation
  was not performed. Successful protected native capture uses a separate transient
  unit, not the production approval file/installed unit.
- Existing SQLite sink/queue quotas retained. Loss/type/storage failure stops only
  the collector and returns failure. No restart/autostart; used grant prevents
  blind retry. Crash evidence remains incomplete, never repaired/deleted.
- At least1GiB disk reserve during capture; at least2GiB install preflight.
  Global owned-session quota500MiB, worker8MiB and finite runtime; no automatic
  eviction. Quota refusal may require a separately approved evidence archive later.

## Package, drift and rollback

Capsule builder: `stage20_public_package.py`; default readiness OFF. Separate
qualification record `ATLAS_STAGE20_PUBLIC_QUALIFICATION.json` is PUBLIC scope
only, not an installation/activation approval. Source delivery SHA and exact
target hashes are in the companion capsule manifest/final GitHub link.
Final v5 native capsule: `/tmp/atlas-stage20-complete-EW8kVA07/public_capsule_v5/`.
PC capsule: `artifacts/stage20_public_capsule_v5/` (generated output not committed).
v5 updates only the qualification's final native-adapter evidence pointer; all
runtime payload and installer hashes are identical to natively exercised v4.
Its MANIFEST.json SHA256:
`8f805a9958291a9ed685aeb0fe6a4fa5a662b3bdf8c73dfbdcec3935449b7e32`.
The committed companion preserves its JSON contents; newline normalization may
make its byte hash different. No binary payload is shipped: `binary_overlays=[]`.

Targets are nine **new** files under `tools/stage20_public/` and one previously
absent `~/.config/systemd/user/atlas-stage20-public-capture.service`. Existing
unit collision aborts. No `/opt/ros` executable/library, live recorder, motor,
mux, map, EKF/nav YAML, mission or seeder file is replaced. Installer helpers are
hashed in the capsule but are not runtime/control installation targets.

Dependency pins: Humble robot_localization3.5.4-1jammy.20260605.164056,
nav2_amcl1.1.20-1jammy.20260607.130817, rclpy3.3.21-1jammy.20260605.142610,
rosbag2_py0.15.16-1jammy.20260607.142735. No dependency installation/upgrade.

Live configuration/map identities still equal Stage19. Mission/seeder are still
`0da12027…` / `db634ff0…`; neither is overwritten. Live recorder `02fcaed2…`
differs from repository copy `7110961c…`: capsule freezes its own copy for imports
only, retaining existing live functionality. Core/writer hashes are byte-identical.
All observed ATLAS unit/drop-in and protected file hashes are retained as preflight
guards; unexpected later drift rejects installation, not blind overwrite.

Installer requires explicit approval, fresh latched/zero-command proof and CPU≤75%,
RAM≤80%, temperature≤70°C. Records timestamped UUID backups under `data/backups/`,
stages/checksums/replaces payloads atomically and never writes owner approval.
Atomic files are not a filesystem-wide atomic transaction; recorded originals and
partial-failure rollback provide recovery. Later unrelated target edits are refused.

Default installation does **not** start or enable recording. After separate
capture approval, a fresh one-use stationary grant includes exact source/map/config
identity and current boot. No file exists/has been granted in production now.
The grant must also match every runtime `files[].path/after` identity and specifies
`mode=read_only_partial_public`; runtime drift denies capture. It is never invented
by the installer. After explicit installation approval only:
`python3 EXACT_CAPSULE/installer/stage20_public_install.py --package EXACT_CAPSULE --install --owner-approved-install`.
Do not add activation flags unless separately approved. Directory creation and
daemon-reload register only this optional disabled unit; no other unit is restarted
and no `systemctl enable` is used.
Activation only starts the optional collector, checks that unit, and rolls back
own files/unit on initial health failure. Later diagnostic failure leaves it stopped,
with no automatic retry and preserved partial data. Never restart EKF/AMCL to test it.

Rollback after approval: run capsule's
`installer/stage20_public_install.py --rollback EXACT_BACKUP --owner-approved-install`.
It stops/removes only the optional unit, restores its own payload, reloads unit
definitions and preserves every recording. No localization/motor service restart.
Owner must inspect exact command/path and approve before running it.

## Return to core localization — shortest honest path

Do not rerun the old cold replay or claim a candidate fixed five jumps from zero
jumps in a different baseline. Existing Stage18 wrong-yaw/input-dependence evidence
and Stage19 missing-initial-reference evidence remain the starting point.

1. Owner decides whether this lower-fidelity stationary public package is useful
   enough to approve. It does not unlock B–E by itself. No driving requested now.
2. For a genuinely faithful new baseline, the specific remaining mandatory private
   overlay gates are reset/setPose/backward-time coverage and production-config
   native equivalence/resource qualification. Do not expand diagnostics beyond
   those prerequisites or require exact historical RNG reconstruction as a generic
   safety gate. Original five-event historical fidelity still needs unavailable history.
3. Only after trustworthy initialization/consumption evidence, compare baseline
   against **one change**: removing only correlated wheel X/Y pose flags while
   preserving commissioned velocity, gyro, signs, dimensions and covariances.
   No global scale/steering flips, arbitrary tuning or production deployment.

Predeclared comparison gates: matched source/consumer coverage and unchanged TF
ownership; no backwards/stale transforms; heading discrepancy reduced on every
eligible turn without worsened translation; report LiDAR quality/uncertainty and
retain UNKNOWN windows. Review Stage18 screened references, not ICP as guaranteed
truth. At stop, report >0.5m/≤2s AMCL jumps, maximum jump, heading/translation span
and covariance. A passing new session requires no unexplained large parked switch,
not merely improved map-fit percentage; old5/afterUNKNOWN stays unchanged now.

Later **unapproved** manual session: one locally clear short forward/reverse leg
and gentle left/right arc, stationary20s before/after, tape distance where available,
with working physical stop and fresh LiDAR/IM10A/encoder evidence. No full-house
repeat, required identical manual trajectory, autonomous goal or map promotion.
Check charger disconnected, headroom/storage/version identity and stop response
first; accept no physical result until actually observed/recorded.

**Next bounded action is owner review/approval of the PUBLIC partial alternative,
or an explicit decision to require the outstanding private-checkpoint gates instead.**
No production deployment or further physical action is authorized by this report.

Postflight: E-STOP latched, zero command, EKF/localization/mux/base active;
Nav2/explore inactive. CPU72%, RAM72%, temperature59°C. Protected EKF/nav/map hashes
remain exact Stage19 identities; no attributable production-overhead claim.
