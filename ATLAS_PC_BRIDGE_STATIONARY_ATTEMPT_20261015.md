# Approved stationary bridge attempt — blocked at preflight

Owner scope: one supervised10s receive-only test, five specified diagnostic
topics,75% CPU/80% RAM/70°C limits, no automatic retry. Continued from
`0ac97c340dd0dfae5f9f76f934a9ef60df01fdef` on
`agent/sync-developer-20261011`.

**Result: BLOCKED BEFORE CONNECTING. No bridge socket or production subscription
was opened. No recording was created. No retry was performed.**

## Outgoing operation boundary

Added and checked `offboard_bridge_contract.py` against the existing bridge's
[Foxglove WebSocket v1 contract](https://github.com/foxglove/ws-protocol/blob/main/docs/spec.md).
The application sender accepts exactly subscribe/unsubscribe for the approved
five topics. Binary application sends, publishing, advertising, services,
parameters, goals and other operations are rejected. Channel/type/CDR checks and
raw incoming payload extraction are tested with synthetic bytes, without sockets.
All four tests in `test_offboard_bridge_contract.py` passed. This validates the
application boundary; no complete live transport client was activated or claimed
validated. WebSocket handshake/close/pong are distinct transport control frames.

## Fresh admission evidence

One read-only Python probe was sent to the Jetson via existing SSH. It samples
`/proc/stat`, memory and thermal sysfs, then is intended to verify cached safety
and sensor evidence. It has no recording or control activation capability.
UTC start:2026-10-15T03:40:58.682110+00:00.

| CPU interval | Duration (s) | Aggregate utilization (%) |
| --- | ---: | ---: |
| 1 | 1.001230 | 73.455760 |
| 2 | 1.003846 | 69.717138 |
| 3 | 1.001429 | 71.452421 |
| 4 | 1.001557 | 69.191919 |
| 5 | 1.000588 | 71.137521 |

CPU mean70.990952%, maximum73.455760%; measured RAM65.046444%.
These samples alone do not establish full admission. The measurement path then
raised exactly:

`TypeError: can't concat NoneType to bytes`

The result preserved an empty thermal-zone map. The exception occurred after
memory sampling and before completing temperature collection/dashboard/service
inspection. It is a diagnostic-software measurement failure; exact underlying
cause is **unverified**, and no sensor/board fault is inferred. The probe did not
preserve a traceback, so a precise failing read cannot be named from this evidence.
Remote Python returned exit2. Recording was not admitted.

E-STOP latch, zero commands, autonomy/commissioning state, required sensor
freshness, dashboard resource checks and fresh Stage20 OFF verification were
**not completed**. Their earlier status is not substituted for current evidence.
No E-STOP, services, clocks, networking, calibration or maps were changed. This
attempt never started the Stage20 recorder or installed anything on the Jetson;
the SSH probe ran from stdin and exited.

## Requested capture results

All five topic counts are0 because subscription never began:
`/scan`, `/im10a/imu/unvalidated`, `/atlas/encoder_update`,
`/atlas/control_policy`, `/cmd_vel`. All five are uncaptured, not demonstrated
transport failures. Message gaps, DDS/bridge loss and live source timestamps
are unavailable. There is no SQLite bag to integrity-check or payload-hash-check.
No false zero-loss or recording-success result is reported.

Jetson during/after subscription overhead is unmeasured; no subscription occurred.
PC live client CPU/RAM and recording/network throughput are unmeasured. PC–Jetson
clock offset remains UNKNOWN. The only CPU/RAM figures above belong to the
read-only preflight window, not to a live recording.

## Durable evidence and next action

Local terminal evidence:
`artifacts/offboard_bridge_once_20261015/preflight_terminal.txt`.
SHA256: `084d4a351e213d27fefe94260d53d50280e2fec4c517933897a771f10d41d22c`.
As-run probe source:
`project_atlas/tools/diagnostics/offboard_bridge_preflight.py`.
Raw as-run PC file SHA256:
`c3fc705d765448e79286e16862fc0a81eddf4e2e85821b8533d4ef319f6cbbc6`.
Line-ending normalization in Git can change that raw-file hash; local artifact
and source were preserved. Generated evidence is not committed.

The attempted preflight source is retained for reproducibility, **not certified
ready for another attempt**. No retry or new live probe follows this failure.
Next necessary work is an offline correction of the measurement error with
per-read exception evidence. Any later stationary live attempt requires a new
explicit instruction, since this approved attempt has stopped. Localization
status is unchanged; no motion or replay investigation was repeated.

This checkpoint is the commit adding this report; exact pushed SHA is supplied
in the final handoff. No production rollback is needed because nothing was
deployed or activated.
