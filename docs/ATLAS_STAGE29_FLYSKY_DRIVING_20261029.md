# Stage 29: FlySky driving integration (implemented offline, NOT deployed, disabled), 2026-10-29

Stage 28 is complete (`docs/ATLAS_STAGE28_FLYSKY_LIVE_RESULT_20261028.md`). This stage adds FlySky FS-i6S driving on
the Jetson side. It uses the existing V3.6.161 firmware (SBUS motor drive compiled out; no flash) and the existing
read-only RC bridge. Every command goes through the existing ROS 2 cmd_vel multiplexer, then the existing motor path.
Nothing is deployed and nothing on the rover changed in this stage.

## Command path

```
FS-i6S ─RF─ FS-iA receiver ─SBUS─ STM32 (V3.6.161: forwards 0xE1, cannot drive from SBUS)
   └─ yahboom_base.py ── /atlas/rc/frames (existing, read-only) ──┐
                                                                  ▼
            atlas_flysky_teleop.py  (NEW; decisions in atlas_flysky_drive_core.py)
              ├─ /cmd_vel_flysky (Twist)  only if gate on + config reviewed + selected + armed
              ├─ /atlas/flysky/stop (Empty)  stop-only
              └─ /atlas/flysky/drive_status (JSON)
                                                                  ▼
   atlas_cmd_vel_mux.py (PATCHED, additive): FLYSKY channel admitted only when FlySky is selected;
   REMOTE (/cmd_vel_joy, Xbox) admitted only when Xbox is selected; Xbox /joy stop + LB reset unchanged
                                                                  ▼
                   /cmd_vel ── yahboom_base.py (unchanged, 0.45 s deadman) ── motors
```

## Safety design

| Requirement | How it is met | Evidence |
|---|---|---|
| No direct SBUS driving | Firmware compiles SBUS drive out (`DRIVE_DISABLED` bit verified on every report). The new node only requests via the mux | Stage 28 live; mux tests |
| One controller at a time | Mux `controller_accepts()`: REMOTE only with XBOX selected; FLYSKY only with FLYSKY selected **and** the gate on. Boot default is XBOX | 17 mux tests on the **live** mux baseline |
| Explicit selection | Services `/atlas/manual_controller/select_xbox` and `select_flysky`; dashboard page `/v2/flysky-drive` | web tests, browser test |
| Handover = zero motion | Selection only while the E-STOP is latched and `/cmd_vel` was zero. It flushes every channel and publishes zero. The normal reset (Xbox LB hold, or dashboard + PIN) is still required afterwards | mux tests |
| Signal loss, stale data | No new frame in 0.30 s, or the SBUS failsafe flag → zero at once. If armed, the node also requests the E-STOP latch and keeps asking until the mux reports it. A repeated frame (same `seq`) is not fresh. Mux FLYSKY timeout 0.35 s → stop within one 50 ms watchdog cycle | core + mux tests |
| Centre-value failsafe is not trusted | The arm switch must be at its far end (> 1700). Centre values (992 and 1024) fall in the INVALID band and disarm. The stop switch reads STOP unless < 400. A config that would put a centre value in ON or RUN is rejected | `test_centre_value_failsafe_without_flags_cannot_drive`, config tests |
| E-STOP priority | Unchanged. Xbox B and voice stop still latch; Xbox absence > 0.5 s still latches. New stop-only input `/atlas/flysky/stop` → same latch. Nothing new can reset | mux tests with the real `RemoteStop` |
| Configurable | `config/atlas_flysky_drive.json`: throttle and steering channel, direction, dead zone, calibration; arm, stop and speed-mode switches; speed, turn-rate and acceleration limits; timeouts | config validation tests |
| No weaker limits | Hard ceilings 0.25 m/s and 0.8 rad/s, equal to the Xbox non-turbo scales in `joy_config.yaml`. Shipped defaults are 0.15 m/s and 0.6 rad/s. The mux clamps FLYSKY again independently. Acceleration is slew-limited; decreases and stops are immediate; a direction change passes through zero | core + mux tests |
| Arming | Arm OFF must be seen first (no arm-through at power-on or after any stop). Throttle must be centred at arming. Arm OFF disarms | core tests |
| Status and config in the dashboard | `/v2/flysky-drive`: active remote, E-STOP, gate, drive-node state, live arm/stop/throttle/steering/speed, the request sent to the mux, and the config with limits and errors. Config is read-only by design | browser test (desktop and phone) |

Design choices that need the owner's acknowledgement:
1. **The throttle is CH2 (right stick up–down), not CH3.** The FS-i6S left stick up–down does not spring back to
   centre. A released stick would keep the rover driving. The config requires `self_centring: true` for the throttle.
   **Owner decision, 09:54:** steering is **CH1** (right stick left–right), stick right = turn right. This replaces the
   CH4 proposed earlier the same morning, so throttle and steering are now both on the spring-centred right stick.
   Releasing the stick stops the rover and straightens it. The cost is coupling: a diagonal push mixes throttle and
   steering beyond the 8 % dead zone. This must be checked in the lifted test.
2. **The Xbox stays switched on while FlySky drives.** It remains the stop and reset device: its absence latches the
   E-STOP exactly as today. FlySky can stop but never reset.
3. **A signal loss while armed always ends in a latched E-STOP.** That needs the normal reset; it is not a silent
   resume.
4. **Switch roles:**
   - SwA (CH5) = ARM, down = on;
   - SwB (CH6) = STOP, up = run;
   - SwC (CH7) = speed, 33 / 66 / 100 % of the configured limit;
   - SwD, VrA, VrB are unused.

## Files

| File | Change |
|---|---|
| `project_atlas/scripts/atlas_flysky_drive_core.py` | new: pure decision core |
| `project_atlas/scripts/atlas_flysky_teleop.py` | new: ROS node. It creates no command publisher unless enabled |
| `project_atlas/scripts/atlas_manual_controller_web.py` | new: GET status and POST select. It cannot reset, drive or configure |
| `project_atlas/config/atlas_flysky_drive.json` | new: `reviewed_by_owner: false` |
| `project_atlas/web/v2/flysky-drive.html`, `flysky-drive.js` | new page; `flysky.css` gets 3 page-scoped rules |
| `project_atlas/scripts/atlas_web_v2.py` | +1 line (page route) |
| `project_atlas/systemd/atlas-flysky-teleop.service` | new, gate `=0`, not installed |
| `tools/deploy/stage29_flysky_drive/insert_flysky_mux.py` | patches the **live** mux 0d959286: +62 lines; 1 line modified (FLYSKY added to the manual-only allow-list); also applies to the repo mux |
| `tools/deploy/stage29_flysky_drive/insert_status_web_hooks.py` | patches the **live** status web 4ab16214: +9 lines, 0 removed |
| `tools/deploy/stage29_flysky_drive/MANIFEST.json` | live and candidate SHA-256 values |
| Unchanged | firmware, `atlas_flysky_core.py`, `atlas_remote_stop.py`, the RC bridge, the Test Lab (still read-only, one subscription) |

Tests:
- New in this stage, 58 in total:
  - `test_flysky_drive_core.py` (25);
  - `test_flysky_mux_patch.py` (17);
  - `test_manual_controller_web.py` (16, including 2 real-browser).
- Together with the existing FlySky and mux suites: **169 tests pass, 1 pre-existing skip**.

## Exact remaining safety blockers

1. **Physical E-STOP tests A–E have never passed.** They are still open in the handoff, and no stop latency has been
   measured. No FlySky ground driving until Xbox-B, dashboard and voice stops are measured on lifted wheels. The first
   lifted test includes the Xbox-B and FlySky-stop measurements. Any separate hardware power-cut is not confirmed in
   the repo: the owner must say whether one exists.
2. **Physical directions are unverified:** throttle sign (CH2 up → forward?) and steering sign (stick right → wheels
   right?). Lifted test only.
3. **Owner review of the config:** `reviewed_by_owner` stays `false` until the owner confirms the table above.
4. **Deployment needs three restarts, each a DDS discovery CPU spike above 75 %:**
   - `atlas-cmd-vel-mux`;
   - `rover-status-web`, the largest participant (spike length unmeasured);
   - the new `atlas-flysky-teleop`, about 19 endpoints.

   Each needs its own scoped CPU-transient approval. A Stage-28-style deployer has not been written yet: it needs
   backups, live-hash checks, the E-STOP latched throughout, observer-guarded windows, and per-file rollback.
5. **Recommended, not required by this design:** set the transmitter failsafe (Function → Failsafe) so that the
   arm channel CH5 reads 240 (OFF) on signal loss.
6. The repo mux carries an undeployed AMCL feature. The patcher applies to both versions; re-run the tests when that
   feature is deployed.

## Plan for the first controlled actuator test (needs separate approval; not started)

Preconditions:
- Wheels off the ground on a stand.
- Owner at the rover holding the Xbox, B within reach.
- FlySky transmitter in hand.
- Area clear.
- Continuous read-only logging running: observer, the `rc_log`-style logger, and drive status.

1. **Deploy with the gate OFF** (mux, web, teleop). Verify:
   - behaviour is identical: Xbox drives, FLYSKY is dropped, the page shows "FlySky driving off";
   - hashes match the MANIFEST;
   - CPU returns to ≤ 75 % after each bounded transient.
2. Owner sets `reviewed_by_owner: true`.
3. **Enable for this test only.** Set the gate to 1, with test limits: `max_linear_mps` 0.05, `max_angular_radps`
   0.2, speed switch at 33 %.
4. With the E-STOP latched, select FlySky. Reset with the Xbox LB hold.
5. **Arm and check directions, one at a time.** Arm: SwA off → on, throttle centred. Then:
   - nudge throttle up, then down;
   - nudge steering right, then left.

   Record wheel direction, `/cmd_vel` and the encoders for each. Any wrong sign → FAIL; stop and fix the config.
6. **Stop tests**, each must end at zero within the measured latency:
   - Xbox B;
   - FlySky SwB;
   - SwA off;
   - transmitter power-off (expect FAILSAFE → latch);
   - Xbox power-off (expect latch).
7. **Restore:** select Xbox; set the gate back to 0 unless further driving is separately approved.

