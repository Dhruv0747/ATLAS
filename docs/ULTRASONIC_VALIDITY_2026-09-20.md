# Ultrasonic sample-validity increment — 2026-09-20

## Status

**Firmware and paired runtime installed from candidate `16ff10c`.** Operator
double-reset enabled the upload, and a later full operator power cycle verified
startup of the hub, recovery, mux and web services without manual service starts.
Fresh ultrasound, environmental/thermal, PCA9685 and decoded radar data returned.
No motor-service restart, drive/map command or autonomy enable was issued during
installation or checking. Runtime restarts were limited to hub, recovery, mux and
web; existing hub reconnect initialization reapplies the saved camera-home command.

**Full sensor stability/safety qualification is NOT passed.** Two passive
observations detected frequent serial-backlog rejection. After renewed
motor/servo-power-OFF confirmation, partial-line handling and bounded same-tick
receive draining were installed. No additional UNO flash was needed. See the
limited post-change observations below; physical fault/clearance/stopping tests
remain pending.

Baseline: `d3f2d87`. The live check found manual-only=true, stop_latched=true,
zero commanded velocity, selected encoders M1/M2/M3, excluded M4, and
navigation_validated=false. Front/rear telemetry was arriving; this is not a
physical reliability PASS. Saved steering geometry and camera home are untouched.

## Installation evidence and recovery history

On 2026-09-20 the operator confirmed that drive-motor and camera-servo power
were OFF, with Jetson/UNO powered. The exact Arduino application device was
identified (VID:PID `2341:006d`). Candidate binary hash, live baseline source
hashes and fresh manual-only/latched-stop/zero-command state were verified.
Previous live source files were backed up under the staging directory's
`backup/`, including the old firmware source and a manifest. A matching raw
installed-flash backup was **not obtained**.

The **first attempt** at native USB 1200-baud bootloader entry did not succeed.
A subsequent DTR transition returned a broken-pipe error; `bossac -i` could not
find a bootloader. That attempt performed no erase/write. Restarted old services
reported active but had USB I/O errors, so recovery was not claimed. No USB hub,
controller or unrelated device was reset by the installer.

The operator subsequently reached RESET and double-tapped it. Upload-mode device
`2341:1002`, serial `E4B063836708`, was identified before using the installed
Arduino core's standard bossac write/reset procedure. The 68,904-byte binary was
written successfully in 4.251 seconds. The application re-enumerated as
`2341:006d`, serial `3718211158323232840133334B573038`.

Direct serial observation then received 28 UVALID1 frames in eight seconds with
zero parsing errors, alongside legacy ranges, USTAT, BME, AMG and heartbeat
frames. Front enabling and radar initialization belong to the existing bridge
startup and were not expected in this pre-bridge capture. This proves the new
protocol ran, **not bit-for-bit flash readback verification**. Bootloader readback
was unavailable; the retained previous build is explicitly NOT a verified image
of the former installed flash.

The six paired Python files and firmware source were installed, without changing
service environments, steering calibration, camera home (1725/1500 microseconds),
M1/M2/M3 selection, M4 exclusion or IMU fusion. All 104 original offline tests
passed again on Jetson staging before installation. A subsequent network outage
prevented immediate end-to-end checking; the operator then power-cycled ATLAS.

After that reboot, all four affected services were enabled and active with
`NRestarts=0`. ROS graph discovery using `--no-daemon` succeeded. Fresh API data
showed `manual_only=true`, `stop_latched=true`, zero linear/angular commands and
`navigation_validated=false`. Fresh board packets are not a physical encoder
test. Two passive ROS observations below exposed the remaining timing issue.
Keep motor/servo power OFF; no additional board RESET is required.

## What already worked / defect found

The UNO samples enabled ultrasonic channels and reports raw distances and
`USTAT` for the web display. LiDAR remains the primary obstacle geometry source.
The existing mux provides an autonomous directional ultrasonic veto alongside
encoder/localization gates and the higher-priority remote emergency stop.

However, legacy ONLINE means a successful echo occurred within **30 seconds**.
The mux accepted a bare positive Float32 (including infinity), retained an old
positive range after an invalid reading, and skipped stale directions. A fresh
display message therefore did not prove a fresh echo or a clear route.

## New contract and behavior

- Firmware adds `UVALID1,T=<uptime_ms>,F=<enabled>:<mm>:<sequence>:<sample_age_ms>,L=...,R=...,B=...`.
- Sequence advances on each attempt, including failed echoes. Age is since the
  completed attempt, not since the last success. Legacy range/USTAT remains for
  compatibility. Banner adds `US_VALIDITY=1`; no pin or camera-home changes.
