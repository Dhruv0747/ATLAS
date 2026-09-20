# Ultrasonic sample-validity increment — 2026-09-20

## Status

Built and tested in source and an isolated Jetson staging directory. **Not
activated:** the subsequent installation attempt could not enter the UNO
bootloader. No firmware erase/write or active source replacement occurred.
The hub/recovery services were temporarily stopped and restarted; no motor
service restart, drive command, map command or autonomy enable was performed.
Their restart is not proof that sensor communication recovered; see below.

Baseline: `d3f2d87`. The live check found manual-only=true, stop_latched=true,
zero commanded velocity, selected encoders M1/M2/M3, excluded M4, and
navigation_validated=false. Front/rear telemetry was arriving; this is not a
physical reliability PASS. Saved steering geometry and camera home are untouched.

## Installation attempt / recovery boundary

On 2026-09-20 the operator confirmed that drive-motor and camera-servo power
were OFF, with Jetson/UNO powered. The exact Arduino application device was
identified (VID:PID `2341:006d`). Candidate binary hash, live baseline source
hashes and fresh manual-only/latched-stop/zero-command state were verified.
Previous live source files were backed up under the staging directory's
`backup/`, including the old firmware source and a manifest. A matching raw
installed-flash backup was **not obtained**.

Native USB 1200-baud bootloader entry did not succeed. A subsequent DTR
transition returned a broken-pipe error; read-only `bossac -i` could not find
a bootloader. No erase/write command was run. The device remained enumerated
as the Arduino application. The operator cannot reach the reset button, and
targeted USB-device reset needs administrator access unavailable to this
session; it was not attempted. No other USB device or hub was reset.

`atlas-uno-r4-sensor-hub.service` and `atlas-sensor-recovery.service` were
restarted with their existing software/configuration. Both reported active,
but the hub then reported USB input/output errors and no fresh sensor data.
Last-known radar, BME680, AMG8833 and ultrasound readings are **stale**, not
recovered live readings. Manual-only and latched stop remained true with fresh
zero commanded velocity. Keep motor/servo power OFF. Existing hub reconnect
initialization can issue saved camera-home commands; no physical servo test
was requested or claimed.

The operator also confirmed that the UNO cable cannot be safely reached.
Further installation/reset attempts are therefore stopped. Do not reach inside
the rover. Safe access to the UNO reset/power connection, or an explicitly
authorized administrator-assisted targeted recovery, is needed before another
attempt. Recheck fresh sensor samples before declaring the old runtime restored.
Firmware installation remains blocked until safe bootloader access is available;
do not deploy the new mux by itself.

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
  **68,896 bytes flash (26%), 10,984 bytes global RAM (33%)**. Build only.
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

## Staging and activation

Candidate only:
`/home/jetson/project-atlas-migration/ultrasonic-validity-20260920/`

Firmware binary SHA-256:
`989dd795e8474977f43b0f47f01548e0c9f802056be44fb67d951dff22222c81`

Before activation, obtain fresh confirmation that drive-motor and camera-servo
power are off, with Jetson/UNO USB still powered. Reconnect currently sends camera
home commands; lifted wheels alone do not address that hazard. Identify the UNO
device afresh and back up live files plus the matching old firmware artifact.
Do not flash or restart from this document without that confirmation.

Deploy the paired firmware + helper + bridge + mux + read-only dashboard/audit
files together while stopped. A new mux with old firmware deliberately blocks
autonomous translation; old raw ranges are not a fallback. Preserve service
environment, home, manual-only/stop latch, steering locks and all calibration.
Record installed binary/source hashes; a source build does not prove flash
contents. Verify every expected sensor still streams after startup. Roll back
the paired candidate if stationary validation fails; do not unlock autonomy.

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

Next: paired installation with motor/servo power off; known-distance front/rear
targets; no echo/disconnection and reconnect; sustained camera/radar/I2C workload;
then isolated stop-output validation. Ground testing follows only after existing
steering, measured encoder distance, stopping, localization and remote-stop gates
are satisfied. Do not repeat previously recorded direction tests without a
relevant change. Profile selection, goal preservation/resumption and room missions
remain separate work, not completed by this increment.
