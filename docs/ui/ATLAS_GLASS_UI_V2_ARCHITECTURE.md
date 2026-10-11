# ATLAS Glass UI V2 — architecture audit and decision (2026-10-11)

Status: **proposal for approval**. Nothing has been implemented or deployed.
The audit was read-only: GET requests only, plus offline replay of page
snapshots in headless Chromium. All POSTs were captured and never sent.

## Final architecture: Jetson-hosted, PC-independent

- **Hosting.** The production UI is static HTML/CSS/JS/SVG files in the repo
  (`project_atlas/web/v2/`). The existing `rover-status-web` process on the
  Jetson serves them on port 8088. That means the same local IP, the same
  Tailscale IP and name, and the same hotspot redirect.
- **No new runtime.** There is no new service, Node, build server, WebSocket,
  database, proxy or cloud dependency. The PC is used only to design and
  review. The dashboard needs no PC at runtime and no PC to edit (no
  mandatory build step).
- **Same backend.** V2 calls the existing endpoints with the existing request
  formats. The `client_allowed` and `same_origin` checks are unchanged. No
  ROS 2, navigation, motor, safety, POST-handler or polling-backend logic
  changes.
- **The only server change.** One small additive GET route that serves files
  from `web/v2/` at `/v2/…`, with a path allowlist and no directory listing.
  The existing pages stay exactly where they are. V1 remains the default and
  the rollback until a separate approval switches the default.

## Audit findings (measured)

| Item | Current |
|---|---|
| Delivery | Command center is inline in Python (`render_control_page`, ~13.5 KB CSS, 11.5 KB HTML, 52 KB JS) plus `/diagnostics.js`. Other pages are static files. No framework, CDN or web font. |
| Pages | Command center, `/mapping`, `/commissioning` (+3 JS), `/wifi`, intercom (:8091), Visual Cloud (:8443), hotspot portal |
| Browser cost | Command center: 566 DOM nodes, ~6 ms script/s, 1.8 MB heap. Mapping: 122 nodes, ~2 ms/s. Commissioning: 603 nodes, ~2 ms/s. No JS errors, no horizontal overflow at 390 / 1024 / 1440 px |
| Network per open command center | camera.jpg ~16.6 req/s × ~21 KB ≈ 350 KB/s; radar ~8.5 req/s; status 40 KB / 2 s |
| Jetson cost per client | `rover-status-web` 0.579 core idle, 0.587 with one replayed v1 client, 0.591 with a lean client. Per-client cost is negligible: the server serves cached frames |
| Jetson idle cost | 0.58 core with no client: one rclpy executor thread at ~52% across 105 subscriptions. A backend/ROS issue, **out of scope** for the UI (separate proposal) |
| Logo | `/logo.png` is **1.19 MB** and loads on every page; it can be ~20–40 KB |
| Phone usability | Single column, 6,126 px tall. The live camera sits ~1,700 px below the drive pad, so you cannot see the camera while driving |
| Duplication | `shutdownAtlas()` exists twice. Each page has its own `$`/`row`/`esc` and colour variables. `diagnostics.js` depends on command-center globals |
| Dead code | `render_page()` (`:2032-2078`) is never called and is broken |

## Options compared

| Option | Runtime added on Jetson | Browser cost | Regression risk | Maintainability | Verdict |
|---|---|---|---|---|---|
| **A. Refine the existing vanilla HTML/CSS/JS.** Extract to static files; one shared token CSS and one shared JS module; SVG icon sprite | none | same or lower (fewer nodes, visibility-aware polling) | lowest: the same functions and request contracts move, not rewritten | better: real files, editable on the Jetson, no toolchain | **Recommended** |
| B. Small library (Alpine / Preact / Lit, 4–15 KB) | none (static) | +4–15 KB, negligible | medium: logic must be re-expressed | slight gain for templating | not justified: no measured problem it solves |
| C. React/Vite SPA | none at runtime, but a Node build on the PC for every edit | +45 KB gz runtime | high: 52 KB of safety-relevant JS rewritten | worse for this project: the PC becomes a build dependency for changes | rejected |
| D. Electron / kiosk app | yes | high | high | worse | rejected |

Current script cost is under 1% of a core, so no framework can measurably
improve performance. The improvements needed are layout, hierarchy, touch
ergonomics and visual polish, and CSS does all of these.

## Design approach

- **Glass look:**
  - layered translucent panels, `backdrop-filter` blur on static chrome only;
  - **no blur over the live camera or radar canvases**, because the
    compositor would re-blur at 8–17 Hz;
  - an `@supports` fallback to solid panels;
  - a reduced-effects toggle that is saved per browser.
- **Phone-first command layout:**
  - camera and drive pad together in the thumb zone;
  - a sticky E-STOP / status bar;
  - the hold-to-drive pad keeps 56 px minimum targets.
- **Icons and fonts:** inline SVG sprite (no icon font); system fonts.
- **Polling, client side only:**
  - camera and radar poll only while their panel is visible, using
    IntersectionObserver; page visibility is already handled;
  - an optional camera rate selector;
  - this cuts bandwidth, not Jetson CPU.
- **Penpot.** It is optional. A Penpot mockup would still have to be
  re-built in HTML. Instead, the proposal is to design directly as an HTML
  prototype rendered against recorded real data, review it with screenshots,
  then iterate. Penpot can be used for mood boards if preferred; it is never
  needed at runtime.

## Must not change (regression checklist, from the inventory)

**Every control and its POST contract**
- drive pad (l/a values, 120 ms repeat; stop on pointerup, cancel,
  lostpointercapture, blur and hidden);
- E-STOP;
- camera pad (90 ms repeat, single in flight, center, home save/go);
- face follow; AI on/eco;
- voice mute;
- shutdown (confirm and token);
- links to mapping, commissioning, diagnostics, Wi-Fi, Visual Cloud and
  intercom.

**Every display and drill-down**
- all 17 health tiles;
- the sensor modal keys;
- radar 2D/3D, environment heatmap and charts, GNSS, network/cellular,
  power/BMS badge, companion panel;
- the diagnostics workbench (logs, filter, export).

**Mapping**
- the `liveStatus()` safety states and stale thresholds;
- green only when localization is verified.

**Commissioning**
- tabs, the confirm on every observation;
- the steering lease, heartbeat and confirms;
- camera step and freshness checks;
- evidence staleness.

**Wi-Fi:** the confirm before connect, and the busy locks.

**Test plan.** Playwright contract tests compare every V2 control's request
(path and body) with V1's, and check release-to-stop behaviour on pointer,
blur and visibility events. Then:
- a supervised on-device check from a phone with the PC off;
- the PC staying off for the whole session.

## Existing security issues (not changed by V2; separate approval)

1. The reboot action pipes a hardcoded sudo password and has no
   confirm/same-origin check (`atlas_status_web.py:2005`, no UI caller).
2. Form POSTs to `/` (drive, camera, reboot, service restart, mapping/nav)
   only check the source IP, with no same-origin/CSRF check. V2 will send
   `X-Atlas-Wifi` and same-origin headers anyway, so the server could
   require them later.
3. `e_stop` sends a zero Twist only and does not set the mux latch.
4. After a shutdown request, `stop` / `e_stop` get 409 (the server already
   stopped the rover).
5. Telemetry strings go into `innerHTML` unescaped in places. V2 will
   escape everything.
