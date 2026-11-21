# Stage20 CPU optimization — bounded dashboard candidate, 14 October 2026

## Result and limits

**One small noncritical inefficiency confirmed and corrected in source. Overall
CPU headroom has NOT been recovered or demonstrated. No production deployment.**
Code commit:`e364e932b997342214738c6196cf856a4de38132`, branch
`agent/sync-developer-20261011`.

The previous ten-minute baseline remains the whole-system reference:mean70.03%,
p95 75.72%, maximum81.93%,37/600 samples over75%, RAM68.38–72.58%, temperature
58.25–58.91°C. It was not repeated to seek a convenient low reading.
No Stage20 package changes/installation/activation, service restart, priority or
sensor-rate changes, camera degradation, motion, steering or map changes.
Stage17B remains HOLD; autonomy authorization unchanged.

## Confirmed avoidable processing

`atlas_status_web.json_response()` pretty-printed every machine-readable response
with `indent=2`. Existing browser clients parse JSON; they do not need whitespace.
The finite native benchmark loaded only the actual `clean_json` and `json_response`
function ASTs from the deployed file; it did not import/start the web server or ROS.
Four real read-only GETs supplied status/map/LiDAR-view/radar payloads. All repetitions
thereafter used the same captured payloads locally, not repeated production requests.

cProfile on20 isolated status responses:439,541 total function calls,0.281s profiled
wall time, of which JSON dumps had0.247s cumulative time and `clean_json`0.033s.
71,280 `_iterencode` calls and211,120 recursive `_iterencode_dict` calls show the
formatting path's repeated work. Profiling overhead is substantial: timings below
are separate **unprofiled** measurements, not those cProfile numbers.

Change: `indent=2` becomes `separators=(",", ":")`. No precision reduction,
filtering, payload cache, age cache, timer/subscription/lock change, freshness
allowance change or request-rate reduction. NaN/Infinity sanitization, `allow_nan=False`,
Unicode handling, HTTP status and cache-control headers are preserved. Content-Length
is recalculated for the smaller body. Human-readable whitespace is the only output
format change; consumers comparing raw bytes will see different bodies.

## Native microbenchmark, not deployed process savings

Five batches of20 responses per variant per payload; table is median CPU milliseconds
per response. Both variants used identical data. Fixed before/after ordering and a
single captured payload per endpoint limit generalization; no whole-server CPU or
real-time scheduling claim is made.

| Endpoint | Before CPU ms | After CPU ms | Reduction | Bytes before → after |
|---|---:|---:|---:|---:|
| status |2.600|1.187|54.3%|39,580 →32,413|
| map |0.255|0.114|55.5%|2,097 →1,495|
| lidar-view |1.774|0.735|58.5%|10,518 →5,073|
| radar |0.124|0.048|61.4%|882 →631|

Median isolated wall milliseconds:status3.002→1.204, map0.280→0.117,
LiDAR2.094→0.908, radar0.124→0.048. Whole benchmark process peakRSS32,700KiB;
this is not an A/B production-RAM result. Single live GET observations were70.6ms,
11.9ms,16.9ms and5.2ms respectively; these are not p95 latency measurements.

Source polling schedules include status0.5Hz, map0.5Hz, LiDAR-view2Hz and radar8Hz
when those views are active. Their simultaneous use is a workload assumption, not
a measured count of current clients. At those rates, the measured serialization
delta predicts only approximately0.35% of **one core**, or0.06 percentage points of
the six-core CPU per such set of clients. Actual traffic/concurrency may differ.
**This cannot plausibly close the observed multi-percentage-point CPU spikes alone.**
Do not misrepresent a54–61% function improvement as a54–61% Jetson reduction.

## Remaining dominant cost: not yet profiled

Existing dashboard CPU42.27% of one core is much larger than this serialization
budget. It must not be attributed to JSON alone. Existing hot/cold ROS executor
separation, idle-camera suppression, compressed-frame reuse and shared2s slow-status
cache already exist; they were not rebuilt or counted as new optimizations.

A bounded live dashboard stack profile was attempted using py-spy0.4.1 installed
only into `/tmp/atlas-dashboard-cpu-ZWJhPgy7/profiler`, not a production environment.
Requested flags:`--pid 2088 --nonblocking --duration 30 --rate 10 --format raw`.
The unprivileged attempt failed immediately: **Permission Denied**. Noninteractive
sudo failed: **a password is required**. Neither obtained stack samples. No ptrace
policy, capabilities, permissions, service configuration or password was changed.
No profiler remains running. Native `perf`/py-spy were not previously available.

Thus there is no evidence yet to justify a larger callback/executor optimization.
Live callback latency, contention and actual per-function call frequency remain
unmeasured. Do not invent results or change sensor dispatch on this evidence.

## Tests and preserved behavior