Abort and stop at once on: any unexpected wheel motion, a wrong direction, a stop that doesn't latch, any
observer signal stale, or CPU, RAM or temperature limits exceeded outside an approved transient.

## Hardware power: owner decisions (2026-10-29 09:57 and 10:00)

- There is **no separate motor-power kill switch**. Motor power comes from the battery through the DC-DC buck
  converter.
- The owner will **not** add a kill switch or any wiring. The current hardware configuration is preserved.

**What follows for safety.** The Xbox E-STOP, the dashboard E-STOP, the voice stop and the new FlySky stop are all
**software**. Each one latches the mux, the mux publishes zero `/cmd_vel`, and `yahboom_base.py` sends zero to the board.
None of them removes motor power. A fault anywhere in that chain could leave the motors driven:
- the base driver;
- the serial link;
- the STM32 firmware;
- the motor driver.

The only independent physical barriers today are:
- wheels off the ground (lifted);
- unplugging the motor connectors at the board. This needs no new wiring and keeps the board, telemetry and the
  receiver powered, at the cost of the encoder counts;
- the main power switch, which also stops the STM32, telemetry and the receiver.

**On the claim that "the E-STOP has prevented unwanted movement".** In every test so far (Stages 27–29) no non-zero
motor command was ever sent. The E-STOP has therefore never been *challenged*. Zero motion shows that nothing commanded
motion. It does not show that a stop interrupts commanded motion. The physical E-STOP tests A–E are still open.

### Residual risks (no independent motor disconnect)

| # | Risk | Why it remains | Mitigation without new hardware |
|---|---|---|---|
| R1 | A software or serial fault keeps the last non-zero speed | Stopping depends on the base sending zero, or its 0.45 s deadman | Verify the deadman on lifted wheels: stop the command stream and measure the wheel stop |
| R2 | The firmware ignores or delays zero | STM32 behaviour has not been tested against a live stop | Measure the stop latency on lifted wheels before any ground test |
| R3 | An E-STOP latch fails to propagate | The mux and the base are separate processes | Verify each stop path (Xbox B, dashboard, voice, FlySky SwB, Xbox off, transmitter off) on lifted wheels |
| R4 | Wrong direction or a runaway on the first powered test | Directions are unverified | Lifted wheels only; test limits 0.05 m/s and 0.2 rad/s; one axis at a time |
| R5 | Operator cannot cut power quickly | No kill switch | The owner keeps the main power switch within reach; optionally, motor connectors stay unplugged for the non-motor steps |

### Required before ANY powered driving test (Stage B or later; not approved)

These checks run on lifted wheels, at the test limits, with continuous logging and the measured latency recorded:
1. **E-STOP paths:** Xbox B, dashboard E-STOP, voice stop. Each must take a commanded non-zero wheel speed to zero, and
   the latch must hold.
2. **Watchdogs:**
   - mux stale-source stop: 0.35 s source timeout, 50 ms cycle;
   - base deadman: 0.45 s, checked by stopping the mux's output stream.
3. **Arbitration:** FlySky is dropped while Xbox is selected, and vice versa. Handover is refused while the E-STOP is
   released.
4. **FlySky failsafe:** transmitter off → FAILSAFE → zero → latch. Also SwB stop, SwA off, Xbox off → latch.
5. If any check fails, there is no driving and the fault is fixed first.

## Stage A: deployment plan (prepared; NOT run; separate approval required)

Script: `project_atlas/tools/deploy/stage29_flysky_drive/deploy_stage29.py`, commit `06c4352`.
Package: `stage29A_pkg_06c4352.tar.gz`, SHA-256 `a0d41ab565f1cd3d…`, already copied to
`~/project-atlas-migration/stage29A_pkg_06c4352/` on the rover. Nothing is installed.

**Read-only preflight on the real rover, 10:13 IST: GO.**
- All three steps' candidates rebuilt from the live files; every hash matches MANIFEST.
- Gate off everywhere; safety OK ×3.
- CPU mean 61.8 % (max 63.9 %), RAM 66.9 %, 62.9 °C.
- No restart: mux 1948, dashboard 2103, base 1953.

Observation:
- Encoders were `[-404, 1471, -14027, 1421]` at 09:27 and `[-402, 1465, -14041, 1408]` at 10:13.
- The E-STOP stayed latched throughout ("B pressed" since 08:29:53; no release in the journal), motor output was 0,
  and the counts were steady afterwards.
- The cause is not proven; the likely cause is handling.

### Order and why

| Step | Restarts | Safety source during the restart | Why here |
|---|---|---|---|
| A1 `mux` | `atlas-cmd-vel-mux` | Observer. Mux-owned signals are exempt only until the patched policy returns (≤ 20 s). The **base-owned** signals (`/motor_speed`, encoder health, base loop, base still, base identity) stay strict | Everything depends on its policy keys. The proven old dashboard remains a second safety source |
| A2 `teleop` | starts the new `atlas-flysky-teleop` | Observer, no exemptions | Small node. It must log DISABLED and must not advertise `/cmd_vel_flysky` before any UI can select it |
| A3 `web` | `rover-status-web` | Observer only. The dashboard is down by design; the observer does not depend on it | Largest and unmeasured spike, so it runs last and on its own |

One step per invocation. Each step refuses unless the previous one is installed, and each has its own approval and its
own CPU bound. The E-STOP stays latched and Xbox stays selected throughout; the gate is checked off before and after.

### Measured CPU recovery criteria (limits 75 / 80 / 70 unchanged)

1. Pre-window: 30 s strict preflight, then every recorder sample before the restart ≤ 75. Otherwise the step is
   refused and nothing changes.
2. Over 75 is tolerated only inside the approved bound for that service.
3. Then 30 consecutive 1-s samples all ≤ 75. RAM ≤ 80 and temperature < 70 hold on every sample, inside the bound too.
4. The steady-window mean must be ≤ the pre-window mean + 4 points (no lasting new load).

Every sample is streamed to disk as taken.

### Proposed bounds (owner decision)

| Step | DDS endpoints | Evidence | Proposed bound |
|---|---|---|---|
| A1 mux | ≈ 48 | Not measured. It lies between two measured restarts: recovery (32 endpoints, last over-limit +8.2–8.7 s, 3 runs) and base (80, +9.3 s) | **15 s** (as approved for the base) |
| A2 teleop | ≈ 19 | Not measured. The join cost is dominated by the per-participant term, so it should resemble recovery | **12 s** |
| A3 web | ≈ 133, plus heavy Python start-up | **Not measured, and not inferable.** Earlier dashboard restarts (Stages 26, 31, 32) recorded no CPU transient. The DDS trend suggests about 10–11 s, but start-up work is outside that model | **20 s, explicitly unproven.** The first restart is the measurement |

### Failure handling

- **Safety failure** (observer unsafe or stale beyond the exemption, protected PID changed, service not back, or
  verification failed): automatic rollback of that step. Backups are restored, the service restarts once, and the
  rollback CPU is recorded but not aborted. Result `FAIL_ROLLED_BACK`. No retry.
- **CPU, RAM or temperature over the limit with safety intact:** result `FAIL_HELD`. There is **no automatic second
  restart**, because a rollback would repeat the spike. The script keeps recording until CPU is back under the limit
  (up to 180 s), then stops. Rollback is the owner's decision:
  `OWNER_APPROVED=yes deploy_stage29.py rollback --step <step> --evidence <dir> --owner-confirms-estop-latched --owner-confirms-rover-lifted-and-clear`
- **Partial states are safe by design.** A patched mux with the old dashboard still runs with Xbox only. The disabled
  teleop without a patched mux stays NOT_SELECTED.

### Physical conditions during Stage A

- Rover lifted and clear; E-STOP latched (Xbox B); Xbox powered.
- FlySky transmitter off (recommended; the gate is off regardless).
- The owner keeps hands off the wheels during each window, so the encoder-stillness checks stay meaningful.
- Motors stay connected, as the owner chose. Stage A commands no motion.

### Command (per step, run detached so a dropped SSH session cannot orphan it)

```
systemd-run --user --unit=atlas-stage29-A1 --collect -E OWNER_APPROVED=yes \
  -p WorkingDirectory=$PKG /usr/bin/python3 $PKG/deploy_stage29.py deploy --step mux --cpu-bound-s 15 \
  --owner-confirms-estop-latched --owner-confirms-rover-lifted-and-clear
```

Tests: 14 fake-rover end-to-end deployer scenarios, part of 240 tests passing across the FlySky, mux and Stage 28
suites. They cover:
- pass;
- each refusal;
- base-signal failure → rollback;
- mux not back → rollback;
- CPU overrun → hold, then owner rollback;
- lasting load → hold;
- protected PID change → rollback;
- teleop advertising a command topic → rollback;
- dashboard verification failure → rollback;
- read-only preflight.

## Stage A1 attempt 1, 2026-10-29 10:22 IST: FAIL, rolled back (fail-closed)

Approved: one A1 attempt (mux only), bound 15 s. Package `06c4352`. Evidence:
`~/project-atlas-migration/stage29-deploy-mux-20261029_102213-284142923/`.

Conditions checked before start:
- E-STOP latched ("B pressed"); Xbox connected (`/joy` age 0.0 s, 15.9 Hz).
- Transmitter off (receiver LOST, last frame 1443 s old).
- Commands and motor output 0; live mux = baseline `0d959286`.
- Encoders had moved 10:13–10:21 with no command: the owner confirmed handling while lifting, and they were steady for
  20 s before the start.

Timeline:

| Time | Event |
|---|---|
| 10:22:17–47 | Pre: safety OK ×3; preflight CPU mean 62.2 / max 64.7, RAM 65.1 %, 61.3 °C |
| 10:22:53 | Backup verified; patched mux `5d096638` installed; `atlas-cmd-vel-mux` restarted (mux-owned observer signals exempt) |
| 10:22:59 (+5.8 s) | Dashboard shows the patched policy: `stop_latched` true, XBOX, gate false, STOPPED. The script cleared the exemption **on that basis** |
| 10:23:00 (+5.8 s) | The observer still had the mux signals stale (foxglove bridge not yet re-subscribed) → IMMEDIATE ABORT |
| 10:23:01 | Original restored (hash verified) and restarted once; rollback CPU recorded |
| 10:23:32 | Rollback complete. Mux PID 431020, original, priority line without FLYSKY, NRestarts 0 |

