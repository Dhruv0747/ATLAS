# CHECK MY LOCATION — Stage A implementation and live validation

## Current status — 11 October 2026, 18:55 IST

**BUILT → TESTED → DEPLOYED → browser verified. Operator acceptance pending.**
The read-only button is installed on `/v2/` and `/v2/mapping`, using one backend.
No driving, stop release, steering adjustment, pose correction or navigation
activation was performed. This does **not** mean localization is fixed.

Source commits on `agent/sync-developer-20261011`:

- Foundation: `44f25271e96e2ed20519e26db5b0a507141eac5c`.
- Adapter/API/UI: `fedee8eebb1a80552aa601fe68585a24d090f6af`.
- Snapshot-clock fix: `92a38936ccb16667a87880571c2e1a0ec33878db`.

### Reuse and exact scope

The existing monitor, accepted map, `global_search`, `decide`, `fit` and
`assess_tracking` are reused. No second AMCL, matcher node or pose publisher.
`atlas_location_check_ros.py` attaches services to the existing monitor and
shares a search mutex with its passive checks. The original `suggest` mode,
thresholds and accepted map remain unchanged.

New adapter binds fresh `/scan`, `/odom`, `/imu/data`, `/amcl_pose`, `/map`,
`/cmd_vel`, `/atlas/control_policy` and scan-time TF. It verifies loaded map
content/metadata against the YAML/PGM hash, coverage in every quadrant, finite
timestamps, two seconds stationary, stop latched and all command axes zero.
Checks repeat during work and at completion. Missing data, map/pose/motion
changes, timeout or cancellation cannot grant authority. Work is limited to
one search, 30 seconds, 1 million map cells and 1440 rays. The existing monitor
unit retains Nice=10 and CPUQuota=60%; this is not a new hard memory limit.

The lifecycle/core files from the foundation plus the adapter and monitor hook
are installed. `atlas_location_check_web.py` and the `atlas_status_web.py` hook
provide `GET /api/location-check` and bounded same-origin JSON
`POST /api/location-check` with `{"action":"start"}` or `{"action":"cancel"}`.
Existing private/Tailscale client restrictions remain. `X-Atlas-Location: 1`
and matching origin are required for POST; client poses/maps are rejected.
This is not a new per-user authentication system. Cancellation targets the
single current job; returned results carry request IDs. No reseed endpoint.

`web/v2/location-check.js` is shared by both HTML pages. It displays AMCL and
independent candidate poses, top two alternatives, margin/separation, fit
definition, covariance, scan/AMCL ages, map hash and calculation/result time.
Historical results are explicitly labeled. Polling cannot overwrite a rejected
request with an old success. Home and E-STOP remain accessible. Cards are
side-by-side at desktop width and stacked at narrow width.

### Tests and actual failures

- **73 scoped Python tests passed (6.509 s)**: lifecycle, search interruption,
  trusted adapter/HTTP security and existing matcher/seeder/monitor regressions.
- **6 JavaScript assertions passed**; Python compilation and `git diff --check` pass.
- Real ROS 2 Humble integration in isolated domain 173: recorded ranges with
  explicitly synthetic stationary timestamps/AMCL reference; successful result,
  cancellation/worker release, map mismatch, missing/stale IMU, missing scan-time
  TF, observed motion and concurrent search rejection pass.
- Recorded-range fixture: best fit **0.994**, second **0.938**, margin **0.056**;
  despite high score and zero synthetic covariance it did **not** verify a
  unique pose. Wrong synthetic AMCL fit was **0.582**, resulting in LOST.
- Live Command Center and Mapping buttons both produced new request IDs and
  completed results. Mobile visual layout and desktop card bounds checked.
- The first live request failed closed as UNCERTAIN on a future-timestamp
  check. Code inspection and a deterministic contention regression exposed
  sampling clocks before locks, which could make a later callback appear
  future-dated. Clocks now sample inside snapshot locks; actual future source
  timestamps are still rejected. Subsequent live checks completed.
- One browser request acknowledgement timed out during activation; it was
  labeled unconfirmed, not successful. Later polling recovered; subsequent
  direct button requests completed normally.
- A follow-up package rehearsal rejected a line-ending mismatch before live
  changes. Byte-captured baseline verification and EOL-only patch adaptation
  fixed packaging. Both install/rollback rehearsals passed afterward.
- Two pre-existing people-experiment tests require absent `rosbags`; they were
  excluded from the scoped passing suite, not counted as passes or installed
  into production. The broader invocation recorded two import errors.

Known-location Hall/corridor ground-truth accuracy has **not** been newly
certified. Synthetic fixture timestamps are not a faithful AMCL failure replay.
Existing matching thresholds were preserved, not retuned to make checks pass.

### Fresh live evidence — not an automatic correction

Measured request `cd2274555689412fab3ba44fd0d38ee2`:

| Metric | AMCL reference | Independent LiDAR candidate |
|---|---:|---:|
| X / Y (m) | 1.469 / -0.254 | 0.335 / -1.335 |
| Heading | 19.1 degrees | 75.0 degrees |
| Held-out scan fit | 0.808 | 0.995 |