- Existing bridge publishes a single JSON snapshot on `/ultrasonic/validity`
  (std_msgs/String, depth 1), with unique connection stream, same-Jetson
  monotonic receipt time, MCU uptime, and four sample records. It also populates
  the existing read-only dashboard fallback cache as `us_validity`.
- States distinguish VALID, NO_ECHO, DISABLED, UNINITIALIZED and transport or
  parse failures. Bridge withholding on USB/parser backlog is fail-closed.
- The mux expires both receipt and source age, detects older reports, preserves
  the original expiry of repeated sequences, rejects changed data with unchanged
  sequence, and accounts for additional transport delay relative to the best
  observed host/MCU clock offset. Clock reset/wrap requires a new bridge stream.
- Forward/reverse autonomous commands require the corresponding front/rear
  sample. Invalid/missing/stale proof stops that direction. Disabled side sensors
  are not automatically enabled or declared clear; valid side echoes can veto
  turns. This is secondary protection, not full-body clearance certification.
- Existing reaction-time/margin stop thresholds are retained, with equality at
  the threshold blocked. No navigation gains, speed increase or remote behavior
  is changed. No capability profile or goal-resume authority is granted.
- Legacy invalid/OK=0 reports clear raw display ranges. Raw topics cannot bypass
  the contract. The capability view explains missing proof instead of treating
  legacy ONLINE as a qualified echo. Relevant evidence changes require retest.

## Validation

- UNO R4 WiFi native-USB build, installed Arduino renesas_uno core 1.6.0:
  compiler reports **68,896 bytes flash (26%), 10,984 bytes global RAM (33%)**.
  The upload artifact is 68,904 bytes; upload and observed protocol are recorded above.
- 30 new offline checks: framing, bounds, no echo, disabled, missing, stale,
  malformed JSON, nonfinite data, replay/repeated sequence, MCU reset, added USB
  delay, front/rear and side vetoes, speed margin, legacy OK bit, backlog,
  bridge-to-contract decoding, mux integration and emergency-stop precedence.
- 58 commissioning/capability/evidence checks and 16 steering checks.
- Jetson Python 3.10: **104/104 passed** in isolated staging, no skips.
- Windows Python 3.13: **103 passed / 1 optional-PyYAML skip**, zero failures.
- Python syntax checks and firmware compilation passed. Driver modules were not
  imported by these tests: selected methods were extracted into offline fakes.
- The physical ROS `test_rear_ultrasonic_guard.py` was **not run**. It remains
  explicitly armed/motor-service-off only and now requires an actual 0.20 m
  obstacle reason; a missing-data/encoder/e-stop block cannot falsely pass it.

### Passive post-reboot observations — no motion publications

The temporary subscriber used same-Jetson monotonic time and the deployed
ValidityWindow. Status-message counts include invalidation events and are NOT
the physical ultrasonic sample rate.

| Observation | Duration | Status messages | Accepted sample reports | SERIAL_BACKLOG | Parse errors | Maximum receive gap |
|---|---:|---:|---:|---:|---:|---:|
| Startup | 60.13 s | 301 | 195 | 105 | 0 | 0.782 s |
| Later stationary window | 60.02 s | 276 | 207 | 69 | 0 | 0.644 s |

Startup also had one missing/stale report and one stale rear sample. The later
window had 207 valid front/rear samples and disabled left/right samples. Observed
front ranges were 1319–2391 mm and rear 222–258 mm; these are uncalibrated
observations, not proof of measurement accuracy. Neither window changed stream ID.
The later 59 serial diagnostic reports included USB pending bytes on six reports
(maximum 152) and parser pending bytes on seven (maximum 71). Nonempty data can
be genuine queued work or just the next incomplete line; it must be distinguished.

Fresh I2C status reported PCA=1, BME=1, AMG=1, SDA=1, SCL=1. BME measurements and
the thermal matrix/status arrived. Radar produced valid decoded frames; its
counter included three bad footers, so zero decoder corruption is not claimed.
These checks do not establish long-run reliability for every sensor. Startup
logs also included a camera-command write timeout and a LiDAR recovery attempt;
their physical behavior was not tested. No fault is hidden by a general PASS.

### Parser follow-up — installed with motor/servo power OFF

The bridge incorrectly treated any trailing partial line as unprocessed backlog
preceding the completed UVALID1 report. The correction leaves that fragment for
the next tick while allowing the already complete report through. Complete
queued lines and pending USB bytes still invalidate; original receive time,
source age, sequence checks and all mux thresholds remain unchanged. Diagnostics
gain `parser_complete_lines` to distinguish these cases. No firmware change.

