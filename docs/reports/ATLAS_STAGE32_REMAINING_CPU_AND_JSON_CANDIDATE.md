# Remaining CPU: dominant cost unresolved; exact-live JSON candidate prepared

2026-10-21, follows e52fb3d. No production changes, restarts, essential-service
stops, safety-limit changes, camera Start, recording or movement.

## What is new

Fresh read-only hash confirms current dashboard98f3c269. Live thread inspection
of PID51991 reports TID52033 at27.3% and TID52093 at13.9% of one core; main thread
~0.3%, another thread2.5%. These `ps -L` percentages are lifetime CPU averages,
NOT a new bounded interval. WCHAN observations are instantaneous, not a profile.
Python thread names do not identify callback roles. Do not assert exact mapping
of Linux TIDs to _spin/_spin_status without tagged evidence.

This resembles the already-measured26.37/12.79% two-thread pattern in Stage20.
Read and reused ATLAS_STAGE20_DASHBOARD_EXECUTOR_CPU_FIX.md and the October11
server audit. Their existing stack samples point to executor paths, but most
are at a native wait-return boundary. They do NOT establish a busy loop, event
storm, time spent rebuilding wait sets, or a defect to patch safely.
No new duplicate subscription found or claimed. Existing split-executor and
raw-subscription experiments must not be repeated as new fixes.

Fresh inspection: py-spy not on shell PATH; ptrace_scope1. No profiler installed,
privilege changed, debugger attached or process paused. Native CPU/per-wakeup
attribution remains missing. CPU load is not itself proof of incorrect behavior.

## Confirmed avoidable work still present in deployed code

Live JSON response formatting remains `indent=2`, unlike the repository's
already-tested compact serializer. This was explicitly preserved in the last
deployment. Reused the existing Stage20 native serialization benchmark and
four retained payloads; did not repeat its live GETs or CPU microbenchmark.

Prior measured CPU milliseconds/response (historical, not new Jetson measurements):

|Payload|Pretty|Compact|
|---|---:|---:|
|status|2.600|1.187|
|map|0.255|0.114|
|LiDAR view|1.774|0.735|
|radar|0.124|0.048|

At the documented assumed polling rates this predicts only~0.35% of one core,
~0.06percentage points of six-core CPU per client set. Actual client workload is
not measured. It cannot plausibly close the multi-point admission spikes alone.
No new total dashboard or whole-Jetson saving is demonstrated.

## Prepared smallest safe correction

Exact-live one-line replacement in `json_response`:
`indent=2` -> `separators=(",", ":")`.
Preserves clean_json, strict finite encoding, values/precision, status/cache
headers and refreshed data; Content-Length correctly follows the smaller body.
Raw response bytes/whitespace change; decoded JSON is identical. No caching,
telemetry reduction, request throttling, timer, QoS, executor or steering change.

`prepare_live_json_patch.py` is an offline builder with exact baseline hash,
single occurrence check, unrelated AST equality and byte-perfect inverse.
Repository's full dashboard file is NOT the package source.

Baseline SHA256:98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79
Candidate SHA256:431d530af7aa88638e247402eb02749ed697ca9e27f14a8c18e02a761e719797
Tar SHA256:6fd4ab23c14cda4594ad0dda4f1a79ec8bafbb56d2136689969e0d582e1e5e71
Private local package:artifacts/astra_concurrent_20261021/json-live-package/json-live.tar.
Contains only scripts/atlas_status_web.py. NOT deployed.

## Tests

Six exact-live tests PASS: nested JSON equality; Unicode/NaN/Infinity/header
behavior; no stale response cache; inverse/reject baseline drift; isolated
install/byte-perfect rollback; equivalence on all four retained real payloads.
Sixty existing dashboard tests PASS against isolated candidate copy on WSL
Ubuntu22.04, including E-STOP/reset HTTP behavior, camera-idle, telemetry,
executor interface and no-reboot tests. No physical test was performed.

## Decision and next necessary action

The JSON candidate is ready for optional, separately approved single-file
installation/web-only restart, fresh gates and backup; it is NOT offered as a
solution to the dominant remaining CPU load. Do not repeat camera attempts or
claim a75% admission fix on these results.

To justify an executor/runtime correction, the discriminating evidence still
needed is a bounded thread-tagged Python/native CPU profile plus useful callback
and wakeup counts, distinguishing actual native CPU/GIL work from sleeping.
This would need a reviewed instrumentation/access plan (no unapproved service
restart, ptrace-policy relaxation, rate changes, artificial sleeps or QoS-warning
suppression). Existing untagged stack counts cannot answer it. Prefer that
investigation over deploying successive small optimizations as headroom fixes.

## Installation/rollback preparation

If approved later: confirm exact baseline/package hashes; fresh E-STOP/manual-only,
zero commands, Astra/recorder OFF,75/80/70 and sensor gates; create a timestamped
backup with original metadata and hash; install only candidate; restart only web
with persistent low-overhead monitoring and settling; verify protected services,
HTTP routes, sensor freshness and matched CPU. On regression restore verified
backup and restart only web, then repeat health/hash checks. No backup or production
write was made for this candidate. Previous working deployment remains installed.
