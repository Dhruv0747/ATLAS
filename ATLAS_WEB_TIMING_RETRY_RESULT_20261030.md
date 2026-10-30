# Timestamp-corrected controlled attempt — FAIL, CPU admission rejected

One owner-approved attempt using bc79776 controls, manifest
7e668845aab6470aeb404b834ef20502442f3ec3997f0f535df4ca0e1cf4431f.
All control/backend package and original rollback hashes verified. No retry.

## Actual timeline

Fresh preflight CPU61.34/63.00/60.97%, RAM63%, temperature max63.281C.
E-STOP latched, manual-only, zero commands, stationary/fresh LIVE encoder telemetry,
recorder OFF, Astra OFF and no AI/camera worker verified.

Temporary supervisor PID205815 and observer PID205843 started. Two valid aggregate
samples were captured before failure during observer startup:

| Interval | CPU | RAM | Max temperature |
| --- | --- | --- | --- |
| 1.001133881s | 70.6485% | 62.6704% | 63.093C |
| 1.000164179s | 92.9293% | 62.3570% | 63.156C |

The unchanged75% CPU guard aborted. Unlike the previous attempt, this is a real
CPU-counter rejection with valid measured intervals. Restart-policy preparation,
file installation and web restart were NOT reached. No observer CPU exemption.
23:50:36 IST supervisor failed;23:50:37 transient unit cleanup finished, NRestarts0.
Systemd total3.020s CPU includes shell/supervisor/observer, not pure profiler cost.

## Process evidence and limitations

In overlapping cgroup intervals, localization rose24.27 to81.52% of one core;
temporary supervisor/observer group92.02 then32.75% of one core; existing Pi Camera
group31.76 then33.94%. Web process38.85 then21.82% of one core. Supervisor process
approximately19.83 then20.25% of one core. These are NOT whole-Jetson percentages.

Process/cgroup readings are sequential: second cgroup windows range roughly
1.35–1.45s versus aggregate1.00016s. Do not sum overlapping parent/child cgroups
or assert exact same-window causation. New observer first interval lacks a PID
delta because it did not exist in the baseline; its cgroup includes startup CPU.
Evidence shows observer/supervisor cost and concurrent localization activity.
It does not by itself prove DDS discovery caused the full spike or resolve the
earlier79.15% shutdown spike. Existing Pi Camera was not started or changed here.

## Cleanup and postflight

Web remains PID182915, active, NRestarts0, Restart=always. Original protected
atlas-/rover- unit identities/states/restart counts match. Three live original files
match exact backups; seven backend additions absent; temporary override absent.
Observer exited. No camera/inference or motor command was issued.

Postflight CPU63.18/64.25/60.56%, RAM62.16–62.20%, temperature max63.25C. Latched
E-STOP, manual-only, zero commands and fresh stationary encoder telemetry passed.
Astra OFF and no Astra/AI processes. Rollback not needed: no production mutation.
No activation restart and no rollback restart were used. No manual recovery needed.
New APIs and candidate browser checks were not reached; backend NOT activated.

Private evidence:
/home/jetson/project-atlas-migration/web-activation-once-timing-20261030/,
Windows work/web-activation-timing-evidence-20261030.
Evidence manifest SHA256:
1203b2d8dfdea503343dd664dc0904da6858f1c25e4bca568e7751d184621a8d.

NO-GO for activation. Preserve evidence for offline analysis of temporary observer/
collector startup and concurrent load. No new attempt or policy change authorized.