CPU, RAM and temperature:
- **Forward restart (patched mux):** +1 71.4, +2 69.6, **+3 100.0**, +4 99.5, +5 97.2, +6 92.7, +7 89.8 %.
  The window was aborted at +7 s, so the forward recovery was not measured. Peak 100.0 %.
- **Rollback restart (original mux):** over 75 % from +1.0 to **+8.1 s** (7 samples, peak 99.7 %). After +9 s:
  23 samples, max 71.6 %, mean 62.2 %, equal to the pre-window mean.
  **This is the first measured mux restart: it ended inside the 15 s bound.**
- RAM max 66.2 %, temperature max 61.8 °C. No limit was exceeded outside the transient.

Safety:
- Base-owned observer signals (`/motor_speed`, encoder health, base loop, base still, base identity) stayed OK for the
  whole window. The only base flags were in the observer's warm-up before the change.
- E-STOP latched throughout. Encoders `[-444, 1473, -14198, 1401]` unchanged before and after.
- Commands 0, motor output 0. Dashboard 2103, base 1953, recovery 1998 and EKF 3440 unchanged.
- After the rollback the E-STOP is still latched. The reason reads "joystick unavailable", because the restarted mux
  boots latched.

**Root cause (deployer bug, not a rover fault).** `wait_mux_back` cleared the mux-signal exemption when the
*dashboard* saw the restarted mux. The *observer* reads the same topics through the foxglove bridge, which re-subscribes
later. The offline fake made both recover at the same instant, so the tests could not see the lag.

**Fix (commit below).** The exemption clears only when the dashboard shows the patched policy **and** the observer's
own verdicts show every mux-owned signal fresh and OK for 1.0 s, within the same 20 s limit. Two tests were added:
- a 1.5 s bridge lag in every fake-rover run (the old code fails it);
- an observer that never sees the mux → rollback.

**Second finding (pre-existing code path, recorded).** The patched mux, stopped by the rollback 7 s after its start and
at 90–100 % CPU, logged `RCLError: Failed to publish: publisher's context is invalid` during shutdown. Its
zero-on-shutdown messages may not all have been sent. The patch does not touch shutdown, and the original mux's stop at
10:22:53 logged nothing. Mitigations held: E-STOP latched, commands already zero, base 0.45 s deadman. The base-deadman
check in the "required before any powered test" list covers this path. There was no retry.

## Stage A1 attempt 2, 2026-10-29 10:37 IST: PASS (accepted by the owner)

Package `1c7f97c`. Evidence: `~/project-atlas-migration/stage29-deploy-mux-20261029_103741-481794692/`.

- **CPU:** peak 99.5 %. Over 75 % for 7 samples, +2.2 to +8.3 s, inside the 15 s bound. 32 post-bound samples all
  ≤ 75 (max 66.9), steady mean 62.9 % vs pre-window 64.1 %.
- **RAM and temperature:** max 66.0 % and 62.8 °C.
- **Exemption timing:** dashboard back at +5.7 s; the observer saw the mux signals fresh from +11.3 s; the exemption
  cleared at +12.4 s. The 5.6 s bridge lag was waited out by the fix.
- **Observer:** 181 verdicts in the window, no base-owned failure, all 132 after the exemption OK, max verdict gap
  0.27 s.
- **Deployed:** mux `5d096638`, PID 442503, priority line `REMOTE > FLYSKY > …`, policy XBOX / gate false.
- **Safety and services:** E-STOP latched; no motion; other PIDs unchanged.

## Stage A2 readiness (2026-10-29 11:06 IST; read-only, NOT deployed)

### The 0.88 s policy age seen in A1
The A1 observer stream shows the cause precisely:

| Window | Policy age | `/cmd_vel` age (same mux process) |
|---|---|---|
| Before the restart | max 0.096 s (10 Hz) | normal |
| +11.3 to ~+18 s after the mux restart | sawtooth up to 0.83 / 0.88 s (about 1–2 Hz) | ≤ 0.21 s from +12.3 s |
| From +20 s | max 0.109 s | normal |

