# Targeted native Nav2 CPU profile preparation

Continuation from ea804af. Owner approved targeted profiling, offline fixes and
GitHub updates, but no production install/restart/camera/movement. Administrator
access is required (`sudo -n true` reports password required). Capture is pending
owner execution; no CPU-saving fix or savings claimed.

## Prepared diagnostic

`tools/diagnostics/nav2_cpu_once.py` adapts the existing hash-pinned profiler.
It targets **atlas-localization.service**, not the Python localization monitor.
Verifies exact launcher argv, user, cgroup membership and eight allowlisted Nav2
executable paths. All child process birth identities must remain unchanged.
Five baseline samples rank actual thread tick deltas, excluding the launcher.
Perf samples only the two busiest stable child threads for ten seconds at19 Hz,
user-space cpu-clock,4096-byte DWARF stacks,no inheritance. All group threads
retain proc ticks and scheduler statistics for context. This bounded sample
does NOT profile every node or kernel execution; unresolved native symbols or
few samples may prevent a defensible fix. Raw stack data remains private.

Strict CPU75%,RAM80%,temperature70C,existing sensor freshness,latched E-STOP,
manual-only,zero command/drive output,recorder OFF and Astra OFF checks remain.
No command-line CPU exception exists in this wrapper. Existing perf tool path
and hash are reused; no package installation, sysctl or permission changes.
Five postflight samples verify resources/safety and protected service identities.
Only the profiler's own process group may receive signals on failure.
No ROS participant, goal, service call or production setting change.

Persistent telemetry.jsonl,perf.log,perf.data and result.json are created under
an exclusive evidence directory. Partial artifacts survive failure. Do not retry
an abort automatically. 45-second outer timeout bounds the owner command.

## Validation and staging

28 tests PASS on PC WSL Ubuntu22.04:6 new wrapper tests plus22 inherited helper
tests. Windows ran the6 wrapper checks but cannot import Linux pwd for inherited
tests; the complete suite was therefore run on Linux, not skipped.
Tests include exact-source/hash checks,strict options,exact target command,
membership rejection,perf bounds,CPU validation,identity checks and owned-process
cleanup. No real profiler was attached during these tests.

Jetson read-only validation: launcher8060,10 group processes,109 threads;
group/owner/executable checks PASS. No profile started. Live Dashboard,voice,
safety reporter and guard hashes match the expected versions. This is not a
fresh resource admission pass; the command repeats those checks before capture.

Staged only under `/home/jetson/project-atlas-migration/nav2-cpu-20261024/`:

| File | SHA256 |
|---|---|
| nav2_cpu_once.py | eea47f2d8ae251a2c25a82c5002da27efd2357c0a2f79703689e6a36fda6e17b |
| native_dashboard_cpu_once.py | 2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18 |

Existing perf binary verified:
d51e7c1b3051d529e9a55c610d3d9e70e3b99ae89eebb477fae23a274e7311ca.
No production files installed, no services restarted. White glass UI,voice,
camera modes and calibration untouched. No rollback of production required.
Keep staged evidence after execution; diagnostic files have no autostart.

## One owner command

Keep ATLAS parked, B latched and sticks released. Run once in Jetson terminal:

```bash
sudo /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B /home/jetson/project-atlas-migration/nav2-cpu-20261024/nav2_cpu_once.py
```

After output, inspect result and raw hashes, native symbols/lost samples, actual
thread CPU and observer CPU versus baseline/postflight. Only then choose a
minimal offline optimization. Do not infer busy waiting from sleeping stacks,
or extrapolate two-thread savings to whole-Jetson CPU. If admission fails, stop;
this approval does not waive CPU limits or authorize a repeat.

## Owner-run follow-up: 2026-10-24 09:04 IST

Owner reported executing the command. Read-only inspection of the exact staged
directory found only the two reviewed scripts and an import cache, with no
evidence directory, result.json, telemetry or perf.data. Both script hashes
still match the table above. No matching nav2_cpu_once or perf-record process
was running at inspection time. The import cache was already possible from the
earlier read-only validation and is not proof that the sudo capture ran.

Capture status is **NO SAVED EVIDENCE FOUND**, not CAPTURE COMPLETE and not a
confirmed CPU guard abort. Existing checks cannot distinguish a terminal/command
or sudo failure from an exception before evidence-directory creation. Exact
terminal stdout/stderr is required; do not guess the cause or automatically rerun.
No new performance measurement, candidate fix or CPU savings claim is possible
from this result. No production changes or new profiling were performed.
