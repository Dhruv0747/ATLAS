# Stage20 CPU headroom and installation fix — 14 October 2026

## Decision

**Preparation complete; production installation BLOCKED by genuine CPU excursions.**
No third installation was attempted. No recording, motion, reboot, service restart,
rate change, renice, calibration/map change or workload suppression was performed.
The corrected installer is tested, but the fresh read-only admission check refused.
Do not request/execute another installation as though stable headroom has passed.

Installer source: `bb8ec665ed5474d7b2b0db22e9b5624ddd137b06` on
`agent/sync-developer-20261011`. The nine qualified public runtime files are unchanged.

## Measured baseline

14:26:21.966–14:36:46.211 UTC (19:56:21–20:06:46 IST), 120 windows,
600 individual CPU intervals totaling600.973s; wall624.264s including process/sysfs
sampling. No installation or collector ran during this window.
CPU is Linux `/proc/stat` delta, busy excluding idle+iowait, guest not double-counted.
Every approximately1s sample is retained; process snapshots span approximately5s.

| Measurement | Result |
|---|---:|
| Aggregate CPU mean / median |70.03% /69.36%|
| CPU p95 / maximum |75.72% /81.93%|
| CPU samples exceeding75% |37/600 (6.17%)|
| Five-sample windows containing an exceedance |25/120|
| Longest consecutive high sample run |3|
| Per-core means, cores0–5 |70.59,66.62,67.31,68.21,73.50,73.78%|
| RAM min / median / max |68.38% /70.27% /72.58%|
| CPU temperature min / max |58.25 /58.906°C|
| 1-minute load min / median / max, six cores |7.66 /11.68 /19.23|
| Instantaneous runnable count min / mean / max |1 /9.54 /52|
| Swap used, first and last |1,835,008bytes, unchanged|
| Free disk at end |394,644,246,528bytes (~367.54GiB)|

NVMe whole-device counters across the first/last gauge snapshots:221,424 sectors
written (113,369,088bytes),1,560 read (798,720bytes),31,148ms device busy time.
Do not sum partitions with their parent device. These are whole-system writes,
not solely diagnostic writes, and not a queue-latency measurement.
CPU/memory/I/O PSI is unavailable on this kernel. Direct hardware thermal-throttle
counters are unavailable; sampled throttle-alert/cpufreq cooling states were0,
fan state1. This is not proof that every possible hardware throttle was absent.
Auxiliary thermal zones2/3/4 are unreadable; primary CPU temperature was available.
An initial probe aborted on an unreadable auxiliary zone before producing data;
that exception is now recorded rather than discarding all other measurements.

### Attribution, not a claim that individual services are defective

Process CPU100% means one core; divide by6 for approximate whole-machine percentage.
Persistent-PID/start-time deltas do not include every short-lived process and are
not an exact accounting of aggregate CPU, kernel/interrupt work or every spike.

| Service/process | Mean one-core CPU |
|---|---:|
| Localization service, all its children |49.93%|
| AMCL alone, PID11903 |6.62%|
| Dashboard, PID2088 |42.27%|
| Camera, PID2988 |31.13%|
| Motor telemetry owner, PID3364 |26.83%|
| Voice companion |23.59%|
| Sensor recovery |15.49%|
| Localization monitor |15.05% (peak36.79%)|
| Command mux |14.77%|
| AI annotator |14.06%|
| Safety reporter |12.61%|
| LiDAR odometry |10.39%|
| UNO sensor hub / IM10A |8.30% /7.13%|
| LiDAR driver / EKF |3.47% /2.11%|
| Visual Cloud agent |1.45%|
| systemd PID1 / user manager PID1901 |0.25% /0.13%|

The localization unit includes map/lifecycle/controller/planner/behavior/BT children;
its total must not be mislabeled as AMCL CPU alone. Existing controller processes
under that unit do not imply an authorized autonomous mission. No graph was changed.
At the peak window the localization monitor was35.24% of one core, but this
correlation does not establish a unique causal process for the aggregate spike.

