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
