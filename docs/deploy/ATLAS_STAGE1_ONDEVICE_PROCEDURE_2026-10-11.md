# Stage 1 (and 1b): supervised on-device procedure

Status: **procedure only.** Nothing has been installed. Each part needs your explicit go-ahead.
- **Parts A–D** install Stage 1 and verify it **without any motor motion**.
- **Part E** (stage 1b, web reset) is a separate approval.
- **Part F** is the only part where wheels turn. It needs **its own approval**, and is done
  **only with all four wheels lifted** off the ground.

**Roles.**
- **Operator (you):** at the rover, with the physical remote in hand, a phone, and line of sight
  to the wheels.
- **Claude:** runs only the commands listed below, over SSH. It sends no drive commands at any
  point.

**Abort rule, any step.** If anything moves unexpectedly, or a result differs from the expected
one:
1. Press the remote's stop (B).
2. If needed, cut motor power with the physical switch.
3. Stop the procedure. Rollback (Part G) restores the previous files.

## Before you start

| Check | How | Expected |
|---|---|---|
| Which remote is connected | Tell me the model. The code expects a gamepad where button index 1 is "B" (stop) and index 4 is "LB" (release) | Confirmed by you. If it is a FlySky receiver, we first map its switches, with no code change |
| Rover parked, in a clear area | visual | yes |
| Remote stop latched | Press B; the dashboard shows "Drive stop latched" | latched |
| Autonomy and auto-reseeding disabled | unchanged from today | unchanged |
| Your PC can be off for the phone test | — | optional for Stage 1 |

## A. Install Stage 1 (no restart yet)

Each command is read-only except `install.sh`, which writes a backup first.

```bash
cd ~/project_atlas/data/staging/2026-10-11 && sha256sum -c SHA256SUMS      # expect: all OK
tar -xzf stage1-safety.tar.gz && cd stage1-safety && cat README.txt MANIFEST
bash verify.sh capture                                                       # saves V1 pages for comparison
bash install.sh
```

`install.sh` must print all of the following, in order:
1. "rehearsal on a scratch copy".
2. "backup to …/data/backups/<stamp>-stage1-safety".
3. "byte-compile ok".
4. "scope check: only the 1 files listed … changed".
5. "NOT restarted".

Any other outcome means the install undid itself (exit 2 or 3) and nothing changed.

## B. Restart, coordinated (dashboard gone for about 5 s; rover latched)

```bash
systemctl --user restart rover-status-web.service
sleep 5 && bash verify.sh stage1
```

Expect `PASS` for:
- service active;
- GET `/`, `/mapping`, `/commissioning`, `/wifi`, `/api/status`, `/api/map` all 200.

`CHECK` lines for the classic page are expected: the classic E-STOP line changed on purpose.

## C. No-motion checks (remote latched the whole time; wheels may stay on the ground)

| # | Action (operator) | Expected | Evidence (Claude, read-only) |
|---|---|---|---|
| C1 | Phone, classic dashboard: tap **E-STOP** once | Toast "EMERGENCY STOP LATCHED. Release with the remote…" | `journalctl --user -u atlas-cmd-vel-mux` shows a latch; `/api/status` `control_policy.stop_latched=true`, reason "voice stop requested" |
| C2 | **Two-finger test.** Hold FORWARD with one finger and tap E-STOP with a second finger | Toast appears, so E-STOP was sent while the other finger was down. This confirms the emulated finding on your phone | The new event log (stage 1b) or the `rover-status-web` journal shows `e_stop` |
| C3 | Hold FORWARD for 2 s | The rover does not move (latched). On the classic page nothing visible changes (drive replies are silent) | `/cmd_vel` stays zero (`ros2 topic echo /cmd_vel --once` repeated); every drive reply is 409 |
| C4 | Turn **phone Wi-Fi off** for 10 s, then back on | Still latched | `stop_latched=true` |
| C5 | Close the browser tab, reopen it | Still latched | same |
| C6 | Release on the remote: sticks neutral, **hold LB 2 s**, then let go. **Before** letting go, check the dashboard still shows latched | Latched until LB is released, then "released by neutral LB hold". **The rover does not move** | `stop_latched=false`; `/cmd_vel` zero, with nothing replayed |
| C7 | Latch again with **B** | latched | `stop_latched=true` |

