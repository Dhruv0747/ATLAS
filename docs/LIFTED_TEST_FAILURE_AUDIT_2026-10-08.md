# Lifted commissioning failure audit — 2026-10-08

## Operator remote-drive follow-up, 2026-10-09 ~10:54 IST

The operator manually drove with wheels lifted and reported M3 physical
rotation. Two read-only owner-status samples taken during the same nonzero
four-wheel output `(85,-85,85,-85)` showed M3 raw encoder counts changing
from -1379 to -7058. This confirms **M3 encoder data is arriving**, correcting
the earlier impression that it had no reading. Over that sampling interval,
M1 changed +24823 and M2 -24395 counts, while M3 changed -5679; the measured
M3 speed was 0.0 then 0.193 m/s versus roughly 0.94–1.21 m/s for M1/M2.
Sampling was not a controlled equal-speed calibration, so the difference
cannot diagnose a specific mechanical or electrical fault. After the operator
released the joystick, status showed zero applied outputs and zero measured
speeds. No repeat motion test, calibration or navigation-authority change was
made. M3 remains an interval-by-interval dynamic-consensus candidate, not a
permanently excluded or independently qualified encoder.

## M3 attempt, 2026-10-09 ~10:37 IST

The operator confirmed all wheels lifted and clear, charger disconnected and
physical cut-off ready. A temporary per-process raw-commissioning gate was
enabled with the software stop still latched. The owner reached `LOCKED` and
accepted no-motion heartbeats. The operator could not release the software
stop; before any pulse, the client aborted on `bms_telemetry_stale` and sent
best-effort stop/abort/exit. Its evidence is on Jetson at
`~/.local/state/project_atlas/lifted_pid/20261009T050714Z_4b78c131e0537658.jsonl`.
The recorded session has no pulse request or `PULSE` state. The operator later
reported that M3 spins under their separate manual control. That confirms
physical response, **not** the reliability or sign of M3 encoder feedback.

Jetson connectivity then dropped. The operator cut motor power and rebooted
Jetson. On reconnection, the temporary raw-test drop-in was moved to
`/home/jetson/project_atlas/data/deploy_backups/20261009_lifted_timing/98-lifted-m3-test.conf.disabled`,
and only the user motor-owner service was restarted. Final live status was
`IDLE`, raw interface disabled, software stop latched, all outputs zero,
`final_zero=true`, with service active and NRestarts=0. No M3 encoder
qualification or autonomous authority was granted. The BMS freshness fault
and reason for the connectivity loss remain to be diagnosed separately.

## Rejected-only delivery probe, 2026-10-09 ~10:30 IST

With operator confirmation that charger was disconnected, all four wheels were
securely lifted and clear, and the physical motor-power cut-off was ready, the
tested timing-only `yahboom_base.py` was deployed from a recoverable backup and
only `rover-base-telemetry.service` was restarted. Raw commissioning remained
disabled, stop latched and applied outputs zero. The new probe sent only
`{"op":"probe","seq":N}` requests, which are rejected by the owner's raw-
interface gate before any commissioning state transition. No `enter`, `arm`,
`pulse`, drive or steering command was sent.

One initial request and a subsequent five-request batch were all received and
rejected as `raw_lifted_interface_disabled`, with `IDLE`, stop latched and
`final_zero=true`. The batch send-to-owner times were 262.0, 48.8, 13.3,
6.6 and 20.7 ms; owner-receive-to-status times were 2.3–2.9 ms. The initial
request took 142.8 ms send-to-owner. Afterwards the user motor service was
active (PID 44109, NRestarts=0). The initial system-wide `systemctl` check
looked for the unit in the wrong scope; `systemctl --user` confirmed it was
active throughout. This is a **PASS for stopped request delivery**, not proof
that a 0.5-second armed heartbeat lease, powered M3 encoder response, or
autonomous navigation is reliable. Those gates remain open.

Live backup: `/home/jetson/project_atlas/data/deploy_backups/20261009_lifted_timing/yahboom_base.py.before`.
Rollback if this diagnostic owner causes a regression: restore that file to
`/home/jetson/project_atlas/scripts/yahboom_base.py`, then run
`systemctl --user restart rover-base-telemetry.service` while ATLAS is safely
stopped. The rejected-only probe was run from the backup directory and is not
an autostart service.

## Follow-up: passive ground check, 2026-10-09

With ATLAS stationary on the ground and software stop latched, a subscription-only
probe ran for 60 seconds. No publishers, services, serial access, motor commands,
steering commands or service restarts were used. Raw commissioning stayed disabled.
After discovery, topic reception covered approximately 54–55 seconds:

