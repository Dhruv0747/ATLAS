# Stage 28: FlySky RC bridge deployed and live result, 2026-10-28

Package: GitHub `8c34db1` (archive SHA-256 `5eedff5e5a015291…`), rebuilt on the Jetson from the live baselines. All hashes matched.

## Deployment (owner-approved, one attempt each, no retries)

The owner approved, at 00:05:
- Stage A with `--cpu-rule transient --transient-bound-s 10`;
- then Stage B with `--transient-bound-s 15`.

| Stage | Window | Result | CPU transient (samples > 75 %) | Notes |
|---|---|---|---|---|
| Preflight | 00:04:30–00:05:05 | GO | none: mean 65.4, max 68.4 | RAM 62.9 %, 64.1 °C |
| A: recovery honours lease | 00:06:02–00:07:30 | PASS | +1.97 s to +8.16 s, peak 100.0 | 30 post-bound samples ≤ 75; observer OK; base untouched |
| B: base + RC bridge | 00:07:43–00:09:28 | PASS | +1.18 s to +9.26 s, peak 100.0 | base PID 1921 → 151784; 1 authorised start; lease released |

Installed files:

| File | SHA-256 prefix |
|---|---|
| `atlas_base_maintenance.py` | — |
| `atlas_sensor_recovery.py` | 5f44cc1f |
| `atlas_yahboom_rc_report.py` | f5165a58 |
| `atlas_rc_readonly_bridge.py` | c717ca1b |
| `Rosmaster_Lib.py` | 15391e14 |
| `yahboom_base.py` | bb6db3a1 |

Backups are in the evidence folders `stage28-recovery-coordination-20261028_000602-745387360` and `stage28-rc-bridge-20261028_000743-183372265`.
`atlas_flysky_core.py` and the firmware are unchanged.

**Owner-confirmation discrepancy.** At 00:05 the owner answered "all isolated, TX OFF". At 00:13 the owner reported that the motors and steering servos were still connected, with the rover lifted. The transmitter was then switched on with the actuators connected. No motion was observed at any point:
- encoders stayed at `[-37, 76, -221, 31]` from 00:04 through 00:26, including full-range stick sweeps;
- `motor_output_zero` and `cmd_zero` held throughout.

## Live results

| Check | Result | Evidence |
|---|---|---|
| `/atlas/rc/frames` | PASS | 1 publisher, 10.0 Hz (by design: firmware report 25 Hz, forwarder cap 20 Hz, base timer 10 Hz) |
| Frame integrity | PASS | sbus valid 5 989+, invalid 0, incomplete 0, garbage 0, resyncs 0; bad source messages 0 |
| Freshness | PASS | frame age max 0.166 s while LIVE (live limit 0.5 s) |
| SBUS drive compiled out | PASS (live) | every accepted 0xE1 report carries status bit4 `DRIVE_DISABLED`; 0 rejections in the base journal |
| CH1–CH4 | PASS | each swept 240–1807 |
| CH5–CH10 (and 11–16) | **FAIL / not demonstrated** | constant 1024 (SBUS centre) for the entire session. The 0xE1 report forwards all 23 raw SBUS data bytes, so the receiver is sending centre. Most likely cause: AUX channels unassigned on the FS-i6S (not proven) |
| Signal loss | PASS | see the timeline below |
| E-STOP / arbitration | PASS | latched throughout; `manual_only`, source STOPPED, commissioning off |
| Xbox controller | PRESENT, drive path not tested | `/dev/input/js0` "D_TGZ Controller" (X-Box 360 pad) held by `joy_node` (PID 2374); `/joy` 17.1 Hz, idle; stop reason "REMOTE STOP: joystick unavailable" is the stored reason from when the latch was set. Driving from Xbox needs an E-STOP reset: not done |

Signal-loss timeline (transmitter switched off, then on):
- 00:24:08.775: LIVE → FRAME_LOST; frames keep arriving with the frame-lost flag set.
- 00:24:09.202: FAILSAFE, +0.43 s; the receiver outputs failsafe values of 1024 on all channels.
- 00:25:59.698: back to LIVE; both flags clear; counters kept (1110 frame-lost / 1105 failsafe).

E-STOP stayed latched and the encoders were unchanged throughout. The earlier "no change" windows (00:17–00:23) were with the transmitter on and untouched; FlySky values are exactly 1024 at rest with no jitter.

## Stage 28 completion criteria

| Criterion | Status |
|---|---|
| Real CH1–CH10 reception | **Partial**: CH1–CH4 live; CH5–CH10 not demonstrated |
| Test Lab verification | PASS for link, flags, CH1–CH4 |
| Failsafe testing | PASS |
| E-STOP and existing controls protected | PASS |
| FlySky driving disabled | PASS (firmware bit verified live; no motion during stick sweeps) |

## Remaining

1. Assign CH5–CH10 to SwA–SwD and VrA/VrB in the FS-i6S Aux-channels menu. Flip each one and confirm the change in the Test Lab. This is a transmitter setting; no rover change.
2. Confirm the physical stick → channel mapping. The assumed mode-2 mapping is not confirmed: CH1 right X, CH2 right Y, CH3 left Y (throttle), CH4 left X.
3. Before any future FlySky-driving stage (not approved), set safe failsafe values on the transmitter. Currently every channel, including throttle, falls back to centre.
4. Xbox driving after an E-STOP reset is untested.

Raw logs are kept on the Jetson and in the owner's `Downloads/atlas_deploy/stage28_flysky_evidence_20261028.tgz` (SHA-256 `ac25284243f966a7…`). They are not committed, per AGENTS.md.
