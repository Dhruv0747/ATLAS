# Dashboard partial GIL profile — new evidence, no runtime fix claimed

Owner-run evidence: `native-cpu-20261023/evidence-6araz0k9` on Jetson.
Run aborted at CPU75.24916943521595%, correctly preserving the75% limit.
No retry, camera start, production edit, service restart or motion performed.

## Verified result

Unlike the earlier zero-sample native abort, this partial capture is usable:
py-spy reports45 samples, zero errors and a completed Speedscope file after INT.
10177bytes; SHA256
`097ab072c68b5172cc8e6f1d5b27380dc9081397e0d5515af399c0f74a35f4cb`.
Telemetry SHA256
`c61c4f167a07422310bf596826fd8b8995cc33e6015be45b6733a60408742e02`.
Raw evidence remains private, not in GitHub.

| Python thread label | Samples | Executor wait-set path | QoS-event path | Dashboard leaf |
|---|---:|---:|---:|---:|
| atlas-web-status-spin | 12 | 10 | 3 | 0 |
| Thread-1 (_spin) | 33 | 24 | 6 | 2 |

Columns overlap: QoS paths may be inside executor paths. Each path counted once
per stack. 34/45 observations include `_wait_for_ready_callbacks`; this includes
Python entity collection, handle management, wait-set construction and readiness
processing, NOT necessarily time blocked in native wait. Nine observations include
QoS-event handling. Four main-thread leaves are `_take_subscription`.
Dashboard leaves are `_set` at429 and the `/arduino/i2c/status` lambda at511.
There is no evidence here identifying glass CSS or snapshot JSON as the dominant cost.

Installed executor source hash verified:
`e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010`.
Read-only source inspection confirms entity gathering, ExitStack enter/exit,
waitable entity counting and wait-set rebuilding in the sampled code paths.

## Resource interpretation

Using only adjacent same-phase proc intervals (excluding phase transitions):
baseline4.0034s whole CPU mean71.801%, peak74.281%; profiling3.0090s mean72.591%,
peak75.249%. Native TID5549 used27.58% one core and5729 used13.96% during the
profile window. Observer Python CPU approximately2.50% one core, excluding
profiler and helper subprocesses. This is NOT a matched optimization comparison.
The exact whole-machine spike cause cannot be assigned from this single-PID data.
RAM/temperature were intentionally not sampled after the failing CPU sample;
do not claim all gates passed at abort. No successful postflight window in the
aborted capture. Subsequent read-only service checks showed all seven protected
PIDs/restart counts unchanged and active.

## Limits and next necessary work

GIL-filtered nonblocking observations are not exact on-CPU function timings;
short capture and potentially inconsistent stacks limit estimates. Python thread
addresses are not native TIDs. The evidence narrows the next optimization to ROS
executor bookkeeping, but does not establish which work is redundant or prove a
busy loop. It does not justify removing subscriptions, QoS warnings, TF updates,
slowing callbacks or installing an executor cache that might miss new entities.

No safe production CPU fix is ready and no CPU savings are claimed. Next work is
an isolated executor-equivalence benchmark using the captured installed source:
measure entity/handle bookkeeping with representative main/status entity sets,
then test any bounded candidate against dynamic add/remove, cancellation,
exceptions, callback ordering and timely safety/status delivery. Do not request
another identical live profile merely because this one aborted. Actual Jetson
savings will still require a separately approved matched deployment comparison.

## Code and preservation

Extended offline analyzer with per-stack path counts and invalid frame-index
rejection;11 analyzer tests passed.22 profiler guard tests retained/passed.
No runtime code changed. Live Dashboard hash remains98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79;
white-glass CSS remains ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5.
No deployment rollback needed: only offline diagnostics/documentation changed.
