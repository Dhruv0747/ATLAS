# Camera settings — issue #11 (25 Oct 2026)

Dashboard page `/v2/cameras` (linked from the Home menu and the camera page): two independent cards, Astra Pro and Pi
Camera Module 3. Each shows connection, running/streaming state, device, current settings, live FPS, and a
recommendation with its reason. Changes happen only in the Settings dialog: grouped controls, server-side validation
while editing, Apply / Cancel / Reset to defaults. Capabilities are a collapsible "Detected capabilities" section.

## Truthful capabilities (from the hardware, not the catalogue)
| Camera | Source | Detected |
|---|---|---|
| Astra depth / IR | read-only OpenNI enumeration of this unit (serial 17122120830, fw 5.8.22), 21 Oct, no stream started | depth 160x120@30, 320x240@30, 640x480@30, 1280x1024@7; IR 640x480@30 (verified), 640x400, 1280x1024/960/720@30; IR 320x240 advertised but never served (shown struck through) |
| Astra RGB | UVC descriptors cached by Linux at plug-in (sysfs; the camera is not opened) | MJPEG 1280x720, 640x480, 352x288, 320x240, 176x144, 160x120 at 30/15 fps |
| Astra controls | same OpenNI enumeration | IR gain, IR exposure, laser on/off: not supported (greyed); registration disabled until calibration |
| Pi Camera | Argus sensor modes printed when atlas-camera starts (journal) | 4608x2592 up to 14 fps, 2304x1296 up to 55, 1536x864 up to 90; no HDR mode, no autofocus control |
| Pi controls | `gst-inspect-1.0 nvarguscamerasrc` on this Jetson | exposure compensation, saturation, white balance, anti-banding, AE/AWB lock, edge enhancement, noise reduction, sensor mode |

Manufacturer figures (Astra 640x480@30; Pi Camera 2304x1296@56, HDR @30, 1536x864@120) are shown separately as reference.

## How settings apply
- **Astra:** saved; used at the next Vision Lab Start (`atlas_vision3d_runtime.driver_args` reads them, validated).
  The camera is never restarted by Apply. The 60-s session, 4-s lease, CPU 75 / RAM 80 / 70 °C guards and the
  port-independent identity check are unchanged.
- **Pi Camera:** saved, then `atlas-camera` restarted through `scripts/atlas_camera_launch.py` (systemd drop-in).
  Refused unless E-STOP latched, manual-only, commissioning disarmed, mission READY and the Vision Lab idle; one restart
  per 20 s. If the camera does not report "Camera node started" within 25 s, the previous settings are restored and the
  camera restarted again. Every apply/reject/failure is logged to `~/.local/state/project_atlas/camera_settings.log`.
- **Defaults are the exact pre-#11 values.** With no saved settings the camera node gets byte-identical parameters
  and pipeline, and the Astra driver gets byte-identical arguments (tested for all six modes).

## Recommendation
Only measured settings are recommended: Astra depth 160x120@30 (24 Oct, 60 s, ~14 fps, CPU 67%) and IR 640x480@30
(21 Oct, 29.7 fps); Pi Camera 1280x720@10 (production, camera node 38–40% of one core). Untested modes are never
labelled "best". Finding for a later benchmark: at 1280x720 Argus runs sensor mode 2 (1536x864, up to 90 fps).

## Tests
`project_atlas/tests/test_camera_settings.py` 21/21: Argus/UVC parsing, rejection of unsupported FPS/resolution/format/
controls, unknown keys, corrupt or invalid saved settings fall back to defaults, identical default launch for both
cameras, API same-origin + header, parked gate (4 refusal cases), Vision Lab session refusal, apply success,
failed start reverts, rate limit. End-to-end with the real plug-in in Chromium (desktop + 390 px phone): validation
messages, Apply/Reset, disabled Apply with reason when not parked, sensor-mode-dependent sizes and FPS limit.

## Not done (needs owner approval)
- Deployment: install files, restart `rover-status-web` (routes), `daemon-reload` + restart `atlas-camera` (launcher drop-in).
- Two-stream load benchmark (would restart cameras with different settings).
- Astra re-detection from the page (opening the device via OpenNI) is not offered; the 21 Oct enumeration is used.
