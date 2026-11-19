# ATLAS Stage 26 — Motor & Encoder Test Lab (Dashboard V2)

Date: Sat 17 Oct 2026. Branch `agent/sync-developer-20261011`. **Status: built and tested offline. NOT deployed. Motor actuation NOT enabled. No physical test has been run.**

## What was built
A new Dashboard V2 page, **Motor & Encoder Test Lab**, at `/v2/testlab`, linked from the Home Dashboard header ("Test lab" next to Commissioning). Works from PC, MacBook and phone.

| # | Requirement | Where |
|---|---|---|
| 1 | Live raw counts M1–M4 | wheel cards (2×2, front row on top, dial turns with the wheel) |
| 2 | Delta, direction, freshness, RPM estimate, health | wheel cards + header chips (RPM is derived from calibrated CPR, labelled "est.") |
| 3 | History graph, forward/reverse comparison | 30 s canvas graph (turns or raw); each wheel vs median of the other three, forward and reverse |
| 4 | One motor at a time | tap a wheel; every test acts on the selected wheel only |
| 5 | Forward / Reverse / STOP | Powered pulse card (gated); STOP = abort the run + the dashboard's normal E-STOP request |
| 6 | PWM and duration | sliders limited to 1–50 and 0.20–0.50 s, imported from `atlas_drive_pid_lifted` (cannot exceed the approved limits) |
| 7 | Read-only hand test | Hand rotation card; never touches the actuator path (tested) |
| 8 | CSV per session | one row per channel per frame (UTC time, monotonic, session, mode, channel, motor, position, raw, delta, direction, rpm, distance, packet age, health, faults); saved on the rover and downloadable |
| 9 | Faults | frozen counts, unexpected sign, missing pulses, stale/no data, count jump, sequence reset, consensus exclusion |
| 10 | Existing navigation unchanged | `index.html` gained exactly one link line (tested); no other V2 page changed |

## Architecture (as required)
- **No serial access.** The web side never opens the STM32 port; the Yahboom base driver stays the only hardware owner.
- **Read side:** own small ROS node (`atlas_testlab_readonly`, started lazily on first page load, stopped after 5 idle minutes) subscribing to `/atlas/encoder_update`, `/atlas/encoder_health` and `/atlas/drive_pid/lifted/status`.
- **Actuation side:** the only publisher is `/atlas/drive_pid/lifted/request`, created only when a pulse run starts. `PulseRun` mirrors the existing reference client step for step: enter → operator releases software stop → arm → one raw pulse → abort → operator re-latches stop → exit. Fields are exactly `{op, session, seq, mode:"raw_pulse", wheel, pwm, duration_s}`. The base driver re-validates everything.
- **No** cmd_vel, joystick, steering, mux, E-STOP, calibration, localization or navigation code is touched (verified by tests and `git status`). No general actuator API: the POST endpoint accepts a fixed allow-list of 8 actions with exact field sets.
- **Pulse controls stay disabled** unless the owner's own status reports every gate: interface enabled, physical power cut-off confirmed to the driver, software stop latched, remote B not held, battery fresh and healthy, entry check clean for 5 s. The page adds a 4-item checklist (wheels lifted, secure support, owner present, cut-off in reach) and the exact phrase `LIFTED CLEAR PHYSICAL POWER CUT READY`, re-entered for every pulse. Missing/stale/unknown status = locked, with the reason shown and a request for owner intervention.
- **Hard timeouts, independent of the web process:** the owner's 0.5 s heartbeat lease zeroes output if this service stalls or dies; pulse length is capped by the owner at 0.5 s; the owner enters ABORTED on any fault. Test `test_independent_lease_zeroes_output_if_the_web_process_dies` shows this against the real state machine.
- The web **cannot** release the E-STOP: the operator must release/re-latch the software stop at the remote exactly as in the existing procedure. If the session is left locked after a web restart, a persisted 0600 token lets the page offer recovery to close it.
- POST protection: custom header + same-origin check + 512-byte limit + JSON only (same pattern as the location-check endpoint).

