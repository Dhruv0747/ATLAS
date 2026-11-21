# Temperature admission probe — offline correction

15 October2026; source baseline `bbf3006ade2c3378c2fa1b74f745a98cea9085c8`;
branch `agent/sync-developer-20261011`. Owner authorized offline repair/tests and
GitHub update only. No SSH, Jetson probe, bridge connection, deployment, live
recording retry, service change or rover motion occurred during this correction.

## Verified defect and uncertainty

The saved attempt failed during thermal collection with
`TypeError: can't concat NoneType to bytes`. It used unbounded `Path.read_text()`
and discarded both the failing attribute path and traceback.

An offline UTF-8 TextIOWrapper over a synthetic raw stream returning `None`
reproduces **that exact exception** on Windows Python3.13 and Ubuntu22.04
Python3.10. This verifies a possible software mechanism. The original Jetson
failure had no traceback, so it does **not** prove which attribute failed or why
its underlying read was unavailable. No thermal hardware fault is inferred.
Original failure evidence and its hashes remain in
[the attempt report](ATLAS_PC_BRIDGE_STATIONARY_ATTEMPT_20261015.md); the exact
old source remains in the baseline commit.

## Correction

`offboard_bridge_preflight.py` now reads each thermal attribute once using
`os.open`/`os.read`, bounded to257 bytes with a256-byte accepted limit. Linux uses
nonblocking mode; file descriptors close even on exceptions. ASCII type names
and integer millidegree temperatures are validated explicitly.

An unavailable/None/empty/malformed/oversized read is a recorded error and still
blocks admission. No retry, fabricated temperature, dashboard replacement or
skipping of failed zones is used. Valid readings from other zones are preserved
as diagnostic evidence without granting admission. Zone ids prevent duplicate
type labels from overwriting separate readings. Each reading retains its type
and source paths. Each failure retains its path, attribute, exception and
traceback; the outer result also records the failing measurement phase.

CPU75%, RAM80%, temperature70°C, stop latch, manual-only, commissioning and
zero-command checks remain unchanged. Passing resources still stops at
`RESOURCE_SAFETY_PASS_SENSOR_ADMISSION_PENDING`; this probe cannot connect to the
bridge or start recording.

## Offline verification

13 new tests pass on Windows, and all **17 focused tests** pass on Ubuntu22.04
Python3.10: the13 temperature/admission tests plus4 existing receive-only contract
tests. All resource, dashboard, service and time dependencies in admission tests
use fixtures; thermal reads use isolated temporary files. No live interfaces.

Covered cases:

- Exact original UTF-8/None exception reproduced.
- Multiple valid zones, including duplicate type labels.
- Empty/blank/malformed/nonfinite/non-ASCII temperatures and impossible values.
- None and EAGAIN reads, one attempt, descriptor cleanup.
- Missing temperature/type files and empty/missing thermal root.
- Oversized attribute refusal and preservation of partial valid measurements.
- Exact70°C/75% CPU/80% RAM boundaries;70.001°C and exceeded CPU/RAM rejected.
- Unlatched stop, armed commissioning, enabled autonomy or nonzero command rejected.
- Temperature read failure emits JSON with paths/traceback and exits2 before
  dashboard/service inspection. No connection or subscriptions are started.

The first Windows test run exposed unavailable `os.O_NONBLOCK` on Windows and a
floating-point rounding error in the fixture. Both were corrected before the
final passes. Linux retains O_NONBLOCK; Windows fixtures use binary file mode.
No live tests were repeated to validate this change.

Reproduce the focused offline suite from `project_atlas/tools/diagnostics`:

`python3 -m unittest test_offboard_bridge_preflight test_offboard_bridge_contract -v`

## Status and next boundary

**Offline software correction verified and committed; Jetson validation deferred.**
This does not establish current Jetson temperature, safety state, transport
delivery or localization accuracy. Stage20 activation has not been attempted.
No new live recording approval is requested or exercised by this change.
Any future Jetson preflight/capture must follow the owner's next instruction.

Rollback of the PC source is available through the parent commit; no production
rollback is necessary. Exact commit SHA/URL is in the final handoff; it is also
resolvable with `git log -1 --format=%H -- ATLAS_PC_BRIDGE_TEMPERATURE_OFFLINE_FIX.md`.
