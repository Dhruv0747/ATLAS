# One authorized CPU-report-only isolated startup — 2026-10-24

Result COMPLETE, no retry. Owner explicitly permitted CPU reporting for this
one diagnostic run; RAM80%,temperature70C and all safety/freshness checks retained.
Default remains strictCPU75%; production guards were not changed.

Supervisor gained an explicit diagnostic-only option, with invalid CPU readings
still rejected.25 offline tests passed. Archive verified locally/remotely:
`0caa06282dee9e84dfe7f4b00d8ac4056f561f024eb31e5cdc9823179c63281f`;
manifest `cc06ba6629e887c64f853637334021af6307c89534ff2875b862b61b6b7b0479`.

## Measurements

Isolated original-constructor worker PID296306 exited0 and stopped cleanly.
Private localhost domain214, isolated HOME, copied sources/local map fixture.
Application node never spun, timers cancelled, service calls blocked.

- ROS init5.027ms; monitor import233.762ms.
- Full Monitor constructor94.883ms wall,85.792ms process CPU.
- Constructor main-thread schedstat wait increased7.857ms; this is not
  whole-system scheduler attribution or a reproduction of production throttling.
- Application destruction7.100ms.
-6/6 synthetic heartbeats delivered; maximum delivery1.278ms,receive gap1.000589s.
-0 synthetic gaps above2s. One heartbeat fell in the broader construction phase
  but before Monitor.total BEGIN, so it does not prove overlap with its94ms work.
- Worker peakRSS77860KiB (about76.04MiB).
-20 whole-system CPU samples mean74.6101%,peak82.6955%.
- RAM peak70.8406%,maximum temperature59.343C.
- All20 production mission receipt samples <=0.1s; no stale mission reproduced.

CleanupCPU71.5928%,RAM70.4780%,temperature59.343C. E-STOP latched, manual-only,
commissioning disabled, zero motor commands/outputs, required sensors fresh,
mission READY, recorder and Astra OFF. Production hashes verified after test.
All11 protected service PIDs/restart counts unchanged, including monitor275216/0,
mission1901/0,voice108742/0,Dashboard94624/0. No restart, installation, camera,
motion, calibrated-cloud or navigation change. White-glass UI and voice retained.

## Meaning and limitations

The original failure is NOT REPRODUCED and is not declared fixed. This excludes
a universally slow constructor under these isolated conditions, not a failure
under production discovery, cgroup quota, Nice10 or nearly100% whole-system load.
Worker runs in an SSH session cgroup, not the production service's60% one-core
quota. No services or scheduling were changed to reproduce that policy.
No executor comparison or CPU savings demonstrated; this is original construction
only. Actual production publisher timing is not measured by Dashboard receipt age.

No further retry is justified without a new discriminating hypothesis. Next
offline work should model quota/discovery differences before proposing another
live experiment or any production deployment. This diagnostic CPU exception is
exhausted; it grants no camera/test/deployment bypass.

## Evidence

Remote `/home/jetson/project-atlas-migration/localization-startup-report-20261024-V2knFo/`:

- result.json `c4e3a3ff8280bcf959484d53609f321a59a610fd26054c62a9b22b8b7fb6f50b`
- guard-trace.jsonl `afb54d93ac7593a494ae22645f57e44b29a3f469c01599ede4666175598ceae6`
- worker-stages.jsonl `52816def8526f587033636f9ea9381f81b03e992d11aba35094cf34b7dfcff81`

Result/guard copies under artifacts/localization_startup_report_*_20261024.json*
matched remote hashes. Per-stage evidence is also embedded in result.json.
Raw evidence/package not committed. No production rollback needed; preserve
isolated directory. Only supervisor option/tests and this report changed in Git.
