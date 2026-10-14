# ATLAS next localization milestone — 14 October 2026

## Decision and status

Track A: **BUILT / TESTED OFFLINE / NATIVE VALIDATED (isolated synthetic ROS)**.
Ready for review, NOT deployed or live RECORDING VERIFIED. Track B: minimal
candidate **BUILT / TESTED OFFLINE**, performance comparison blocked by missing
initialization history. Neither LOCALIZATION IMPROVED nor PHYSICALLY VALIDATED.
No full-house drive is requested. Stage 17B remains HOLD; autonomy stays disabled.

## Installed baseline preserved

The previously installed public-only 120-second package remains OFF. Read-only
post-test verification found all nine payload hashes and all 83 protected production
file hashes unchanged. Optional unit static/inactive, PID0, restart count0; no grant.
Manifest SHA256: `fd73590a71244541e1e527b5023a5a6f34d80e45ff4e46435954a0eb69732a7b`.
Backup/rollback evidence:
`/home/jetson/project_atlas/data/backups/20261014T161223Z-stage20-e894fd8a74894292a9480cc0b9bb2309`.
Boot unchanged: `260efab5-7a80-4d97-85e4-68465df67608`.
Production PID/restarts unchanged: EKF3234/0, localization11868/17,
motor3364/1, mux1913/0, remote1963/0, safety1977/0, dashboard2088/0.
Historical restart counts are not new test restarts. Nav2/explore inactive.
E-STOP latched, policy STOPPED, commissioning false, linear/angular commands zero.
No production service, map, steering, calibration or authority was changed.

## Recorder implementation

The old explicit public duration gate required exactly120s/500MiB. New explicit
`--public-only --stationary-30 --duration 30` uses a distinct single-use approval
profile; legacy default and legacy service template remain unchanged. A 30s grant
cannot authorize legacy capture or vice versa. No live grant was created.

The receipt window is at most30s after sensor preflight; callbacks refuse later
receipts. Writer drain/shutdown share10s. ROS teardown, checksums and evidence writing
are outside that writer wait budget: optional unit RuntimeMaxSec50 plus
TimeoutStopSec12 bounds the whole process. This is NOT a strict40s process claim.
Cancellation at the deadline cannot be reported as complete. Missing required bag
topics, stale sources, unsafe control state, resource refusal or writer loss report
incomplete/nonzero exit. Forced termination leaves inspectable incomplete evidence.

Reuses existing topic list, raw CDR queue/writer,500MiB quota and evidence retention.
No additional public topics excluded: raw encoder updates/counts, raw/corrected IMU,
scan/raw scan, wheel/EKF odometry, AMCL/particles, TF/static TF, steering commands,
control status and source/receipt identity remain. Existing public-only exclusions
of private estimator instrumentation remain; no internal-state fidelity is implied.
Raw IMU is retained when available, not treated as another required gyro authority.
Further topic narrowing would remove requested evidence; no such reduction made.

Required continuous receipt age <=2s, supported source stamp age -0.5..2s; AMCL,
particles and static TF require receipt, not periodic forced pose publication.
TF source-age preflight checks the first transform only, not every frame chain.
Full raw transforms are preserved for later chain analysis. AMCL/particles seen only
in preflight but not during capture cause incomplete capture; no AMCL update is forced.
New profile uses reliable transient-local static TF subscription and re-subscribes
after preflight to capture retained static transforms inside the receipt window.

## Tests and actual Jetson impact

Private network/PID/device sandbox, ROS domain187, synthetic publishers only,
nice19, process timeout/CPU limits; no live collector or motor access.
Final native capture:
`/tmp/atlas-stationary30-avHg8uSb/public_f4d5f60c/captures/capture_20261014T165349Z_5f8afd10`.

| Metric | Measured result |
|---|---:|
| Bounded receipt span |29.988929s (30s ceiling)|
| Writer/ROS flush elapsed |0.070283s|
| Child CPU / wall |14.931261 /31.055631s|
| CPU equivalent |48.08% of ONE core, not whole Jetson|
| Peak RSS |74,112KiB (72.375MiB)|
| Logical bag/evidence size |55,758,035 bytes (~53.18MiB)|
| Logical bytes /30s |~1.77MiB/s|
| Free storage |394,201,198,592 bytes|
| Queue peak |160,969 bytes /138 messages|
| Application drops / backlog / writer errors |0 /0 /none|
| Exact received CDR/ledger pairs |20,645|
| Verified source headers |7,014; no missing measured interior headers|
| Callback mean /max |0.335 /30.599ms|

