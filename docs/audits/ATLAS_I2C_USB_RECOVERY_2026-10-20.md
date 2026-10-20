# UNO I2C / USB recovery and clock-safe silence watchdog

## What is verified

This incident had two different phases, not one proven common cause:

1. The UNO's native USB initially streamed fresh frames but reported PCA9685,
   BME680 and AMG8833 unavailable, SDA/SCL LOW. That is not a dashboard-only fault.
2. During the supervised temporary pin test and restoration, the USB path later
   failed enumeration. Kernel logs show xUSB transfer errors, another downstream
   hub disconnect, descriptor timeouts (-110), and address errors (-71).
   Those later errors do not establish the cause of the earlier I2C failure.
3. The operator reported A4/A5 disconnected. The temporary standalone sketch
   reported both LOW in nine rounds of GPIO_PULLUP, WIRE_IDLE and
   GPIO_AFTER_WIRE_END. No independent voltage measurement or known-high control
   input was captured. These readings do not certify permanent MCU damage, nor
   independently verify that every parallel SDA/SCL connection was isolated.
4. The saved commissioned 68904-byte hub binary was restored: SHA256
   `989dd795e8474977f43b0f47f01548e0c9f802056be44fb67d951dff22222c81`.
   Upload succeeded, but USB did not initially return. Several operator resets
   and USB reconnects did not immediately restore it. Only after the operator's
   full power cycle did native USB, normal UVALID1 protocol and all three I2C
   devices return. This verifies running protocol, not bit-for-bit flash readback.

The existing exact-device ModemManager-ignore rule is installed. USB is authorized
with power/control=on and runtime_status=active. No evidence justifies blaming
autosuspend or disabling ModemManager/networking. LED tick marks are local
device/activity indicators, not proof of a working Jetson USB transport.

## Reproduced software defect and scoped repair

The eight-second serial-silence watchdog used time.time(). Pure tests executing
the actual bridge tick reproduce two failures: a backward wall-clock step delays
reopening a silent link; a forward step reopens a healthy link unnecessarily.
The boot journal confirms initial NTP synchronization and a wall-time correction
in this session. It does not prove the watchdog triggered today's initial I2C
failure or the subsequent kernel USB failure.

Changed only transport receive timestamps and silence duration to time.monotonic().
The eight-second threshold, reconnect backoff, sensor rates, message formats,
per-sample validity, DTR behavior, GPIO handling, firmware, camera-home settings,
steering and motion authority are unchanged. No reset/flash is part of this fix.
Wall timestamps remain for human-facing telemetry; reconnect scheduling already
used monotonic time and was not duplicated.

67 offline tests pass: four clock tests, six serial-fragment tests, 38 ultrasonic
validity/bridge/mux tests and 19 USB identity tests. Before the change, the two
clock-step behaviors and new timestamp contract failed as expected. Fixture
updates use the new clock field and isolate the current independent localization
guard; production localization/stop logic was not edited.

## Deployment

Original live bridge SHA256:
`c77ddd38c0ade69db54bee785baa602847c6556aa54cddc80e7e5c94205abf63`.
Installed tested bridge SHA256:
`34e43322fcf7844d45f6ae272b2de150bc8d8adb53f8cf2a31e798a88faa5eff`.

First attempt rolled back because its six-second postflight ran before the first
fresh I2C status frame (Python/ROS startup plus the existing five-second frame
period). Failure evidence remains at
`/home/jetson/project-atlas-migration/i2c-clock-20261020-5pW4EbVY/`.
Second attempt uses a bounded 25-second read-only readiness wait, retaining all
freshness thresholds and rejecting actual offline devices. It verified source
hash, fresh sensor data, latched manual-only stop/zero commands, recorder OFF,
protected source/calibration hashes and unchanged essential service identities.
Only the UNO bridge restarted. No hub/controller/network reset was performed.

Verified deployment/rollback folder:
`/home/jetson/project-atlas-migration/i2c-clock-ready-20261020-glw8ENc8/`.
Rollback: restore bridge.original.py there to
`/home/jetson/project_atlas/scripts/ultrasonic_arduino_bridge.py`, then restart only
atlas-uno-r4-sensor-hub.service while stopped. No calibration or map rollback needed.
Local raw evidence remains in artifacts/uno_pin_probe_20261020/ and is not in Git.

Post-deployment stationary observation: PASS, 13 samples over 60 seconds, no
freshness/offline failures. PCA9685, BME680 and AMG8833 remained reported online.
Essential service PIDs/restart counts and protected hashes remained unchanged.
Stop remained latched, commands zero, commissioning disabled and recorder OFF.
CPU endpoint samples were 64.7% and 62.4%, RAM 49%, temperature 52/51 C; these
are endpoint readings, not a continuous resource-peak qualification. Evidence:
`stability60.json` in the verified deployment folder. This short check does not
prove the original intermittent I2C lockup permanently eliminated.

## Limits and next discriminating evidence

The transport timing defect is fixed, but the original I2C electrical/firmware
lockup's root cause remains UNRESOLVED. A successful cold restart and short
observation do not establish permanent fault elimination. Do not declare the
UNO/sensors damaged, change power rails blindly, repeatedly flash firmware,
automatically reset a shared USB hub, or weaken fail-closed sensor handling.

If the failure returns, capture USB identity/kernel events, hub sample ages and
MCU uptime/recovery counts before resetting. To distinguish an electrical clamp
from GPIO-reporting/peripheral state, measure the actual sensor supply and SDA/SCL
voltages during the fault with a verified isolated/reference input. No further
physical test or motion was requested/performed for this clock repair.
