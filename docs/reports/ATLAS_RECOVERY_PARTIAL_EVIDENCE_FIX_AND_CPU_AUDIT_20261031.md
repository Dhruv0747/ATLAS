# Recovery collector correction and CPU audit — 2026-10-31

Continue from fa29d67. OFFLINE correction only. No new monitoring system,
benchmark, Jetson package installation or service restart. Recovery remains last
verified STOPPED; incident OPEN. Earlier read-only audit checks changed nothing.

## Confirmed defect and correction

The last attempt failed on a150ms attribution scan deadline, NOT a confirmed CPU
limit violation. snapshot() had already read /proc/stat but raised before returning
its partially built record; sample() therefore never persisted those counters.
The failed interval cannot be reconstructed retrospectively.

Minimal changes to existing collector/consumer:
- Keep150ms budget. When exhausted, STOP scanning and return acquired aggregate,
  process and group counters with complete=false, collection_issue and explicit
  unread PID/group lists. Do not retry or extend the scan.
- Read selected cgroups and the identified Recovery PID before other PIDs.
- Persist partial snapshots through the existing atomic writer. A skipped PID is
  not falsely classified as exited. No missing CPU counters are invented.
- Evaluate valid aggregate CPU and all existing resource/telemetry/E-STOP gates
  independently of attribution completeness. A partial attribution sample can
  accompany a valid safety observation; it is never a complete process profile.
- Classify measured CPU-limit rejection separately from invalid sampling intervals
  and other safety-observation failures. An invalid aggregate interval still aborts;
  observer failure/staleness and external deadlines remain fail-closed.

CPU75%, RAM80%, temperature<70C, freshness, command-zero and E-STOP unchanged.
No raised collector budget. A single kernel read may finish after the budget;
existing parent heartbeat/timeout still bounds a stuck observer. No guarantee of
complete attribution during starvation or SIGKILL is claimed.

8focused tests PASS in0.044s: five new deterministic delayed-read fixtures plus
existing inventory, cgroup-format and integrated first-rejection tests. They prove
priority PID/group retention,60%CPU partial sample saved without false overload,
90%CPU rejection with retained evidence, skipped!=exited, and late interval rejected
as SAMPLING_INTERVAL. No native benchmark or service test was repeated.

Changed runtime sources: startup_cpu_attribution.py, recovery_attribution_trial.py,
recovery_startup_diagnostic.py. Tests: test_partial_cpu_evidence.py plus the existing
invalid-budget assertion. Previously approved package remains untouched; its hashes
must not be reused for this corrected source.

## ROS/DDS initialization assessment

Saved original unit uses `bash -lc 'source /opt/ros/humble/setup.bash; exec python3 ...'`.
Existing Stage32 direct-launch optimization avoids repeated shell/ROS setup for
Astra workers; its effect on Recovery has NOT been measured or compatibility-
validated. It is a possible small future launch correction, not an established
Recovery fix. It would not remove rclpy Node/DDS initialization.

Saved earlier failures were in Node initialization before custom recovery scans.
Latest attempt reached custom status-publisher construction only AFTER termination
began. Current original Recovery already uses raw serialized delivery for
freshness-only subscriptions. Reapplying that optimization cannot fix startup.
Dashboard/telemetry profiles show executor and QoS bookkeeping, not proof of a
specific removable defect. Do not disable parameter services, QoS events, DDS
participants or safety subscriptions, nor introduce lifecycle wait-set caching
(the earlier cache experiment failed entity/heartbeat tests).

**Confirmed:** attribution timeout discarded valid evidence; aggregate background
load remains substantial; several small deployed optimizations exist.
**UNKNOWN:** dominant ROS/DDS startup cost, cause of historical93.624% spike,
whether a ROS initialization code change would safely reduce it. No CPU fix claimed.

## Concise audit of previous CPU work (existing reports, no new tests)

Process CPU numbers below are percent of ONE core; whole-machine numbers are
separate. Non-matched or short windows are not sustained causal proof.