## Results (offline, no rover motion)
- New tests: **61 pass** (`test_testlab_core` 36, `test_testlab_web` 18, `test_testlab_static` 7). They include pulse runs against the **real** `LiftedDriveCommission` (happy path, operator never releases, cancel before/during pulse, status loss, transport failure, foreign-session status, owner rejecting, recovery), every gate blocking independently, every out-of-bounds pulse value rejected, fault detection on Stage 25 signatures (M3 forward loss, M2 wrong direction), hand-test logic identical to `tools/diagnostics/encoder_hand_test.py`, CSV format, path traversal, and "no raw/cmd_vel/serial surface".
- Full suite: 717 tests, 2 failures that are **pre-existing and unrelated** (`test_ultrasonic_validity…bare_positive_float`, `test_atlas_safety_status_camera_heartbeat…`); both fail identically without these changes.
- Browser check (Chromium, simulator only) at 1360 px and 390 px: no console errors. Simulated supervised pulse driven from the page through the real state machine: waits for the operator, one bounded pulse, output zero, session closed, CSV written; STOP aborts a run.
- Offline simulator for trying the page without a rover: `tools/testlab/sim_server.py` (no ROS, no serial).

## Safety status
- Candidate B undeployed; Foxglove hardening deferred; Stage 17B on hold; 3-of-4 fail-closed consensus unchanged; calibration, steering, localization, E-STOP, mux, navigation untouched.
- **Physical E-STOP tests are still not passed. Nothing here claims a motor or encoder pulse test has passed.** Observations from the base driver ("MATCH/REVERSED/NO_DELTA") are shown as evidence only.
- Live rover today (read-only check): `rover-status-web` and `rover-base-telemetry` active; base environment has no lifted flags, so the page would show "Pulse locked" and be read-only until you enable the interface.

## Important finding while preparing deployment
The repo's `atlas_status_web.py` contains **other undeployed work** (single-person steering) that the live file does not. Copying it would silently deploy steering code. So the deployment **patches the live file in place with 4 lines** (import + two hook lines; plus one `PAGES` entry in `atlas_web_v2.py`). Rehearsed on a copy of the real live file: diff is exactly those lines; rollback is byte-identical.

## Deployment (needs your explicit approval; not done)
Package: `project_atlas/tools/deploy/stage26_testlab/`
1. Read-only/observe deployment (recommended first): `OWNER_APPROVED=yes ./apply.sh` on the Jetson. It refuses unless the live files are the expected pre-state, backs up the 3 touched files with checksums, adds 5 new files, patches in place, restarts **only** `rover-status-web` (page is unavailable for a few seconds; the rover is not driven by that service), and smoke-tests the page and API. Base driver is not touched.
2. Rollback: `./rollback.sh` restores the backups, deletes the new files, restarts only `rover-status-web`.
3. **Enabling pulses is a separate step and a separate approval:** `base_dropin/99-testlab-lifted.conf.disabled` sets the two base-driver flags. It needs a base-driver restart, and only with the rover lifted, securely supported, a reachable physical motor-power cut-off, and you present. It is not applied by `apply.sh`. Remove the file and restart the base to disable again.

## Known limits
- One pulse needs a fresh enter/arm cycle, so each pulse requires you to release and re-latch the software stop at the remote. That is the existing safety design; I did not shorten it.
- Direction comparison during free driving uses the other three wheels as reference, so with a faulty second wheel the reference degrades; pulse and hand tests use explicit expectations instead.
- "Unexpected direction" while driving freely is only a warning (a pivot turn can legitimately do it).
- The saved session list shows the last 20 files; the rover keeps the last 100 in `~/project_atlas/data/diagnostics/testlab/`.
- A copy of the live `atlas_status_web.py` I fetched for comparison is in your PC Downloads folder (`live_status_web.py`); I could not delete it without a delete approval. It contains no secrets.