Three added offline cases cover partial tails, new USB bytes during parsing and
preserving the original timestamp when a held report drains. Jetson staging:
**107/107 pass**. Windows: **106 pass / one optional-PyYAML skip**.

The operator then confirmed both motor and camera-servo power OFF. The installed
bridge SHA-256 was checked, backed up and atomically replaced. Only hub/recovery
were stopped/started. The first corrected 60.18-second observation received 241
status messages: 199 valid front/rear reports and 42 backlog invalidations, zero
parse errors and no stream change. Maximum message gap was 0.540 seconds and
maximum reported source sample age 0.481 seconds. This was an improvement in the
observed window, not a controlled CPU-load comparison or complete resolution.

The original reader performed one USB read, decoded lines, then rejected pending
reports if more bytes had arrived during decoding. The next bounded correction
drains newly arrived bytes in the same callback, within the existing 8192-byte,
128-line and 8-ms processing budgets. These are cooperative processing budgets,
not a hard realtime guarantee for an individual ROS publish or USB call. Actual
remaining USB/complete-line backlog still fails closed; no sensor age threshold
or autonomous safety policy was relaxed.

Five additional offline cases verify same-tick bursts, byte/line/time budgets and
empty reads. All **112 tests pass on Jetson staging**; Windows has **111 passes
and one optional-PyYAML skip**. The initial staging run needed the unchanged
`atlas_serial_lines.py` fixture copied into the isolated test directory. The
drain correction was then deployed through the same stopped, hash-checked,
backup-and-replace procedure. Calibration and service environments are untouched.

### Final bounded-drain stationary observation

- Duration: **120.03 s**; 424 validity/status messages, of which **421 were valid
  front/rear sample reports** and **3 were fail-closed SERIAL_BACKLOG events**.
- Zero parse errors, zero stream-ID changes and no stale accepted samples in
  this observation. Left/right remained DISABLED, not assumed clear.
- Maximum receive gap **0.551 s**, maximum host-envelope delivery age **0.136 s**,
  maximum MCU-reported sample age **0.481 s**. Those are observed maxima, not
  certified worst-case latency or safety thresholds.
- Of 119 periodic serial diagnostics, none showed a complete line still queued
  at that sampling instant; 13 had a partial fragment and two had USB bytes
  pending (maximum 25). Event-level backlog rejection remained active.
- Front echoes ranged **1314–2362 mm**, rear **222–245 mm**. The broad front
  variation requires known-distance/reflector testing; no accuracy claim.
- Hub/recovery active with NRestarts=0; hub/recovery/mux/web remain enabled for
  startup. Fresh dashboard/commissioning data included ultrasound, BME680,
  AMG8833, PCA9685 and decoded radar. BME gas quality can still report WARMING;
  camera pulse reports are not physical servo feedback.
- Manual-only and latched stop remained true, with zero command. M1/M2/M3
  selected, M4 excluded, navigation unvalidated. No fusion or motion permission.

Compared with the earlier windows (69 backlog events/60 s, then 42/60 s), the
final window had three/120 s. These were sequential observations at varying CPU
load, not a randomized controlled benchmark. Jetson CPU snapshots remained about
91–97.5%; no claim that the receive correction optimized the whole system.
The three remaining queue events, prolonged-load/fault cases, echo accuracy and
physical stopping still require investigation/qualification. Do not hide them or
claim that autonomous navigation is now commissioned.

During the deliberate first hub stop, the old process logged an rclpy invalid
context while publishing during shutdown; the replacement started normally.
This shutdown traceback is not counted as a spontaneous sensor disconnect.

### Follow-up: communication expiry and operator distance reference

Motor and servo power remained OFF under the operator's confirmation. The
read-only check identified the exact bridge PID/command line and verified a fresh
latched stop, manual-only and zero command. It temporarily stopped only the
recovery owner, then used SIGSTOP for 3.5 seconds on the bridge. A detached
eight-second PID/start-time-checked resume guard was armed first; normal finally
handling also restores the bridge and recovery. No serial device was opened by
the observer and no ROS/actuator command was published.

Both deployed ValidityWindow readings became `STALE_REPORT`. The existing
commissioning API showed front/rear `STALE_OR_MISSING`, age 3.8 s. After SIGCONT,
fresh readings returned within the six-second observation window with the same
stream ID. The test received 44 frames with zero parse errors; hub and recovery
were active afterward, stop/manual-only still true. Evidence:
`software_pause_check.json` in the staging/evidence directory.

