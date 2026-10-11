# ATLAS stage 5: Glass UI V2 as the only dashboard, 2026-10-11

Operator request: 13:39 IST ("disable classic V1, keep Glass V2"). Latched by the operator with
Xbox **B** at about 14:18. Installed 14:21:50; `rover-status-web` restarted 14:21:57.

## What changed

| Path | Before | After |
|---|---|---|
| `/`, `/index.html` | classic V1 command center | **V2 command center** (same bytes as `/v2/`) |
| `/mapping`, `/commissioning`, `/wifi` | classic pages | **302 → `/v2/mapping`, `/v2/commissioning`, `/v2/wifi`** |
| any other unknown GET path | classic page (catch-all) | **404** |
| `/v2/...` | V2 | unchanged |
| `/api/*`, `POST /`, `/camera*.jpg`, `/camera.mjpg`, `/diagnostics.js`, `/commissioning.js`, `/steering-commissioning.js`, `/commissioning-evidence.js`, `/manifest.webmanifest`, `/logo.png`, `/map.png` | — | **unchanged** |
| V2 page links | "Classic page" / "Classic dashboard" links to V1 | all lead to the V2 command center; no V2 page links to a disabled V1 path (test-enforced) |

Files changed:
- `scripts/atlas_web_v2.py`: `serve_default()`.
- `scripts/atlas_status_web.py`: one hook, plus the 404 in place of the catch-all.
- `web/v2/{index,mapping,commissioning,wifi}.html`.

Commit `5b49f25`.

**Not changed:** motors, mux (same PID 1872 throughout), localization, Nav2, network, calibration,
autonomy (still disabled), and the E-STOP and reset logic.

**V1 is preserved, not deleted.**
- `render_control_page()`, `atlas_mapping.html`, `atlas_commissioning.html` and
  `atlas_wifi_web.PAGE` remain on disk. V2's `command.js` and sub-pages are generated from them.
- `ATLAS_CLASSIC_UI=1` in the service environment restores the old routing exactly, with no file
  change. This is tested.

## Dependency check before removing V1 routes

| Consumer | Uses | Effect |
|---|---|---|
| Rescue hotspot portal, network fallback, Wi-Fi manager URLs, mobile notifier link, PWA `start_url` | `http://<host>:8088/` | now opens V2 |
| MCP server | `/api/status`, `/camera.jpg` | unchanged |
| CrowPanel | `/camera_panel.jpg`, `/camera_overview.jpg`, APIs | unchanged |
| Intercom (:8091) | link to `:8088/` | now opens V2 |
| V2 sub-pages | V1 JS assets (`/commissioning.js`, …) and `/diagnostics.js` | kept, verified 200 |
| Legacy HDMI dashboard | separate app, autostart disabled | not affected |
| Old bookmarks to `/mapping`, `/commissioning`, `/wifi` | | redirected to V2 |
| Browser tabs already showing V1 | keep polling the same APIs until reloaded | close or reload them; reloading gives V2 |

## Evidence before deployment

- **Unit tests:** `test_v2_default_route` (8, real GET handler, including the classic switch).
  `test_atlas_web_v2`, `test_status_web_estop_safety`, `test_status_web_estop_reset`,
  `test_status_web_no_reboot` and `test_status_web_executor_split` all pass.
- **Package:**
  - rehearsal on an export of `e5c1976` gives the expected files and a byte-identical rollback;
  - tamper tests: refused before change (edit) and rolled back (new file);
  - Jetson checksums 10/10;
  - rehearsal on a scratch copy of the live tree: 6/6 MATCH, live tree hash unchanged.
- **Isolated Jetson end-to-end** (domain 77, `127.0.0.1:18088`, real web module with stage 5,
  live mux copy): **48/48 E-STOP and web-reset checks, 0 failures**. The stage 5 routes were
  checked on the same isolated server.
- **Browser (headless Chromium, recorded data):**
  - E-STOP: 0 failures, covering two-finger E-STOP on the V2 pad and dock, timers cancelled, and
    single fire per input;
  - reset panel: 0 failures in V1 and V2;
  - V1→V2 ID and link inventories: nothing missing;
  - control-contract run: see "Open items".

### Incident during preparation (no motion; evidence log affected)

