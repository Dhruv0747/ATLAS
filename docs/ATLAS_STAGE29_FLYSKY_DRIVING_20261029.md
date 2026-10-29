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
   Steering is CH4 (left stick left–right), stick right = turn right.
   This is the mirror of the Xbox layout (left = throttle, right = steering).
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
