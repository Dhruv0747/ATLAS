# Explicit lifecycle cache experiment — not deployable

## Scope and decision

Follow-up to commit 93de0ba. PC-only native ROS Humble testing, in the existing
private network namespace, Domain 216, localhost only. No Jetson connection,
production installation, restart, camera start, movement or safety change.
Voice, white glass UI and production CPU75%/RAM80%/70C limits are untouched.

This tests an explicit executor-cache lifecycle prototype, NOT a patched FastDDS
RMW library. It rebuilds the static executor only at known, serialized entity
mutation boundaries. It is not an automatic interception of Nav2 entity changes.
**No deployable CPU fix is established. Both candidate paths are rejected.**

## New evidence

1. Pre-destruction invalidation releases the old executor cache. Subscription
   removal passes (unlike the previous stock-static failure), but delivery after
   subscription recreation fails within the one-second fixture bound.
2. Adding a second invalidation after creation (a committed new generation)
   still fails recreated delivery. Standard control passes 21 deliveries and
   heartbeat failure detection in 0.396 s in this comparison.
3. Explicitly detaching enumerated callback groups before removing nodes fails
   with `Callback group needs to be associated with executor.` Standard control
   passes and detects heartbeat loss in 0.398669 s in this comparison.

The first pre-only variant's standard control detected failure in 0.397939 s.
All candidates passed the original 20-message initial delivery before reaching
the mutation failure. Candidate timer/bond stages are NOT claimed to pass.

Confirmed: cache invalidation alone does not preserve the required ROS entity
dispatch behavior; public group enumeration/removal also exposes an ownership
incompatibility in this attempted rebuild sequence. Unproven: the exact internal
collector/association defect. A stale callback-group association is a hypothesis,
not a verified upstream root cause. Do not force-reset association flags or mask
the exception to manufacture a pass.

## Reproduction and CPU gating

Use the existing native build and isolated runner described in
ATLAS_NATIVE_ROS_ENTITY_BOND_TEST_20261024.md:

```
bash project_atlas/tools/diagnostics/native_ros_entities/run_isolated.sh --explicit-lifecycle
bash project_atlas/tools/diagnostics/native_ros_entities/run_isolated.sh --explicit-groups
```

First command retains pre/post mutation invalidation; second additionally attempts
explicit group detachment. Expected nonzero failure exits preserve the evidence.
No production topic, configuration or library is modified. Build uses -O2 and
-Wall/-Wextra/-Werror with the privately extracted bondcpp dependencies.

The existing interleaved CPU stage remains after correctness gates and is not
reached. **No new CPU savings measured; no whole-Jetson savings or Astra readiness
claim.** Rebuild cost is not evidence of an improvement.

Final CLI-dispatch regression after separating the two reproducible modes:
`--explicit-lifecycle` exits 1 at recreated delivery (standard heartbeat 0.358978s);
`--explicit-groups` exits 1 at group association (standard heartbeat 0.399926s).
Both built successfully; failures are deliberately visible, not converted to passes.

## Next necessary engineering work

Trace exact static-collector callback-group association ownership in the matching
Humble source and test invalidation inside that owner, rather than reconstructing
executors around it. Any real RMW retention candidate must separately prove
entity lifetimes, wakeups, concurrent teardown, services/QoS and bond behavior.
Only then run matched CPU measurements, including mutation costs. No driving or
live installation is necessary or requested for this next step.

Changed files: offline fixture, this report, README, CHANGELOG and blocker note.
Rollback: no ATLAS rollback needed; no deployable package produced. Preserve the
working production executors. Offline changes can be reverted as a normal Git
commit without touching live services or raw diagnostic evidence.
