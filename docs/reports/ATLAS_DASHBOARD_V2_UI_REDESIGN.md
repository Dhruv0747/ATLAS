# ATLAS Dashboard V2 redesign: Home and 3D Vision Lab (Stage 31)

Date 2026-10-21. Status: **FIX IMPLEMENTED, OFFLINE TESTED, JETSON VERIFIED (package rehearsal), not DEPLOYED.**
Screenshots (camera feed replaced by a placeholder): `evidence/stage31_ui/`.

## What was wrong

The old Home has 14 panels at the same visual weight, 13 header buttons, a duplicate page bar, voice-LED legends, GNSS footnotes and long technical status strings, all permanently visible.

On a phone the page was 7,657 px tall and 436 px wide on a 390 px screen, so it scrolled sideways (`before_home_*.webp`).

## Design

The look is the existing ATLAS identity, unchanged: logo, Michroma headings, sky/terrain/amber/signal tokens, subtle glass. This keeps every V2 page consistent. The change is hierarchy:

1. **Top bar.**
   - Logo.
   - The single most important fact, in a large colour-coded **safety pill**: "E-STOP latched" with its reason, "Commissioning armed", or "Stop released".
   - Connection, mode (manual only or autonomy permitted), localization and motion chips.
   - The battery badge.
   - Home, Navigation and Diagnostics, plus a **More** menu: Commissioning, full camera, LiDAR 360°, Wi-Fi, Visual cloud, Talk/listen, Classic layout, Shut down.
2. **Systems rail.** Seven compact cards (Jetson, Battery, LiDAR, Depth camera, Wheel encoders, IMU, Network). Hardware health stays as a one-line summary that opens the full grid.
3. **Primary area.**
   - Live camera.
   - Safety and manual drive: E-STOP reset with PIN, hold-to-drive pad including its E-STOP.
   - Mission and position: saved map preview, mission, control, localization, drive controller, plus the existing "Check my location" tool.
4. **Test labs.** Three clearly labelled shortcuts: Motor & Encoder, FlySky, 3D Vision Lab.
5. **Collapsible drawers**, closed by default and remembered per browser:
   - Hardware health;
   - Camera pan/tilt and tracking;
   - Voice companion;
   - Range sensors and radar;
   - Power and environment;
   - Network/GNSS/cellular;
   - Jetson report and AI power;
   - Drive report;
   - **Developer diagnostics**: raw telemetry table, service logs, USB identity, file fingerprints, all unchanged.

E-STOP stays prominent on every layout. The fixed bottom dock is unchanged, the drive-pad E-STOP is unchanged, and neither is ever inside a menu or drawer (a test enforces this).

## Sensor presentation

Each card shows:
- the name;
- a state pill: Connected / Stale / Fault / Disconnected / Unverified / Unavailable / Off;
- one or two real measurements;
- the last update time.

Tapping a card opens the existing detail view. Missing data is shown as unavailable, never as an invented value.

| Card | What it shows (all from existing telemetry) |
|---|---|
| Jetson | CPU, RAM and temperature bars with a tick at the 3D camera admission limits (75% / 80% / 70 °C) |
| Battery | DALY BMS charge, volts, amps, cell spread, SOC source. If the BMS is stale or invalid the card says so and hides the values |
| LiDAR | Live top-down point plot (`/api/lidar-view`, polled only while the card is on screen), scan Hz, valid points, nearest obstacle and side |
| Depth camera | Astra viewer state from the new lease-free `/api/vision3d/summary`, e.g. "Last start stopped safely at 80.8% CPU (limit 75%)" |
| Wheel encoders | Four wheels laid out like the rover, with count and direction, consensus state, and excluded wheels in red |
| IMU | Attitude dial (roll and pitch horizon, heading marker), yaw, and whether the gyro feeds the EKF |
| Network | Active route, Wi-Fi / cellular / Tailscale check results, rescue hotspot state |

## 3D Vision Lab

- A state banner answers "is it working, and if not, why":
  - RESOURCE BLOCKED reads: "CPU reached 80.8%, above the 75% limit, so the camera was turned off and the driver was stopped. Nothing else on ATLAS was changed."
  - Alongside it: measured CPU, RAM and temperature against their limits, and "Camera driver: Stopped safely".
- Clear Depth only / Depth + RGB choice, **Start 60-second view** and **Stop camera** buttons.
- Depth and RGB panels with live/stale chips, FPS, frame age, a colour legend, and click-to-measure with honest wording ("uncalibrated").
- IR, point cloud and the obstacle prototype sit in a drawer, **"Disabled until calibration"**. The cloud checkbox stays disabled.
- Raw runtime and calibration JSON sits in a Developer diagnostics drawer.
- The standard E-STOP dock was added. It uses the same `estop.js` request as the LiDAR and camera pages.

## Preserved behaviour, checked

- Every element `id` of the old Home exists exactly once. `command.js`, `shell.js`, `diagnostics.js`, `motion-status.js` and `location-check.js` are unchanged and load in the same order; `home-cards.js` loads last.
- Drive (`data-l`/`data-a`), camera (`data-cam`/`data-dir`), tracking and AI button markup is identical.
- Headless-browser comparison of a held Forward press, a held Pan right and an E-STOP press on the old and new Home: identical request sequences (`action=drive…start=1/0`, `action=stop`, `action=camera…`, `action=e_stop`); only the random press nonce differs.
- Loading the new Home, opening every drawer and opening a card detail sends **no** POST.
- `home-cards.js` only GETs `/api/lidar-view` and `/api/vision3d/summary`. It never calls `/api/vision3d/status`, because that GET extends the camera viewer lease.
- The old Home stays at `/v2/classic.html`, byte-identical to the live file (sha256 `f53d6812…`).

## Desktop, tablet and mobile tests

Offline harness:
- Real `/api/*` replies captured read-only from the Jetson at 13:57, with the Pi camera image replaced by a placeholder.
- Chromium 1440×900, 900×1100 and 390×844.

| Page | Desktop | Mobile 390 px |
|---|---|---|
| Home before | 3,903 px tall | 7,657 px tall, **436 px wide (sideways scroll)** |
| Home after | 1,580 px tall, no overflow | 3,503 px tall, **390 px (no sideways scroll)** |
| Vision Lab after | 1,288 px, no overflow | 1,653 px, no overflow |

No JavaScript errors on any page. Click-to-measure returned a reading against a synthetic depth frame.

**Not yet verified live**, because the new pages were not deployed: real camera feed in the new layout, real Astra frames, and behaviour on your actual phone.

## Deployment

See section 10 of [`ATLAS_NEW_DEVELOPER_HANDOVER_AND_RECOVERY.md`](ATLAS_NEW_DEVELOPER_HANDOVER_AND_RECOVERY.md).
- `apply-ui` is static-only and needs no restart.
- The Home Depth card shows "Open lab" until `apply-astra` adds the summary route.
- Roll back with `rollback-ui`. The classic page also stays available at `/v2/classic.html`.
