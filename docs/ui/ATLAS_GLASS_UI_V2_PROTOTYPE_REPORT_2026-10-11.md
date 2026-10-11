# ATLAS Glass UI V2: prototype and feature-preservation report (2026-10-11)

Status: **prototype on branch `claude/localization-motion-investigation`. Not deployed.**
- The production dashboard on the Jetson is unchanged.
- V1 (`/`, `/mapping`, `/commissioning`, `/wifi`) stays the default and the rollback.
- Everything below was tested offline, in headless Chromium, against responses recorded from the
  live Jetson. Every POST was captured by the test harness and never sent.
- **Nothing here is a physical verification.** The on-device check with your PC powered off is
  still required, and is part of the deployment proposal below.

## What was built

| File | Purpose |
|---|---|
| `web/v2/index.html` | Command center. It keeps all 57 V1 element IDs, every control, inline handler and data attribute, and adds a status bar, a sticky E-STOP dock and a responsive layout |
| `web/v2/command.js` | **Generated** from the V1 inline script by `tools/ui_v2/build_command_js.py`. It is verbatim except for 3 asserted patches:<br>- P1: poll the camera only while it is visible (plus the optional data saver);<br>- P2: poll the radar only while it is visible;<br>- P3: the Wi-Fi link opens `/v2/wifi`.<br>If V1 changes so that a patch no longer matches exactly once, the build fails |
| `web/v2/shell.js` | Layout helpers and **display-only** chips (localization, motion, stop latch). The localization chip mirrors the Live map page's `liveStatus()` order and thresholds, so it is never more optimistic than the map. Motion and latch chips show "unknown" when status is more than 5 s old |
| `web/v2/{mapping,commissioning,wifi}.html` | **Generated** from the V1 pages by `tools/ui_v2/build_pages.py`. The V1 markup and scripts are kept verbatim; V2 styles are layered by cascade order |
| `web/v2/estop.js` | Dock E-STOP for the Live map and Wi-Fi pages. Sends exactly the command-center request: form POST `/`, `action=e_stop` |
| `web/v2/base.css`, `glass.css`, `pages.css` | Tokens, the topographic backdrop, glass surfaces, the reduced-effects mode (`html.lite`) and the `@supports` fallback |
| `web/v2/assets/` | Logo as 2 KB WebP / 11.5 KB PNG (V1: 1.19 MB PNG); Michroma display font (18 KB, OFL); an SVG icon sprite |
| `scripts/atlas_web_v2.py` + 3 lines in `atlas_status_web.py` | Additive `/v2/...` static route on the existing port 8088, after the existing `client_allowed()` check. It uses an allowlist (page aliases, the `assets/` folder, known file types), has no directory listing, rejects dotfiles and traversal, and lets `ATLAS_WEB_V2_DIR` override the folder. **Not deployed** |
| `tests/test_atlas_web_v2.py` | 6 unit tests for the route: aliases, traversal and encoded traversal, hidden files, unknown types, the ordering after `client_allowed`, and that every repo V2 file is servable |
| `tools/ui_v2/test_ui_v2.py`, `harness.py` | The offline regression suite and recorded-data harness |

Architecture is unchanged:
- static HTML, CSS and JS, served by the same Jetson process;
- no framework, build server, CDN, web font service or PC dependency;
- no new endpoint except the static `/v2/` route;
- no ROS, navigation, motor, safety or POST-handler change.

### Identity

The ATLAS logo, name, cyan and green, and the operational wording are kept. Colours are taken
from the logo:
- sky `#22B8F0` for information and navigation;
- terrain green `#7CC242`, used **only** for verified/OK;
- amber for warnings;
- signal red **only** for E-STOP and faults.

The Michroma wide display face is used for headings and E-STOP. A faint topographic-contour
backdrop gives the glass panels something to sit on. It is static and composited once.

## Regression results (offline)

| Suite | Result |
|---|---|
| **Element IDs**: every V1 ID present in V2, after load with all `<details>` opened | Command 57/57, Live map 10/10, Commissioning 25/25, Wi-Fi 12/12. **0 missing** |
| **Links**: every V1 link target present in V2 (`/x` ≡ `/v2/x`) | **0 missing** |
| **Request contracts**: each visible V1 button pressed in V1 and in V2, comparing path, body, `Content-Type`, `X-Atlas-Wifi` and confirm-dialog text. Confirm dialogs are run twice, once dismissed and once accepted | Command 29/29 (desktop) and 29/29 (phone); Live map 1/1; Wi-Fi 3/3; Commissioning, all 9 tabs: 15, 34, 19, 15, 15, 15, 15, 14, 14 controls, **all identical**. 14 controls are common to every tab, so this covers 156 commissioning comparisons. The steering lease's random session ID is masked before comparison; the first run flagged it as a false difference |
| **New V2-only controls** | Command center: `#v2Estop` (dock E-STOP), `#v2CamRate` (data saver), `#v2Lite` (reduced effects). Live map and Wi-Fi: `#v2Estop` only. No other new request path |
| **Hold-to-drive** | V1 and V2 identical: 13 drive posts in 1.5 s, **median gap 120 ms**, `action=stop` on release (desktop mouse and phone touch emulation) |
| **Release-to-stop with the pointer still down** | `pointercancel`, window blur, page hidden: stop sent and **0 drive posts after the event**, in both V1 and V2 |
| **E-STOP bodies** | Drive-pad E-STOP and dock E-STOP both send `action=e_stop`, byte-identical to V1 |
| **E-STOP while a drive button is still held** | **V1 and V2 both keep sending drive posts after `e_stop` (7 in 0.8 s).** This is the existing hazard. V2 does not fix it silently; see the security proposal, item 1 |
| **States shown** (command-center chip / Live map) | VERIFIED → "Localization verified" / "LIVE / LOCALIZATION VERIFIED BY LIDAR"<br>DEGRADED → "Localization degraded" / "NOT CONFIRMED – PARK TO CHECK"<br>LOST → "Localization lost" / "LOCALIZATION LOST"<br>MOVING → "Moving · not verified" + "Moving" / "MOVING – NOT VERIFIED"<br>CONNECTION DELAYED → "OFFLINE", "Connection delayed", "Motion unknown" / "CONNECTION DELAYED – ROVER STATE UNKNOWN"<br>STOPPED → "Stopped" |
| JS errors on load | 0 on every page and viewport |
| Route unit tests | 6/6 pass |

