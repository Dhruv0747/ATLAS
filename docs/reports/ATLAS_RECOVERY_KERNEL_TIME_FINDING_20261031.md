# Recovery overload: saved kernel-time evidence — 2026-10-31

Offline review only. No Jetson connection, new profile, benchmark, restart or
runtime edit. Recovery remains last verified STOPPED. Existing safety limits intact.

## New discriminating finding

Using adjacent saved snapshots 004/005/006 from the approved a2073b4 attempt:

| Whole-machine CPU component | Interval ending005 | Rejected interval006 |
|---|---:|---:|
| User + nice |46.98%|47.74%|
| System |15.94%|30.15%|
| IRQ |1.85%|3.02%|
| SoftIRQ |1.51%|6.03%|
| Total busy |66.28%|86.93%|

Raw rejected deltas in /proc/stat order user,nice,system,idle,iowait,irq,softirq,steal:
214,71,180,77,1,18,36,0 (597 ticks). Prior interval totals596 ticks.
System+IRQ+softIRQ rose about19.90 whole-machine percentage points; total busy
rose20.66 points. Thus approximately96% of the INCREASE is kernel-accounted time.
This is not a claim that96% of all CPU is kernel time, nor a hot-function profile.
Kernel system time includes work charged to processes, so do not add it to the
previous PID/cgroup totals. Interrupt/softirq attribution is not per-PID attribution.

Recovery and Localization remain concurrent contributors; neither is established
as sole source. Many other processes also rose (static TF, camera, rplidar, etc.).
That is consistent with broad startup/discovery effects but DOES NOT prove a DDS
storm, interrupt defect, network problem, repeated initialization or busy loop.

## Why no substantial safe patch is justified by saved profiles

The Oct24 Nav2 profile has only15 USER cpu-clock samples on two selected threads.
It confirms wait-set bookkeeping/bond dispatch, not kernel hot functions or a
removable defect. It predates this boot and cannot identify this kernel spike.
Prior static/lifecycle executor caching failed entity removal/heartbeat checks;
that approach remains rejected. Do not repeat it or suppress QoS/bond monitoring.

Recovery fault scan30s grace and status timer5s exclude those periodic callbacks
from this early rejection. Existing original code already uses raw freshness
subscriptions. Localization was already running, not initialized again by Recovery.
Dashboard decreased and mux rose modestly in the rejected interval; no removable
redundancy established. Type preload ed85ebd moves roughly16ms PC import work but
has no demonstrated Jetson impact and does not target the dominant observed rise.

## Decision / validation

NO-GO for claiming a real CPU fix or scheduling another blind restoration attempt.
No runtime change made: the available evidence identifies CPU category, not a safe
removable operation. Changing DDS transports, discovery, subscriptions, IRQ policy,
service availability or safety timers would be an unverified experiment.

Offline validation consisted of recomputing deltas from retained raw counters and
cross-checking the saved collector's66.275168%/86.934673% values and interval IDs.
No new tool was created and no unrelated suite was rerun. Existing type-preload
focused tests remain prior evidence; they are not evidence of a CPU improvement.

The missing evidence is kernel call-path attribution for this rejected interval;
it cannot be reconstructed from /proc counters or user-only perf samples. This
report does not request another live collection or restart. Keep existing evidence
and Recovery stopped until a separately reviewed safe corrective action exists.