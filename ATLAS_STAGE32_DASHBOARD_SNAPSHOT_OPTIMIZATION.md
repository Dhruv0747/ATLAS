# Stage 32: offline dashboard snapshot optimization

2026-10-21. Baseline cd75929. OFFLINE CANDIDATE ONLY; no Jetson connection,
camera Start, service restart, installation, recording or movement this task.

## Confirmed local inefficiency, not the whole-Jetson root cause

The actual AtlasRosNode.snapshot method filters every stored timestamp into a
new list on every request (up to 128 stamps per key), while holding the callback
lock. _set also evaluates deque(maxlen=128) on every call to dict.setdefault,
even when the key exists. Both are redundant operations.

Extracted the real methods using AST, without importing ROS or instantiating a
web node. Synthetic fixture: 100 keys, 128 ordered recent timestamps per key;
empty fallback, fixed clock. This is a stress fixture, NOT a captured production
request mix. Five batches of 2,000 snapshots; five batches of 100,000 callbacks;
median process CPU time. Separate cProfile run of 1,000 snapshots.

|Offline host|Baseline snapshot|Candidate snapshot|Reduction|
|---|---:|---:|---:|
|Windows Python 3.13|0.914063 ms|0.218750 ms|76.07%|
|WSL Ubuntu 22.04 Python 3.10|0.475341 ms|0.081724 ms|82.81%|

Linux callback bookkeeping: 0.472107 -> 0.309756 microseconds (~34.39%).
Windows: 0.78125 -> 0.625 microseconds (coarse process-clock resolution).
Linux cProfile attributes 0.506 of 0.696 seconds (~72.7%) to the history list
comprehensions in this fixture. Candidate profile total0.156 seconds; no such
comprehension. Profiling overhead differs: use unprofiled medians for savings.

This does NOT explain the entire live web process's ~44.84% of one core.
At a hypothetical 10 snapshots/s, Linux measured snapshot savings would be only
~0.00394 CPU-seconds/s, or0.394% of ONE core. Real request rates and Jetson costs
are not measured here. No claim that this alone resolves the76.61% rejection.
ROS executor, serialization, other endpoints and other services remain possible
contributors. No new whole-Jetson before/after result exists.

## Minimal single-runtime-file change

`project_atlas/scripts/atlas_status_web.py`:
- Allocate history deque only when a key is first seen.
- Remove expired prefix entries under the same lock, then calculate rate from
  the remaining deque without allocating/scanning a complete temporary list.

Only _set writes histories; its monotonic timestamps are ordered under the lock.
An expired prefix can never become fresh again. History remains bounded at128.
The10-second strict boundary, duplicate timestamp handling and rate rounding
are preserved. First cleanup after a long idle remains bounded by128 per key.
No sensor value, timestamp, freshness result, fallback, safety decision, response
or HTTP endpoint is cached. Existing locks and all publishers/subscriptions,
timers, camera settings, Domain77,75/80/70 limits and4-second lease are unchanged.

## Verification

60 Linux dashboard tests PASS, including5 new differential tests:
- randomized ordered histories, expiry and new callbacks (40 cycles,100 keys);
- exactly10s boundary, duplicates, single and empty histories;
- fallback precedence, fresh age and battery explanatory fields;
- changing stop-state values and advancing clocks (no stale cached result);
- bounded128-entry callback retention.

Existing executor/interface, E-STOP/reset, no-reboot, camera idle and dashboard
panel tests pass. Windows:29 tests pass;3 modules fail import because cv2 is
absent. Full suite rerun in WSL passes60/60. No hardware acceptance implied.

Reproduce from repository root:
`python3 project_atlas/tests/profile_status_web_snapshot.py`
`python3 -m unittest discover -s project_atlas/tests -p 'test_status_web_*.py' -v`
The benchmark baseline is pinned to cd75929 and requires that Git object.

## Review package and rollback plan (NOT executed)

Local tar: `artifacts/astra_concurrent_20261021/dashboard-snapshot-candidate.tar`
contains ONLY `scripts/atlas_status_web.py`.
Tar SHA256:7cdd887200b0c01d76dd45d7882913696b0d3ee103abfef962c180c4907df150.
Packaged file SHA256:e0b7d6eee33e02f889e22f60aee6b3f00ec636f39bfd2487f3d9d4d88ab6804c.
Baseline Git LF bytes SHA256:73094079d270ec146b442021da1996a0747554831c55a2ecaf342941f227fe78.
These are repository/package hashes, NOT freshly verified live hashes. Line
endings can change checkout hashes; verify the exact approved package bytes.

Before any deployment: owner approval; fresh safety/resource state, Astra and
recorder OFF, E-STOP latched, manual-only and zero commands; verify live file
matches the reviewed baseline (investigate any difference, do not overwrite).
Capture protected PIDs/restart counts; copy live file with metadata into a new
timestamped migration backup and verify its hash. Start low-overhead monitoring.
Install this file only and restart ONLY rover-status-web if separately approved.
Allow restart transient to settle; verify sensor freshness, E-STOP/zero state,
Pi Camera, protected service identities and unchanged limits. Keep Astra OFF.
Measure parked web-process and whole-machine CPU under comparable dashboard
polling; do not claim the synthetic percentage as a whole-machine saving.

Rollback on installation or health regression: restore verified original bytes
and metadata from that specific backup; restart only rover-status-web under the
same approved procedure; confirm original hash and all safety/health checks.
No backup path is claimed to exist yet. Existing Stage32 rollback backups remain
untouched. No persistent service/permission/calibration changes are proposed.

## Next approval

Single-file installation, backup and monitored rover-status-web-only restart,
followed by parked CPU/health comparison with Astra OFF. No camera Start is
included; a later live preview test requires separate approval and fresh guards.
Do not raise CPU to80% on the basis of these results.
