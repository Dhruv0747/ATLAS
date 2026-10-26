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

## Deployment — 25 Oct 2026 12:13–12:21 IST (owner approval 12:11)

Pre-checks: E-STOP latched, manual-only, commissioning disarmed, mission READY, `/cmd_vel` zero, motor speed 0,
Vision Lab OFF, no Astra process, recorder inactive; live files unchanged since the build (no drift); no route conflicts.
Backups: `~/project-atlas-migration/camset_20261025/backup/` (status web, web_v2, vision3d runtime, index/camera pages,
camera_node.py, atlas-camera.service); one-step `rollback.sh` alongside.

| Step | Result |
|---|---|
| Install files | 14 files + capability JSON; hashes recorded |
| Restart `rover-status-web` | up in 6 s; `/v2/`, `/v2/cameras`, `/api/cameras/*`, Vision Lab, camera page, `/camera.jpg` all 200 |
| Drop-in + `daemon-reload` + restart `atlas-camera` | launcher passed the exact previous parameters; capture pipeline **byte-identical** to before; frames live |
| API checks | missing header / foreign origin 403; invalid Astra/Pi modes, HDR request 400 with reasons; Astra Apply saved for next Start (no camera start), Restore -> defaults |
| Pi Apply (JPEG 75->76) / Restore Defaults | first attempt falsely reported failure and reverted: the verifier counted the **stopping** process's normal ExternalShutdownException traceback. Fixed (judge only lines after the new launcher line; 4 regression tests, 25/25), redeployed the web module, retested: both 200 "restarted", parameters as requested, pipeline identical, frames live |
| Resources before -> after (60 x 1 s) | CPU 62.3 -> 61.9% mean (max 65.1 -> 66.1), GPU 0 -> 0%, RAM 60.5 -> 59.4%, temperature 63.7 -> 64.2 C |
| Safety after | E-STOP latched, manual-only, commissioning disarmed, mission READY, commands zero, LiDAR/IMU/encoders fresh |
| Protected services | only rover-status-web and atlas-camera changed PID; none failed |

Also confirmed: after the Jetson's ~10:30 reboot the Astra came back CONNECTED on USB 2.3.4 with access links
(port-independent rule survives a reboot).

### Still open (issue #11 stays open)
- Two-stream load benchmark on the Jetson (needs separate approval; would restart cameras with other settings).
- Astra settings take effect at the next Vision Lab Start; not exercised live (no Astra streaming allowed during deployment).
- Astra modes come from the 21 Oct read-only OpenNI enumeration; a runtime re-detection from the page is not offered.
- Replug at an alternate port: verified offline and across a reboot, not by a physical replug.
- Dialog Cancel/close and visual layout verified in Chromium against the real plug-in offline; the deployed page
  serves the same JS/CSS (hash-verified) but was not driven in a browser on the Jetson.


---

## Verification report — 26 Oct 2026 (real Jetson, ATLAS parked)

ATLAS parked for every on-robot step: E-STOP latched, manual-only, commissioning disarmed, mission READY, zero commands. No motor, navigation, mission or safety-limit change. Two disruptive steps (two-camera load, USB replug) were run only after separate owner approval.

### Deployed
- `6881d08`: Issue #11 completion. Pi FPS is measured from frame timestamps, not the 1 Hz `camera_info` heartbeat (the old "0.9 FPS"). Also: Astra received vs configured FPS, runtime read-only OpenNI re-detect, USB 2.0 budget, formats. Merged onto `c6a46d7` (Vision Lab refusal messages, deployed earlier today).
- Only rover-status-web was restarted (dashboard back in 12 s). Protected services (mux, base, remote, camera, safety, EKF, LiDAR) kept the same PIDs with no restarts.
- Rollback: `~/project-atlas-migration/i11pkg2_20261026/rollback.sh` (backups beside it).
- Tests: full suite `pytest -s` gives 1111 passed, 84 failed, 20 skipped. All 84 failures also fail on the pre-change HEAD; none are new.

### Acceptance checklist
Evidence types: **[live]** = my test on the deployed Jetson, **[owner]** = owner action/observation, **[offline]** = automated tests.

