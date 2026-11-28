# Astra Depth + RGB startup: evidence and bounded offline correction

Status: **diagnostic/cleanup candidate tested offline, NOT DEPLOYED. Startup reliability remains unresolved.**
Branch: agent/sync-developer-20261011; baseline f3868f1.
No camera Start, recording, permission change, service restart, movement or reboot.
The new owner task took priority over ongoing isolated USB-rule validation; that
work is preserved separately, uninstalled, and not included in this deployment.

## Exact retained failure

Worker17825, camera17885, mode concurrent, Domain77:

| Evidence | Value |
|---|---|
| Driver launch elapsed (worker monotonic) | 3.740436269 s |
| Failed sample elapsed (worker monotonic) | 4.485395100 s |
| Interval between those landmarks | 0.744958831 s |
| Guard sample window | 1.001 s (not a shortened launch-only window) |
| Failed aggregate CPU | 78.46153846%, limit75% |
| Last admitted aggregate CPU | 70.03012048% |
| Last admitted RAM / hottest zone | 67.05665% /60.968C |
| Driver RSS / CPU | 86276KiB /45.7159% of ONE core |
| Worker RSS / CPU | 19828KiB /3.9942% of ONE core |
| Final state | RESOURCE BLOCKED; driver_stopped=true |
| Frames | owner reports depth0/RGB0; no delivery evidence in retained driver log |

RAM/temperature in the final state are the last admitted sample, NOT measurements
from the rejected CPU sample; that sample correctly skipped other work.
Driver one-core CPU must not be confused with aggregate host CPU. On six cores it
is roughly7.62% capacity, but sampling intervals differ and this is not a measured
isolated overhead subtraction. No before/after live candidate CPU measurement exists.

Retained driver log wall timestamps (same log):

1. 1792596272.975738216: ROS init done.
2. 1792596272.976962838: opening2bc5/0403@1/14.
3. 1792596273.220526071: Astra connected, SDK serial17122120830.
4. 1792596273.269103135: depth160x120@30 selected.
5. 1792596273.308090013: rclcpp signal_handler(SIGINT/SIGTERM).
6. 1792596273.334964466: publisher creation fails, context invalid.
7. 1792596273.338407828: device close done.
8. 1792596273.502013677 onward: parameter undeclaration cleanup errors.

**Signal precedes context error by26.874ms.** The retained RESOURCE BLOCKED reason,
guardian source (exception -> finally -> SIGINT -> wait) and this log support CPU
guard cancellation followed by a ROS shutdown/startup race. The error is not
evidence that context invalidity caused the CPU rejection. Exact old guardian
signal-send monotonic timestamp was NOT recorded, so a complete original
monotonic-to-wall cross-process reconstruction cannot be claimed.

USB identities and named jetson RW ACLs are present for001/014 and001/011. Successful
OpenNI connection establishes depth access during this attempt. No evidence of
USB re-enumeration/access failure in this attempt. Both interfaces were verified
read-only; no permission mutation. Independent RGB USB contention is unproven:
the driver was interrupted before evidence of successful RGB startup.

## Confirmed defect versus hypotheses

Confirmed: aggregate CPU exceeded guard; ROS signal handling precedes invalid
context; driver startup was interrupted. Existing diagnostic line filtering
omitted the signal line, losing crucial ordering evidence. Cleanup also had a
poll/signal race: ProcessLookupError could prevent final state writing, and
cleanup of one child could prevent attempting cleanup of the other.

Unresolved: specific host process causing the extra aggregate load, whether RGB
initialization adds avoidable work, and whether vendor publisher initialization
needs coordinated cancellation. Namespace-collision warning is present but does
not prove duplicate subscriptions or explain this CPU sample. Parameter cleanup
errors remain visible; no vendor exceptions are suppressed. No speculative
frame-rate, CPU scheduling, calibration or driver patch was made.

## Exact correction

Only deployment target: `project_atlas/scripts/atlas_vision3d_runtime.py`.

- Retain signal-handler lines alongside original errors in driver diagnostics.
- Add bounded scalar lifecycle events (maximum32), each with monotonic and wall
  time: start, launch, resource rejection, cancellation, signal send, process reaped.
