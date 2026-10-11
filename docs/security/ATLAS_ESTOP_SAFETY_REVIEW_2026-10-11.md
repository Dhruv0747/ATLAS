# ATLAS E-STOP and dashboard safety review: prepared change (2026-10-11)

Status: **prepared and tested offline only.**
- Not deployed.
- No motor-moving test was run.
- Production `rover-status-web` on the Jetson is unchanged: sha `51f8e111…` equals the repo at
  `aa93355`.

This document covers Stage 1 of the approved plan. It implements items 1, 2 and 4 of
`ATLAS_DASHBOARD_SECURITY_FIX_PROPOSAL_2026-10-11.md`.

## What changes

| # | Change | Where | Commit |
|---|---|---|---|
| 1a | **E-STOP latches.** `e_stop` publishes zero, then the **existing** mux stop input `/atlas/voice/stop` (`Empty`). This is the same latch the commissioning page's LATCH DRIVE STOP already uses. If the latch publisher is unavailable, the zero is still sent and the reply is `503`, telling the operator to use the remote stop (B) | `atlas_status_web.py` do_POST + `AtlasRosNode.latch_drive_stop()` | `c71b95d` |
| 1b | **Drive refused while latched.** `drive` gets `409` and a zero Twist while a web E-STOP is less than 1 s old (this covers the window before the mux policy updates), or while fresh (≤1 s) `/atlas/control_policy` reports `stop_latched`. A stale policy does not block; the mux remains the authority | `AtlasRosNode.drive_stop_latched()` | `c71b95d` |
| 1c | **V2: E-STOP cancels local drive.** It fires on **pointerdown**, stops the 120 ms hold-to-drive repeat, and blocks drive presses from fingers that were already down until all fingers lift. Keyboard activation still works | `tools/ui_v2/build_command_js.py` P4a–c, `web/v2/shell.js`, `web/v2/estop.js` | Stage 1 UI commit |
| 2 | **Reboot action removed.** It piped a hard-coded sudo password and had no confirmation or origin check. It now returns 400 | `atlas_status_web.py` | `a7e2299` |
| 4 | **Stops during shutdown.** `stop` and `e_stop` are handled **before** the `SHUTDOWN_PENDING` gate, so they are never refused. Shutdown also latches the mux during its 2 s poweroff delay | `atlas_status_web.py` | `c71b95d` |

**Release stays physical and unchanged.** No web action publishes a release. The mux's
`RemoteStop` clears the latch only from the Xbox remote: sticks neutral, then LB held at least
2 s, then LB released. Two other facts are unchanged:
- `/atlas/remote_stop/reset` still needs a live, neutral joystick;
- the mux already latches by itself whenever the joystick is missing (`joystick unavailable`).

Behaviour changes you will notice:
- **Web E-STOP latch.** After a web E-STOP, the rover cannot be driven from any source (web,
  Foxglove, Nav2, commissioning) until it is released on the remote. Today the web E-STOP is a
  single zero command.
- **Commissioning lease.** A latch revokes any commissioning lease, exactly as LATCH DRIVE STOP
  already does. Re-arm it explicitly.
- **Wording.** The mux reports the reason as `REMOTE STOP: voice stop requested`, because the web
  reuses that input rather than changing the mux. A clearer reason would need a mux change, which
  is out of scope.
- **Classic dashboard.** It now shows "Drive stop latched…" (409) when you try to drive while
  latched. Before, it showed "Short safe drive pulse sent" even though the mux was discarding the
  command.

## New finding: E-STOP on V1 does not fire during a two-finger touch

This was tested in Chromium with real CDP touch points, phone viewport. One finger held Forward
and a second finger tapped E-STOP.

| | V1 (`onclick`) | V2 (pointerdown) |
|---|---|---|
| `e_stop` sent | **No.** A second-finger tap produces no `click` while another finger is down | Yes |
| Drive posts after E-STOP while the first finger stays down | V1 keeps driving (13 posts per 1.5 s) | **0** |
| A fresh press after all fingers lift | drives | drives (the server returns 409 if latched) |
| Mouse or keyboard E-STOP while a button is held (DOM click) | `e_stop` sent, then **7** more drive posts | `e_stop` sent, **0** drive posts |