Two defects were found and fixed during testing, before this report:
- **Motion chip.** It kept showing "Stopped" after the link dropped. It now shows "Motion
  unknown".
- **Stop-latch chip.** It could not be hidden because the CSS overrode `[hidden]`.

## Browser and network measurements

All figures come from the same recorded data, with 10 s windows, using Chrome DevTools Protocol
metrics.

| Metric | V1 | V2 (camera in view) | V2 (scrolled away) |
|---|---:|---:|---:|
| Camera frame requests / 10 s (phone, desktop) | 160 | 160 | **0** |
| Radar requests / 10 s | 80 | **0** (radar panel below the fold) | **0** |
| Script time, ms per s (phone) | 4.9–5.2 | 3.7 | **0.8** |
| Layout time, ms per s (phone) | 5.8–7.1 | 5.7 | 3.4 |
| JS heap | 2.0 MB | 1.6 MB | 1.7 MB |
| DOM nodes (CDP count) | 4,618 | 5,060 (+SVG icons) | 4,900 |
| First-load transfer, command center | **1.28 MB** (the 1.19 MB logo is sent with no cache header, so it is downloaded on every load) | **132 KB** | |
| First-load transfer, Live map | 1.21 MB | 52 KB | |
| First-load transfer, Commissioning / Wi-Fi | 32 KB / 5 KB | 61 KB / 39 KB (shared CSS and font, cached after the first V2 page) | |

What this means:
- **Bandwidth per open dashboard** drops by about 350 KB/s whenever the camera is off screen.
  Radar polling (8.5 req/s) stops unless the radar panel is visible.
- **Jetson CPU barely changes.** The server answers from cached frames (≈0.01 core per client,
  measured in the architecture audit). The Jetson-side gains are in the server audit
  (`docs/audits/ATLAS_DASHBOARD_SERVER_PERF_AUDIT_2026-10-11.md`).

## Screenshots

`before/after` pairs (V1 left, V2 right) for each page:
- **Viewports:** phone 390×844 @3×, 11-inch tablet 1194×834 @2×, desktop 1440×900.
- **Pages:** command center, Live map, Commissioning, Wi-Fi.
- **State gallery:** VERIFIED + STOPPED, DEGRADED, LOST, MOVING, CONNECTION DELAYED.

Wi-Fi names and addresses are replaced with placeholders in every image.

## Known limitations of the prototype

- The reduced-effects toggle is hidden on phones; the phone dock shows E-STOP and motion only.
  Data saver is available everywhere.
- Commissioning keeps its own LATCH DRIVE STOP (#stop, same handler) and pins it in the dock. It
  does not add a second E-STOP with different semantics.
- Battery, camera and other tiles still show their last value while offline; this is V1
  behaviour from the shared script. The new status chips do show "unknown".
- Sub-pages are V1 markup restyled; their information density is unchanged by design.
- Not tested: real touch hardware, Safari/iOS, and the on-device network path.

## Deployment proposal (needs your separate approval)

1. **Preconditions:**
   - ATLAS parked, remote stop latched;
   - autonomy and reseeding disabled (unchanged);
   - a backup of `scripts/atlas_status_web.py` in `data/backups/2026-10-1x-glass-ui-v2/`, with
     `ROLLBACK.sh`.
2. **Copy:**
   - `web/v2/` → `~/project_atlas/web/v2/`;
   - `scripts/atlas_web_v2.py` and the 3-line hook in `atlas_status_web.py` → `~/project_atlas/scripts/`.
3. **Restart only `rover-status-web`.** Coordinated with you, because the dashboard drops for
   ~5 s. Check that `/`, `/mapping`, `/commissioning` and `/wifi` are byte-identical to before.
4. **Supervised check with your PC powered off, from a phone:**
   - `/v2/` over the LAN IP, the local name and Tailscale;
   - camera, chips and E-STOP dock (wheels lifted);
   - hold-to-drive release on the lifted rover;
   - the Live map state;
   - commissioning tabs (read-only);
   - the Wi-Fi page loads, but **no connect**.
5. **Leave V1 as the default.** Switching `/` to V2 is a later, separate decision after you have
   used `/v2/` for a while.
6. **Rollback:** delete `web/v2/`, restore the backed-up `atlas_status_web.py`, and restart
   `rover-status-web`.

The security fixes (E-STOP hold hazard, reboot password, same-origin checks, shutdown stop) are
in `docs/security/ATLAS_DASHBOARD_SECURITY_FIX_PROPOSAL_2026-10-11.md`. They are independent of
this deployment and should not be bundled with it.