CPU was already back at 63–67 % during the slow window. A starved mux would have delayed both topics, so the lag is in
the delivery of the policy topic (most likely the foxglove bridge's new subscription settling), and it is transient.

Steady state at 10:5x, 60 s: 235/235 verdicts OK.

| Signal | max age | p99 |
|---|---|---|
| Policy | 0.107 s | 0.101 s |
| `/cmd_vel` | 0.238 s | — |
| `/motor_speed` | 0.601 s | — |

Max verdict gap 0.254 s. A2 does not restart the mux, but it adds a new subscriber to the policy topic. If the policy
age reaches 1.0 s during the join, A2 aborts and rolls back. The limit is **not** raised.

### Two verification defects found in the readiness check and fixed before any A2 attempt
1. `advertised_topics()` blocked forever on the real bridge: the observer WebSocket has no timeout after the handshake.
   It now reads with a hard deadline and fails closed on no advertisement (`e16c377`).
2. `/cmd_vel_flysky` **is already advertised**, because the A1 mux subscribes to it. "Topic absent" would have
   failed a correctly disabled teleop. The check is now behavioural (`6c54ddd`): subscribe through the bridge, require
   **0 messages** on `/cmd_vel_flysky`, and a received `drive_status` with state `DISABLED`.
   Live: `/cmd_vel_flysky` advertised, 0 messages in 3 s; policy 30 messages in 3 s, decoded.

### Package and dependencies (verified on the rover)

| File | SHA-256 prefix |
|---|---|
| `scripts/atlas_flysky_drive_core.py` | 567f0433 |
| `scripts/atlas_flysky_teleop.py` | feecba2c |
| `config/atlas_flysky_drive.json` | 031c9c08 |
| `~/.config/systemd/user/atlas-flysky-teleop.service` | eca2270f |

- Package `6c54ddd`, SHA-256 `627a7506…`. All four files are new; their destinations are absent.
- `systemd-analyze --user verify` passes on a staged copy of the unit.
- On the rover's Python 3.10.12, with the **live** `atlas_flysky_core.py` (3e4b379e): the config validates, it is
  *not usable* (`reviewed_by_owner` false), and gate-off logic gives `DISABLED`, publishing nothing.
- The ROS Python dependencies import (no init, no participant).
- **Unit:** `After=` mux and base; `PartOf=atlas-cmd-vel-mux` (a mux stop or restart also stops or restarts the
  teleop; one-way); `Restart=on-failure`; gate `=0`; FastDDS UDPv4.
- **Not enabled:** it will not start at boot. After a reboot the dashboard would show "drive node not running".
- **Endpoints:** 2 subscriptions, 2 publishers (stop, status) plus rosout and parameter events, 6 parameter services:
  about 18. No `/cmd_vel_flysky` publisher while disabled (code path, then checked behaviourally).
- **Backup and rollback:** the backup records all four files as absent. Rollback stops the unit, removes the four
  files and runs `daemon-reload`. **No other service is restarted** (tested).

### Proposed CPU transient bound for A2: **12 s**
Measured restart transients today and on 28 Oct:

| Restart | DDS endpoints | Last sample over 75 % |
|---|---|---|
| Recovery (3 runs) | 32 | +8.2–8.7 s |
| Base | 80 | +9.3 s |
| Mux, A1 | ≈ 48 | +8.3 s |
| Mux, rollback | ≈ 48 | +8.1 s |

The duration is about 8–9 s regardless of endpoint count, so it is dominated by the per-participant join. A new
18-endpoint participant should be similar or shorter. 12 s leaves ≥ 2.7 s over the worst measured case. The teleop's
first start is itself unmeasured, so this is an inference from those measurements.

### GO / NO-GO for ONE A2 attempt
**GO only if all of these hold in one gated pre-check immediately before launch** (as for A1 attempt 2):
1. E-STOP latched: policy fresh (≤ 1.0 s), `stop_latched` true, source STOPPED.
2. Xbox connected and selected: `/joy` ≤ 0.5 s old; `manual_controller` XBOX; `flysky_drive_enabled` false.
3. Commands and motor output zero.
4. Transmitter off: receiver FAILSAFE (flag set), LOST or NO_FRAMES; never LIVE or FRAME_LOST.
5. Gate off: nothing in `hardware.env`, the mux unit environment or a `flysky-drive.env`.
6. A1 intact: live mux `5d096638`, active, NRestarts 0.
7. The four destinations absent; no other stage unit running.
8. Wheels still: encoders unchanged across the pre-check (≥ 16 s), and the owner confirms lifted, clear and hands
   off.
9. Observer healthy: all signals OK; policy age p99 ≤ 0.2 s; verdict gap ≤ 1.0 s.
10. Resources: deployer preflight (30 s) and pre-window all ≤ 75 % CPU, ≤ 80 % RAM, < 70 °C.

**PASS criteria** (deployer, unchanged limits):
- one start;
- CPU over 75 % only within 12 s, then 30 samples ≤ 75, steady mean ≤ pre-window + 4;
- RAM and temperature strict on every sample;
- observer continuously OK with **no exemptions**, gap ≤ 1.0 s;
- unit active, journal shows `FlySky teleop DISABLED`, no traceback;
- 0 messages on `/cmd_vel_flysky` over 3 s; `drive_status` received with state `DISABLED`;
- policy unchanged (latched, XBOX, gate false, STOPPED);
- mux 442503, dashboard 2103, base 1953 and the other protected PIDs unchanged;
- dashboard safety ×3.

**On failure:**
- A safety or verification failure means automatic rollback (stop, remove, daemon-reload; no other restart).
- A CPU, RAM or temperature overrun with safety intact means `FAIL_HELD`: the disabled node stays running and the owner
  decides. Its rollback restarts nothing.
- No retry.

## Stage A2, 2026-10-29 11:09 IST: PASS

Package `6c54ddd`; bound 12 s. A gated GO check of conditions 1–8 passed in one pass immediately before launch: receiver
FAILSAFE/LOST, `/joy` 0.0 s, encoders still. Evidence: `~/project-atlas-migration/stage29-deploy-teleop-20261029_110913-377995741/`.

- **Installed:** drive core `567f0433`, teleop `feecba2c`, config `031c9c08` (`reviewed_by_owner` false), unit
  `eca2270f`. The backup recorded all four as absent. Unit `atlas-flysky-teleop` is active, PID 461352, NRestarts 0,
  **disabled**: it will not start at boot.
- **CPU:** peak 100.0 % at +2.1 s. Over 75 % for 8 samples, +1.1 to +8.2 s, inside the 12 s bound. 30 post-bound
  samples all ≤ 75; steady mean 64.4 % vs pre-window 62.5 % (+1.9 points: the new node's steady load).
  RAM max 70.2 %, temperature max 63.2 °C.
- **Observer:** 169 verdicts in the window, 0 not OK, no exemptions, max gap 0.26 s.

  | Signal | max age in the window |
  |---|---|
  | Policy | 0.442 s |
  | `/cmd_vel` | 0.568 s |
  | `/motor_speed` | **0.850 s** (steady 0.60 s; the 1.8 Hz topic delayed by the spike) |
  | Encoder health | 0.442 s |
- **Behavioural verification:** `/cmd_vel_flysky` advertised (the mux's subscription), **0 messages** in 3 s;
  `drive_status` 7 messages, state `DISABLED`. The journal shows `FlySky teleop DISABLED: gate off; config not reviewed`.
- **Safety:** E-STOP latched, XBOX, gate false, commands and motor output 0, encoders unchanged. Mux 442503,
  dashboard 2103, base 1953, recovery 1998, EKF 3440 and foxglove 2056 unchanged.

## Stage A3 readiness (read-only, 2026-10-29 11:11 IST; NOT deployed)

**Preflight GO.**
- The web candidates were rebuilt from the live files, and every hash matches: status web `4ab16214`, web_v2
  `4893d1f6`, flysky.css `34d3e404`.
- New destinations absent; `/api/manual_controller` and `/v2/flysky-drive` return 404 today.
- The endpoint module imports on Python 3.10.12.
- Safety OK ×3; CPU mean 63.0 / max 66.3 %; RAM 65.7 %; 63.0 °C. The teleop is publishing the status the new page
  will show.

**Proposed bound: 20 s, explicitly unmeasured.** Six restarts are now measured: recovery ×3, base, mux, teleop. All
ended their over-75 % period between +8.1 and +9.3 s, whether the node had 18 or 80 endpoints, which supports a
duration dominated by the DDS join. The dashboard is different in kind: about 133 endpoints plus a large Python
start-up (the 217 KB module, HTTP server, many subscriptions), and no dashboard restart has ever been measured.
A CPU-only overrun gives `FAIL_HELD`, with no automatic second restart.

**Main A3 risk: a spurious fail-closed abort.**
- `/motor_speed` publishes at only 1.8 Hz. Its freshness margin under the unchanged 1.0 s limit is structural: steady
  0.60 s, and 0.85 s during A2's 7 s spike.
- The dashboard restart is the largest spike, so the observer may see `/motor_speed` exceed 1.0 s. That is a safety
  failure and triggers automatic rollback, which means a second dashboard restart (CPU recorded, not aborted).
- This fails closed. It is not unsafe, but it costs a second spike. The limit stays 1.0 s.
- During the dashboard restart the dashboard E-STOP button is unavailable for about 10–20 s. Xbox B and voice stop
  are unaffected.

**GO/NO-GO for one A3 attempt:** the same ten conditions as A2, with these changes:
- **6:** A1 and A2 intact (mux `5d096638` active; teleop active, `DISABLED`, NRestarts 0).
- **7:** the three new A3 files absent.

**A3 PASS criteria** (unchanged limits):
- CPU over 75 % only within the approved bound, then 30 samples ≤ 75, steady mean ≤ pre-window + 4;
- observer continuously OK with no exemptions;
- `rover-status-web` back with a new PID and no traceback;
- `/api/manual_controller` shows selection supported, XBOX, gate false, FLYSKY not selectable, drive node running and
  `DISABLED`;
- `/v2/flysky-drive` served; FlySky Test Lab API unchanged (read-only);
- dashboard safety ×3; other PIDs unchanged.

## Stage A3 attempt 1, 2026-10-29 11:14 IST: FAIL, rolled back (fail-closed)

Package `6c54ddd`; bound 20 s. A gated GO check of conditions 1–8 passed. Evidence:
`~/project-atlas-migration/stage29-deploy-web-20261029_111404-215965998/`.

What passed:
- **Backup:** six files backed up (3 originals, 3 absent).
- **Install:** candidates installed: status web `983024c3`, web_v2 `252d9261`, css `e5852855`, endpoint
  `a38a6b35`, page `89f017a9` / `b2d0c83f`. `rover-status-web` restarted once.
- **CPU, first measured dashboard restart:** over 75 % at +0.9 s (76.1), then from +6.0 to **+15.3 s**
  (11 samples, peak 99.8 %), inside the 20 s bound. 30 post-bound samples all ≤ 75; steady mean 63.5 % vs
  pre-window 63.9 %. RAM max 66.2 %, temperature max 63.2 °C.
- **Observer, no exemptions:** 201 verdicts, **all OK**, max gap 0.255 s.

  | Signal | max age |
  |---|---|
  | Policy | 0.149 s |
  | `/cmd_vel` | 0.246 s |
  | `/motor_speed` | **0.598 s** (the predicted risk did not occur) |
  | Encoder health | 0.161 s |
- **Functional verification** passed: new PID 464121, policy latched / XBOX / gate false / STOPPED.

What failed:
- The final dashboard safety ×3 failed one predicate, `web_drive_stop`. Its raw value was `{}`: the item was absent.
- **Rollback, automatic:** originals restored (hashes `4ab16214` / `4893d1f6` / `34d3e404`), the three new files
  removed, `rover-status-web` restarted once.
- Rollback CPU over 75 % from +1.0 to +15.2 s (13 samples, peak 99.7 %) and recorded. Dashboard now PID 464587.
- Test Lab page 200 and API read-only. A1 (mux 442503) and A2 (teleop 461352) untouched. E-STOP latched, commands and
  motor output 0, encoders unchanged.

**Root cause (deployer verification defect, not a rover fault).** The dashboard creates `web_drive` only when it
first publishes a drive command (`publish()` sets `STOP` or a speed). `drive_active` starts False. A freshly started
dashboard therefore has **no** item. The original dashboard, restarted by the rollback, showed the same `None` for
over 30 s. The Stage 28 predicate treats absent as a failure, and no earlier step had restarted the dashboard, so
A3 could not pass as written.

**Fix.** After the dashboard restart only, `web_drive` *absent* is accepted and recorded per snapshot ("no dashboard
drive command since start"). A *present* value other than `STOP` still fails. Every other predicate and check is
unchanged. Two tests were added: the fake rover's restarted dashboard has no item (the old code fails it), and a
non-STOP value → rollback.

**Shutdown tracebacks.** Both dashboards (2103 and 464121) logged `Exception in thread atlas-flysky-ros` when
stopped. It is the same pre-existing shutdown-time behaviour of the Test Lab's executor thread in the original and the
patched dashboard. It is not a runtime fault.

**Bound evidence now measured.** The dashboard restart is over 75 % until about +15.3 s (forward) and +15.2 s
(rollback). The 20 s bound held with about 4.7 s of margin, so keep 20 s for a retry.

## Stage A3 attempt 2 (final), 2026-10-29 11:26 IST: PASS. Stage 29 Stage A COMPLETE

Package `fd4e8ba`; bound 20 s. A gated GO check of conditions 1–8 passed. Evidence:
`~/project-atlas-migration/stage29-deploy-web-20261029_112630-341126257/`.

- **CPU:** peak 99.0 %. Over 75 % for 15 samples, +1.0 to **+17.2 s** (attempt 1: +15.3 s), inside the 20 s
  bound with 2.8 s of margin. 30 post-bound samples all ≤ 75; steady mean 63.6 % vs pre-window 63.8 %.
  RAM max 66.7 %, temperature max 63.1 °C.
- **Observer, no exemptions:** 197 verdicts, all OK, max gap 0.258 s.

  | Signal | max age |
  |---|---|
  | Policy | 0.196 s |
  | `/cmd_vel` | 0.255 s |
  | `/motor_speed` | 0.609 s |
  | Encoder health | 0.126 s |
  | Base still | 0.296 s |
- **Dashboard safety ×3:** all predicates true. `web_drive` absent in 3/3 (fresh dashboard), accepted under the
  corrected rule, with every other predicate including zero commands and zero motor output true. The independent
  observer was continuously OK, `cmd_zero` and `motor_output_zero` included, through the window that ended just before.
- **Independent observer after the run (8 s):** 29/29 OK; `/cmd_vel` all zeros; `/motor_speed` 0.0; E-STOP latched.
- **Selection API:** `/api/manual_controller` reports selection supported, XBOX, gate false, latched,
  `can_select {XBOX: false, FLYSKY: false}`; the drive node is running and `DISABLED` ("FlySky driving is disabled on
  this rover"). A POST without the dashboard header returns 403.
- **Pages:** `/v2/flysky-drive` serves "ATLAS · FlySky Driving". `/v2/flysky-testlab`, its scripts, the mapping card
  and `/v2/` all return 200. The Test Lab API is still read-only, on `/atlas/rc/frames`, receiver FAILSAFE (transmitter
  off).

### Deployed state (all with the gate OFF)

| Step | Live file(s) | Service |
|---|---|---|
| A1 | `atlas_cmd_vel_mux.py` 5d096638 | `atlas-cmd-vel-mux` 442503 |
| A2 | teleop feecba2c, core 567f0433, config 031c9c08 (`reviewed_by_owner` false), unit eca2270f | `atlas-flysky-teleop` 461352, disabled at boot |
| A3 | `atlas_status_web.py` 983024c3, web_v2 252d9261, flysky.css e5852855, endpoint a38a6b35, page 89f017a9 / b2d0c83f | `rover-status-web` 471062 |

Base 1953, recovery 1998, EKF 3440 and foxglove 2056 are unchanged. E-STOP latched, XBOX selected, motion zero.
Backups are in each step's evidence `backup/`; rollback is `deploy_stage29.py rollback --step <step> --evidence <dir>`.

### Still not approved / open before any powered test
- E-STOP release.
- Gate on.
- `reviewed_by_owner`.
- Powered tests and Stage B. Before any of these, verify on lifted wheels:
  - every E-STOP path;
  - the mux 0.35 s and base 0.45 s watchdogs;
  - arbitration;
  - FlySky failsafe → latch.
- **No independent motor-power disconnect** (owner decision). The software E-STOP is not power isolation.
- Mux shutdown `RCLError` seen once under CPU saturation: zero-on-shutdown may be lost; the base deadman mitigates.
- The A3 transient is now measured at 15–17 s, so 20 s has only about 3 s of margin for future dashboard restarts.

## Commissioning preparation, 2026-10-29 11:55–12:16 IST (read-only on the rover; nothing enabled)

### Home-page shortcut (deployed, static files only, no restart; commit e9d9a31)
`/v2/` now has a **FlySky Driving** tile that links to `/v2/flysky-drive`, and the labs grid is 2×2 (one column on phones).

| File | Before | After |
|---|---|---|
| index.html | 3e8e55d2 | 80f905a4 |
| home.css | 9f93d704 | cad19a86 |

Backups: `~/atlas_backups/stage29_home_button_20261029/`. The mux, teleop and dashboard PIDs did not change.

### Why FlySky could not be selected (12:09, live `/api/manual_controller`)
`blocked_reason` read "FlySky driving is disabled on this rover". Two causes, both by design:
- the gate is off (`ATLAS_FLYSKY_DRIVE_ENABLED` is not 1);
- `reviewed_by_owner` is false.

The runtime conditions for selection were all met: E-STOP latched, source STOPPED, XBOX selected, receiver live.

### Owner decisions (12:10)
- Accepted the CH2 throttle / CH1 steering layout.
- Kept SwA = arm, SwB = run/stop, SwC = speed.
- Kept the 0.05 m/s and 0.20 rad/s commissioning caps, with no base profile change.
- `reviewed_by_owner` and the gate stay off until the switch positions and final safety behaviour are confirmed.

### Staged on the rover (not applied)
- `~/project-atlas-migration/stage29A_pkg_3807645/` (tar 1ced5709, manifest check OK).
- Candidate config `owner_review/atlas_flysky_drive.review_candidate.json` (2a2d9b7f). Versus live 031c9c08 it changes only `max_linear_mps` 0.15→0.05 and `max_angular_radps` 0.6→0.20, and `reviewed_by_owner` stays false.

### Switch check
- **Static read (5 s):** CH5 = CH6 = CH7 = 240 (SwA OFF, SwB RUN, SwC 33 %), CH1 = CH2 = 1024.
- **Owner-moved 60 s check (12:15, 75 s record, file fcbb8bbd):** 749 frames, no failsafe or lost frames, longest gap 0.125 s, and **no channel changed**. CH5/6/7 stayed 240 and CH1/2 stayed 1024 throughout. E-STOP stayed latched, /cmd_vel 354/354 zero, /motor_speed zero, 0 messages on /cmd_vel_flysky, encoders unchanged.
- **Result: switch positions NOT verified.** Frames were fresh, so either the switches were moved outside the window, or the transmitter's AUX assignment no longer puts SwA–SwC on CH5–CH7. Not resolved; re-check on the Test Lab page first.

### Findings that affect the lifted-wheel test (measured from code and config, not on wheels)
- **SwB and SwC are 3-position on the FS-i6S; SwA and SwD are 2-position** (FS-i6S user manual). The stop logic is still safe: RUN only below 400 (up); middle or down stops and latches.
- **SwC scales the cap.** At 0.05 m/s:
  - SwC up: 0.0165 m/s, inside the base's |vx| ≤ 0.02 zero band. **The wheels can never move.**
  - SwC middle: 0.033 m/s, about 61 PWM.
  - SwC down: 0.05 m/s, about 62 PWM.
  - FLYSKY uses the autonomous profile (60 + 40·|vx|), below the manual 80 PWM breakaway floor. The wheels may not turn on the stand, and if they don't, stop timing cannot be measured. Caps kept by owner decision; revisit only with measured evidence and a separate approval.

## Dual-controller dashboard (12:15 request): implemented and tested offline, NOT deployed

The FlySky Driving page now shows the controller visually. All of this is read-only on the visualisation side.

**Page behaviour**
- **Xbox mode:** an original Xbox 360 layout schematic (not product artwork). Every stick, trigger, bumper, face button, D-pad and the Back/Start/Guide buttons is labelled. Controls highlight live, stick positions move, and each control shows its ATLAS function and state.
- **FlySky mode:** an original FS-i6S schematic. It covers both sticks (CH1–CH4), SwA–SwD (CH5–CH8) with up/middle/down levers, the VrA/VrB knobs (CH9/CH10), the rear Key 1/Key 2 (not on any channel) and the power buttons. Raw channel values, positions and change highlights come from the existing read-only Test Lab API.
- **States:**
  - Active
  - Inactive (other remote selected)
  - Blocked (E-STOP latched or signal lost)
  - Proposed (in the FlySky setup, gate off)
  - Planned (VrA/VrB camera, not implemented)
  - Not used
- **FlySky roles are read from the drive node's reported config, never from the page.** A differing running config raises a visible warning. Nothing proposed is shown as Active unless gate on, reviewed, FLYSKY selected, signal live and E-STOP released.
- **Selection:** SELECT XBOX / SELECT FLYSKY are the existing mux-backed buttons (the only POST, unchanged). The blocked reason is shown next to them, and "Selected" comes only from fresh mux policy. "Show Xbox / Show FlySky" changes only the drawing and is labelled "Preview only" when it differs from the selected remote.
- **Indicators:** selected remote, actual command source, E-STOP, FlySky driving enabled, Xbox and FlySky signal (lost, stale, failsafe, dropped frames, not installed).
- **Layouts:** desktop and tablet use side callouts; on a phone the drawing is cropped and the legend is stacked.

**Verified Xbox assignments.** Read from the rover's own files, whose hashes match the repo:
- teleop_twist_joy.yaml edfea663:
  - LB (4) is the hold-to-drive dead-man;
  - RB (5) is turbo;
  - axis 1 drives at 0.52 / 0.65 m/s;
  - axis 3 steers at 1.20 / 1.60 rad/s.
- atlas_remote_stop.py 1a44fb37:
  - B (1) is REMOTE STOP and latches;
  - LB held 2 s with sticks centred, then released, resets the E-STOP.
- camera_joystick_node.py 6b5ad455: D-pad (axes 6/7) pans and tilts the camera, and Y (3) homes it.
- Not used: A, X, LT, RT, Back, Start, Guide, the stick clicks, left stick left-right and right stick up-down.
- Live `/joy`: 8 axes and 11 buttons, triggers resting at +1.0.

**New files**
- `scripts/atlas_controller_input_web.py`: GET `/api/controller_inputs` only (POST 405). It runs its own lazy read-only node with one `/joy` subscription and no publisher or client, stopped after 60 s idle. The dashboard's existing `joy` item, which feeds the web E-STOP observation, is untouched.
- `web/v2/controller-map.js`, `web/v2/controller-viz.js`: GET only.
- `tools/flysky/drive_sim_server.py`: real backends, simulated inputs.

**Deployment: one dashboard restart, approval required.** New deployer step **`view`**, chained on A3 (its baselines are the A3 candidates):

| File | A3 (live) | view |
|---|---|---|
| atlas_status_web.py | 983024c3 | e0809e70 (+1 import, +1 GET route) |
| flysky-drive.html | 89f017a9 | b5b4f12e |
| flysky-drive.js | b2d0c83f | dd02e0e5 |
| flysky.css | e5852855 | 2fa74556 |
| atlas_controller_input_web.py, controller-map.js, controller-viz.js | (new) | see MANIFEST.json |

- `view` is not required for driving: gate-on checks only mux/teleop/web, and `step_done` treats A3 files replaced by an installed `view` as superseded.
- Rollback restores the exact A3 files.
- Preflight and the view pre-check use the documented fresh-dashboard rule (`web_drive` absent accepted, any non-STOP value fails).

**Tests:** test_controller_dashboard (19), deployer ViewStep (3 new), and all Stage 29 and UI suites.

## Real controller photos (owner request 13:22; replaces the schematics before any deployment)

The approved deployment of 7f196ac was **held and not run**, because the owner asked for real photos first.

**Xbox photo**
- "Xbox-360-Controller-Black.jpg" by Evan-Amos, Wikimedia Commons, **public domain** (attribution not required; credited anyway). The owner chose this one; downloaded with approval.
- The SHA-1 matches the Commons record.
- Cropped and scaled by exactly 0.5 to `web/v2/assets/xbox360-controller-black.webp` (1680×1230, aspect kept).
- It is a three-quarter view, so **LB, RB, LT and RT are not visible**. They are drawn as markers beside the top edge and labelled "top edge", never as invented positions.
- The only free shoulder-button view found is a white controller under CC BY-SA 3.0 (attribution and share-alike). Not downloaded; optional.

**FlySky photo**
- No freely licensed FS-i6S photo exists on Commons, and the manufacturer and retailer photos are copyrighted.
- **The owner supplied his own front photo and confirmed he took and owns it.** Stored as `web/v2/assets/flysky-fs-i6s-front.webp` (1416×1252, native size).
- The FS-i6S manual diagram, also sent by the owner, was used **only as a layout reference**. It showed the earlier hand-drawn FS-i6S layout was **wrong**:
  - the screen is at the bottom;
  - the gimbals are above the screen;
  - VrA and VrB are on the top shoulders behind SwA and SwD;
  - there is one power button in each lower corner.
- That drawing has been **deleted**. If the photo is missing, the page says so, and the controls table still works. The Xbox schematic, whose layout is right, stays as the Xbox fallback.
- VrA and VrB are drawn as markers beside the corners. Key 1 and Key 2 have no rear photo yet.

**Overlays**
- Every overlay is defined in original photo pixels under one transform, so it cannot drift from the photo at any page size.
- Measured: face buttons by colour segmentation, all other controls on a pixel grid.
- Live elements: highlights, stick-deflection vectors, trigger fill, and a three-dot up/middle/down indicator next to each switch (the photo itself cannot move).
- Tests:
  - overlay position relative to the photo constant within 0.5 % at 1440, 1024 and 390 px;
  - rendered aspect equal to the native aspect, so nothing is stretched;
  - missing-photo fallback;
  - live switch indicator;
  - images only from `/v2/assets`, plus the licence record `web/v2/assets/CONTROLLER-IMAGES.txt`.

The `view` step now also installs the two images and the licence record. Nothing outside `/v2/assets` changes for the images: WebP is already served, so `atlas_web_v2.py` is untouched. **A new owner approval is needed for the new commit; the 7f196ac approval does not carry over.**

## Stage 29 `view` deployment, 2026-10-29 14:45 IST: PASS (commit 59956c9, owner-approved, one attempt)

**Before the attempt**
- Fresh read-only preflight GO at 14:43: all four steps rebuild from the live files, gate off, safety OK ×3, CPU mean 62.9 %.
- Owner confirmed: E-STOP latched, rover lifted and clear.

**Deployer** (`systemd-run --user --unit=atlas-stage29-view`, bound 20 s), evidence `stage29-deploy-view-20261029_144517-889315630`:
- Pre-check: safety OK ×3, CPU mean 62.4 %.
- Backup of A3 `atlas_status_web.py` 983024c3; the new files were absent before.
- Installed `atlas_status_web.py` e0809e70, `atlas_controller_input_web.py` d2505ddb, `controller-map.js` 8f1f302b, `controller-viz.js` 545aebf9, both images (556474a3 / 5edbd50c), the licence record, and the page/js/css.
- Restarted `rover-status-web` only (PID 471062 → 563039).
- CPU over 75 % for 11 samples, peak 99.5 %, last at +15.34 s, inside the 20 s bound. All 30 samples after the bound ≤ 75 %, and the steady mean was 63.9 % against 63.7 % before. RAM and temperature OK on every sample.
- Verified: policy latched, XBOX, gate off, STOPPED; `/api/controller_inputs` read-only; page served. Post-check safety OK ×3, encoders unchanged [-444, 1473, -14198, 1401], `web_drive` absent (fresh dashboard).
- **Result: PASS.** Mux 442503 and teleop 461352 unchanged.

**Live checks after the deploy**
- All page files, both images and the licence record are served with the committed hashes. `/v2/`, `/v2/flysky-testlab` and `/v2/testlab` return 200.
- `/api/controller_inputs`: Xbox LIVE at 16–18 Hz, 8 axes and 11 buttons, `layout_ok` true.
- A POST to `/api/controller_inputs` is refused (400 from the dashboard, which never routes a POST to the module).
- `/api/manual_controller`: XBOX, latched, gate off, `can_select` both false, reason "FlySky driving is disabled on this rover"; teleop DISABLED. No traceback in the dashboard journal.

**Rendering**
- The owner's browser pane did not run the page's scripts (approval needed per action), and headless Chromium cannot start on the owner's PC workspace.
- So the **exact deployed files** (hashes checked) were pulled from the rover with **live API snapshots** and rendered in Chromium, at 1440 px and 390 px:
  - both real photos load, at native aspect ratios 1.366 and 1.131;
  - "Xbox connected", "Selected remote: Xbox", E-STOP latched, FlySky driving off;
  - FlySky receiver shown as "receiver failsafe" (the live state at 14:49, transmitter likely off);
  - the Show FlySky preview is labelled "Preview only";
  - SELECT FLYSKY is disabled with the exact mux reason;
  - legend states Active/Blocked/Not used (Xbox) and Proposed/Planned/Not used (FlySky), never Active for FlySky;
  - no horizontal scroll, no console errors, no non-GET request.
- Live-highlight path, with **injected** test input on the deployed code: Xbox presses light LS, RS, D-pad, Y and B; FlySky switch changes light SwA and SwC, and the dots read SwA DOWN, SwB UP, SwC MIDDLE, SwD UP. **Physical button presses on the live page were not observed by Claude.** The owner should open the page and confirm.

**Dashboard load with the page's polling**
- Status-web process: 49.1 % of one core idle, 50.0 % polled. System busy 63.6 % idle, 63.0 % polled. The difference is within noise.

## Live input check and E-STOP release incident, 2026-10-29 15:01–15:30 IST

**15:01 check (300 s):** no input arrived. The FlySky receiver was in FAILSAFE throughout, so the transmitter was off. This also explains the 12:15 "no switch change" result:
- in failsafe the receiver outputs exactly CH5–CH8 = 240 and the sticks at 1024 with no jitter, which is what the 12:15 recording showed;
- the transmitter was probably off then too.

**15:22 check (300 s, file cad948c7, 1496 samples of exactly what the page receives):**
- **FlySky switch positions verified (raw):**
  - SwA (CH5): 240 up, 1807 down.
  - SwB (CH6): 240 up, 1024 middle, 1807 down.
  - SwC (CH7): 240 up, 1024 middle, 1807 down.
  - SwD (CH8): 240 up, 1807 down.
  - These match the config thresholds: arm >1700, off <400, run <400, speed bands.
- CH1–CH4, CH9 and CH10 all swept the full 240–1807 range.
- Link: LIVE 1420 samples. Failsafe during transmitter power-on (0–0.6 s), at 72–80 s, and at power-off (293–300 s).
- Xbox: /joy live, 8 axes and 11 buttons. Received: A, LB (with A), RB, LT, RT. **Not received: B, X, Y, D-pad, sticks.** The mux stop reason stayed "joystick unavailable", proving B never reached the mux in that window.

**15:28 B check (75 s):**
- B reached /joy and the mux, which logged "REMOTE STOP: B pressed". **The Xbox stop path works.**
- Right stick axis 3 and LS were also seen.

**INCIDENT: E-STOP released and the Xbox drove.**
- At about 15:29:32 the mux logged "release LB to reset" then "released by neutral LB hold": **LB held alone for 2 s and released (the designed reset)**, while Claude's B-check instruction asked for B presses and a left-stick push **without repeating the LB warning**.
- With the latch released and Xbox selected, the mux logged "Safety stop: REMOTE released" six times between 15:29:35 and 15:29:42: six Xbox drive commands, each ended by releasing LB or the stick.
- Encoders went from [-444, 1473, -14198, 1401] (14:46) to [17452, -15665, -17394, -16521]: **the wheels turned** (about 17,000 counts on three wheels, about 3,000 on m3).
- At about 15:29:50 Claude **re-latched the stop with the dashboard E-STOP** (POST / action=e_stop: "EMERGENCY STOP LATCHED"; mux reason "voice stop requested"). Afterwards: motor_speed 0, /cmd_vel 0, source STOPPED, XBOX, gate off.
- The owner had confirmed "lifted and clear" at 14:44. Whether it was still lifted at 15:29 is **unconfirmed (asked)**.
- Learned:
  - The Xbox reset is one hand gesture away during any Xbox button test. Every instruction that involves pressing Xbox buttons while latched must repeat "never hold LB alone".
  - Prefer tests that don't need the Xbox.
  - The software E-STOP, mux and base all behaved as designed. The failure was in the test procedure.

## review-config PASS and gate-on attempt 1 FAIL (rolled back), 2026-10-29 15:48–15:52 IST

- **15:34 preflight NO-GO:** E-STOP unlatched again by an LB hold (second accidental release). The Xbox drove 12 short commands (15:31:58–15:32:20); encoders reached [85409, -80279, -36483, -80953]. Claude re-latched it with the dashboard E-STOP. The owner says it was accidental, the rover stayed lifted, and the Xbox was put down. At 15:48 the Xbox was at rest: no button pressed and sticks centred over 50 samples.
- **15:48 preflight GO:** all four steps installed, gate off, safety OK ×3, CPU mean 63.9 %.
- **15:50 review-config: REVIEWED.**
  - `config/atlas_flysky_drive.json` 031c9c08 → 875feb35.
  - Changes: `reviewed_by_owner` false→true, `max_linear_mps` 0.15→0.05, `max_angular_radps` 0.6→0.2.
  - Backup in `stage29-review-config-*/backup`. No restart.
  - It stays in place; it takes effect only when the gate is on.
- **15:50:45 gate-on attempt 1, bound 15 s: FAIL, ROLLED BACK.** Evidence `stage29-gate-on-20261029_155046-033732978`.
  - Pre-checks OK (safety ×3, CPU mean 63.2 %).
  - Drop-ins written, mux restarted at 15:51:27.
  - The deployer logged "mux back on the dashboard after 1.1 s", but the policy it saw had **`flysky_drive_enabled: False`**: it came from the **OLD mux**, which kept publishing for about 1 s after the restart command. A mux started with the gate on reports True.
  - The observer's mux signals were also still OK from the old mux. The exemption cleared at +1.4 s.
  - At +1.46 s the real restart gap appeared (all five mux signals stale/unsafe), and the deployer aborted as designed.
  - The base-owned signals never failed. Encoders were unchanged at [85409, -80279, -36483, -80953], motor_speed 0, /cmd_vel 0.
  - Rollback: drop-ins removed and the mux restarted again; mux 605157, teleop 605159, which logged "DISABLED: gate off".
  - The rollback restart had CPU over 75 % for about 32 samples (two mux restarts about 40 s apart). Reported; recovered to about 65 %.
  - Final state: E-STOP latched (mux startup latch), XBOX, gate off, drive DISABLED.
- **Root cause:** a deployer defect, the same class as A1 attempt 1. "New mux back" was judged by a field (`manual_controller`) that the old and new mux both publish.
- **Fix** (`wait_mux_back(expect=...)`):
  - gate-on must see **`flysky_drive_enabled` True** on the dashboard; the old mux can never show it;
  - then the observer's continuous OK stretch must **start after** that proof and last **1.5 s**, longer than the observer's 1.0 s freshness, so cached old-mux data cannot satisfy it.
  - Test environment mux-back timeout 4→6 s (real: 20 s).
  - New fake-rover scenario `old_mux_lingers_s` reproduces the failure.
- **A second gate-on attempt needs a new owner approval (no automatic retry).**

## gate-on attempt 2 (package 3c5058f, bound 15 s), 2026-10-29 16:23 IST: FAIL, ROLLED BACK (CPU)

**Before the attempt**
- Fresh preflight at 16:20: NO-GO only on "step teleop: already present", because preflight compares the config with the original install. The live config 875feb35 is exactly the owner-approved review-config result, and every other teleop file matches.
- All safety checks passed (gate off, safety OK ×3, CPU mean 62.7 %).
- The owner chose to proceed. Gate-on re-checks this itself, ignoring the config by design.

**The attempt** (evidence `stage29-gate-on-20261029_162300-765004199`)
- Pre-checks OK; mux restarted at 16:23:41.
- **The corrected new-mux check worked:** "new mux proven on the dashboard (flysky_drive_enabled True) after 14.8 s". The restarted mux took 14.8 s to publish.
- CPU stayed at 97–100 % from the restart. At +15.57 s it was 99.3 %, past the 15 s bound, so: "mux-back: IMMEDIATE ABORT: CPU > 75.0 after the 15.0 s bound". No safety-signal failure.
- Rollback: gate removed, mux restarted again (mux 619923, teleop 619924, DISABLED). That restart had **30 samples > 75 %, about 30 s at about 100 %**.

**After**
- E-STOP latched, XBOX, gate off, drive DISABLED.
- Encoders unchanged [85409, -80279, -36483, -80953]; motor 0; /cmd_vel 0.
- No gate drop-ins; CPU back to about 66 %.

**Finding:** mux restart transients now run 15–32 s, against +8.1 and +8.3 s at 10:22–10:37. The cause is not measured. The likely contributor is more DDS participants: the dashboard's lazy FlySky Test Lab and controller-input nodes while a page is open, plus the enabled teleop's command publisher.

**Deployer behaviour to reconsider:** an abort during the mux-back wait rolls back even when the new mux is already proven and only CPU is over, and the rollback restart repeats the spike. The owner's rule is "CPU-only overrun → hold". No automatic retry was made; a new attempt needs owner approval.

## Restart-time investigation and CPU-only HOLD fix (2026-10-29 16:29–17:10 IST, offline and read-only; nothing restarted)

### Restart transients today (deployer CPU streams; 1 Hz whole-machine CPU)

| Restart | Over 75 % until | Notes |
|---|---|---|
| A1 mux (10:22, 10:38) | +5–8 s | before the FlySky teleop existed |
| A2 teleop start (11:09) | +7 s | |
| A3 / view dashboard (11:14, 11:27, 14:45) | +10–12 s | |
| gate-on 1 restart (15:51) | aborted at +1.5 s | |
| gate-on 1 rollback (15:52) | +33 s | |
| gate-on 2 restart (16:23) | still 99 % at +15.6 s | |
| gate-on 2 rollback (16:24) | +31 s | |

Pre-window means were 64–69 % all day.

### Findings (read-only)

1. **46 DDS participants** (processes with RTPS ports; 44 at the Stage 28 measurement). The dashboard's lazy FlySky Test Lab and controller-input nodes share the dashboard's single participant (one set of RTPS ports 7450/7451). They add only a few endpoints, and only while a page is open. **They are not a material contributor.**
2. **Since A2, every mux restart also restarts the FlySky teleop** (`PartOf=atlas-cmd-vel-mux`). Mux stop 16:23:42.25, start 16:23:42.87, teleop start 16:23:42.88: two participants re-announce at once.
3. **Main cause: the on-demand feature manager** (`atlas-feature-on-demand`, PID 2106, `atlas_feature_on_demand.py` 8797d992).
   - By design ("fail-open: unknown means features on") it treats `/atlas/control_policy` older than **policy_stale_s = 5.0 s** as autonomy demand.
   - The restarted mux printed its priority line only at 16:23:47.3, about 4.5 s after start, under 100 % CPU, and the policy was stale beyond 5 s.
   - At 16:23:48 the manager started atlas-vision-lidar-fusion and atlas-ai-annotator (`"demand": {"autonomy": true}`), and atlas-person-sensor-fusion, atlas-experience-store and atlas-agent-team came up at the same moment. That is five extra participants plus a camera-AI warm-up (the annotator alone used 30.9 s CPU).
   - They stopped again at about 16:29:17 (idle_s 300 + min_on 60).
   - The same cascade followed the 15:51:39 rollback restart. It did not happen at the 10:38 mux restart: the policy came back within 5 s and no teleop restarted with it.
   - The added load slows the mux start, which keeps the policy stale: **self-reinforcing**.
   - The rollback restarts (31–33 s) began during the first cascade.
4. The manager's threshold is read only at start, and **stopping the manager runs `restore-all` (starts every managed feature)**. Tuning it is not a quick or free change. Not done; recorded as a follow-up.

### Deployer fix (prepared, tested, not run)

- In the mux-back wait, safety failures, unreliable monitoring and RAM/temperature still abort at once (fail closed). The CPU bound is judged separately: **CPU over the bound HOLDs (CpuOverrun) only if** all of these hold:
  - the new mux is proven on the dashboard;
  - the observer has itself seen every mux-owned signal OK since that proof;
  - the observer has produced verdicts since the restart with no gap over its limit and no failure.

  Otherwise it is **not CPU-only** and rolls back as before (mux unproven, observer silent or unresponsive, any failure). After the wait, the existing post-restart CPU classification already HOLDs on CPU-only.
- Gate-on HOLD: no rollback restart. It keeps recording until CPU recovers, saves a read-only held-state report (policy, gate drop-ins), and leaves the decision to the owner: accept, or `gate-off` (one mux restart).
- **Preflight bug fixed:** `reviewed_config_ok()` accepts the live config only if it is EXACTLY the reviewed candidate + `reviewed_by_owner` true + COMMISSION_CAPS. Any other edit is still NO-GO.
- Regression tests (`GateOnHold`):
  - CPU-only after the proof → HOLD, one restart, gate still on;
  - CPU-only during the wait → HOLD;
  - CPU over the bound before the proof → ROLLED_BACK;
  - base safety failure → ROLLED_BACK;
  - observer frozen → ROLLED_BACK ("safety monitoring not operating reliably");
  - preflight GO with the reviewed config and NO-GO with a tampered one.
- Limits 75 / 80 / 70 and the 15 s bound unchanged.

## Root-cause fix: authorised-restart lease for the on-demand feature manager (2026-10-29 17:32–18:40 IST, offline)

**Goal:** a stale mux status during an AUTHORISED restart must not look like an autonomy request.

**Mechanism** (reuses Stage 28's `atlas_base_maintenance.py` lease format unchanged; live a768626a):
- **Own folder:** a separate tmpfs root `/run/user/<uid>/atlas-mux-maintenance`.
- **Bound to the deployer:** the lease is tied to this boot, the deployer's PID and start time, and a boot-clock deadline (at most 240 s).
- **Deployer side:** it arms the lease around each reviewed mux restart (A1-style mux step, gate-on, gate-off, rollback) and around the feature-manager restart. It always releases it, also on failure.
- **If the deployer dies,** the lease turns INVALID and the feature manager behaves exactly as today.

**Feature manager** (`scripts/atlas_feature_on_demand.py`, live 8797d992 → candidate b0fb5b43; five original lines changed, the rest added):
- **While a VALID lease exists:**
  - a stale or missing `/atlas/control_policy` or `/atlas/mission_status` keeps the last received verdict; nothing received yet means no demand;
  - this is bounded to `mux_restart_grace_s` = 60 s after the input went stale, or after the manager started;
  - `restore-all` is skipped, because the authorised restart brings the manager straight back.
- **No lease, INVALID lease, or grace over:** today's fail-open rules, unchanged. A fresh policy with manual_only false, a fresh mission ≠ READY and every other trigger still start features at once.
- The allowlist, boot grace, min-on, idle timers and replay are unchanged. The unit file and the config are unchanged.

**Deployer** (`deploy_stage29.py`):
- `mux_lease()` context.
- New step **`features`**:
  - replaces the one file (with a backup);
  - restarts `atlas-feature-on-demand` under the lease. The NEW file on disk runs `ExecStopPost restore-all`, which sees the lease and skips;
  - verifies the manager logged its start, started no managed feature, and that all 8 feature states are unchanged;
  - if any feature starts, it rolls back.
- **Rollback cost:** a rollback stops the manager under the lease, restores the old file and starts it. The old code fails open at start, so a rollback starts the features once (documented).
- **gate-on refuses** until `features` is installed.
- `installed()` accepts the config in the install-order check only when it is exactly the reviewed one (found by the new tests).

**Tests**
- `tests/test_feature_on_demand_mux_lease.py` (12):
  - without a lease, stale means autonomy;
  - the lease holds the last verdict, bounded by the grace;
  - a genuine request is never hidden;
  - fresh start under a lease waits, then fails open;
  - a stale mission keeps its last verdict;
  - the lease ending mid-restart returns to fail-open;
  - the Planner starts nothing while held;
  - the real lease file through NONE / ACTIVE / owner gone / corrupt;
  - read caching;
  - restore-all is skipped only under a valid lease.
- The original 15 feature-manager unit tests are unchanged and pass.
- Deployer: `MuxLease` (every restart is leased and released, including the failed gate-on and its rollback; an existing lease refuses gate-on before any change) and `FeaturesStep` (gate-on needs it; a cascade during the restart rolls back).

## `features` step deployment, 2026-10-29 20:16 IST: PASS (package eba4f6d, bound 15 s, owner-approved, one attempt)

- Owner confirmed the rover is lifted and clear; wheel 3's 180-count change (16:23–19:25) was a hand turn.
- Fresh preflight 20:15: GO (teleop accepted with the reviewed config; `features` candidate rebuilds from the live file); CPU mean 62.8 %. All 8 managed features inactive before.
- Evidence `stage29-deploy-features-20261029_201601-346213736`:
  - backup 8797d992; lease armed 20:16:39; installed b0fb5b43; restarted atlas-feature-on-demand only (2106 → 733934).
  - CPU over 75 % for 8 samples: +2.9 s 97.0, +4.2 99.8, +5.3 100, +6.3 99.0, +7.3 98.2, +8.3 95.0, +9.3 90.4, **last +10.28 s 78.2**. All 30 samples after the bound ≤ 75 %. Steady mean 63.3 % against 64.1 % before. RAM/temperature OK.
  - Lease released; post-check safety OK ×3; encoders unchanged [85409, -80279, -36663, -80953].
- **Independent checks**
  - The old process's ExecStopPost logged `restore_all_skipped` (authorised restart lease).
  - The new manager logged `start`, then `inputs_stale_held` and, 2 s later, `inputs_stale_hold_end`: the policy arrived and the lease covered the gap.
  - **All 8 features stayed inactive.**
  - Lease file removed (only lock files remain).
  - Mux 619923, teleop 619924, base 1953 and dashboard 563039 unchanged.
  - Policy: latched, XBOX, gate off, STOPPED.
- Gate-on attempt 3 is **not yet approved**.

## Gate-on attempt 3, 2026-10-29 20:24 IST: PASS (package eba4f6d, bound 15 s, owner-approved, one attempt)

- Fresh preflight 20:23: GO (all five steps installed, teleop with the reviewed config). CPU mean 62.4 %, max 65.5 %.
- Evidence `stage29-gate-on-20261029_202417-771696135`:
  - Pre-checks: safety OK ×3, CPU mean 63.1 %.
  - Lease armed 20:24:55; mux restarted 20:24:58, with the teleop following.
  - **New mux proven: dashboard `flysky_drive_enabled` True at +9.7 s**; observer OK since +12.5 s; exemption cleared at +14.2 s.
  - **CPU over 75 % for 12 samples, peak 100 % (+3.6 to +6.7 s), last +12.72 s at 78.3 %** (inside the 15 s bound). All 30 samples after the bound ≤ 75 %; RAM/temperature OK.
  - Lease released; post-check safety OK ×3; encoders unchanged [85409, -80279, -36663, -80953]. **PASS.**
- **Feature manager:** `inputs_stale_held` → `inputs_stale_hold_end` after 0.9 s. **All 8 features stayed inactive**; no cascade, against 5 services and 15–33 s on attempts 1–2.
- **Final state**
  - Gate drop-ins present for mux and teleop (runtime, cleared by gate-off or a reboot).
  - Mux 738599; teleop 738601, which logged "FlySky teleop ENABLED" and then "NOT_SELECTED: selected controller is XBOX".
  - Policy: latched ("joystick unavailable"), XBOX, gate True, STOPPED.
  - **`can_select` {XBOX: false, FLYSKY: true}**, blocked_reason empty.
  - Drive config reviewed, no errors, limits 0.05 m/s and 0.20 rad/s.
  - motor_speed 0, /cmd_vel 0; base 1953 unchanged.
- **Not done (needs separate approval):** SELECT FLYSKY, E-STOP release, powered lifted-wheel test.

## Night software completion, 2026-10-29 20:30–21:00 IST (no live change, no restart)

- Gate ON and reviewed config 875feb35 left as they were. Not done: E-STOP release, FlySky selection, any command.
- **New, offline:** `tests/test_flysky_morning_sequence_offline.py` (7 tests). It runs tomorrow's sequence through the real drive core, the patched mux and the Xbox RemoteStop with the exact reviewed config (hash proven 875feb35):
  - select, LB reset, arm, forward, reverse and turn;
  - SwC up 0.0165, middle 0.033, down 0.05 m/s, never above the caps;
  - SwB middle latches;
  - after any latch (SwB, Xbox B or dashboard) an LB reset still needs SwA off and on again;
  - LB+A cannot reset;
  - Xbox is selectable again only while latched.
- **New helper:** `tools/deploy/stage29_flysky_drive/stage29_morning.py` (`precheck` / `record` / `analyze`), read-only and enforced by a source test. 5 tests.
- **Bug found by the live read-only dry run and fixed:** one Jetson thermal zone refuses reads, which crashed the precheck. Unreadable zones are now skipped, and an unknown temperature is NO-GO.
- **Live read-only dry runs** (package bc79e75 at `~/project-atlas-migration/stage29A_pkg_bc79e75`):
  - **precheck:** 17 of 19 OK. It is NO-GO only because the FlySky transmitter is off (receiver FAILSAFE) and SwC reads 240, which is the failsafe value. CPU 63.8 %, RAM 65.6 %, 65.5 °C; encoders unchanged; all 8 features inactive.
  - **recorder (10 s):** all topics captured: /joy 171, rc frames 99, policy 100, /cmd_vel 46, encoders 98–100. OVERALL FAIL with no events, as designed.
- Morning checklist: `docs/ATLAS_STAGE29_MORNING_LIFTED_WHEEL_CHECKLIST_20261030.md`.
- **Physically unverified:**
  - wheel directions;
  - real stop and latch times on powered wheels;
  - whether 0.033–0.05 m/s turns the lifted wheels at all (about 61–62 PWM against a manual breakaway of about 80);
  - FlySky failsafe with powered wheels.
- **Residual risks:**
  - no independent motor-power disconnect;
  - the gate is lost on a reboot.

## FlySky SwD (CH8) E-STOP reset, 2026-10-30 (branch agent/stage29-flysky-reset-20261030; NOT deployed)

- **Owner request (09:48):** reset or unlock the E-STOP from the FlySky instead of Xbox LB.
- **Morning incident it follows:** at 09:24 an LB reset released the E-STOP while the Xbox was selected, and the Xbox drove the lifted wheels at 0.52 m/s and 1.2 rad/s (wheel 3 about 25,000 counts). This was the third such event.
- **Choice of control:** SwD (CH8) is unused, verified at 240 / 1807; a receiver failsafe of 1024 is neither position. The FS-i6S rear keys are not sent on any channel (CH11–16 constant).
- **Xbox stays required:** while the Xbox is off, the mux re-latches every 50 ms, so the Xbox remains the independent stop device. Driving without the Xbox would remove a protection and was not done.

**Gesture** (scripts/atlas_flysky_reset.py, teleop side). All conditions must hold for the whole gesture:
- FlySky selected and E-STOP latched;
- receiver LIVE, with no failsafe or frame-lost, for at least 3 s;
- SwA up, SwB up, right stick centred;
- then: SwD up for at least 1 s, SwD down for 2–5 s, SwD up. The teleop sends one request.

**Mux side** (independent; insert_flysky_reset_mux.py, additive over the deployed mux 5d096638). It releases only if:
- the reset gate is on, the drive gate is on and FlySky is selected;
- the E-STOP has been latched for at least 2 s;
- the Xbox is fresh and untouched for at least 1 s;
- the rover is commanded zero and the encoders are fresh, READY and still for at least 1 s;
- the request is fresh (0.3 s or less), carries a new sequence number, and no other request came in the last 3 s.

A release flushes every channel. The drive core is unchanged, so motion still needs SwA up then down (a fresh arm).

**Offline results**
- 29 fault-injection tests, with 17 of 17 deliberately broken checks caught.
- Every stop still latches after a FlySky reset (1.3 s or less), and the Xbox LB reset still works.
- Dashboard reset card checked in every state in a browser.

**Deploy step `reset`** (deploy_stage29.py; MANIFEST step 'reset'). The earlier steps are pinned to the files verified on the rover on 2026-10-30, so their hashes are unchanged.
- **Requires:**
  - all five Stage A steps installed and the gate ON;
  - exactly the reviewed config 875feb35, with CH8 free;
  - E-STOP latched and Xbox selected;
  - safety ×3 and the resource preflight.
- **Change:** installs 7 files, writes the runtime drop-in 91-atlas-flysky-reset.conf (mux and teleop), and runs ONE leased mux restart (the teleop follows).
- **Proof that the new mux is running:** policy flysky_reset.enabled True, with 1.5 s of observer OK after that.
- **Verification:**
  - mux and teleop PIDs changed, teleop ENABLED;
  - 0 messages on /cmd_vel_flysky and 0 reset requests;
  - teleop status NOT_SELECTED, with reset UNAVAILABLE;
  - the page serves the reset card;
  - safety ×3.
- **Failure handling:** a CPU-only overrun HOLDs; any safety or verification failure rolls back (files restored, drop-ins removed, one leased restart).
- **gate-off** also removes the reset drop-ins. After a reboot, gate-on and then `deploy --step reset` re-enables without copying files.
- **Deploy tests:** 28 pass. They cover the PASS path, refusals with no change, rollback (teleop not enabled, new mux unproven, base signal failure, unexpected requests or commands), CPU HOLD followed by the owner's rollback, rollback after a PASS, gate-off, the reboot re-enable, and source checks.

### Reset deploy attempt 1, 2026-10-30 11:09 IST: FAIL_ROLLED_BACK (package ed2b55e, bound 15 s, owner-approved, one attempt)

- **Preflight**
  - 11:08:10 NO-GO: FlySky still selected.
  - The owner pressed SELECT XBOX at 11:08:23.
  - 11:09:31 GO: CPU mean 62.7 %, max 65.1 %.
- **Window**
  - Lease armed; 7 files installed; reset drop-ins written; mux restarted at 11:10:24.
  - **New mux proven on the dashboard (policy flysky_reset.enabled True) at +10.2 s.**
  - **CPU over 75 % from +2.2 to +16.4 s**: peak 100 % (+4.2 to +8.2 s), 83 % at +15.7 s and +16.4 s, then 64.6 % at +17.4 s.
- **Why it rolled back:** at +15.7 s, after the 15 s bound, the observer had not yet itself confirmed the mux-owned signals for the required 1.5 s after the dashboard proof. By the documented rule this is not a CPU-only case, so the deployer failed closed and rolled back instead of holding. The observer reported no failure at any time during the window.
- **Rollback**
  - Files restored to 5d096638 / feecba2c / b5b4f12e / dd02e0e5 / 8f1f302b / 545aebf9, and atlas_flysky_reset.py removed.
  - Reset drop-ins removed; one leased mux restart.
  - Rollback CPU over 75 % until +15.1 s (peak 100 %), then a steady mean of about 62.5 %.
- **State after the rollback (verified)**
  - Gate drop-ins still present (gate ON).
  - E-STOP latched, XBOX selected, source STOPPED.
  - Teleop NOT_SELECTED, can_select FLYSKY true.
  - motor 0, /cmd_vel 0, encoders unchanged [81195, -74122, -62144, -74805].
  - AI/fusion features inactive; base PID 1953 and dashboard PID 563039 unchanged.
  - New mux PID 1163521, teleop PID 1163523.
- **Finding:** the two mux restarts today stayed over 75 % until +16.4 s and +15.1 s. Gate-on attempt 3 on 10-29 ended at +12.7 s. A 15 s bound has no margin at the current 63–65 % baseline. No automatic retry was made. Another attempt needs an owner decision (for example a 20 s bound).
