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

Next: complete bounded stationary timing/fault checks; known-distance front/rear
targets; no echo/disconnection and reconnect; sustained camera/radar/I2C workload;
then isolated stop-output validation. Ground testing follows only after existing
steering, measured encoder distance, stopping, localization and remote-stop gates
are satisfied. Do not repeat previously recorded direction tests without a
relevant change. Profile selection, goal preservation/resumption and room missions
remain separate work, not completed by this increment.