## What is verified about the previous failure?

The collector was never started. The old exact postflight measurement was lost;
79.7% was a subsequent rollback-time sample, not the missing rejected sample.
**The exact historical trigger/cause remains bounded uncertainty.**
New evidence demonstrates that CPU can exceed75% during ordinary production plus
lightweight observation without installation. It does not prove an installation
could never contribute a transient spike.

Overhead measured after the baseline, in isolation/read-only:

- Probe:17.571 CPU-seconds over624.264wall-seconds, about2.81% of one core,
  **0.47% of six-core capacity** on average. Not subtracted from admission readings.
- Fresh-process installer/checker imports:0.216s wall,0.141s child CPU.
- 100 payload/installer/protected hashes:0.0165s wall,0.00610s CPU; all matched.
- Native fake-root transaction including unit parser:0.422s wall,0.0387s parent
  CPU plus0.2925s child CPU; process peakRSS23,704KiB. Admission values were test
  fixtures for this transaction; no real service-manager reload was executed.
- Read-only systemctl show:0.0406s wall,0.00657s client CPU. Manager means/peaks
  during baseline were PID1:0.25/2.31%, user manager:0.13/0.96% of one core.
  The baseline window containing the14:30:26UTC show query had maximum73.58% CPU.
- Previous real daemon-reload duration from preserved evidence was0.646s.
  Its isolated CPU contribution was not captured. No live reload was repeated
  merely to benchmark it; simulated registration cannot qualify live reload CPU.

These small measured costs do not identify the precise old spike, nor justify
discarding a high reading. Broad optimization is outside this change.

## Confirmed software defects corrected

1. Generic resource refusal discarded its exact rejected sample. Installer-only
   `stage20_resource_admission.py` now persists all five CPU intervals, timestamps,
   method/durations, process snapshot, RAM, temperature, free disk, thresholds,
   safety values, refusal reason, installation-begun and rollback-required state
   **before raising**. Existing sanitized process output/traceback logging remains.
2. The prior supervisor's postflight sat outside the installer's transaction.
   Both preflight and postflight now use the same callback; postflight refusal is
   inside the rollback boundary. A failed check cannot leave a successful return
   requiring an improvised outer rollback.

Unchanged ceilings:CPU75%, RAM80%, temperature70°C, free disk at least2GiB.
Each of five consecutive approximately1s intervals must pass (accepted duration
0.9–2s); invalid/missing/delayed measurements refuse. Any spike refuses, without
averaging it away or retrying until low. The original dashboard safety/resource
guard remains an additional requirement, including a high cached CPU value.
The five-interval method is explicitly stricter observation, not threshold relaxation.
`stage20_public_preflight.py` and all nine runtime payloads remain byte-identical.

## Validation

- PC Stage20 suite:97 tests,96 PASS,1 native-POSIX permission test skipped on Windows.
- Jetson focused installer/resource suite:32/32 PASS, including native permission.
- 13 injected phase failures (before backup, each of nine copies, unit copy,
  registration, resource postflight) restore the exact target baseline.
- Preflight refusal writes no targets; postflight79.7% fixture rolls back.
- Boundary values, high dashboardCPU, stale/unlatched/nonzero safety evidence,
  NaN/missing metrics, delayed intervals, log-before-error, success and refusal pass.
- Native fake-root installation verifies all nine hashes; native unit parser passes;
  offline systemctl reports `static` (no install section/autostart). Collector not run.
- Exact sandbox rollback preserves existing-evidence sentinel and backup.
- Python compilation and diff whitespace checks pass. No affected ROS node/binary
  was changed or rebuilt. Live manager registration was deliberately simulated.

## Fresh refusal and unchanged production

Single read-only admission at14:37:06–14:37:11UTC, after isolated tests:
CPU intervals **67.297762,68.556701,68.166090,79.897785,77.364865%**;
measurement window5.215784s. Direct RAM72.173517%, CPU temp58.593°C,
free394,643,591,168bytes. DashboardCPU75.4%, RAM72%, temp59°C.
Intervals3/4 and dashboardCPU all exceed75%; **REFUSED**, installation_begun=false,
rollback_required=false. This rejection is fully retained, unlike the prior failure.
No subsequent admission retry was made to seek a lower sample.

