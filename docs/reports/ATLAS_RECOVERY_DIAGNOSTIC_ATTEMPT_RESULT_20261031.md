# One diagnostic Recovery restoration — 2026-10-31 result

Reviewed source fdae8b6; manifest674b15132d1f1a6db7278957e0539f9815a37890e6a1ed652fe063b6f74a4f3c.
Exactly ONE approved attempt. **FAIL; incident OPEN; Recovery STOPPED.** No retry.

## Execution and failure

Original live code and independent backup both verified SHA256
5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Package hashes passed. Original Restart=always, PID0, no pending job and no policy
conflict verified. Fresh three-sample safety admission passed, then independent
observer windows passed before the one start. No source file replacement occurred.

IST timeline:
-08:35:24 diagnostic supervisor started, PID364710.
-08:35:26–28 admission CPU55.7265%,60.7744%,60.0332%.
-08:35:29 first observer window74.1176% (before Recovery started), then59.6346%,
 60.2349%,60.3679%. No CPU threshold rejection was recorded.
-08:35:32.635 start intent durably reserved; Recovery started once PID364817,
 birth tick5693803. Identity observed monotonic56938.134189088.
-08:35:33.539 first saved sample spanning Recovery startup: CPU68.7291%,
 collection54.737ms. Target PID and actual cgroup attached successfully.
-Next scan exceeded the existing150ms collection budget while iterating PIDs.
 Observer health became FAILED at mono56940.100210326. The scanner raised before
 returning its sample, so that failing interval's partial CPU/PID data was NOT saved.
-08:35:34 systemd began stopping Recovery;08:35:36 stopped, lifetime CPU1.888s.
-08:35:37 supervisor exited FAIL; independent ExecStopPost cleanup completed.

This was a collector deadline failure, NOT a measured CPU>75% rejection. The
failed interval's aggregate CPU, process deltas and duration beyond150ms remain
unknown. Do not assume CPU was safe, overloaded or that the delay was harmless.
Observer scheduling contention and scan work are possibilities, not proven causes.

Recovery did not reach verified READY. The maintenance-coordination initialization
message and invalid-context publisher exception occurred AFTER stop had begun;
this is not proof of an independent firmware/sensor fault or a CPU hot function.

## Retained attribution

The first startup sample retained:
- Recovery PID364817:45user+21system ticks at100Hz =0.66CPU-s cumulative since birth.
- Recovery cgroup inode17612, CPU1.012406s cumulative; includes service-group work,
 not just the final Python PID. Do not sum process and group CPU or treat this as
 a full measured interval delta (the group was initially absent).
- Concurrent localization:18.5967% of one core over1.021158s.
- Concurrent Dashboard:39.3244% of one core over1.021161s.
- Command mux:17.2375% of one core over1.021171s.
- Observer cumulative CPU through this sample0.3921176s.

Earlier completed collector scans34.3–54.7ms. Raw first-interval PID/cgroup evidence
was captured, but the NEXT failing scan was lost. This demonstrates a remaining
failure-evidence gap under startup contention. No complete attribution or cause
of the historical93.624% overload is claimed.

Eight completed safety samples: peak CPU74.1176%, peak RAM62.5845%, peak temperature
63.0C. Those peaks exclude the incomplete rejected scan; not whole-attempt maxima.

## Verified cleanup and safety

Recovery PID0, ActiveState failed (STOPPED), Restart=always, NRestarts0, no pending
job. Original code hash unchanged; current systemd unit text exactly matches saved
preflight original-unit.txt. Temporary Recovery override absent.
Transaction activation=true, rollback=false, restored=true; cleanup records one
start attempt and policy RESTORED. No additional start or restoration retry.
Recovery PID364817 and diagnostic PIDs364710/364744 absent from /proc.

All41unrelated atlas/rover unit identities, states, cgroups and restart counts
unchanged. Initial raw postflight comparison was false because it included the
owned diagnostic supervisor transitioning from active to failed. Inspection showed
that was the ONLY changed entry; the explicit comparison excluding Recovery and
its owned supervisor is saved in protected-service-comparison.json. No unrelated
service change was hidden.

Fresh independent postflight CPU59.6284%, RAM58.4308%, temperature63.0C, telemetry
packet age0.018s; E-STOP latched, zero commands, stationary encoders and policy
checks PASS. Astra OFF with two empty driver inventories. No inference, controller,
firmware, motor, mapping or Vision Lab changes.

The owned supervisor runtime unit was hash-verified, confirmed PID0, removed and
user daemon-reload completed. No critical service restart. Saved package and
ATTEMPT_USED retained. Cleanup result is VERIFIED; restoration result is FAIL.

## Evidence / next action

Private evidence with verified EVIDENCE_SHA256SUMS:
Jetson /home/jetson/project-atlas-migration/recovery-startup-diagnostic-20261031
PC C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/recovery-startup-diagnostic-evidence-20261031
Contains original config, transaction, target identity, start intent, all completed
samples, journals, postflight and cleanup records. Raw telemetry is not committed.

**NO-GO for another start now.** Next work must be offline: preserve already-read
aggregate/partial process counters when collection times out and inspect whether
the /proc evidence collector can remain bounded without delaying independent
safety rejection. Do not raise CPU or collector limits or repeat starts to obtain
more evidence. No corrective code change was made during this approved execution.
Recovery's central fault-recovery functionality is still unavailable. Keep the
incident open until original Recovery is actually READY and independently verified.