| Previous change | Deployment evidence/current check | Measured benefit/limit |
|---|---|---|
| Recovery freshness subscriptions use raw serialized messages | Historical deployment; current original source retains raw policy |~20.0→15.3%one core historically; steady-state only |
| Voice raw scan/IMU ingress | Historical deployment; later voice patch installed |26.8→19.2%indicative, mismatched windows |
| Camera publish only demanded raw/JPEG; dashboard camera lease | Historical deployment, existing dashboard lease code retained |Avoids unused payload work; no matched total CPU gain in cited report |
| AI annotator skips rendering with no viewers | Current hash8c3a06c matches deployed patch; service currently inactive |14.08→9.49%one core historically; system70.00→70.86%, no total gain |
| Localization search pacing | Current monitor hashcddbbc8 matches paced version |Worker peak74.27→32.19%at20%budget; final10%budget installed historically; sustained system gain not demonstrated |
| Dashboard snapshot timestamp/allocation reduction | Deployed ae63113; later dashboard source evolved |System69.270→71.215%; web44.845→45.383%; no saving demonstrated |
| Dashboard private executor count optimization | Deployed Oct23; live source still imports private helper, current helper hashes differ from original deployment |Web46.869→44.652%; system71.218→71.100%; not significant system headroom. Current helper revision provenance not established by original hash |
| Voice private executor | Current file matches a88ff78 deployment hash |25.161→24.016%; system71.399→71.469%; no total gain |
| Safety scan rotates each ray once | Current file matches94f52bcc deployed hash |13.5663→13.1037%; system70.723→71.360%; no total gain |
| Localization executor replacement | Rolled back; current cddbbc8 confirms original restored |Mission freshness failure; no valid post-window benefit |
| Compact JSON | Still indent=2 in current live dashboard; candidate not deployed |Native function benchmark54–61%faster, estimated only0.06whole-host points/client; not a restoration solution |
| Astra direct worker launch/depth conversion | Historical deployment reports |Depth conversion~55%faster OFFLINE; no proven live system saving; Astra OFF so irrelevant to parked load |
| Static/lifecycle wait-set caching / one-pass trials | Rejected or inconclusive offline |Do not repeat as ready fixes |
| Feature-on-demand manager | Active; logs show optional AI group stopped when demand cleared |Current optional AI/agent-team/fusion/store PIDs0. Current low idle baseline is different workload, not proof of one patch's gain |
| Monitoring/timing/snapshot diagnostics | Some deployment failures/rollbacks; original Recovery restored on disk |Diagnostics, not demonstrated runtime CPU optimizations |

Source reports: ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_DEPLOYMENT.md,
ATLAS_BACKGROUND_SEARCH_CPU_20261015.md, ATLAS_PARKED_CPU_MANUAL_ONLY_20261015.md,
docs/*IDLE_CPU_2026-10-04.md; retained ATLAS-github branch docs
ATLAS_EXECUTOR_DEPLOYMENT_RETRY_20261023.md, ATLAS_VOICE_EXECUTOR_DEPLOYMENT_20261024.md,
ATLAS_SAFETY_SCAN_DEPLOYMENT_RETRY_20261024.md, ATLAS_LOCALIZATION_INSTALL_ROLLBACK_20261024.md,
ATLAS_CPU_FINAL_DEVELOPER_HANDOVER_20261024.md. Audit is of accessible source/history,
not proof that every historical experiment or current helper byte is accounted for.

## Current consumers and duplicate-work assessment

Fresh read-only systemd/PID checks matched these processes to the already saved
Oct31 passive12s interval. This is existing interval evidence, not a new profile:

| Process/service | PID | Saved12s CPU, one core % |
|---|---:|---:|
| Dashboard |182915|48.31|
| Base telemetry |3258|31.20|
| Voice |2145|26.54|
| Pi Camera driver |2725|19.80|
| Command mux |1949|19.80|
| Safety status |1989|14.81|
| Localization monitor |2067|13.15|
| LiDAR odometry |2697|12.90|

Fresh ps lifetime values differ (Dashboard46.5, base30.5, camera29.6, voice25.3):
these are NOT fresh matched-window measurements. Localization cgroup from retained
capture averaged20.02%one core. Core EKF2.50%, shadow EKF2.08%, feature manager2.50%,
agent supervisor3.41%, local LLM3.08%, visual cloud1.58% in the saved interval.
Astra is not the existing Pi Camera process. Voice profile evidence previously
placed most CPU in ROS work, not a busy speech-inference worker.

Two EKFs are active, but shadow candidate publishes no TF and has a distinct
output; this is a small explicit experimental workload, not proof of duplicate
production localization. Do not remove it without dependency review/approval.
The dashboard's control/status executors serve different subscriptions and safety
roles; saved audit found no duplicate constant-topic subscriptions.

Feature manager's fail-open code treats stale/missing demand as autonomy demand
outside an authorized maintenance lease, and ExecStopPost restores managed units.
That can create startup bursts. Current boot logs show one experience-store start
at16:32:35 Oct30, then optional features stopped at16:52. There are NO feature-manager
start events around the08:35Oct31 failed Recovery attempt. Hence it is a confirmed
startup-policy risk but NOT the cause established for this incident. Stopping the
manager would itself risk starting optional work; do not do that.

Historical parked whole CPU~70–74%; Oct31 passive baseline58.22%, active60.32%, after
59.26%. Recovery and several optional features now stopped, different boot/client
load and observer costs: cannot credit that difference to a particular patch.
Historical Grafana gaps do not fill the missing rejected interval; no new Grafana
health claim is made.

## One recommended next corrective action

Use THIS small partial-scan correction in the existing bounded original-Recovery
restoration procedure, after separate execution approval and fresh admission.
No new framework, profiling prerequisite or benchmark is needed. Do not bundle
unproven ROS/DDS changes, disable useful services or raise any threshold. If actual
CPU exceeds75%, still stop and report the now-retained CPU evidence. This removes
the confirmed tooling blocker; it does not promise CPU headroom or Recovery READY.
