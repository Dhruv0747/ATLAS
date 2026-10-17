# ATLAS FlySky full integration and Xbox cutover: status report

Branch `agent/sync-developer-20261011`. Date 2026-10-17. Builds on `ATLAS_FLYSKY_SBUS_TEST_LAB.md`.

## Status ladder (honest)
| Stage | State |
|---|---|
| BUILT | Test Lab page and service, receiver bridge (proposal), channel mapping model, dual-remote arbiter model, deploy/rollback package |
| TESTED OFFLINE | Yes: 117 FlySky, mapping, failsafe-matrix, arbiter, package and Test Lab tests pass |
| INSTALLED | **Read-only Test Lab page only** (20:11 IST). Bridge, adapter and arbiter are NOT installed |
| LIVE SBUS VERIFIED | **No.** No real receiver frame has been seen anywhere |
| FLYSKY DRIVING VALIDATED | **No.** Not implemented for activation, never tested physically |
| XBOX RETIRED | **No.** Xbox untouched and still the only drive source |

## 1. Verified STM32 SBUS capability
Verified read-only:
- Board firmware reported by the base driver: **3.6**, car type 5 (journal, `Yahboom board ready ... firmware=3.6, car_type=5`).
- Installed `Rosmaster_Lib.py` (V3.3.1) defines report types speed 0x0A, MPU raw 0x0B, IMU 0x0C, encoder 0x0D, ICM raw 0x0E. **No RC/SBUS type exists, and unknown types are silently ignored.**
- Yahboom's public repo and docs say the board "supports SBUS", with no serial function id or channel report documented in anything I could read. Its firmware folder `1.Expansion board STM32 driver/` was not readable by me without a URL approval, so I could not check the firmware source.

Not verified, and cannot be verified without risk:
- Exact board revision and silkscreen (needs a photo of the board).
- Whether valid SBUS frames reach the STM32, and whether firmware 3.6 decodes them. Only the STM32 debug UART (USART1, micro-USB) or a logic analyzer on the SBUS pin can show this. Opening the base serial port to probe would compete with `rover-base-telemetry`, so I did not.
- SBUS pin voltage and inversion: vendor page states neither.

**Conclusion:** with the current protocol and library, the Jetson cannot receive FlySky channels from the STM32. Whether firmware 3.6 emits an undocumented RC report is unknown.

## 2. Chosen data path and rationale (recommendation, needs your approval)
| | A. STM32 firmware forwards RC | B. Dedicated read-only adapter on Jetson |
|---|---|---|
| Firmware change | Yes: backup, flash, and a new report type in the library | None |
| Risk to motor/safety behavior | Touches the board that runs motors and the encoder/PID loop | None; separate port, separate process |
| Latency | Shares the 115200 link | Own link |
| Needs | Firmware source, toolchain, flashing access, rollback image | Receiver iBUS or inverted-SBUS output, adapter with unique serial, 3 wires |
| Reversible | Only if the original firmware image can be read back | Unplug |

**Recommend B.** Preferred wiring: FS-iA10B iBUS output to a dedicated USB-serial adapter RX (+GND). Normal polarity, no inverter. Your three CH340 adapters have no serial numbers and their ttyUSB numbers swap on reboot, so use a different adapter (for example CP2102 with a unique serial) or a udev rule by physical USB port. Confirm 3.3 V vs 5 V logic before connecting. The existing SBUS-to-STM32 wire can stay as is. Receiver failsafe/frame-lost flags are not available over iBUS; SBUS carries them but needs an inverter. Link loss then rests on frame staleness plus a frozen-output detector.
Bridge: `scripts/atlas_rc_readonly_bridge.py` (BUILT, TESTED OFFLINE, NOT INSTALLED).

## 3. Actual live receiver values
None. No frame has been observed.

## 4. Channel mapping
None recorded. `scripts/atlas_flysky_mapping.py` (BUILT, TESTED OFFLINE) defines the reviewed-mapping file: throttle, steering, estop required; measured min/centre/max, deadband, reversal applied in software only (never motor polarity); refuses an unreviewed, incomplete, duplicate or out-of-range mapping; no default channel assignment exists.