The backend latch (1a/1b) protects V1 only when `e_stop` actually arrives. In the two-finger case
it never does. **The physical remote B button is the reliable stop for V1 touch use.**

The fix for V1 is a one-line change (bind `#stop` on `pointerdown`). I have **not** made it,
because you asked to keep V1 unchanged. I recommend approving it as part of this safety stage.

Evidence gap: this was emulated. It must be confirmed on your phone using the on-device check
below, which needs no motion.

## Also found (not changed)

- `scripts/check_gnss_at.sh:12` and `scripts/setup_atlas_plymouth.sh:31` also contain
  `echo password | sudo -S …`. They are manual operator scripts, not web-reachable.
- The password string is in git history in all three files. Rotating the Jetson password is your
  action. Rewriting history is a separate decision.
- Commissioning's LATCH DRIVE STOP (`commissioning.js`) is also `onclick`. That page has no
  hold-to-drive, so the two-finger case does not arise there, but the same pointerdown change
  would be harmless.
- Item 3 (same-origin requirement on form POSTs) and item 5 (escaping, intercom auth) are **not**
  in this stage.

## Offline test results

| Suite | Result |
|---|---|
| `tests/test_status_web_estop_safety.py`: real `atlas_status_web` module, ROS stubbed, real HTTP handler `do_POST` | 11/11:<br>- `e_stop` = zero then latch;<br>- drive after E-STOP → 409 + zero only;<br>- drive refused while the mux reports a latch;<br>- allowed when unlatched or the policy is stale;<br>- no web action releases;<br>- 503 + zero if the latch publisher is missing;<br>- 503 saying "Zero speed NOT sent" if the ROS link is down (fix `e0e2156`);<br>- `stop`/`e_stop` accepted while shutdown is pending (everything else 409);<br>- shutdown latches after stop |
| Same file, **mux contract**: the real `AtlasCmdVelMux.on_voice_stop`/`hold_remote_stop`/`on_stop_joy` and the real `RemoteStop` | Voice-stop input latches, flushes the WEB channel and publishes zero. Only neutral sticks + LB held ≥2 s + LB released clears it; 1.5 s and "still held" do not |
| `tests/test_status_web_no_reboot.py` | 2/2: no `sudo -S` or reboot branch in the source; `action=reboot` → 400 |
| Existing mux / remote-stop tests | `test_atlas_cmd_vel_mux_stop_hold` 6/6, `scripts/test_remote_stop` 10/10 |
| Browser (`tools/ui_v2/test_ui_v2.py`, safety section) | V2: 0 drive posts after E-STOP (DOM click and two-finger touch, pad and dock E-STOP). Release-to-stop on pointer up, cancel, blur and hidden is unchanged (0 drive after the event). The 120 ms cadence is unchanged. Every button's request contract still matches V1 |

## On-device checks, after you approve deployment (no motion required)

1. Rover parked and **remote stop latched**, with the Xbox remote in hand.
2. **E-STOP latch.** From your phone, press E-STOP on V2. Expect the toast "EMERGENCY STOP
   LATCHED…" and the **Drive stop latched** chip; `/atlas/control_policy` `stop_latched: true`.
3. **Drive refused.** Hold Forward on V2 and on the classic page. Expect "Drive stop latched…"
   and no wheel motion (the mux was already latched).
4. **Two-finger check.** Hold Forward with one finger and tap E-STOP with another, on V2 and on
   V1. Note whether the toast appears. This confirms or refutes the V1 finding on your real phone.
5. **Physical release.** Release with the remote (neutral, hold LB ≥2 s, let go). Confirm the
   chip clears. Then latch again with B before ending.
6. Only with **wheels lifted**, and only if you separately authorise it: a short hold-to-drive
   pulse, then E-STOP, to confirm the wheels stop and stay stopped.

## Deployment and rollback

The package is `deploy/stage1-safety/`. It contains a patch against the deployed baseline,
`install.sh` (dry-run, backup, then apply) and an auto-written `ROLLBACK.sh`.
- **Restart:** `rover-status-web` only, coordinated, with the rover parked and latched. The
  dashboard drops for about 5 s.
- **Rollback:** run `ROLLBACK.sh` from the backup folder, then restart `rover-status-web`.

The V2 frontend part (1c) ships with the `/v2/` package (Stage 2), because V2 is not installed
yet.