| Criterion | Result | Evidence |
|---|---|---|
| Two independent camera cards; connection / streaming / device / FPS | **PASS** | [live] Both cards Connected. Astra on USB 2.3.4, later 2.3.1; Pi on CSI 0. |
| Pi actual FPS (was "0.9 FPS") | **PASS** | [live] Measure (API + dashboard button): 10.0 fps over 2.9 s, 30 frames, configured 10. The 0.9 was the 1 Hz heartbeat, now never shown as FPS. |
| Runtime mode detection, not the catalogue | **PASS** | [live] Read-only re-detect 12:16 and 18:33: serial 17122120830; 8 depth / 21 IR / 23 colour modes; no stream started. |
| Validation; unsupported/over-budget refused | **PASS** | [live] IR 1280×1024@30 and 1280×960@30 greyed out (over 32 MB/s); "Valid for this camera" with per-stream MB/s. [offline] API rejection tests. |
| Cancel / Apply / Restore (Astra) | **PASS** | [live] Cancel left the saved settings unchanged. Apply depth 320×240@30 saved. Restore went back to 160×120@30. |
| Apply / Restore (Pi), parked only | **PASS**, with defect below | [live] Apply JPEG 80: restarted, 10.0 fps. Restore: JPEG 75, back to the previous pipeline. |
| Saved Astra settings used by Vision Lab | **PASS** | [live] Saved depth 320×240@30. Driver log: `set depth video mode Resolution :320x240@30Hz`. 560 frames at 320×240, ~26.5 fps received. Peak guard CPU 70.3% (limit 75), RAM 62%, 64 °C. Clean stop. |
| Disconnected state shown | **PASS** | [owner+live] During the port change the dashboard showed `NOT_DETECTED · Astra not detected on USB`. |
| Replug at alternate port | **PASS** | [owner+live] Moved from 2.3.4 to 2.3.1. Detected automatically, same serial and modes, access set up automatically (group `atlas-astra`). See the note on the first attempt below. |
| Two-stream Jetson load benchmark (limits unchanged) | **PARTIAL: 42 of 60 s** | [live, approved] Astra depth+RGB with the Pi camera streaming: guard CPU 65.6–70.8%, Pi 10.0 fps, depth ~13 fps, RGB ~14.3 fps received, 482/525 frames, no limit hit. Both runs (27 s, 42 s) ended with `viewer lease expired`. The test PC lost its Tailscale link (route changes 16:18:07, 16:20:03, 16:20:28 IST); the Jetson kept sampling every second. |
| No motor/mission/safety change; no camera on page load | **PASS** | [live] Parked throughout; protected PIDs unchanged; the camera started only on an explicit Start. |

### Defects found
1. **Pi Apply restarts the camera twice.** About 9 s after each Apply/Restore, `atlas_sensor_recovery` logged `RECOVERING: camera (stale: no data for 8.9s); restarting atlas-camera.service` (attempts 1/3 at 12:18:10, 2/3 at 12:19:44 IST). That's a second outage, and it uses up the recovery budget.
   - **Fix committed, NOT deployed** (`240340b`): a bounded "intentional restart" hold (≤40 s, honoured for `atlas-camera.service` only and only if ≤45 s ahead). Any read error means the existing recovery runs; 9 new tests.
   - Deploying needs the owner's approval: it restarts atlas-sensor-recovery and rover-status-web.
2. **First replug attempt (17:03):** the Astra failed to start on hub `1-2.3` port 1 (`device descriptor read error -71`, `not accepting address`, `unable to enumerate USB device`). The hub reset, and the GPS adapter on hub `1-2.4` logged -32 errors and went offline until reboot.
   - The camera never appeared on USB, so no software could attach to it. It's a power/contact limit of that hub port.
   - **Proposed (not built):** a read-only dashboard message that explains a failed enumeration and names the port.

### Status
Leaving this issue **open**:
- the double-restart fix needs approval and deployment;
- the full 60-s two-stream run, from a client on the same LAN, needs one more owner-approved run (or owner acceptance of the 42-s result);
- the enumeration-failure message is proposed.


---

## Final verification: 26 Oct 2026, 18:38–18:50 IST (owner-approved)

Pre-checks: E-STOP latched, source STOPPED, manual-only, commissioning disarmed, mission READY, zero commands, drive controller DISABLED, Vision Lab OFF. ATLAS stayed parked throughout. The 7 protected services (mux, base, remote, camera, safety, EKF, LiDAR) kept the same PIDs with no restarts.

