# First-fault preservation — offline correction, 2026-10-31

Original watchdog rejection occurred October 30 at 21:47:56. Its original cause
remains UNKNOWN. The October 31 boot refusal replaced its reason. This patch
cannot recover that lost evidence and does not clear the existing latch.

Changes limited to guard.py: first FAULT.json is retained, including legacy or
corrupted bytes; later refusals use fault-events.json (last 16 events, maximum
64 KiB). A nonblocking flock serializes fault writers. Existing atomic writes
retain fsync, atomic replacement and directory fsync. First fault is committed
before any subsequent-event work. Disk errors propagate; main still stops the
optional exporter in its existing finally path and no_fault still rejects.
Broken latch symlinks now also reject. Corrupt history is preserved, not repaired.
No automatic reset, rotation or deletion of the first latch is permitted.

Evidence records wall time, monotonic time, boot ID (null if unavailable), action,
reason and whitelisted currently observed safety data: resource samples, topic
ages, policy booleans, command values, speed and encoder counts. Missing/invalid
values are null, never healthy defaults. Observation context resets every sample
and new invocation, so prior healthy samples cannot impersonate rejected data.
Raw API payloads and arbitrary exception text are not recorded. Existing limits
and validation predicates are unchanged. Atomic temporary files are fixed-name
and bounded by the same payload sizes. Storage failure cannot guarantee durable
evidence; it still rejects and retains any previously committed records.

Validation: focused test_monitoring_persistent.py only, 42 tests PASS. Includes
first-fault/repeated refusal, fresh-module persistence across simulated boot,
corrupt first latch/history, broken symlink, atomic-write failure and redaction.
Existing guard threshold, API timeout and rollback tests are in that same suite.
No real reboot, firewall operation, service restart or Jetson command executed.

GO for separately approved correction preparation/deployment after checking exact
live guard hash and preserving root-owned state and original guard bytes. NO-GO
for activation or fault clearance: those require separate evidence review and
approval. This patch alone will not restore monitoring.

Rollback (not executed): restore only the exact pre-install guard.py backup with
its original ownership/mode and verify SHA256. Preserve FAULT.json, events and
all prior state; never delete/clear evidence as rollback. Do not restart any
unit or remove firewall protection as part of this offline patch. The old guard
can overwrite fault evidence on a future invocation, so retain archived evidence
and obtain separate approval before running it. No package hashes from earlier
activations may be reused for this changed guard.