## D. Stop accepted during shutdown

This is **not** run on the device, because it would power the Jetson off. It is covered by:
- the unit tests;
- the isolated end-to-end run, where `stop` and `e_stop` return 200 and `drive` and `camera`
  return 409 while a shutdown is pending.

If you ever use SHUT DOWN, the server also latches the mux before powering off.

## E. Stage 1b: web reset (separate approval; stage 1 must be installed)

1. **Set your PIN** on the Jetson, typed by you, 6–12 digits:
   ```bash
   python3 ~/project_atlas/scripts/atlas_estop_reset.py set-pin
   ```
   Only a salted hash is stored, with mode 0600.
2. **Install and restart:**
   ```bash
   cd ~/project_atlas/data/staging/2026-10-11 && tar -xzf stage1b-estop-reset.tar.gz && cd stage1b-estop-reset
   bash install.sh && systemctl --user restart rover-status-web.service
   ```
3. **Run the checks.** The remote stays connected and latched, and the wheels may stay on the
   ground: a reset does not move the rover.

| # | Action | Expected |
|---|---|---|
| E1 | Classic and V2 dashboards (V2 after Stage 2) | Panel shows **STOP LATCHED — RESET AVAILABLE** with the remote connected and neutral, rover still and no button pressed |
| E2 | Hold FORWARD, then look at the panel | **RESET BLOCKED — a drive button is still pressed** (for 1.5 s after release) |
| E3 | Switch the remote off | **RESET BLOCKED — physical remote not connected** |
| E4 | Enter a wrong PIN and confirm | "RESET BLOCKED: wrong operator PIN". After 5 wrong PINs, locked for 5 min |
| E5 | Correct PIN and confirm | "E-STOP RELEASED. Nothing moves until you press a drive button again." **No motion.** |
| E6 | Immediately hold FORWARD | The **first** press after the reset is refused if any drive request came less than 0.5 s earlier. A held button never resumes. **Do not test motion here.** Part F covers it |
| E7 | Latch again with B (or E-STOP) | latched |
| E8 | Claude, read-only | `~/project_atlas/data/safety/estop_events.jsonl` has `e_stop`, `latch_state`, `reset_denied`, `reset_denied_pin` and `reset_granted` entries, and never the PIN |

## F. Motion confirmation: separate approval, all four wheels lifted

| # | Action | Expected |
|---|---|---|
| F1 | Release with the remote (C6) | released |
| F2 | Hold FORWARD on the classic dashboard for 1 s | Wheels turn slowly |
| F3 | While still holding FORWARD, tap E-STOP with another finger | **Wheels stop within about 0.3 s and stay stopped** while the first finger is still down |
| F4 | Lift the first finger, press FORWARD again | **No motion** (latched) |
| F5 | Repeat F1–F4 on Glass UI V2 (after Stage 2), pad E-STOP and dock E-STOP | Same |
| F6 | (stage 1b) Web reset, then press FORWARD once, briefly | Wheels turn only on this fresh press; nothing turns at the moment of reset |
| F7 | Latch with B, lower the rover | end |

## G. Rollback, any time

```bash
bash ~/project_atlas/data/backups/<stamp>-stage1b-estop-reset/ROLLBACK.sh   # if 1b installed (undo it first)
bash ~/project_atlas/data/backups/<stamp>-stage1-safety/ROLLBACK.sh
systemctl --user restart rover-status-web.service
```

Each `ROLLBACK.sh` is pinned to the tree it was installed into. It restores the exact previous
files and removes only the files that stage added.

## What the isolated tests already showed (no hardware involved)

The tests ran the real web server and the **live** mux code, copied from the Jetson, on a private
DDS domain with a synthetic remote and odometry. The full results are in
`docs/deploy/ATLAS_STAGE1_ISOLATED_TEST_RESULTS_2026-10-11.md`.