**Scope:** successful software communication-pause expiry and resume check.
This does not prove a physical cable disconnect, electrical fault, no-echo state,
or actual stopping distance. The permanent stop latch stayed active, so zero
motor output must NOT be attributed specifically to the ultrasonic guard.

The initial exchange was interpreted as confirmation of a flat target 500 mm
from the FRONT transducer. A separate 30.03-second passive observation found:

| Measurement | Front | Rear (no reference target requested) |
|---|---:|---:|
| Fresh valid reports | 105 | 105 |
| Median | 1352 mm | 243 mm |
| Minimum–maximum | 1324–1406 mm | 222–244 mm |

The operator later clarified that there was no verified 500 mm reference target;
the actual scene was roughly 2.5 m open in front and 0.2 m behind. Therefore the
computed +852 mm "error" and screening-band result are void as an accuracy test.
The raw capture is retained as historical evidence, not calibration evidence.

Result: **front known-distance qualification remains open**, rather than failed
against a valid reference. Firmware channel mapping remains
front TRIG D2 / ECHO D3, rear D8 / D9. The source uses round-trip echo time
`duration * 0.343 / 2` in millimetres; no unit/scale or pin change was made.
Do not apply an arbitrary scale factor or start autonomous movement from this
stationary evidence. Front and rear reference testing is still pending.

Raw observation stays on Jetson as
`reference_front_500mm_1789885159.json`; only this result summary is committed.

The operator subsequently confirmed that the live ultrasonic readings themselves
were plausible for the scene. A simultaneous 20.03-second stationary comparison
with the existing measured LiDAR transform and +/-0.25 m chassis extent found:

| Source | Front | Rear |
|---|---:|---:|
| Ultrasonic median | 1.347 m | 0.243 m |
| LiDAR median nearest range, +/-5 degrees | 2.755 m | 0.514 m |
| LiDAR estimated clearance from chassis edge | 2.454 m | 0.314 m |

LiDAR and ultrasound are at different origins and heights and have different
beam geometry. The comparison confirms live data, not identical surfaces or
precision calibration. LiDAR remains primary for mapping/navigation; ultrasound
is secondary close-range evidence and may not silently convert uncertain data to
clearance. Raw evidence is `lidar_comparison_1789885934.json` on the Jetson.

A final 120.15-second passive stability window recorded 424 reports: 418 valid
front/rear samples, six fail-closed `SERIAL_BACKLOG` reports, zero parse errors,
one stream identity, maximum 0.538-second report gap and maximum accepted sample
age 0.404 seconds. Observed ranges were 0.988–2.378 m front and 0.222–0.244 m
rear. This is sustained stationary communication evidence, not physical sensor,
braking or autonomous-navigation qualification. Raw evidence is
`final_stationary_stability.json` on the Jetson.

The front sensor was then checked at its relevant close-protection distance.
With an operator-set flat target 30–35 cm from the transducer face, 15/15 fresh
samples were valid and inside that interval: minimum 317 mm, median 328 mm,
maximum 332 mm. ATLAS remained manual-only, stop-latched and at zero commanded
velocity. This passes stationary screening for the **front secondary close-range
role only**. It does not qualify long-range precision, physical braking distance,
failure recovery or ultrasound as a LiDAR replacement. No threshold, scale or
calibration value was changed to obtain the result.

The rear sensor was checked with an operator-confirmed flat target 30–35 cm from
its transducer face. The first 15-sample window was entirely valid, measuring
286–307 mm with 306 mm median (13/15 inside the stated interval). A repeated
15-sample window was also entirely valid but measured 272–282 mm with 281 mm
median. This passes **conservative secondary close-obstacle detection**, because
the observed bias reports the obstacle closer and therefore warns earlier. It
does not pass as a precision range instrument. LiDAR remains primary and the
short bias is retained as an explicit limitation; no scale or threshold changed.
After target repositioning, a third 15-sample window measured 301–311 mm with
311 mm median; all 15 readings were inside the operator-confirmed 300–350 mm
interval. This cleanly confirms the rear close-obstacle role while preserving
the earlier variability as evidence rather than deleting it.

Physical rear failure/recovery was then checked with drive-motor and camera-servo
power confirmed OFF. Before disconnect, rear was stably valid at 316 mm. After
the operator unplugged only the rear ultrasonic connector, ten consecutive fresh
reports were `NO_ECHO` with `range_mm=null`; front remained valid and velocity
commands remained zero. The old 316 mm value was never presented as current.

