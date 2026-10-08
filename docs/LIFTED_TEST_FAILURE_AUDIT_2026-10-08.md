# Lifted commissioning failure audit — 2026-10-08

## Conclusion

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