- New response tests:3/3 PASS on PC and3/3 on Jetson in an isolated scratch tree.
  They cover nested values/Unicode, NaN/Infinity, unchanged input, status/headers,
  correct byte length, and changing age values between requests (no stale cache).
- All four real captured payloads decode identically before/after; non-length
  headers match. Repository candidate and minimal live-only patch produce
  byte-identical compact responses on all four inputs.
- Existing status-web test collection initially encountered missing PC OpenCV and
  Windows default text-decoding errors. With explicit UTF-8 and an inert cv2 import
  stub (no image operations tested),54/55 checks pass; the remaining assertion is
  POSIX0600 permissions unsupported by that Windows test filesystem (reported0666).
- That PIN-file permission behavior was checked separately against the unchanged
  pure-Python module on native Jetson, in a temporary directory:0600 and verification
  PASS. This is not a claim that the entire suite was rerun on native ROS.
- ROS/E-STOP/remote tests are mocked policy regressions, not physical validation.
  Camera continuity/quality, live TF, callback deadlines, Wi-Fi fallback and BMS
  behavior were not exercised with deployed new code, because deployment is forbidden.

No production PID/restart change:dashboard2088/0, EKF3234/0, localization11868/17,
motor telemetry3364/1, mux1913/0, remote1963/0, safety1977/0. Historical counts17/1
are not new restarts. Nav2/explore units remain inactive. Read-only status snapshot
is preserved locally; no control endpoint was invoked. The live dashboard file
hash remains unchanged. There is no post-deployment CPU/RAM/temperature comparison
because nothing was deployed. That acceptance remains pending owner approval.

## Important deployment drift

Live dashboard SHA256:
`1be48aa972bdf79f66f22d1e2cd0da3da3f8e35ef58604e26e437be831bdc716`.
Repository contains additional single-person steering diagnostic integration absent
from production. **Do not copy the entire repository dashboard file onto Jetson.**
Its unrelated import/publishers/timer/endpoint changes are not part of this task.

A minimal candidate derived from the exact live file changes only the JSON line
and explanatory comment. Candidate SHA256:
`687ecf69106d7ffac122926f1e52b820b1abd373814a9fc725a772b3c96a48d5`.
Local artifacts:`artifacts/atlas_status_web_cpu_live.py` and
`artifacts/atlas_status_web_cpu_candidate.py`. Raw snapshots/profiles and metrics
are in `artifacts/stage20_dashboard_json_profile/`; Jetson originals are under
`/tmp/atlas-dashboard-cpu-ZWJhPgy7/result/`. Not committed per repository policy.

## Rejected/unqualified candidates

- Lower camera FPS/quality, sensor rates, safety polling or CPU threshold: not allowed.
- Disable ordinary services to make a resource sample pass: rejected.
- Cache whole telemetry responses/ages: rejected as freshness risk.
- Assume all localization-unit CPU is AMCL: wrong; includes multiple children.
- Broad executor rewrite or camera pipeline change without a live stack profile:
  unqualified; existing optimizations must be preserved.
- Treat JSON optimization as sufficient Stage20 headroom: rejected by its small
  absolute measured budget. No repeated admission sampling or installer retry.

## Classification and controlled proposal

| Label | Status |
|---|---|
| CONFIRMED BOTTLENECK |Only excess work in JSON response formatting, not dominant system bottleneck|
| FIXED IN SOURCE |Yes, one response serialization change|
| TESTED OFFLINE |Yes, real-payload native function benchmark and regressions|
| PERFORMANCE IMPROVEMENT VERIFIED |Only isolated serialization CPU/bytes|
| DEPLOYMENT READY |Minimal candidate prepared; fresh safety/hash and restart approval still required|
| DEPLOYED |No|
| PHYSICALLY VALIDATED |No|

One possible controlled deployment, **not executed**: while parked/E-STOP latched,
verify exact live source hash and current safety; back up only dashboard script and
unit identity; apply the minimal JSON-only patch; with explicit approval restart
only `rover-status-web.service`. Preserve motor/steering/EKF/AMCL/Nav2/network/BMS
units. Verify decoded values, freshness, camera continuity, stop-policy reporting,
TF availability and existing controls without commanding movement. Run comparable
parked-load observation using the unchanged CPU method. Restore the exact script
backup and restart only the dashboard if any regression appears. Record backup path
at execution; no production backup/restart has happened yet.

**Recommendation:** do not perform a dashboard restart solely to claim Stage20
headroom recovery; the expected gain is too small. First obtain the bounded,
nonblocking stack profile with operator-authorized privileged execution. This
requires access the current SSH session does not have, not another drive test.
Only after identifying a larger demonstrated inefficiency should additional
changes or combined deployment be proposed. Production optimization/restart and
Stage20 installation each still require separate explicit approval. Install-only
headroom, if later passed, will not qualify actual recording load.