- Classify only observed signal-before-context ordering; leave unproven cases
  explicitly unproven. CPU/resource reason remains primary, exceptions retained.
- Tolerate owned-child exit between poll and signal, preserve SIGINT then bounded
  SIGKILL escalation, reap child, attempt both owned-child cleanups independently.
- Report driver_stopped only on verified process exit; preserve cleanup failures.

This does not repair the vendor's context race itself or lower host CPU. It makes
shutdown evidence reliable and fixes an actual cleanup race without weakening the
guard. Claiming reliable combined startup would be premature.

## Tests

66 focused tests passed:
-9 new lifecycle/order/cleanup tests.
-13 guard worker simulations including concurrent launch with78.4615% CPU failure,
  resource-before-signal ordering, reaping, lease expiry, stale policy and failures.
-6 USB denial/success tests;8 Stage30 sensor/resource tests.
-15 existing Stage32 IR tests.
-4 uncalibrated preview tests, including actual browser JS geometry executed with
  Node: synthetic wall4740 points, invalid-depth rejection, bounded cloud size.
-10 Dashboard state tests, including zero-frame and RESOURCE BLOCKED messages.
-1 native ROS2 Humble PC-only context test: publisher creation succeeds with valid
  context, is rejected after shutdown; context is cleaned up. Localhost, Domain171,
  no messages published, no Jetson subscription. NOT a vendor driver acceptance.

All six driver argument vectors compare exactly equal to baselinef3868f1; Depth,
IR and RGB parameters unchanged, Domain77 and1s/75%/80%/70C guard preserved.
Existing calibrated PointCloud2 gate remains enabled. Diagnostic browser preview
does not publish ROS PointCloud2 or reach navigation.

Windows initially failed Linux-only getuid import; lifecycle tests rerun on WSL.
Existing fake-process tests were corrected to represent wait()/returncode after
reaping; no safety assertions removed. Preview/UI tests rerun with Node and UTF-8,
all pass without dependency skips. Full historical suite not claimed green.

## Package, rollback and deployment approval

Live original runtime SHA256:
`fc807489b06699d73efdd246913849a3d11315d6bfcba707eedd0e1381c9b5aa`.
Candidate file SHA256 (package bytes):
`feedd883cbb9335569dcf50d33aaf5f66e3db85352dab54b2b3dba76c9137500`.
Original probe unchanged:
`f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384`.
Package contains ONLY runtime and a hash manifest, generated in local artifacts.
No live backup created because deployment not authorized; existing backups preserved.

Before installation: fresh safety/resource admission, camera/recorder OFF, no goal,
exact live hashes, backup runtime + mode/owner, verify restore hash, protected PIDs.
Atomic replace only reviewed runtime; verify installed hash. The web process imports
runtime code and may retain old objects; new workers execute the updated file, but
web-side status retention must be confirmed. If a restart is required, STOP for
separate permission—none is authorized by this report.

Rollback: camera OFF, restore exact backed-up runtime atomically, verify original
SHA and service identities. No USB rules/ACL, map, steering or calibration changes.

Next approval: install this ONE diagnostic/cleanup file after checks; then ONE
separately approved guarded stationary live verification only when baseline
headroom passes. Owner should choose Depth-only P0 preview or combined startup;
do not run both under one-session approval. Persistent low-overhead monitoring
must precede session. Stop on first failure, no retry. No resource-limit relaxation.
Actual CPU improvement remains unmeasured; expected extra work is a bounded handful
of timestamps and scalar fields, not a new subscriber or background service.

## Preserved state and evidence

Raw logs/state retained locally under `artifacts/astra_concurrent_20261021/`, not
committed (no camera images). Final read-only service check: camera1824,
telemetry3293,mux1814,EKF2868,localization4595,LiDAR1815 active; all restarts0,
same identities as before. No Astra driver process present. Live runtime/probe
hashes unchanged. Working Depth/IR/preview code not deployed over or reconfigured.

LiDAR world-writable vendor rule remains a separate documented hardening task in
ATLAS_PERMANENT_USB_ACCESS_AND_REBOOT_RECOVERY.md. USB native sandbox work remains
separate; no live udev rule or membership installed.
