# Priority incident: original recovery startup CPU overload — 2026-10-31

Scope: retained evidence and source/history review only. No recovery start, live
profiling, current robot probes, ROS participant, camera, AI, controls or firmware
changes. Saved retry evidence copied read-only; Prometheus queried only for its
historical07:40–07:45IST window. No Vision Lab feature development.

## Confirmed timeline and accounting

Original source SHA5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Snapshot output disabled. Retry package85d439f4..., not the earlier candidate run.

| Evidence | Observation |
|---|---|
| Journal07:44:13IST | Original recoveryPID349210 started |
| Accepted CPU before start |58.66%,63.48%|
| First newPID sample mono53859.612264522 |69.165% aggregate; PID34921047user+22system ticks at100Hz =0.69CPU-s since birth; start_ticks5385868; RSS10252pages=40.05MiB |
| Watcher at same sample |PID349108 cumulative0.253178336CPU-s, includes initialization/prior monitoring; not a same-window delta |
| Rejection mono53860.589931457 /07:44:15 |93.624161% CPU; no rejected-window process/cgroup/raw aggregate deltas retained |
|07:44:15 | Cleanup stops recovery; traceback in rclpy Node parameter-service creation with invalid context |
|07:44:17 | Process exited; lifetime serviceCPU1.828s includes startup+stop |
|07:44:18 | Supervisor failed; lifetime supervisor-unitCPU1.203s includes watcher and cleanup |

Do not add overlapping lifetime and process totals or compare them as synchronized
windows. If six CPUs were online and window approximately1s,1.828CPU-s is at most
30.47 whole-machine points; it cannot alone explain93.62%. This is a CONDITIONAL
upper bound, not measured attribution: onlineCPU count/rejected endpoints are not
retained in that row. Aggregate background contention is plausible and the parked
baseline~60% is measured; exact concurrent contributors are unavailable.

## What the source and stack establish

Both latest failures stopped within super().__init__('atlas_sensor_recovery').
81.34% candidate attempt was creating parameter publisher; original93.62% attempt
was creating parameter services. These exceptions follow the stop decision, so
are consistent with interrupted ROS context, not proof of a primary startup bug.
No READY marker was recorded. Recovery's custom subscriptions,30s startup-grace
checks, recovery dispatch, snapshot adapter and2s/5s timers are after that call.
Thus snapshot writes, custom sensor callbacks and automatic recovery scans did not
cause this attempt's pre-readiness load. Python imports and rclpy/DDS initialization
still consumed work beforehand; no stack sampler apportions their CPU.

DDS discovery/parameter endpoint creation and graph activity in existing participants
are hypotheses, not confirmed dominant functions. Localization had concurrent load
in an earlier observer attempt (24.27->81.52% ONE core in differently aligned
windows), but its CPU was not collected in this93.62% event. Unchanged service PIDs
do not mean unchanged load. Kernel interrupts/scheduler contention are unmeasured.
No evidence supports disabling localization, voice, safety or parameter services.
No tight recovery-loop regression is shown. Existing raw=True freshness subscriptions
were already optimized; do not repeat that change or claim it fixes constructor work.

## History comparison

- Oct27 maintenance restart98.8391%: candidatePID33049 reached READY about2.04s
  after start; rollback originalPID33128 READY about2.94s after start. Lifetime
  candidateCPU3.040s, no exact process-window attribution. API delay1.391s correlated,
  not causal. Successful READY proves functional startup, NOT compliance with75%
  throughout startup. See Stage28 saved investigation in stage28 worktree.
- Oct30 web shutdown79.15% occurred before replacement initialization; cause UNKNOWN.
- Oct30 observer startup92.93% included new observer/supervisor cost and localization
  activity, but overlapping process/cgroup intervals prohibit exact attribution.
- Oct31 recovery81.34% and original93.62% both rejected during Node construction.
- Original recovery ran successfully asPID2005 before these attempts. Saved steady
  operation and prior successful start are not matched startup CPU measurements.

Only a short high sample followed by enforced shutdown exists. LaterCPU~59% shows
recovery after abort, but cannot establish transient versus sustained startup load
had the service been allowed to continue. No startup exemption is justified.

Historical Prometheus query at07:45IST with5m range:19up samples,all0; CPU and thermal
series empty. Grafana has no missing attribution to recover. Its ordinary scrape
cadence would not resolve a1s spike even if healthy. No monitoring repair performed.

## Safety implications while recovery is stopped

Latest retained postflight: E-STOP latched,zero fresh commands,stationary encoders,
LIVE packets; other protected service identities unchanged. This is retained
state, not a claim about present unobserved state. RecoveryPID0 remains incident
status pending separately approved restoration.

Independent code paths remain: cmd-vel mux E-STOP/deadman/stale-owner logic; base
telemetry and its systemd watchdog/restart-on-failure path; ordinary sensor services'
own systemd policies; Dashboard safety display. They do not require the recovery
node. Source configs show mux50ms watchdog period and base5s systemd watchdog,
but no live fault injection/revalidation was performed here. Reporting nodes are
not substitutes for actuator safety enforcement.

Lost: central stale/fault detection, bounded sensor-service restart coordination,
recovery status publishing, and its Stage28 maintenance acknowledgement. A hung
sensor that remains running may not be recovered by systemd Restart alone. Do not
claim full protection or authorize movement/navigation/firmware maintenance.
Monitoring exporter/watchdog was already unavailable in retained evidence, so do
not rely on Grafana as an operational safety layer. Keep E-STOP latched/rover parked.

## Smallest justified correction and tests

Confirmed diagnostic bug: watch() raised at CPU>75 before persisting acquired raw
counter endpoints. Added rejected_cpu_evidence.py and a narrow call at rejection.
It marks independent health failed FIRST, then saves already-acquired CPU endpoints,
monotonic boundaries and ABORT reason. It performs no new process/HTTP/thermal probes
after rejection. Evidence-write error still fails closed. Production/package files
unchanged; this new repository dependency is NOT part of any approved live package.

Three focused rejection tests plus three watcher tests PASS (six total): raw
counter retention, failure-first ordering if disk write fails, no further probes
past CPU guard, stale/missing watcher rejection and startup-counter inclusion.
No runtime optimization or CPU saving is claimed. No safe performance fix can be
selected from missing attribution. Disabling ROS services, reducing safety checks,
raising thresholds or ignoring initialization spikes is NOT justified.

## Shortest safe recovery plan / verdict

NO-GO for another start. Original source/config already restored; no repeated file
rollback or Vision Lab work is needed. Keep incident OPEN. First complete bounded
independent process/cgroup evidence retention that survives the rejected interval,
without the known expensive full/proc scan; validate its overhead offline and retain
all relevant PID identities/exit gaps. Reuse historical evidence; no current live
profiling authorized. Then prepare a separately approved, single monitored original
recovery start only if fresh headroom passes and a concrete measured mitigation or
adequate new evidence justifies it. Keep75%CPU/80%RAM/<70C unchanged. If evidence
cannot justify a start, report blocker rather than force success.

Private evidence:work/recovery-startup-incident-20261031 (saved journal,samples,
result and historical prometheus-history.json); Stage28 prior reports and previous
observer records remain preserved. No raw private telemetry committed.
