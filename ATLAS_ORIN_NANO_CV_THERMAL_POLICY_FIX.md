# Orin Nano CV temperature policy and fresh safety check

15 October2026. Continued from `1ed30475b82f77b42747c4ff719d191c022561dc`
on `agent/sync-developer-20261011`. Owner authorized investigation, probe correction
and a read-only safety recheck when reachable, with ATLAS stopped and recording off.

## Verified explanation

NVIDIA explicitly confirms that CV0/CV1/CV2 offline status is expected on Orin
Nano because the corresponding DLA/PVA hardware is absent:
[NVIDIA staff explanation](https://forums.developer.nvidia.com/t/offline-cv0-cv1-and-cv2/318940/39),
[sensor mapping](https://forums.developer.nvidia.com/t/offline-cv0-cv1-and-cv2/318940/15).
The [NVIDIA thermal guide](https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html#thermal-sensing)
also documents EAGAIN when a GPU/CV sensor's power rail is off. Expected absent
Nano CV readings must not be interpreted as an overheating/device-failure signal.

Fresh runtime device-tree identity:
`NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super`.
Its CV0/CV1/CV2 temperature attributes returned errno11/EAGAIN, matching the
documented nonapplicable Nano readings. Prior probe code incorrectly required
every listed zone and therefore refused on this expected condition. This is
the verified thermal admission policy defect. The historical TypeError's exact
failing attribute remains unavailable from that older log.

## Probe correction

- Read model identity from `/proc/device-tree/model` for each invocation. No
  operator override or assumed identity from a hostname is used.
- Only exact `cv0-thermal`, `cv1-thermal`, `cv2-thermal` **temperature EAGAIN**
  on a verified Orin Nano is classified `not_applicable`, with null temperature,
  original path and errno retained.
- Require valid CPU, GPU, SoC0/1/2 and TJ temperatures on this model. Unknown
  platforms retain strict error handling; the exception does not apply to NX/AGX.
- CV permission errors, malformed values and other I/O errors still block.
  Any available CV temperature is measured and checked, not discarded.
- Keep every actual temperature subject to70°C. CPU75%, RAM80%, E-STOP,
  zero-command, manual-only and commissioning checks remain unchanged.

No kernel thermal zones, power states, clocks or production files were modified.
The corrected PC-side probe was executed through SSH stdin, without installation.

## Tests

26 focused offline tests pass on Ubuntu22.04 Python3.10:22 probe tests plus4
receive-only operation contract tests. Added model/errno discrimination, required
core-zone failure, missing zones, available CV reading retention, device-tree
identity, end-to-end Nano admission and stop-latch refusal coverage.
The previous binary-read/traceback regressions and resource boundaries also pass.
No synthetic recording campaign was repeated.

## Fresh Jetson result

Initial read-only identification attempts could not connect. After owner confirmed
power ON, the corrected probe reached Jetson through the existing Tailscale SSH
endpoint. No networking or services were changed to restore reachability.
UTC start2026-10-15T03:54:40.283366+00:00 (09:24:40 IST).

| Check | Fresh evidence | Verdict |
| --- | --- | --- |
| CV0/1/2 | EAGAIN, model verified Nano | Not applicable; correct |
| Required thermal reads | Six valid; no thermal_read_errors | Pass |
| CPU/GPU | 61.5/60.75°C | Pass |
| SoC0/1/2, TJ | 60.593/61.156/60.343/61.5°C | Pass |
| CPU5×1s | 77.891156,70.068027,71.864407,69.759450,69.655172% | First interval exceeds75% |
| CPU mean / max | 71.847643 /77.891156% | Mean does not override failed interval |
| RAM | 67.269996% | Pass |
| Dashboard resources | CPU74.7%, RAM67%,61°C | Numeric limits pass; resource measurement age not exposed |
| E-STOP / policy source | stop_latched=true, STOPPED; policy age0.1s | Pass |
| Motor command | lin=0, ang=0; command age0.1s | Pass |
| Commissioning | commission_armed=false | Pass |
| Manual-only gate | manual_only=false | Required manual-only condition fails |
| Stage20 recorder | inactive, PID0, NRestarts0 | OFF confirmed |
| Disk | 395,472,146,432 bytes free | Observed |

**Overall verdict: BLOCKED for CPU interval0 and manual_only=false.**
The thermal false refusal is corrected and verified on this device. There is no
claim that autonomy is actively driving merely because manual_only is false:
the source is STOPPED with the stop latched. Neither flag nor CPU limits were
changed to obtain a pass. No recording retry was performed.

Other cached evidence: LiDAR age0.5s, encoders/health age0.0s, odometry age0.0s;
encoder-health says navigation_validated=false/autonomy_ready=false. This is not
ground validation, full IM10A-topic verification, a live bridge test or a
localization improvement. No movement was requested or commanded.

Localization unit remains PID8798/NRestarts8; base telemetry PID1869/NRestarts0.
These were observed, not restarted. Stage20 remains inactive. The probe contains
no recording activation or control commands.

## Evidence / next necessary action

Local artifact: `artifacts/offboard_nano_cv_check_20261015/terminal_tailscale.txt`.
SHA256: `7150821d92913a27f715cbacf1c5c0a8bf77dfacb02125d7fa910ed4f516d6f9`.
Generated raw diagnostics remain outside Git. This report and source/tests are
committed to the working branch; exact SHA/URL is in the final handoff.

Before any future recording, address CPU headroom and establish the required
manual-only safety state through an authorized change, then check admission
freshly. No active safety setting was changed in this task. Existing recording
and movement restrictions remain in effect.