Result **MISMATCH**, **1.567 m / 55.9 degrees** disagreement, margin **0.066**.
The second candidate had fit **0.929**, only 0.020 m away but 170 degrees
different in heading: rotational aliasing remains a real limitation.
Both start and end evidence confirmed stopped/latched, fresh sensors, map
identity and scan-time TF. Start/end scan ages were **0.169 / 0.152 s**.
AMCL covariance was small; this did not override the independent mismatch.
Later page requests reported 1.65–1.72 m disagreements with margins near the
existing threshold. These are scan-match candidates, not ground-truth poses.

### Measured Jetson resource impact

| Measurement | Before | After |
|---|---:|---:|
| Whole-machine busy CPU, separate 15 s windows | 69.21% | 69.78% |
| RAM, total minus available | 5623.1 MiB | 5656.9 MiB |
| Dashboard CPU, one-core units | 40.95% | 41.77% |
| Dashboard RSS | 168.46 MiB | 169.24 MiB |
| Monitor CPU, one-core units | 13.61% | 20.26% |
| Monitor RSS | 107.28 MiB | 104.24 MiB |

These non-identical workload windows include the existing passive checks and
browser activity; they are **not** a causal overhead estimate or full-load
navigation qualification. No resource tuning was performed.

Finite live requests: computation **2.86–3.10 s**. Profiled run wall time
**3.18 s**, monitor CPU time **2.25 s**, peak RSS **104.25 MiB** (no increase
over that warmed start); first measured request grew RSS by **7.71 MiB**.
Short sampled CPU peak **88.72% of one core**, not of the six-core machine.
During the profiled check, dashboard status requests all returned HTTP 200 in
**12.6–68.4 ms** locally; location polling max **43.7 ms**; acknowledgement
**30.2 ms**. Final scan/odom/IMU/AMCL ages were **0.150/0.016/0.038/0.281 s**.
These local HTTP timings do not guarantee Wi-Fi/Tailscale/browser latency.

### Deployment, safety and rollback

Stage 11 installed nine files; stage 12 updated only adapter and shared JS.
All installed result hashes match the committed package. Initial activation
restarted only `atlas-localization-monitor` and `rover-status-web`; follow-up
restarted only the monitor. No units, calibration or navigation parameters edited.
Direct ROS checks before/after each stage found latched stop and zero commands.
Mux PID **330413**, localization PID **5670**, recovery PID **330414**, motor
telemetry PID **1878** and camera PID **2678** remained intact. Nav2 and explore
remain inactive; reseeding mode remains `suggest`.

Rollback scripts, both rehearsed byte-for-byte:

1. `/home/jetson/project_atlas/data/backups/2026-10-11-185201-840465047-stage12-location-snapshot/ROLLBACK.sh`
2. `/home/jetson/project_atlas/data/backups/2026-10-11-184639-168019222-stage11-location-check-final/ROLLBACK.sh`

For full removal while parked/latched, run them in that order, then restart only
`atlas-localization-monitor` and `rover-status-web`. Scripts restore exact old
files and remove only the stage's additions. Do not restart AMCL or motor units.
No rollback is requested now. Existing diagnostics and map files are preserved.

Installed SHA256:

```text
f6f81d3252a0e1470137d9cd76d4a6e9bcd729c63c53ebfb7df963b6e25b8785 scripts/atlas_location_check_job.py
0c6240ad117dda0509d02ac37f84c98e671e88103d8572e8c7fdd2fe48d8b2d0 scripts/atlas_location_check_ros.py
37fd6cedfeeac05d4a717d2ff18477c67a0747ebb5e9261e781c7b07185006cb scripts/atlas_location_check_web.py
fff2ab007e45d2ac44bd001b65d1327c297a19ba362feb5eb3a1f866cec40b2a scripts/atlas_localization_monitor.py
abe5c2a3b66984264596c0fea974d5aa24014c3613689701b1f6d034d5ddcb64 scripts/atlas_localization_verify_core.py
1be48aa972bdf79f66f22d1e2cd0da3da3f8e35ef58604e26e437be831bdc716 scripts/atlas_status_web.py
e0291f844ea16474868a83ad76f7126a125b07dbe8a4063909d9617758be1f6c web/v2/index.html
d8b43593e3e952807e957b570e50a032b749e0080b31d2eaccccaec540f21ec8 web/v2/mapping.html
ee9519f497194cd899b7c117467b4d88302f84253415963e4a6660e09df7e5f6 web/v2/location-check.js
```

Private evidence retained under `/home/jetson/atlas_recorder_smoke_KWJkzy/`:
`location_smoke_01..03`, `location_activation_01..02`, resource before/after,
failed-clock snapshot, live/profile request reports and stage packages. No raw
private recordings were added to GitHub.

### Remaining limits / next action

Stage A is usable now while stopped and B latched. If the existing passive
search owns the worker, the button explicitly asks the operator to retry;
there is no unbounded retry or overlapping search.
Stage B one-use approved correction and post-reseed validation are **not built
or enabled**. No correction button is exposed. Further evidence is needed to
resolve AMCL/map disagreement and certify candidate accuracy across rooms.
No driving is requested for this handoff, and no autonomous-navigation pass
is claimed. The owner can inspect both deployed pages without moving ATLAS.

## Archived foundation checkpoint (superseded by the Stage A report above)

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