### Deployed (fix3)
| File | sha (old → new) | Commit |
|---|---|---|
| scripts/atlas_sensor_recovery.py | ea8b4da4 → c6b5ac79 | `240340b` |
| scripts/atlas_camera_settings.py | d1229c81 → dbfc69d5 | `240340b` |
| scripts/atlas_camera_settings_web.py | f11a6daf → 71627d3e | `240340b` + `b36c0bd` |
| scripts/atlas_astra_usb.py | b7b49e55 → b7c8cd4e | `b36c0bd` |
| web/v2/home-cards.js, cameras.js | 7c8f1daf → 3adbcd0b, c2087598 → 2993bd00 | `b36c0bd` |

- Restarted only `atlas-sensor-recovery` and `rover-status-web` (dashboard back in 20 s).
- Backups and rollback: `~/project-atlas-migration/fix3_20261026/rollback.sh` (auto-rollback was armed for import, service, safety and protected-PID checks; it was not needed).
- Tests: full suite `pytest -s` gives 1118 passed, 84 failed, 20 skipped. All 84 failures also fail on the pre-change HEAD; 0 new. New tests: 9 (recovery hold) and 7 (USB start failure).

### 1. Pi Camera double restart: FIXED, verified live
- Pi Apply (JPEG 80) took 11.1 s, Restore Defaults 10.6 s; Pi camera at 10.0 fps after each.
- `atlas-camera` started **exactly twice** (18:44:58 Apply, 18:45:33 Restore). Before the fix each action also triggered a recovery restart.
- Sensor recovery logged `RECOVERY HELD: camera stale: no data for 9.7s; atlas-camera.service is being restarted on purpose (bounded hold…)` and no `RECOVERING: camera`.
- The hold file expired by itself 10 s after Restore.
- The hold only applies to `atlas-camera.service`, is capped at 45 s, and any read error means normal recovery runs.

### 2. Dual-camera benchmark: PASS (full 60 s, LAN client)
Client: headless Chromium on the owner's PC over the Wi-Fi LAN (`http://192.168.1.16:8088`), not Tailscale. Pi camera page streaming plus Vision Lab "Depth + RGB", default modes (depth 160×120@30, RGB 320×240@15). Limits unchanged (75% CPU / 80% RAM / 70 °C).

| Result | Value |
|---|---|
| Session | `60-second session complete`, 60 guard samples, no guard triggered, driver stopped cleanly |
| Guard CPU | avg 63.0%, min 60.5%, max 66.7% |
| RAM / temp (last guard sample) | 61.6% / 65.2 °C |
| Astra received fps | depth 13.6 avg (742 frames), RGB 14.7 avg (818 frames) |
| Pi camera fps (measured) | 9.7 avg, 10.0 max |
| Astra driver | ~8% of one core, 85 MiB RSS |
| Slow or failed dashboard requests | none |

The two earlier runs (27 s and 42 s) ended only because the Tailscale client link changed routes.

### 3. USB start-failure message: deployed
- When the Astra is `NOT_DETECTED`, the dashboard reads the kernel log (read-only, last 15 min) for a port that gave up starting and still has nothing attached.
- It then explains the failure: Home card pill "USB failed", Camera settings chip "USB start failed", and the message *"A USB device plugged into port 2.3.1 failed to start at HH:MM (power or contact problem)… If that was the Astra: unplug it, then use a different port or a powered USB hub."*
- No reset, power-cycle, unbind or retry was added; USB identity, states and recovery are unchanged.
- **Verified with the deployed code** on the Jetson: the kernel lines captured at the 17:03 failure, a simulated USB tree with the camera absent, and the deployed Camera settings page, which showed chip `USB start failed` plus the message. The real 17:03 kernel log wasn't saved by that boot, so a live recurrence can't be replayed safely; the full set of failure and no-failure cases is covered offline.

### Acceptance summary
Every criterion from the 18:33 report is PASS. The open items there are now closed: the benchmark ran the full 60 s (PASS), the double restart is fixed and verified (PASS), and the enumeration message is deployed and verified (PASS).

Unrelated note: sensor recovery reported `RECOVERY INCOMPLETE: radar; hardware inspection may be required` (radar stale 90 s, attempt 2/3 this boot). That predates this work and is not part of #11.

Closing as complete.
