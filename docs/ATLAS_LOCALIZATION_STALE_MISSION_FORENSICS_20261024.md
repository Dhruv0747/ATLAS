# Stale mission-status investigation, 2026-10-24

## New verified findings

Read-only retained user journal shows original PID1948 stopped at06:55:59;
replacement started06:56:00; rollback stop requested06:56:11. At06:56:12,
candidate PID274997 was still inside `Monitor.__init__`, constructing
`ManualLocationCheck`, specifically creating `/atlas/location_check/cancel`.
Its context became invalid following the stop request. The optimized spin call
comes AFTER `node = Monitor()`: it had not executed in this process. Therefore
the stale telemetry is not evidence of the candidate executor dispatch failing.
The context-invalid traceback at rollback is consistent with shutdown during
construction, not evidence of an independent pre-stop startup exception.

Original PID1948 also logged ExternalShutdownException followed by a second
shutdown error on exit. Traceback source text can reflect the replaced file on
disk; do not interpret its displayed import line as code the old process ran.

The localization monitor publishes `/atlas/localization_check`, not mission
status. Repository mission control publishes `/atlas/mission_status` on a1s
timer. Dashboard stores callback receipt wall-time and computes age from it.
Thus stale dashboard mission status alone cannot distinguish delayed publisher,
DDS delivery, subscriber callback, or wall-clock effects.

Mission-control service was observed active PID1901/restarts0 during this
read-only investigation. Its journal had no entries in06:55:50–06:56:20; absence
of log entries does not prove timely publication. Previous deployment omitted
this service from its identity comparison.

CPU during settling reached100%. Resource contention coincided with the failure,
but no original failed snapshot, mission source timestamps, publisher callback
trace, per-process startup CPU or scheduler trace was captured. Exact cause of
the freshness loss remains **unresolved**. Do not relax the2s freshness check,
extend settling blindly or retry installation based on these findings.

## Newly supplied profile

Retrieved `evidence-hsn1ccyq` from the existing localization-cpu-20261024 directory.
Profile SHA256 matches owner and remote:
`72c21e1edd89b9cf4a55f44cf92d47d012abd3f895f279405d967cb74262d98c`.
This is restored original PID275216, NOT candidate startup.

- Main thread199 samples:159 leaf samples at executor wait line678.
- Background search147 samples:129 at pacing sleep line25,10 at coarse scores
  line214,6 at NumPy sum,2 elsewhere. Sleeping samples are not CPU attribution.
- Main-thread kernel tick delta211 over19.0221s at100Hz:11.0924% of one core.
- Whole-system20 samples mean73.2595%, peak81.0580%.
- Profile reports unchanged protected services before/after.

This new profile confirms a background search existed in this later capture,
unlike the earlier profile, but does not prove it caused the restart incident.
No new profiler, ROS participant or recording was launched by this investigation.

Private local evidence: `artifacts/localization_profile_after_rollback_20261024/`.
result.json SHA256 `fab65334e249efdff859ed13b0fd94d58b0175ccb8ebc728fb77e8c29440cb18`;
telemetry.jsonl SHA256 `1863545c40c0f99fee317e0ed0b888eefe60dbb4ab4fe73251d19674917d9d19`.
Read-only journal observations above remain in task transcript; no raw logs committed.

## Minimal verified offline correction

Changed only the deployment diagnostic tooling and its tests:

- Persist bounded sensor receipt ages, mission READY predicate, available receipt
  timestamp/rate, phase and monotonic acquisition/check times BEFORE validation.
- Preserve failure evidence and re-raise the original exception without retry,
  refetch or converting a failure into success.
- Timestamp all trace events, including failure, not just CPU samples.
- Include mission-control identity in protected-service comparison.
- No raw sensor arrays, private mission text or unlimited payload copies logged.

This corrects a confirmed evidence-loss defect, not the unresolved runtime
freshness loss. Production guard/probe files, monitor, voice and UI are unchanged.

11 offline tests pass, including real probe code extracted without executing
ROS: mission age2.0 passes;2.001,missing,negative andNaN fail. Tests verify exact
failure age, original exception identity, one checker invocation, success return,
bounded logging and retained service/safety protection. Diff whitespace passes.
No CPU savings or live fix claim; no repeat deployment or camera test.

## Next necessary action / rollback

Keep the original live monitor. A future separately approved bounded deployment
must use enhanced evidence and startup-specific attribution before changing
resource policy or retrying the executor candidate. Existing data cannot locate
the delayed mission-status boundary exactly. No further manual drive is needed.
This offline tooling was not installed; rollback is reverting its repository
commit. Existing production backup remains in the prior deployment evidence
directory. No service, camera, calibration, safety limit or motor changes made.
