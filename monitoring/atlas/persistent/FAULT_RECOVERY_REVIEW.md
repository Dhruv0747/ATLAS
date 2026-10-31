# Monitoring fault review and one-attempt recovery procedure

Prepared 2026-10-31. **Not executed. Separate execution approval required.**
This is a supervised procedure using the existing guard and activation sampler,
not a new observer. Do not rerun either historical installation command.

## Evidence and current state

- 2026-10-30 20:45:27 IST: exporter started successfully.
- 2026-10-30 21:47:56: watchdog rejected a condition and exited 78/CONFIG;
  exporter stopped. The retained journal has no specific rejection predicate.
- 2026-10-31 09:34:08: startup refused the retained latch. The old guard
  overwrote the original reason with the later refusal. Original predicate,
  rejected resource/safety values and original fault boot ID are **UNKNOWN**.
- Last-health at 21:47:45 is an earlier healthy observation, not the rejected
  sample. It cannot establish whether CPU, telemetry, firewall or another gate
  triggered the failure. Reboot refusal is confirmed; boot ordering as the
  original cause is not confirmed.
- Owner-provided installation result: first-fault guard installation PASS;
  retained state hashes, service identities and firewall unchanged; exact
  original guard backup available. This fixes evidence loss, not the cause.
- Read-only check 2026-10-31 11:20:40–11:20:53 IST: firewall failed, watchdog
  and exporter inactive; all three MainPID=0, NRestarts=0; no TCP 9118 listener.
  Exporter remains enabled with Restart=on-failure.
- Dashboard observations: CPU 62.5–63.2%, RAM 62%, temperature 62 C;
  stop_latched=true, manual_only=true, commission_armed=false; linear/angular
  commands and motor speed zero. Encoder counts [114,-138,-155,-178], unchanged
  from installation; interval deltas all zero. MCU LIVE, packet age 0.035 s;
  policy/command ages 0.1 s, encoder observations 0.0 s.
  These are current software observations, not a new physical motion test or
  a substitute for the execution-time one-second resource sampler.
- Recovery PID 1982/NRestarts 0, dashboard 2064/0, MCU 3487/1, all active.
  The MCU restart count was already present. No services changed in this review.

Live hashes re-read successfully:

| File | SHA256 |
|---|---|
| /usr/local/libexec/atlas-monitoring-guard.py | 27d4cacae47044a1675cf911aad60a69fc78dd5b85de14bdb6d5480288a560e1 |
| /opt/atlas-monitoring-exporter/atlas_health_exporter.py | 0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d |
| retained FAULT.json, verified by installation result | 3715b150b880ed06d9e21f25006b81a699693328bb77a80155cf148dcdb1ae97 |

Root-only state was not reread over SSH: its latest verified hashes come from
the owner's installation result. A fresh privileged comparison is mandatory
before reset. Any difference requires review, not replacement of the expected
hash. The original state copy is under
`/var/lib/atlas-first-fault-install-08439e1/original-state/`.

## Execution gate and bounded sequence

Approval must explicitly accept an **UNKNOWN original trigger** for one observed
recovery attempt. A healthy current sample alone does not explain the old fault.
Administrator authentication is local Jetson terminal only.

1. Recheck hashes, root-owned file modes, original unit configuration/enabled
   state, complete firewall rules and monitoring unit/PID state. Reject any
   running monitoring process, listener, unexpected table/rule, package drift,
   or unknown state file. Preserve a timestamped, root-only before manifest.
   Verify the Windows source is still 192.168.1.6, Jetson 192.168.1.16 on
   wlP1p1s0. Do not modify Tailscale or other tables.
2. Use the existing `activate_timestamp_retry_once.sample(..., protected=False)`
   and guard validation for three consecutive one-second preflight samples.
   Keep the existing CPU 75%, RAM 80%, temperature <70 C, freshness, E-STOP,
   manual-only, uncommissioned, command-zero and unchanged-encoder predicates.
   Admission requires CPU <75% and RAM <80%. Missing/nonfinite data rejects.
   Reuse the function only: do **not** invoke its old installation `main()`.
3. All monitoring units must remain inactive. Take the existing operations and
   evidence locks nonblockingly. Create a unique root-owned 0700 archive once;
   reject an existing attempt directory. Copy every regular state file with
   metadata, excluding no evidence, and current boot ID, unit configuration,
   rules and relevant journal. Refuse symlinks, special files, unexpected files,
   more than 64 state files or more than 1 MiB of state. Bound journal output to
   150 entries/1 MiB. Never rotate/delete the old archive to make room.
4. SHA256 every copied file and compare source/archive byte-for-byte. Fsync files,
   manifest and archive directory. Record an approval/attempt identifier and the
   reset reason, explicitly UNKNOWN original trigger. Disk/write/verification
   failure means **no reset**. The evidence archive is local/private, never Git.
5. Before reset, arm and verify an independent systemd expiry timer, maximum
   360 seconds, using the existing guard `rollback` action. Save the timer
   identity. The terminal supervisor has a 330-second limit, preserving time
   for cleanup. A failed timer registration means **no reset**. Do not cancel
   expiry on an exception, disconnect or missing PC confirmation.