| Signal | Samples | Maximum observed age/gap |
| --- | ---: | ---: |
| Control policy reception | 565 | 0.137 s inter-arrival |
| Lifted status reception (IDLE only) | 560 | 0.124 s inter-arrival |
| Cached encoder sample | 560 | 0.263 s age (none over 0.35 s) |
| Receive-thread encoder sample | 560 | 0.0475 s age |
| Encoder health reception | 554 | 0.138 s inter-arrival |

Serial encoder packet counter advanced 5730 → 7078, with checksum errors and
write errors both zero throughout the observed health messages. All sampled
outputs were zero and stop remained latched. Temperature at the initial check
was approximately 58 C. Base service reported active with zero automatic restarts.

Result: PASS for this limited passive stationary observation, **not** for an
active commissioning session, powered encoder response or autonomous driving.
The unresolved client/owner heartbeat path still needs no-motion qualification
without asserting that a ground-supported rover is lifted. No hardware changes
or air lift are needed for continuing passive diagnostics.

## Conclusion

### Subsequent live check, 2026-10-09 09:21–09:24 IST

The BMS alternated healthy reads (13.20 V, reported SOC about 95–96%) with
eight-second Bluetooth timeouts. Added stage-only error labels to
`atlas_daly_transport.py`; all twelve Daly offline tests passed. Deployed this
helper after checking the existing live source, syntax-checked it on Jetson,
and restarted only `rover-daly-bms.service`. Failures at 09:23:35, 09:23:54,
09:24:02 and 09:24:10 explicitly identified **connect**, before MTU/data parsing.
One healthy read at 09:23:44 does not establish stability. An additional service
restart occurred during observation; sensor recovery was active. No evidence
yet distinguishes phone contention, radio conditions or Bluetooth stack faults.

Final owner sample: IDLE, stop latched, raw interface disabled, all outputs
zero; cached encoder age 0.093 s and receiver age 0.003 s. BMS was unhealthy.
Base PID 3120 and NRestarts=0; this work did not restart the motor owner or
change steering. No motor test was attempted. The heartbeat investigation and
powered M3 qualification remain open; do not count this as either passing.

Rollback of the diagnostic-only change (does not repair the link): restore
`/home/jetson/project_atlas/scripts/atlas_daly_transport.py.pre_stage_audit_20261009`
to `atlas_daly_transport.py` in that same directory, then run
`systemctl --user restart rover-daly-bms.service`.

The repeated attempts have not established an M3 hardware failure. All six
available JSONL sessions from today contain **zero pulse requests** and no
observed nonzero applied outputs. The commissioning pipeline has encountered
several independent readiness, transport and scheduling defects before motion.
M3 rotation/encoder-direction reliability therefore remains unqualified.

This audit changed no rover controls, safety thresholds or live services.
Source baseline: `7e35614`, branch `agent/fix-mapping-footprint`.

## Recorded failure sequence

Evidence directory on Jetson: `~/.local/state/project_atlas/lifted_pid/`.
Times below are UTC, as encoded in the filenames (add 05:30 for local time).

| Session prefix | First failure | Interpretation / status |
| --- | --- | --- |
| 20261008T094506Z | fresh_latched_stop_required | Owner did not see required fresh stop state; not an encoder test. |
| 20261008T101458Z | control_policy_stale | Original policy cadence left inadequate margin. Publishing changed to 10 Hz; later scheduling failures mean end-to-end delivery is not qualified. |
| 20261008T110222Z | bms_unhealthy | Entry occurred before healthy battery readiness. Client preflight added. |
| 20261008T114102Z | no_active_session | Consistent with lost initial entry during discovery; subscriber matching added. No proof the motor board failed. |
| 20261008T114226Z | bms_telemetry_stale | Fixed waits produced roughly 11.3-second polls against a 10-second freshness limit. Bounded response-driven polling deployed; short probes improved, endurance not proven. |
| 20261008T131845Z | motor_controller_link_lost | Safety checked cached encoder freshness. This error does not distinguish a physical serial outage from delayed ROS processing. |

Client enter/heartbeat send gaps in those six logs were at most 0.236 s.
These timestamps show client send attempts, not owner receipt/execution times.
They cannot prove middleware delivery or exclude executor delay.

Separate no-motion diagnostic trials subsequently aborted on stale policy and
heartbeat expiry. Their summarized observations were captured in tool output;
the temporary observer did not persist a complete request/receive timing trace.
This is an evidence gap, not grounds to declare a specific DDS defect.

