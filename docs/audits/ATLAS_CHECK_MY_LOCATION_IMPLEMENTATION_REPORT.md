# CHECK MY LOCATION — implementation checkpoint

11 October 2026. Dedicated branch `agent/sync-developer-20261011`.
**Foundation built and isolated-tested; feature NOT deployed or operator verified.**
This is an incomplete implementation checkpoint, not the requested final acceptance.

## Existing components and verified gaps

Reuse `atlas_localization_verify_core.global_search`, `decide`, `fit`, and
`assess_tracking`; do not add another matcher, AMCL, or pose publisher. The
current monitor uses that no-prior search and is live in `suggest` mode.
Source and installed monitor/core agree after line-ending normalization.
Installed SHA256 before this work:

- monitor: `35dd7407b300b5be0bbac0ee48948fc0ff356ea84507d0041985181ea0ed0a24`
- core: `2e6e22393df9166bb8106d0961f0af46f2be22338b2e2984436e4b6dd8cf562d`

Two code facts matter: the current monitor obtains mounting TF using `Time()`
(latest, not the acquisition time), and its timeout discards results without
terminating the computation thread. Neither fact alone proves the historic
AMCL jumps were caused by this monitor. No new root cause is claimed.

## Candidate changes (not installed)

- `atlas_localization_verify_core.py`: optional cooperative checkpoint before
  map indexing, each coarse heading, each candidate and refinement iteration.
  Default search scoring, calibration and thresholds are unchanged.
- `atlas_location_check_job.py`: one active worker, unique request IDs, immutable
  evidence copies, 30-second maximum cooperative deadline, cancellation,
  old-result rejection, changed-map/motion/localization/AMCL rejection, explicit
  final evidence requirement, and timestamped historical result labeling.
- Timeout/cancel retains the worker slot until exit acknowledgement. A timeout
  cannot start overlapping searches merely because the UI considers it done.
- No correction, seed, velocity, TF, navigation service call, or HTTP endpoint
  exists in this candidate. Navigation and correction flags remain false.

The trusted adapter is **not yet implemented**. Its coverage qualification and
TF consistency inputs must not come from browser-supplied booleans. The adapter
must bind actual scan timestamps, scan-time TF chain, accepted-map content hash
and loaded occupancy metadata, control state, odometry/gyro motion history and
AMCL epoch. Cooperatively checking time is not a hard process memory limit;
bounded input sizes and worker resource limits still need implementation.

## Tests and limits

On Jetson in the isolated scratch directory, with BLAS/OMP limited to one thread:
**33 tests passed in 4.323 seconds**: 13 new job lifecycle tests, two new actual
matcher interruption tests, and 18 existing matcher/seeder/status regressions.
The full initial suite failed because scratch dependencies were absent. After
copying existing fixtures, two people-experiment tests still could not import
`rosbags`; these two were explicitly excluded, not counted as passes. No package
was installed on production to hide that limitation.

Synthetic matcher regression is not a fresh real-world Hall/corridor acceptance.
Recorded false-confident and ambiguous cases must still be evaluated through
the completed request pipeline. No current independent location or fresh pose
comparison was produced by this new feature.

## API / security / UI — remaining implementation

Proposed single backend operation for both buttons: POST request, GET status
by request ID, POST cancellation. Paths are not yet registered. Require existing
private/Tailscale client checks, same-origin JSON, bounded request size, and
server-side job ownership/rate limiting. Reject user-provided pose/map/scan data.
Do not expose a correction endpoint in Stage A.

Both Command Center and Mapping buttons, side-by-side AMCL/candidate poses,
top-two ambiguity metrics, data ages and map version remain to be implemented
and browser-tested. No inert or misleading button was added to production.

Stage B needs a separate server-side one-use confirmation token bound to the
candidate, map/scan identities, expiry and safety epoch, plus isolated AMCL
pre/post-correction tests. It is **not ready for activation** and still requires
the owner's separate deployment approval. Keep `suggest` mode unchanged.

## Resources / deployment / rollback

No production files changed, no service restarted, no pose reseeded, no movement.
Candidate tests ran in `/home/jetson/atlas_recorder_smoke_KWJkzy/location_check_candidate/`.
No background process installed. Existing deployment `eb4c88c` is preserved.
The settled baseline and current safety evidence are in
[the reliability checkpoint](ATLAS_CORE_RELIABILITY_CHECKPOINT_2026-10-11.md).
There is no feature-specific CPU/RAM or latency benchmark yet: the whole-system
baseline is NOT the overhead of a feature that has not been deployed.

Next engineering action: implement the trusted ROS snapshot adapter and connect
the existing monitor's single search owner to the bounded lifecycle; then APIs,
UI, recorded-case and browser tests, resource benchmark and rollback rehearsal.
No driving is needed for this next step. A live Stage A deployment requires
passing those gates and fresh parked/latched-stop evidence. Existing rollback
packages remain untouched; no new live rollback path is claimed.