6. Apply a dedicated runtime-only exporter drop-in containing `[Service]` and
   `Restart=no`, followed by system daemon-reload; verify effective Restart=no.
   Save the original policy. This prevents an automatic second exporter start.
   No existing unit file is replaced and no rover/user unit is reloaded.
7. Recheck unchanged source hashes under the locks. Remove only the verified
   `FAULT.json` and stale `observer-active.json` from active state, after durable
   archival; fsync the state directory. Preserve other state files. Release
   locks before starting units. This is the single authorized rearm, not a
   general reset command. A second rearm in the same attempt is prohibited.
8. Start only monitoring firewall with `systemctl --no-block start`; continue
   one-second safety samples during startup. Require completion within 10 s
   and use existing `guard.verify_firewall()` to verify the exact inet table,
   input priority/order, permitted IPv4 source/interface/destination and the
   following TCP 9118 DROP (including other sources/IPv6). Failure aborts.
9. Start only the exporter with `systemctl --no-block start`; its installed
   Requires/BindsTo/After dependencies start the watchdog and prevent exporter
   readiness before guard validation. Keep the supervisor's one-second sampling
   active during startup; require startup within 25 s, watchdog healthy, no
   latch, stable PIDs and no restart increments. No blocking start may suspend
   safety sampling. At most one start request per optional unit, no retries.
10. Observe for 300 s from the first start, within the overall deadline, using
    the existing guard's protected sampling. Persist samples incrementally and
    preserve the rejected sample/reason. Verify PC Prometheus target freshness,
    real timestamps/values, Grafana and missing-value handling via existing
    queries. Do not induce failures or increase scrape frequency. Capture CPU,
    RAM and temperature baseline/active measurements without attributing all
    aggregate change to exporter overhead; use existing unit CPU/memory counters.
11. A supervised success requires complete local safety evidence AND PC
    verification before expiry. Restore only the temporary restart drop-in,
    daemon-reload and verify original policy without restarting. Verify protected
    service identities and unrelated firewall rules are unchanged. Only then
    cancel the expiry timer and leave monitoring active. Missing evidence or
    operator disconnect is not success: allow cleanup, report FAIL/PENDING.

## Failure cleanup and rollback

The existing watchdog fail-closes on rejected safety data; exporter BindsTo and
WatchdogSec protect observer failure. The independently armed timer bounds the
attempt if the supervising process dies. No new ROS node is involved.

Existing cleanup primitive (only after execution approval):

```sh
sudo /usr/bin/python3 -I -B /usr/local/libexec/atlas-monitoring-guard.py rollback
```

It disables/stops the optional exporter, stops the monitoring watchdog, proves
exporter PID=0 and no 9118 listener, then stops the monitoring firewall unit and
removes only its owned, exactly verified table. It refuses table deletion if a
listener remains or ownership/rules differ. Never flush tables or bypass this
refusal. In that case keep protection and report manual intervention required.

Preserve any NEW FAULT.json and events. If cleanup leaves no fault, restore the
old archived FAULT.json atomically and verify its recorded SHA256 before restoring
enabled state. Do not overwrite a new fault with the old one. Thus every failed
attempt remains latched. Preserve the original archive and a separate failed
attempt record; unknown original evidence stays available byte-for-byte.

After successful shutdown verification, remove only the attempt's runtime
Restart=no drop-in, daemon-reload, and confirm the original Restart=on-failure.
Restore the recorded enabled state with `systemctl enable` **without --now**,
only after a fault latch is verified present. No monitoring or rover restart.
The archival record is intentionally retained, not rolled back. No application
file, original guard, safety configuration or unrelated firewall rule changes.
If cleanup is interrupted, retain the safer stopped/disabled state and timer;
do not claim original policy restoration until verified. Never auto-retry.

## Validation and remaining execution risks

Focused existing tests: `test_monitoring_persistent.py -k 'fault or rollback or
latch'`: **10 passed, 32 deselected**, Ubuntu 22.04, 2026-10-31. They exercise
first-fault persistence, repeated refusal/simulated reboot, corrupt evidence,
rollback ordering and listener-retains-firewall behavior. Existing unchanged
42-test guard evidence is reused; no unrelated suite rerun.

This document changes no executable. The complete archive/rearm/expiry sequence
above has **not** been executed or tested end-to-end as an automated package.
Existing activation main refuses an installed, fault-latched system and must
not be reused. A small reviewed transaction wrapper is still required before
issuing a single execution command; reuse its sampler/guard/rollback, not its
installer. Focused wrapper tests must cover archive failure/no reset, changed
latch/no reset, second invocation rejection, SIGKILL/expiry, new-fault retention,
startup failure, listener retention and exact policy restoration.

**GO: fault review and procedure preparation. NO-GO: execution today.** Remaining
gate is that wrapper's offline validation plus fresh privileged state comparison,
not more CPU diagnosis or live experimentation. No latch reset, unit start,
firewall modification or deployment took place during preparation.

Required subsequent owner approval: ONE archival/rearm and bounded monitoring-only
recovery, acknowledging UNKNOWN original cause; only optional firewall/watchdog/
exporter starts, temporary monitoring-only Restart=no override/system daemon-reload,
independent expiry, failure cleanup and conditional persistence after verification.
No ROS/Recovery/camera/controller restart, movement, firmware change or PR merge.