E-STOP=true, sourceSTOPPED, policyage0s; linear/angular commands0, age0.2s.
Commissioning is not armed. Nav2/explore service units remain inactive/disabled.
83 protected production hashes and exact dependency versions match.

| Production service | PID before/after | Restarts before/after |
|---|---:|---:|
| EKF |3234/3234|0/0|
| Localization |11868/11868|17/17|
| Motor telemetry |3364/3364|1/1|
| Command mux |1913/1913|0/0|
| Remote |1963/1963|0/0|
| Safety reporter |1977/1977|0/0|

Start-monotonic timestamps also unchanged. Historical17/1 restarts are not new
restarts caused by this task. Public diagnostic targets, user unit and approval
grant remain absent; unit inactive/not installed, not falsely described as an
installed disabled unit. Empty directories from the previous rollback remain.

## Exact candidate, evidence and rollback

New manifest: [ATLAS_STAGE20_CPU_CANDIDATE_MANIFEST.json](ATLAS_STAGE20_CPU_CANDIDATE_MANIFEST.json)

SHA256:`fd73590a71244541e1e527b5023a5a6f34d80e45ff4e46435954a0eb69732a7b`.
This replaces neither the old retry manifest nor its evidence. Installer source
commit is recorded separately; original runtime source identity is preserved.
All nine runtime and eight installer hashes are in the manifest; no secret values.

Jetson scratch package:`/tmp/atlas-stage20-cpu-kHPUKBLO/cpu_candidate`.
This path is temporary, not a production deployment. Reverify identity/existence
before any separately approved future attempt.

Raw evidence stays off Git per repository policy; local copies are in `artifacts/`:

- `baseline_v2.jsonl` (local`stage20_cpu_baseline_20261014.jsonl`), SHA256
  `9caf1fd4094f4a6639d2833f5acbc6cff0a62035ba3667b7b6fddb5042c7b410`.
- `cpu_rehearsal.jsonl`, SHA256
  `e68367189163b38cd35dc264c9531ca2ebc841c94e3b8fee66fdec74473a22a4`.
- `fresh_admission.jsonl`, SHA256
  `1a90abefd37974bda4069a656a5e75e80e03a3e72fe10300161117e1c862d076`.
- `cpu_result.json`, `overhead.json`, probe/rehearsal scripts in the same scratch
  directory; terminal test output retained in this task. Raw process command lines
  were not collected. Probe logs contain no ROS messages or recordings.

Sandbox backup:
`/tmp/atlas-stage20-cpu-kHPUKBLO/cpu_fake_project/data/backups/20261014T143706Z-stage20-75fea3d097fb4cc7852293c3cdafa5a4`.
Prior production rollback evidence remains:
`/home/jetson/project_atlas/data/backups/20261014T141748Z-stage20-f194331e2176414cbbb95d19b41bbc53/`.
No new production backup was needed because no third installation began.

## Next approval gate

**Not install-ready under the current resource evidence.** The fresh gate failed
and25/120 baseline windows contained over-limit CPU. An OFF package's low passive
cost does not grant permission to bypass the owner's installation guard.

Do not ask for unconditional installation approval or repeat attempts now.
The next decision needs a separately scoped production-load review if the owner
wants to establish reliable headroom; do not stop essential services or change
sensor rates without approval. No threshold change is proposed.

Once headroom is independently established, request explicit approval for **one**
installation-only attempt of the exact manifest above: fresh safety/resource/hash
checks, nine new files and one absent optional user unit only, no activation/grant,
no existing-service restart, backup before writes, automatic exact rollback on
postflight failure. A fresh high reading aborts; no retry loop. The present approval
does not cover that attempt, recording or autonomous motion. Localization remains
unresolved and was deliberately not reinvestigated here.
