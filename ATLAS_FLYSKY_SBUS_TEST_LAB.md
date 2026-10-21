# ATLAS FlySky SBUS Remote Test Lab (Stage 27): offline build, NOT installed

Branch `agent/sync-developer-20261011`. Date 2026-10-17. Nothing was installed on the Jetson, no service was restarted, nothing was actuated. Everything below was built and tested offline.

## Bottom line
- The dashboard page, service, simulator, tests and a reversible deployment package are ready.
- **No real FlySky frame has been observed.** I cannot tell you today that SBUS data reaches the STM32, or that the Jetson can read it. The most likely answer to the second question is **no, not with the current setup** (see 2 and 3).
- Until frames are verified, the page shows **SIGNAL NOT VERIFIED**. It never shows CONNECTED because a receiver is paired or its LED is lit.
- Your existing Xbox remote is not touched in any way.

## 1. Receiver protocol and electrical interface (documented, not measured)
| Item | Finding | Status |
|---|---|---|
| FS-iA10B SBUS | 25-byte frames, 100000 baud, 8E2, **inverted** logic, 16 channels (11 bit) + 2 digital + frame-lost + failsafe flags | From protocol documentation; not measured on your receiver |
| FS-iA10B iBUS | 32-byte frames, 115200 8N1, **normal** polarity, 14 channels, checksum, no failsafe/frame-lost flags | Documentation; not measured |
| STM32 board SBUS port | Yahboom docs: S/V/G pins, USART2 RX, receive only, 100000 baud 9-bit even parity 2 stop. Docs state no voltage and no inversion handling | Vendor docs; your board revision unverified |
| Logic level | Receiver 3.3 V vs 5 V signal unknown | **Owner to confirm before any wiring** |

## 2. Do live SBUS frames reach the STM32?
**Unknown.** Physical pairing or receiver LED state does not prove it. I only know:
- The Yahboom demo firmware parses SBUS and prints channels on USART1, but I do not know which firmware ATLAS runs.
- The production report protocol that `yahboom_base.py` (Rosmaster_Lib) reads has frame types speed, MPU raw, IMU attitude, encoder and ICM raw. **None carries RC channels.**
- I did not alter firmware (needs separate authorization) and did not open the base serial port (the dashboard must never touch it).

## 3. Can the Jetson access the data?
**Not today.** With the production protocol there is no path from the STM32 SBUS input to ROS. Options:

| Option | Firmware change | Notes |
|---|---|---|
| A. iBUS to a **dedicated** USB-serial adapter (read-only) | none | Simplest. Normal polarity, no inverter. RX + GND only, TX unconnected. Needs the FS-iA10B iBUS-capable output wired, and an adapter with a **unique serial** (your three CH340 adapters have none, and their ttyUSB numbers swap on reboot) |
| B. SBUS to a dedicated adapter | none | Needs a hardware inverter or an RX-inverting adapter |
| C. STM32 forwards SBUS over the existing link | **yes** | Needs separate owner authorization; not proposed now |

Prepared for A/B: `scripts/atlas_rc_readonly_bridge.py` (proposal, not deployed). It reads one port, validates frames, publishes only `/atlas/rc/frames` at 20 Hz max, subscribes to nothing, has no write call, and refuses ambiguous or already-open ports.

## 4. Actual channel values and mapping
**None. No frames were seen, so I have no values and no mapping.** I did not assume CH1 = steering or CH2 = throttle. The page discovers roles at run time: the Test Lab shows per-channel live value, min/max seen, movement arrow and activity highlight, lets you rename channels, and the stick pads let you pick which channel drives each axis. The mapping will be recorded from your stick movements once frames flow.

## 5. Dashboard implementation
- Page `/v2/flysky-testlab` (`flysky-testlab.html/.js`, `flysky.css`, reusing Test Lab styling). Home gets a clearly visible "FlySky Remote Test Lab" shortcut.
- Service `atlas_flysky_web.py`: **one** ROS subscription (`/atlas/rc/frames`), **zero publishers**, API `GET /api/flysky/state`, `POST /api/flysky/action` (`session_start`, `session_stop`, `reset_ranges`, header `X-Atlas-Flysky: 1`). No drive, E-STOP, pulse or release action exists.
- States: NO_SOURCE / NO_FRAMES show **SIGNAL NOT VERIFIED**; LIVE (valid frame < 0.5 s) CONNECTED; STALE > 0.5 s; LOST > 3 s; FAILSAFE and FRAME_LOST from SBUS flags only (iBUS: "not observable"). **RSSI/signal strength is always "not available"**; nothing is invented.
- CSV export of a bounded session (30000 rows / 1500 s / 20 Hz, idle auto-stop 120 s, 50 files kept).
- Screenshots: `evidence/stage27_flysky/` (simulator scenarios, desktop and mobile).