The first isolated run at 13:52–13:55 was started without its private `ATLAS_ESTOP_EVENT_LOG` and
PIN-file settings. Its test server therefore appended **20 test events to the live safety log**
(`data/safety/estop_events.jsonl`, lines 174–193, 13:54:57–13:55:31: client `127.0.0.1`, the remote
"LB"/"B" reasons, and `shutdown_pending:true`).
- These came from the isolated domain-77 rig. ATLAS's real mux and latch were not involved.
- The log was **not edited**. Treat those lines as test data.
- Its web-reset section did not run, because it lacked a test PIN. No PIN attempt was made against
  the live PIN file, which it could read.
- Fix: `e2e_estop_test.py` now refuses to start unless both paths point outside
  `~/project_atlas/data` and `~/.config/project_atlas`. The rerun used private files and left the
  live log untouched.

## Deployment (latched, parked)

- **Pre-checks:**
  - latch true ("REMOTE STOP: B pressed");
  - `/yahboom/odom` 0.0000 m over 5 s, max |v| 0;
  - 0 non-zero `/cmd_vel`;
  - package checksums OK.
- **Install:** 6/6 MATCH. Backup with pinned `ROLLBACK.sh` at
  `~/project_atlas/data/backups/2026-10-11-142150-126057400-stage5-v2-default`.
- **Restart:** `rover-status-web` only, at 14:21:57. NRestarts 0. Its ROS link was ready about
  15 s later.
- **Latch:** still true after the restart, with no reset blockers. Mux PID 1872 unchanged.

**Live hashes after deployment:**

| File | sha256 (prefix) |
|---|---|
| `atlas_status_web.py` | `ac05831b` |
| `atlas_web_v2.py` | `6c58e6cc` |
| `index.html` | `9ee00392` |
| `mapping.html` | `c588f629` |
| `commissioning.html` | `517d6348` |
| `wifi.html` | `3c8d5be0` |

These equal commit `5b49f25`.

## Verification after deployment

`verify.sh stage5`: **all PASS**.
- On 127.0.0.1, the LAN IP and the Tailscale IP: `/` is byte-identical to `/v2/`, and the three old
  page paths redirect to `/v2/...`.
- Every `/v2/` page, API and JS asset, the manifest, logo and map return 200.
- All three camera JPEGs return 200.
- An unknown path returns 404.

**From the PC** over Tailscale and the LAN, with an iPhone user agent:
- `/` serves V2 (17,121 B, 0.02–0.17 s);
- `/mapping` returns 302;
- `/api/status`, `/api/estop/state` and `/camera.jpg` return 200;
- `/camera.mjpg` streamed 786 KB in 4 s.

**A real phone has not been tested.** That is block E of the operator session.

## Resource use

| Measure | Before (13:50, V1 default) | After (14:22–14:25) |
|---|---|---|
| `rover-status-web` CPU, 60 s | 43.0% of one core | 42.7% of one core |
| `rover-status-web` RSS | 178 MB | 172–177 MB |
| Threads | 23 | 23 |
| Wi-Fi TX | 307 kB/s | 35 kB/s |
| Tailscale TX | 97 kB/s | 6 kB/s |
| Dashboard clients connected | the PC (3 sampled connections) | **none** |

**The network drop reflects clients, not the UI.** The before window had the PC's dashboard tabs
polling; the after window had no dashboard open. Per-client load is the same for V1 and V2 (the
recorded request contracts are identical, and V2 skips camera and radar requests while they are
off screen). A like-for-like figure needs one V2 tab open for 60 s. Server CPU is dominated by ROS
subscriptions, not page serving.

## Rollback

- **Fast, no file change:** add a `rover-status-web` drop-in with `Environment=ATLAS_CLASSIC_UI=1`,
  run `systemctl --user daemon-reload`, then restart `rover-status-web` (rover latched).
- **Full:** `bash ~/project_atlas/data/backups/2026-10-11-142150-126057400-stage5-v2-default/ROLLBACK.sh`,
  then restart `rover-status-web`.
- Redirects are 302, not 301, so browsers do not cache them and rollback takes effect on reload.

## Open items

- **Operator physical checks are not passed.**
  - C1–C3 on V2: the pad E-STOP and dock E-STOP on a real phone.
  - V2 on the phone with the PC off, over the LAN and over Tailscale (block E).
- **V2 is now the only UI.** If V2 fails on a device, use the physical remote's **B** to stop, then
  roll back as above.
- **The headless control-contract suite** (`test_ui_v2.py contracts,safety`) was still running at
  the time of writing. Its result will be appended here.
