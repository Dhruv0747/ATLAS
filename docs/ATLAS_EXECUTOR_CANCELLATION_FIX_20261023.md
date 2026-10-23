# Offline cancelled-task correction and CPU retest

## Confirmed defect and bounded correction

The captured Jetson executor removes done/cancelled tasks from `_pending_tasks`
before draining `_ready_tasks`. A cancelled or externally completed task can
still be in that ready queue. Looking it up in the pruned dictionary raises
KeyError. This is reproduced with the original exact source, not inferred from
the CPU samples. No evidence establishes this as the cause of live CPU overload.

The correction checks `task.cancelled() or task.done()` immediately after popping
the ready task, before dictionary lookup. It skips only terminal tasks, does not
catch arbitrary KeyErrors, and leaves healthy callbacks and their exceptions
unchanged. The same guard is present in the PC's installed Humble executor.
This is not a general claim that every possible concurrent executor race is fixed.

The offline transformer in `benchmark_executor_counts.py` now produces two
independent candidates from the hash-verified captured original:

| Variant | SHA256 |
|---|---|
| Captured original | e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010 |
| Cancellation guard only | d005c1f91ab6e88e74c8f3f062ff5fc750264dff00a2f8217c81cbb7a44d247d |
| Guard plus count optimization | 543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1 |

No files in `/opt/ros` or ATLAS production were changed. Candidates are compiled
in memory on the PC. Wrong original source hashes fail closed.

## Validation

48 tests passed: nine new native cancellation tests, six count-candidate tests,
11 profile-analysis tests and22 profiling guard tests. No skips in the explicit
native run. Tests use WSL Ubuntu22.04/Python3.10/Humble, localhost-only domain213,
not Jetson or production ROS domains.

New tests reproduce the original cancelled/done-task KeyError, then verify the
combined candidate handles:

- cancellation before spin;
- externally completed or exception-completed tasks;
- cancelled coroutine rescheduled when its awaited future completes;
- duplicate requeue of an already-completed task;
-200 queued tasks with alternating cancellation:100 healthy callbacks run in
  order, cancelled callbacks never run, a subsequent healthy callback still runs;
- bounded shutdown and source-integrity rejection.

Both cancellation-only and combined native benchmark variants also pass ten
ordered ROS messages, subscription add/remove with delivery, callback exception
propagation and shutdown. Cancellation errors are now null in both variants.
These tests do not certify robot E-STOP deadlines under production traffic.

Reproduce native regressions from the repository root on PC:

```bash
source /opt/ros/humble/setup.bash
ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=213 ATLAS_CAPTURED_EXECUTOR=artifacts/executor_benchmark_20261023/executors.py python3 -m unittest discover -s project_atlas/tests -p test_executor_cancellation_native.py -v
```

Captured source is retained privately, not committed as generated evidence.

## CPU comparison: mixed, not a demonstrated deployment gain

For a fair comparison both variants include the cancellation guard. Existing
107-subscription idle-spin workload, median CPU microseconds per call:

| Order | Cancellation-only | Combined | Interpretation |
|---|---:|---:|---|
| cancellation-only first | 623.719 | 631.289 | combined1.21% slower |
| combined first | 645.512 | 534.113 | combined17.26% faster |

The counting microbenchmark remains faster (52.9–61.1% reduction over these two
runs), but full-executor variance is too large to claim a stable percentage.
Earlier5.45–8.06% PC results are historical, not a guaranteed outcome. Do not
select only the favorable run. No Jetson CPU/RAM savings, loaded callback deadline
improvement or Astra headroom is demonstrated. No new live profiling performed.

## Status, next step and rollback

Cancelled-task defect: corrected and verified for the offline regression cases.
Live deployment: NONE. Count optimization: prepared, CPU benefit not yet stable
at full-executor level. Next step is a longer interleaved same-process benchmark
and loaded callback/QoS/concurrent-entity tests before a Dashboard-only overlay
package is considered. No global library installation is recommended.

Do not install/restart on the strength of these results. A future deployment
requires separate approval, exact live hash checks, original-file backup, scoped
Dashboard-only loading and an approved web-only restart/rollback procedure.
There is no live rollback to perform now. Offline changes are revertible by Git.

White-glass UI, controls, steering, sensors, camera state,75% CPU/80% RAM/70C
safeguards and all production services remain untouched. No Jetson commands,
camera start, movement or recorder activation in this work.