## 5. Integration architecture (design; only the first box is installed)
`FS-i6S -> FS-iA10B -> [read-only bridge, own adapter] -> /atlas/rc/frames -> Test Lab page (INSTALLED)`
Later, each step needing separate approval: `-> mapped adapter (arming, neutral sticks, deadman, fresh data) -> existing command mux limits -> existing steering/4WS path`. The adapter would never write motor or raw commands, and E-STOP and the mux stay in charge. Arbitration rules R1 to R7 are in `atlas_remote_arbiter_model.py` (FlySky drive disabled by constant).

## 6. Safety/failsafe implementation
Fail-closed logic is modeled and tested offline, not live. Covered: transmitter off, receiver disconnected, stale frames, unverified link / bridge crash / USB unplug (all end as no verified fresh frame), loss latching with no automatic rearm, E-STOP from any source or dashboard, no automatic transfer to Xbox, simultaneous Xbox reported as conflict and dropped, invalid or impossible channel values fail to neutral, frozen receiver output detector.
Not yet covered: explicit SBUS failsafe/frame-lost on live hardware, sudden switch movement handling in a real adapter, motor-board connection failure path. A transmitter switch is never a substitute for the physical motor-power cutoff.

## 7. CPU and latency
Offline (container): 0.025 ms per frame decode, 0.37 ms per page snapshot, 0.26 MB session memory. Live after install: `rover-status-web` was ~32% of one core in the first minute (restart transient; the pre-existing level is ~41 to 45%), 25 threads. Load average on the Jetson was 12 to 34 (6 cores, ~35% idle) before and after, so it is pre-existing. Control latency under Jetson load is **unmeasured**, because there is no frame source and no drive path.

## 8. Offline regression
117 passed across FlySky core/web/static/overhead/render/bridge, arbiter, mapping and failsafe matrix, package and Test Lab static (`evidence/stage27_flysky/test_output.txt`). Full repo suite earlier: 812 passed, 2 pre-existing unrelated failures.

## 9. Deployment and rollback
Installed 2026-10-17 20:11 IST via `tools/deploy/stage27_flysky/apply.sh` from commit 4159f07 (archive sha256 `2c581fc4...`). Backup `~/project_atlas/.pre_stage27_flysky_20261017_201114`. Rollback: `tools/deploy/stage27_flysky/rollback.sh` (restores 3 files, removes 5 new, restarts only `rover-status-web`).
Live hashes now: `atlas_status_web.py` fdd39477a19ee5ec, `atlas_web_v2.py` fa32d4574c82a21e, `index.html` 50c0040bad62ec3b. The apply script printed a false "page check failed (000)" because the service needed more than its 4 s wait on this loaded Jetson; every later check returned 200. (Fix: lengthen the wait in a later commit.)
Verified live: `/v2/flysky-testlab` 200, `/api/flysky/state` 200 with **SIGNAL NOT VERIFIED**, `NO_SOURCE`, 0 publishers, RSSI not available, Home link present, E-STOP still latched (reason "REMOTE STOP: joystick unavailable"), manual_only true, `/cmd_vel` zero, base driver and Test Lab untouched.

## 10. Physical-test results
None performed. Tests 1 to 4 are prepared as a procedure below, not run.

## 11. Xbox migration readiness
Not ready. None of the retirement conditions is met. Xbox stays the only drive source; nothing was disabled.

## 12. Commits and pending approvals
Commits: 4159f07 (Stage 27 offline build), plus the commit containing this report.
Pending, each needs your explicit approval:
1. Receiver input choice and rewiring (Option B hardware, voltage/inversion confirmation).
2. Reading the Yahboom firmware repo folder (URL approval) or sharing the firmware source, if you want Option A evaluated.
3. Enabling the read-only bridge service.
4. STM32 firmware change of any kind.
5. Implementing and installing the mapped FlySky adapter (needs verified mapping first).
6. Lifted-wheel test, ground test.
7. Xbox cutover.
Still open from before: physical E-STOP tests, Jetson password rotation, temporary key removal, wheel 2/3/4 encoder crosstalk.

## Supervised test procedure (prepared, not run)
1. Read-only: with a receiver input installed, move each stick and switch; confirm the Test Lab shows each channel and nothing moves.
2. Signal loss: switch the transmitter off; confirm STALE then LOST (and failsafe flag if SBUS); motors disabled throughout.
3. Lifted wheels, owner present, physical power cutoff within reach, low scaling: forward/reverse, steering, STOP, loss-of-link.
4. Low-speed ground test only after 3 passes and the encoder issue is addressed.
