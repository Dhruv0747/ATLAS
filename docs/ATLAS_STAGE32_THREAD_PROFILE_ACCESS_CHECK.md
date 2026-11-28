# Stage 32: thread-profile access checkpoint — 2026-10-21

Continuation of `3bf9264406ba0846efa2dc33316872f39a4778a3`.
No optimization, production installation, restart or camera Start performed.
Compact JSON remains undeployed.

## New verified evidence

- Dashboard PID remains 51991. Its two previously observed expensive Linux
  threads are TID 52033 and TID 52093, both named python3. Their previous `ps`
  lifetime CPU values (27.3% and 13.9% of one core) are not fresh interval
  measurements and do not identify their Python functions.
- Actual read-only open of `/proc/51991/mem` failed with errno 13, Permission
  denied. No memory bytes were read. `ptrace_scope=1`; `perf_event_paranoid=2`.
  No policy was changed. Passwordless administrator access is unavailable.
- GDB exists, but was not attached: pausing the production dashboard is not an
  acceptable substitute for a low-overhead sampling profiler. py-spy and perf
  were absent at the checked executable paths; the old scratch profiler path
  no longer exists.
- One fresh 1-second whole-machine CPU sample was 70.1874%. This is not a
  headroom baseline, overhead estimate or permission to start a camera.
- Summary API returned RESOURCE BLOCKED, driver_stopped=true, retaining a
  77.8731% guard failure. `pgrep -x astra_camera_no` returned no process.
  The retained result is not a current CPU measurement or an active stream.
- The preliminary thread-counter helper aborted before collecting samples
  because it required the literal OFF state rather than recognizing the
  stopped RESOURCE BLOCKED state. Its error was preserved, not interpreted
  as camera activity. Protected service PID/restart identities were unchanged.

## What is NOT established

No thread-tagged stack profile was captured. The CPU-consuming functions,
callback attribution, scheduling cost and prospective CPU savings remain
unverified. Old untagged executor stacks are not sufficient to attribute CPU
to these two threads. No performance fix or regression-test success is claimed.

## Single next action

Obtain administrator-assisted access for a reviewed, bounded external sampling
profiler attached only to the existing dashboard PID. Do not lower ptrace
policy globally, restart the dashboard, insert production instrumentation or
create ROS participants. Prepare and review the profiler executable/version,
hash, timeout, sampling rate and exact invocation before asking the owner to
run the administrator command. Never request the administrator password.

The capture must pair per-thread CPU deltas with thread-tagged stacks, preserve
Python/native thread-ID mapping, and include matched no-profiler/profile CPU
windows plus profiler CPU. Fresh safety/resource admission must pass first.
Abort sampling on any existing limit failure; do not stop protected services.
Only after identifying actual hot paths should an optimization be proposed,
tested offline and packaged with rollback. No useful CPU saving is estimated
from the access failure.

## Evidence and rollback

Private diagnostic-only evidence:
`/home/jetson/project-atlas-migration/astra-20261021/thread-profile-precheck.json`.
No production files or permissions changed; no production rollback required.
CPU75%, RAM80%, temperature70C, ROS Domain77 and all camera restrictions remain
unchanged. Production health beyond the checks explicitly described above is
not newly certified by this report.