After reconnect, rear automatically returned to valid 330–331 mm reports with
increasing sample sequence. The bridge exposed a new stream identity, so the
validity owner treated the restarted source explicitly rather than accepting a
replayed pre-disconnect sample. A following 30.14-second direct ROS observation
recorded 103 reports: 102 valid per active channel, one fail-closed backlog,
zero parse errors and rear range 310–337 mm. Raw evidence remains on the Jetson
as `rear_reconnect_stability.json`. One dashboard API request timed out during
the reconnect window; direct ROS evidence showed the sensor stream itself was
healthy. This passes rear physical disconnect and automatic-recovery behavior.

The isolated validity/mux guard suite was then repeated: 38/38 checks passed on
Windows and 38/38 on the Jetson staging copy. It covers close, stale, missing,
no-echo and direction-specific veto behavior, including the speed-dependent stop
margin. It is not a physical braking-distance result. Manual remote commands do
not pass through the autonomous ultrasonic guard, so manually approaching an
obstacle would not qualify the NAV2/recovery stop path. Live autonomous sources
remain gated by the unresolved encoder ground validation.

## Deployment records and guarded follow-up

Staging, backup and local evidence directory (not committed telemetry):
`/home/jetson/project-atlas-migration/ultrasonic-validity-20260920/`

Firmware binary SHA-256:
`989dd795e8474977f43b0f47f01548e0c9f802056be44fb67d951dff22222c81`

Before any follow-up bridge restart, obtain fresh confirmation that drive-motor and camera-servo
power are off, with Jetson/UNO USB still powered. Reconnect currently sends camera
home commands; lifted wheels alone do not address that hazard. Identify the UNO
device afresh and back up live files plus the matching old firmware artifact.
Do not flash or restart from this document without that confirmation. Firmware
installation is already done; do not reflash it for the trailing-line correction.

The paired firmware + helper + bridge + mux + read-only dashboard/audit
files were installed together while stopped. A new mux with old firmware deliberately blocks
autonomous translation; old raw ranges are not a fallback. Preserve service
environment, home, manual-only/stop latch, steering locks and all calibration.
Evidence retained locally: `flash_result.json`, `flash_upload.log`,
`new_firmware_telemetry.json`, `runtime_result.json`, `passive_observation_60s.json`
and `passive_settled_60s.json`. Runtime source hashes are in `runtime_result.json`.
The old source and manifest are under `backup/`; the previous binary is named
`previous_native_build_NOT_flash_readback.bin`. Source builds and uploader success
are not matching flash readbacks. Follow-up source snapshots are under
`fragment-fix/project_atlas/` and `bounded-drain-fix/project_atlas/`.

Current installed bridge SHA-256:
`32f6f662bcfd504a66356cf0b4bc32ccc229e846056ea16a837854f27ca06345`

Follow-up records: `fragment_fix_deployment.json`, `bounded_drain_deployment.json`,
`passive_fragment_fix_60s.json`, `passive_bounded_drain_120s.json`. The two previous
bridge sources are retained as `backup/bridge_before_fragment_fix.py` and
`backup/bridge_before_bounded_drain_fix.py`. Original candidate `16ff10c` remains
the firmware/mux/helper baseline; the bridge has the later receive correction.

Do not use the old raw-range behavior to bypass a validity rejection or unlock
autonomy. If rollback is required, keep motion physically inhibited and review
the paired firmware/runtime versions; never weaken a gate just to get a PASS.

## Remaining limits / next tests

The 20–4200 mm limits match existing firmware acceptance, not an independently
measured transducer envelope. No-echo may mean excessive range or poor reflection,
not necessarily a disconnected sensor. The conservative veto may stop travel;
do not bypass it to make a mission pass. A reduced-sensor profile needs separate
physical qualification and approval.

MCU and host clocks are not synchronized: initial transport delay cannot be
bounded from the first report alone; offset drift/backlog and restart behavior
require live validation. ROS source labels are not cryptographic device identity.
No over-the-wire CRC was added. Cross-talk, angles, blind zones, wiring noise,
actual reporting latency, braking distance and firmware-load regression remain
unqualified. An offline PASS is not a physical sensor or stopping PASS.

Next: perform sustained camera/radar/I2C workload, then isolated stop-output
validation. Ground testing follows only after existing
steering, measured encoder distance, stopping, localization and remote-stop gates
are satisfied. Do not repeat previously recorded direction tests without a
relevant change. Profile selection, goal preservation/resumption and room missions
remain separate work, not completed by this increment.
