# CPU sampler timing correction — offline PASS

Only web_activation_supervisor.py changed in the activation controls. No Jetson
operation, restart, camera/inference or safety-limit change. Staged backend,
rollback originals, independent observer, restart policy and counter library remain
byte-for-byte unchanged.

## Root cause and fix

Saved aggregate timestamp25071.332245102, snapshot completion25071.518948531:
collection overhead186.703429ms. Previous deadline was completion/persistence+1s,
but validation measured between aggregate-counter start times. First interval was
therefore at least1.1867s, exceeding the unchanged0.9–1.1s window.

Deadline now equals previous cpu_started+1s. Saved-case remaining wait after
collection is0.813296571s minus persistence overhead. Setup is excluded from the
ADDITIONAL WAIT, not CPU accounting. Consecutive counter deltas still include
collector/observer/setup CPU and all competing work. No reset, skipped first
sample or subtraction of CPU usage.

Next deadline follows each actual sample timestamp, avoiding catch-up bursts after
small delays. Actual monotonic duration remains validated0.9–1.1s. Invalid intervals
save the rejected raw endpoint, previous aggregate counters/time and delta before
aborting. CPU>75%, RAM>80%, temperature>=70C still reject. Observer and restart/
rollback behavior unchanged. The old79.15% spike cause remains UNKNOWN.

## Focused validation

8 tests PASS: saved187ms reproduction; setup CPU inclusion;75%/76% boundary;
short/late/long intervals and retained evidence; small-delay re-anchoring without
counter reset; invalid clocks; no wall-clock dependence; native PC/WSL sampling.

Native intervals:1.000770323s,1.001041154s,1.001257088s. Deliberate187ms CPU work
after the initial read remained in the first process delta:20ticks at100Hz,
19.99% of one core. Aggregate PC CPU1.25%,0.125%,0.0625%. This validates timing/
accounting, not Jetson savings or readiness. Unchanged prior safety tests reused.

## New single-use package

PC folder: work/web-restart-controls-timing-20261030.
SHA256SUMS SHA256:
`7e668845aab6470aeb404b834ef20502442f3ec3997f0f535df4ca0e1cf4431f`.
Supervisor SHA256:
`d0b1a8ef5892b45d007d33ab209840717c753e3bd73788dc975366f12f32be53`.
Other three control artifacts exactly match previous package. Backend manifest
a586c2d22276ef4f7385387a79cadd581b2c7a52567d89a8754ee051b9c99e68 and all20 entries,
including rollback originals, verified unchanged locally. New controls not copied
to Jetson and not executed.

## Execution ONLY after separate approval

Copy/hash-verify the NEW control folder; follow existing fresh safety, hash, backup
and browser checks. Never reuse the consumed unit, transaction or command.

```sh
systemd-run --user --unit=atlas-vision-activate-timing-once-20261030 \
  --property=Restart=no --property=RuntimeMaxSec=180s \
  --property=TimeoutStopSec=45s --property=KillMode=control-group \
  --property='ExecStopPost=/usr/bin/python3 -B /home/jetson/project-atlas-migration/web-restart-controls-timing-20261030/web_activation_supervisor.py --stage /home/jetson/project-atlas-migration/web-activation-once-timing-20261030 --recover' \
  /bin/bash -lc 'source /opt/ros/humble/setup.bash && source /home/jetson/project_atlas_ws/install/setup.bash && exec /usr/bin/python3 -B /home/jetson/project-atlas-migration/web-restart-controls-timing-20261030/web_activation_supervisor.py --stage /home/jetson/project-atlas-migration/web-activation-once-timing-20261030'
```

GO for review of one separately approved controlled attempt, subject to fresh
admission. No transient exemption. At most one activation/one rollback restart.
Unsafe/interrupted recovery may restore originals/policy while leaving Dashboard
stopped. Actual Jetson profiler overhead and successful activation are unverified.