## 6. Offline test results
`102 passed` (FlySky + arbiter + package + Test Lab static), full repo suite 812 passed. Two pre-existing failures are unrelated (`test_atlas_safety_status_camera_heartbeat`, `test_ultrasonic_validity`, both fail on clean HEAD too). I updated one stale Test Lab check that assumed a single added Home link.

| Required test | Where |
|---|---|
| valid / invalid / incomplete SBUS and iBUS frames | `test_flysky_core.py` (31) |
| loss of signal, stale data, failsafe, frame-lost | `test_flysky_core.py`, `test_flysky_web.py` (18) |
| channel mapping, clamping | `test_flysky_core.py` |
| dashboard rendering (headless Chromium, desktop + mobile) | `test_flysky_render.py` (6) |
| no motor/servo actuation (no publishers, no cmd_vel/estop/service, read-only port, static scan) | `test_flysky_web.py`, `test_flysky_static.py` (9), `test_flysky_bridge.py` (6) |
| CSV export | `test_flysky_web.py` |
| CPU and memory overhead | `test_flysky_overhead.py` (5) |
| dual-remote design rules | `test_remote_arbiter.py` (15) |
| deployment package apply/refuse/rollback | `test_stage27_package.py` (5) |

## 7. Resource impact (offline, container CPU; Jetson not measured)
- Decode + ingest: 0.025 ms per frame. At ~71 frames/s (SBUS worst case) about 0.2% of one core.
- State snapshot: 0.37 ms per request; at 4 Hz about 0.15% of one core.
- Session memory: 0.26 MB after 20000 frames (~220 B per stored row, bounded).
- No permanent thread or timer. The subscription is lazy; with the page closed there is no work.
- Caveat: the dashboard already uses ~45% CPU (Stage 26 A/B: pre-existing). Jetson numbers must be re-measured after install.

## 8. Deployment and rollback (needs your approval)
`tools/deploy/stage27_flysky/`:
- `apply.sh` requires `OWNER_APPROVED=yes`, exact pre-state hashes (`atlas_status_web.py` 6658db94, `atlas_web_v2.py` c3607f41, `index.html` a03baf88), and a latched E-STOP. It backs up to `.pre_stage27_flysky_<stamp>`, adds 5 new files, patches 3 existing files additively (+3 hook lines, +1 page entry, +1 link), import-checks, and restarts **only `rover-status-web`**. A second apply is refused.
- `rollback.sh` restores the 3 files, removes the new files, restarts only `rover-status-web`.
- Rehearsed on a copy of the real live files: apply, re-apply refusal, byte-identical rollback.
- With no receiver input installed the page honestly shows SIGNAL NOT VERIFIED (no source). Installing it gives you the page, not live channels.

## Future dual-remote design (not implemented, not deployed)
`scripts/atlas_remote_arbiter_model.py` states the rules as tested code: one active source, explicit selection, E-STOP always wins and switching never releases it, stale/unverified yields zero, loss of the active source latches until reselect, conflicts reported and dropped, FlySky driving refused (`FLYSKY_DRIVE_ENABLED = False`). Not imported by any production node.

## 9. GitHub
Branch `agent/sync-developer-20261011`; commit hash is in the final message of this task and the git log.

## 10. Remaining approvals
1. Install the Stage 27 package (one `rover-status-web` restart, E-STOP latched).
2. Choose and wire a receiver input (iBUS or SBUS to a dedicated unique-serial adapter) and confirm voltage/inversion; or separately authorize a firmware route.
3. Enabling the bridge service on the Jetson.
4. Any FlySky driving: separate, later, not designed for activation.
5. Still open from before: physical E-STOP tests, Jetson password rotation and temporary key removal, motor/encoder fault root cause, Candidate B, Stage 17B.

## Where you stand on the final goal
You cannot yet move the sticks and watch channels on the dashboard. That needs step 2 (receiver data reaching the Jetson). Everything on the dashboard side is ready and waits for it.
