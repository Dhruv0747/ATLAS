# Native Dashboard CPU capture: usable, not a verified runtime fix

Owner run: `native-cpu-20261023/evidence-qod4956t`,23 October2026.
Capture status COMPLETE; one-time diagnostic CPU exception only. No camera,
motion, production file change or service restart. All protected service PIDs
and restart counts match before/after. Raw perf data remains private on Jetson.

## Integrity and actual samples

- perf.data781992bytes, SHA256
  `cfe3eec939f4c2bea68ab7f1e21827315439f3d68296d6f9aae7d14f5f7901be`.
- `perf report --stdio --no-children --call-graph none --sort pid,dso`:
  **75 cpu-clock:u samples, zero reported lost samples**.
- Approximate sampled event count3,947,368,350 user CPU nanoseconds across the
  two selected threads. Not whole-system CPU or elapsed wall time.
- Selected Linux TIDs5549 and5729; birth IDs8465 and10025 respectively.
- Kernel execution and other processes/threads were not profiled. The data
  cannot establish the cause of whole-Jetson spikes or total system overhead.

Self/sample attribution, NOT inclusive call-stack totals:

| Shared object | Samples | Fraction of these75 samples |
| --- | ---: | ---: |
| CPython3.10 interpreter |53|70.67%|
| rclpy native bindings |7|9.33%|
| libc |6|8.00%|
| FastDDS |4|5.33%|
| clock, NumPy, nav_msgs conversion, TF, RMW (one each) |5|6.67%|

TID5549 contributes49samples; TID5729 contributes26. Individual one-sample
functions represent1.33% of this small dataset, not precise stable percentages.
Python evaluation, method lookup/calls and allocation appear repeatedly. Smaller
native paths include FastDDS readiness, subscription conversion and TF insertion.
Inclusive rcl_wait/rmw_wait occurs in5samples (6.67%); wait-set destruction in
3samples (4%). Inclusive counts overlap and must not be summed as self CPU.

This distinguishes actual on-CPU work from the earlier Python profile's frequent
wait-boundary observations. It does NOT prove a native busy loop, GIL contention,
an event storm, duplicate subscriptions or an avoidable fault in the ROS executor.
The large native-wait CPU hypothesis is not supported by this short capture.
The selected threads execute Python/ROS work; browser glass rendering is not in
these stacks. This does not measure client browser CPU/GPU.

## Resource and safety results

| Window | CPU mean | CPU peak | RAM maximum | Temperature maximum |
| --- | ---: | ---: | ---: | ---: |
| Five baseline samples |70.8158%|71.8855%|71.9134%|60.312C|
| Eleven profile-window samples |72.5273%|78.5235%|72.0472%|60.406C|
| Five postflight samples |71.1689%|74.0496%|71.9696%|60.437C|

These windows differ in background work and duration. The difference is NOT a
measured CPU saving, nor can the entire increase be assigned to perf. The owner
exception permitted the profile-window CPU excursion only. All other recorded
checks passed. Production CPU75%, RAM80%, temperature70C policies unchanged.
No claim of sustained75% Astra admission or usable3D Preview follows.

## Fix decision and remaining evidence

There is now native CPU evidence, but CPython native frames do not identify
executed Python file/function/line. The prior Python samples are from another
boot and include native waiting. They cannot safely be treated as a synchronized
function-level CPU profile of these native TIDs.

No speculative sleep, timer reduction, removed subscription, QoS-warning
suppression, executor replacement or production ROS-library modification was
implemented. Previously tested tiny JSON/cache improvements do not solve this
remaining headroom problem and are not being relabelled as fixes.

**Next discriminating action:** a bounded GIL-filtered Python function profile
of the existing Dashboard, with the same proc CPU/deadline accounting, or an
equivalent isolated executor workload that resolves function costs. This would
identify avoidable Python bookkeeping before changing it. A further privileged
live profile needs a new reviewed owner-run command/approval; none started here.
No drive or camera test is needed. No runtime CPU fix is ready for deployment
from the75 native samples alone. Do not describe this result as CPU FIXED.

## Changes, verification and rollback

This checkpoint adds the reviewed analysis only. No additional profiler run,
runtime package or production restart. Existing19 profiler regression tests
were already passed for the capture helper; they are not runtime optimization
tests. Native perf header/sample/loss inspection is the new evidence validation.
White-glass and Dashboard code remain unchanged. Rollback not required because
production was not modified; existing UI backups remain preserved.
