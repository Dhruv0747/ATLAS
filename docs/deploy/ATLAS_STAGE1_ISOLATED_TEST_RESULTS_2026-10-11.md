# Stage 1 / 1b: isolated test results (2026-10-11)

Nothing here touched the rover's motors or its live ROS graph. Four kinds of test ran:

| Where | What ran | Isolation |
|---|---|---|
| Jetson, `/tmp/estope2e` | The **real** `atlas_status_web` web server, from a copy of the live scripts with the stage package(s) installed by the package's own `install.sh`, plus the **live** `atlas_cmd_vel_mux.py`. The live mux differs from the repo copy (sha `dacb4b82…` vs `ca534992…`); the live one was used. Also a synthetic remote (`/joy`, 20 Hz) and synthetic `/odom` | Private DDS domain 77, `ROS_LOCALHOST_ONLY=1`, web on `127.0.0.1:18088`. The mux environment matches the live unit (`ATLAS_MANUAL_ONLY=0`, `ATLAS_ULTRASONIC_ENABLED=1`). Temporary PIN file and event log. Shutdown and reboot actions are never called |
| Container | Unit tests: the real module with ROS stubbed, and the real HTTP handler | no network |
| Container | Headless Chromium with real CDP multi-touch against recorded ATLAS responses | no requests leave the harness |
| Container + Jetson | Package rehearsals | copies only |

Live `scripts/` + `config/` hashes were identical before and after every Jetson run. No live event
log was created, and no test process was left running.

## Your seven requirements: evidence

| Requirement | Result | Evidence |
|---|---|---|
| **Two-finger touch triggers E-STOP** | PASS (V1 fixed, V2 pad, V2 dock) | Browser: one finger holds FORWARD, a second finger taps E-STOP. `e_stop` is sent exactly once. The unfixed V1 sends no `e_stop` |
| **Drive-repeat timers and held controls cancelled** | PASS | Browser: after E-STOP, 0 drive (or camera) requests while the first finger stays down. The `hold` and `cameraHold` timers are cleared. Mouse, keyboard Enter/Space and touch tap each send exactly 1 `e_stop` |
| **Backend latches the drive stop** | PASS | E2E: `e_stop` returns 200 `latched:true`. The mux policy shows `stop_latched=true` within 1 s |
| **No drive accepted while latched** | PASS | E2E: a client posting drive every 120 ms gets **15 of 15 refused (409)**. Mux `/cmd_vel` output had **0 non-zero** messages. The same holds after a web-server restart |
| **Network loss and browser disconnect cannot release** | PASS | E2E: still latched after each of: 5 s with no HTTP traffic, a half-sent request then a dropped connection, the web server killed (no motion while it was down), the server restarted, and the remote signal lost for 2 s. Every non-existent "release" action leaves it latched |
| **Stops accepted during shutdown** | PASS | E2E: with shutdown pending, `stop` and `e_stop` return 200; `drive` and `camera` return 409 |
| **Remote release procedure** | PASS | E2E against the live mux code:<br>- LB held with a stick deflected: no release;<br>- LB held 1.2 s: no release;<br>- still latched while LB is held past 2 s;<br>- releases only on letting go after neutral + LB ≥ 2 s.<br>Nothing replays after a release; only a new command drives |

### The same scenarios on the current production code (baseline, before Stage 1)

This is the same E2E harness against an unmodified copy of the live scripts:
- E-STOP returns "EMERGENCY STOP ACTIVE" and **does not latch**.
- **22/22 drive requests after E-STOP were accepted**, and the mux output carried **58 non-zero
  commands**.
- With shutdown pending, `stop` and `e_stop` were **refused (409)**.

This is the hazard Stage 1 removes.

## Stage 1b (web reset): 49/49 end-to-end checks

The run used stage 1 + stage 1b, with the stage 1 suite included.

| Requirement | Result |
|---|---|
| Never starts motors or resumes movement | Mux output had **0 non-zero** messages during and for 2 s after a granted reset. The following were all refused, with no motion: repeats of a press begun before the reset, repeats of a press whose start never arrived (network outage), and an old page without press ids. **Only a new press (start after the reset) drove** |
| All drive buttons released first | A drive request in the last 1.5 s → RESET BLOCKED |
| Motor commands at zero throughout | The server publishes zero before calling the mux. The mux keeps zero while latched (0 non-zero observed) |
| Explicit confirmation and authorised operator | Missing confirmation → 400. Request without the dashboard's origin header → 403. Forged or expired challenge → 409. 5 wrong PINs → locked out (429) even with the right PIN |
| Reject when stale, unsafe or unconfirmed | Blocked when: rover moving, remote disconnected, shutdown pending, odometry, `/cmd_vel` or mux policy stale (unit tests), or the challenge came from before a server restart. With the stick deflected, the server's checks pass but **the mux refused** (it is the final authority) |
| Fresh manual command required | As above (press-id rule, applied after **any** release, remote or web) |
| Hardware E-STOP never bypassed | Software can only ask the mux to clear its software latch. Any hardware stop in the power path is outside software control |
| Network loss never releases | No release without a granted POST. Challenges die with the server process |
| Clear display | STOP LATCHED — RESET AVAILABLE / RESET BLOCKED (with reasons) / NOT LATCHED — RELEASE ALL DRIVE BUTTONS, THEN PRESS AGAIN / CONNECTION LOST — RESET BLOCKED, in V1 and V2 (browser test 0 failures; screenshots attached) |
| Every stop and reset event logged | `stop`, `e_stop`, `latch_state`, `release_observed`, `reset_denied`, `reset_denied_pin`, `reset_refused_by_mux` and `reset_granted` were all present. **The PIN never appears** |

A defect found and fixed during this work: the first version required a 0.5 s gap in drive
requests after a reset. The end-to-end test showed it would accept a client whose repeat requests
resumed after a pause. It was replaced by the press-id rule (`e65fe67`) and retested.

## Package safety (every stage)

| Check | Result |
|---|---|
| Checksums | `SHA256SUMS` verified on the PC copy and on the Jetson |
| Install orders | **All valid orders of the five stages** (stage 1b after stage 1) gave the expected files and rolled back byte-identical. Stage 1b alone is **refused before any change** |
| Unintended files | Scope guard: a patch that edits an extra file is refused before any change (exit 2). One that creates an extra file is rolled back automatically (exit 3), leaving the tree identical. Tested for every stage |
| Rollback root | Pinned at install time. The checker runs every rollback without `ATLAS_ROOT` |

## Not yet shown (needs the device and your approval)

- Real phone touch behaviour (procedure C2).
- The physical remote's actual button mapping (FlySky vs the code's gamepad indices).
- Wheel motion stopping (procedure F, wheels lifted).
