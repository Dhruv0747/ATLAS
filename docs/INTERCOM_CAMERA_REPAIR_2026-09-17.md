# Intercom and camera-control repair — 2026-09-17

## Evidence

- HTTPS intercom page and state endpoint responded, but a hardware-isolated
  test of the deployed audio pipeline sent 768 bytes for 320 mono s16 samples
  (only 640 bytes are valid). The extra allocation padding can cause noise and
  excessive playback duration; it is not evidence that every audible click
  has the same cause.
- Camera JPEG remained live while PCA/camera, environmental and radar reports
  aged together. Kernel logs recorded UNO USB disconnects at 19:44:56 IST,
  errors -32/-71, and CMSIS-DAP enumeration at 19:45:49. The driver reopened
  that debug port despite the installed sensor application using native USB.
- The physical trigger for that disconnect is not established: a software
  recovery does not prove the USB cable, hub or power supply fault-free.

## Changes

1. `atlas_intercom.py`: send sample bytes only, serialize writes, bound the
   write timeout, and discard previous-call queued microphone frames at start.
2. `ultrasonic_arduino_bridge.py`: commissioned native mode requires a verified
   native-device symlink; no generic ACM/debug fallback. Missing-interface
   retries are throttled to two seconds and reported as offline.
3. `atlas_status_web.py`: reject camera commands if controller status is older
   than two seconds or not explicitly online; offline reports cannot turn
   camera/PCA status green. Servo pulse acknowledgements are not encoders.

## Recovery and deployment

The user could not reach RESET. Stopped only the sensor-hub bridge, used the
UNO debug serial reset/boot mechanism and installed BOSSA with `-i -R` only,
then confirmed the original native application returned. **No erase, write,
firmware upload, or USB device permission change was performed.** Arduino's
[bridge source](https://github.com/arduino/uno-r4-wifi-usb-bridge/blob/main/UNOR4USBBridge/UNOR4USBBridge.ino)
documents the reset line-coding behavior. The installed Arduino platform
configuration confirmed this board's BOSSA upload/reset interface.

Backup: `/home/jetson/project-atlas-migration/intercom-camera-fix-20260917/before/`.
Candidate tests preceded copying the three runtime files into
`/home/jetson/project_atlas/scripts/`. Intercom, sensor hub and status web services
were restarted and remain enabled for startup. No full Jetson reboot was tested.

## Validation

- 18 repair/serial unit tests passed in the Jetson intercom environment,
  including the installed PyAV resampler. Six existing camera mapping tests
  passed separately. Both embedded dashboard scripts passed JavaScript syntax
  checks. Python files compiled successfully.
- Synthetic bidirectional WebRTC: connected, 148 returned audio frames and
  109 playback packets; corrected packet sizes 608 bytes for the initial
  partial frame and 640 thereafter. Stop returned HTTP 200 and AI-voice mode.
  No real microphone capture or speaker playback was used for this test.
- Dashboard pan: 2300 → 2150 → 2300 us, acknowledgement about 0.320 s.
  Tilt: 1500 → 1650 → 1500 us, acknowledgement about 0.119 s.
  The first probe aborted on its overly strict 100-us test bound because the
  existing dashboard step is 150 us; its cleanup returned pan before retesting.
- PCA, BME680, AMG8833 and radar messages returned. Short observation cannot
  certify long-duration electrical reliability or every sensor's calibration.
- No rover wheel/steering, navigation parameters, firmware or safety policy
  was changed. Camera pulse settings returned to their test-start values.
- Final 20-second read-only ROS observation received 663 `/cmd_vel` messages,
  all zero. Mux remained manual-only with its existing remote-stop latch.
  Camera reports stayed 0.0–0.2 seconds old, radar decoded fresh valid frames,
  and no further USB kernel errors appeared after deployment during observation.

Remaining: user confirmation of physical pan/tilt and a two-room intercom audio
check. Hardware recurrence requires correlating future USB/power evidence;
do not treat these results as a permanent electrical fault guarantee.
