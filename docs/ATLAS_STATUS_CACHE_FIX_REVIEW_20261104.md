# /api/status non-blocking diagnostic cache — independent review (2026-11-04, offline)

Builds on the previous developer's uncommitted correction (worktree ATLAS-status-cache-fix, base 551f22b).

## Defect (CONFIRMED offline) and correction
Live `atlas_status_web.py` (4b5906f7) refreshes network/system/service diagnostics INSIDE the request while holding
`_slow_cache_lock` (`ip addr`, `ip route get`, `ss`, each with a 2 s timeout). Concurrent requests, including the monitoring
watchdog's 0.5 s `/api/status` read, wait behind it. The five focused tests reproduce a ~2 s block on the live bytes
(2 failures, 2 errors) and PASS (0.13 s) on the candidate. The correction uses single-flight background collection, atomic
publication stamped with the collection START, expiry unchanged at 2 s, and stale diagnostics shown as unavailable
("--"/None), never zero or healthy. ROS safety values are still read fresh on every request.
The 10:59:42 watchdog TimeoutError cause remains UNKNOWN (CSI restart overlap is correlation only).

## Review findings
- Exact-live: the candidate edited the repo file, which differs from live (Stage 29 controller imports/executor).
  The changed region is byte-identical in live, and the candidate changes nothing else, so the same region was applied to
  the exact live bytes: candidate 68f5379c (patch in tools/deploy/status_cache_fix_20261104).
- Watchdog (guard.py 27d4caca) reads only `ros` from /api/status, so it is unaffected by unavailable diagnostics and
  can no longer be blocked by them.
- Vision gates (stationary_gate.check, atlas_vision_feature_guard.check) read `system.ram_percent`. While diagnostics
  are stale they raise TypeError inside `except Exception` admission paths: fail-closed (refusal), never healthy.
  At Web start, the first second or so refuses Vision admission until the first collection publishes.
- Measured on the Jetson (read-only, 20 rounds): the three subprocesses take p50 14 ms, max 29 ms, 8.1 ms child CPU per collection.
  Refreshing every 1 s instead of every 2 s adds about 0.07 whole-Jetson points (approximation: `ss` variant).
  `DIAGNOSTICS.snapshot()` (the nested cache) was not timed and is out of scope.
- /api/status now answers in 5-34 ms.

## Deployment (prepared, NOT executed)
`install.sh` pins live 4b5906f7, jetson:jetson 644, and backs up the live file before an atomic same-directory replace that keeps the mtime.
`rollback.sh` restores the exact bytes and refuses unknown bytes. Sandbox PASS. No restart: the new code loads only at
the next rover-status-web start (Restart=always, so a crash or reboot would load it). Web restart = protected operation
needing its own approval (unobserved interval, DDS rejoin CPU). Monitoring recovery for the new fault 4f04831f needs a
new single-use transaction afterwards.