SQLite integrity and checksums passed. Physical disk writes could NOT be measured
reliably: private proc I/O unavailable and rusage block output reported zero.
Zero does not mean no disk writes; logical growth is the measured proxy. This is
an explicit resource-measurement limitation before production activation.

Native missing-sensor preflight, active scan loss, stale scan, cancellation,
forced process termination and fake-root one-use approval adapter tests passed.
Scan-loss receipt span7.183s, stale-scan7.001s, cancellation5.058s: all incomplete,
writer stopped. Cancellation had four unreceived trailing sender stamps, explicitly
reported; zero application queue drops is not a zero transport-loss claim.
Systemd unit parser passed; no live unit installed or enabled.
Final Windows regression:106 tests,105 passed/1 environment skip; four candidate
contract tests passed. Native tests cover ROS serialization unavailable on Windows.
Deadline-stop normalization was added after native capture and covered by unit tests.

Retained failed experiments: first fixture compared independently serialized CDR
padding and failed; corrected to compare received bytes to their receipt ledger and
source timestamps. Strict static-TF-only fixture then exposed a genuinely missing
retained static sample; reliable transient subscription fixed it and final native
capture passed. A cancellation fixture initially required all trailing sender
samples; corrected to retain/report interrupted-tail loss, not call it complete.
All failed native evidence remains in the same scratch root; none deleted.

## CPU admission remains blocked

Preserved prior five intervals:79.496,76.897,69.257,72.712,68.313 percent;
RAM73.091%, temperature58.031C. CPU75/RAM80/temp70/free2GiB admission unchanged.
No convenient-sample retry.30s lowers total work, not instantaneous load. Synthetic
recorder cost does not demonstrate safe production headroom. Existing raw CDR fast
path is reused; no measured CPU optimization claimed. Smallest next step is a
separately approved bounded headroom investigation, not deleting required topics
or relaxing75%. Production recording remains refused until genuine headroom exists.

## Minimal fusion candidate and evidence

See [full candidate evaluation](ATLAS_MINIMAL_WHEEL_POSE_FUSION_EVALUATION.md).
Only wheel pose X/Y selection indices0,1 are removed; velocity6,7 and IMU gyro11
remain. No scale/sign/bias/covariance/timing/steering/map changes. Manifest pins
baseline YAML SHA256 `69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed`.
Reuses existing Stage19 variant builder, not another estimator implementation.

Existing screened evidence covers53/126 windows across four eligible drives;
73 windows unknown and fifth drive has zero eligible windows. Recorded EKF yaw
errors1.190,1.058,1.748,1.794deg are lower than wheel3.052,2.163,3.332,3.406deg;
translation results mixed. These are old evidence, NOT new candidate results.
Candidate relative heading/translation, covariance, continuity, TF, post-stop and
AMCL-jump improvements all UNKNOWN. No favorable-window selection or native replay
rerun: previous cold baseline was off1.343m/18.401deg even after rigid alignment.
Missing relative anchors, covariance and time history prevent valid A/B comparison.
Five parked AMCL jumps, maximum2.206m, remain unresolved, not zero.

Smallest future evidence: actual EKF initialization and selected observation/TF
history from a separately approved normal startup, or a genuine restorable filter
checkpoint. Original AMCL reproduction additionally needs initialization/private
particle/weight/RNG/event history. Public30s stopped capture cannot recover those
old states or prove moving performance. Do not deploy candidate fusion yet.

## Deployment/rollback preparation and next approval

Source prepared only: capture, approval gate, integrity inspector, optional30s unit.
The existing installer is not authorization to overwrite installed files. A reviewed
exact-hash upgrade manifest/transaction is still required before installation;
do not reuse the old fresh-install command blindly. Preserve existing120s template.
Back up current three diagnostic scripts and both optional-unit copies with hashes,
compare protected83 files/PIDs, install only approved diagnostic diff, leave unit
inactive/not enabled/no grant. Roll back only those backed-up diagnostic files/unit;
preserve all bags and existing production files. No production restart needed.

Next approval request: permission to prepare/review that minimal installation-only
upgrade transaction and bounded CPU-headroom work; no activation or motion included.
Activation requires separate explicit approval plus passing unchanged admission.
No driving is needed now. Code/report commits are recorded in the final handoff
and follow-up documentation; branch `agent/sync-developer-20261011`, never main.