## Confirmed findings

1. **Cached feedback can lag a healthy receiver.** One stationary observation
   had cached age 0.536 s while receiver age was 0.005 s. Normal-mode 30-second
   observation: 292 samples, maximum cached age 0.177 s and receiver age 0.049 s,
   outputs zero. Thus the generic link error is insufficient evidence to replace
   an encoder, motor controller, USB cable or battery.
2. **Safety and telemetry share the base's single-threaded ROS executor.**
   `_publish_board_state` refreshes the cached encoder sample, while safety
   callbacks consume it via `_lifted_snapshot`. The receive thread can remain
   healthy while callback processing is delayed. Profiling observed keepalive
   callback duration up to 0.165 s and board-state duration up to 0.096 s.
   These measurements identify timing exposure, not the unique cause of every
   missed deadline.
3. **Discovery contention is real.** GNSS repeatedly probed under the shared
   exclusive discovery lock while motor startup reported `USB discovery busy`.
   Pausing GNSS during base restart restored startup. GNSS was then restored.
   That workaround is not a permanent fair-retry/backoff solution.
4. **The host was busy, but neither RAM exhaustion nor overheating was shown.**
   One snapshot had load average 38.60; vmstat samples showed 73–81% aggregate
   CPU busy, about 2.3 GB available memory, no swap use, and temperature near
   62 C. Load average is not CPU percentage. These observations do not prove
   the Jetson is incapable of running ATLAS.
5. **The diagnostic harness also needs repair.** Its ROS shutdown hung after
   exiting the session, delaying the enclosing shell's normal-mode restoration.
   The observer process was terminated, restoration completed, and IDLE,
   zero outputs, stop latched and raw testing disabled were verified. Future
   harnesses need bounded shutdown plus unconditional restoration/verification.

## What earlier attempts got wrong

Repeated powered-test preparations were attempted before the complete no-motion
commissioning channel was qualified. Each prerequisite fix uncovered another
failure; those are not six failed M3 rotation tests. Describing the generic
link-loss message as a confirmed USB disconnection was too strong. Likewise,
passing offline tests is not proof of live timing reliability.

Duplicate service-call coalescing failed its stationary check and was reverted.
The five-second continuous readiness gate is retained as a fail-closed startup
improvement; a later heartbeat failure proves it is **not** the final timing fix.

## Required next work, in order

1. Build a bounded no-motion harness that records sequence, client send time,
   owner receive time, callback start/end, actual serial packet timestamp and
   fault snapshot. Use a common host monotonic clock. Persist evidence before
   shutdown and verify cleanup even on timeout. Never send arm/pulse during
   this audit stage.
2. Identify whether remaining delay is client scheduling, DDS delivery, owner
   executor scheduling or a blocking callback. Do not relax freshness/heartbeat
   limits to conceal it, and do not automatically disable essential sensors.
3. Make one measured change to the responsible path. Add regression coverage
   and compare under the same normal workload. Preserve sole motor ownership
   and emergency-stop priority if telemetry is separated from critical work.
4. Proposed acceptance: three 60-second no-motion commissioning sessions,
   zero unexpected aborts, zero motor outputs, unchanged safety deadlines, and
   verified cleanup. Deliberately missing heartbeat must still abort. Preserve
   each result and exact revision; these gates have **not** passed yet.
5. Only then request one bounded M3 pulse with fresh operator readiness and
   battery/clearance checks. Do not ask the user to repeat a route or recalibrate
   steering to solve this software test-channel problem.

Oct9 source-only preparation: the client evidence now records the monotonic
instant before each request publish; the motor owner would include the last
request callback-receive time and each status-publish time. Its sequence ack
already correlates requests and statuses. These fields allow common-host
send→receive and receive→status comparisons without relaxing the heartbeat
lease. The motor-owner change is **not deployed**, raw commissioning remains
disabled, and no no-motion endurance or lifted motor test has passed from this
source change alone.

## Source control and deployment scope

At audit start the local working branch was seven commits ahead of its remote.
The main branch also had unrelated upstream changes; this audit does not merge
or reset them. Synchronize the existing working branch by ordinary fast-forward
push, then verify hashes and ahead/behind. Do not claim the default main branch
or a PR has been updated by pushing this branch.

Raw logs, temporary probes, credentials and generated artifacts are deliberately
excluded from Git. The audit, production changes and regression tests are the
items intended for synchronization. GitHub synchronization is distinct from
Jetson deployment and from hardware validation.
