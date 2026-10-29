# Stage 28: paused state and how to resume (saved 2026-10-28 00:42 IST)

Stage 28 is **not complete**. CH5–CH10 have not been assigned and verified on the transmitter yet. Everything else is
deployed and working. The owner paused for two days.

## State left on the rover (read-only check at 00:41:42)

- **Safety:** E-STOP latched; source STOPPED; manual-only. Encoders unchanged at `[-37, 76, -221, 31]` since 00:04.
- **RC link:** `/atlas/rc/frames` LIVE at 10 Hz, 1 publisher.
- **Services:**
  - base `rover-base-telemetry` PID 151784;
  - recovery `atlas-sensor-recovery` PID 150794.
- **Temporary units:** the evidence loggers (`atlas-stage28-*`) were stopped; none are running.
- **Actuators:** the motors and steering servos were still connected when the session ended; the rover is lifted. Lifting is not isolation.

## What is deployed

| Item | Commit | Live files (SHA-256 prefix) | Backups |
|---|---|---|---|
| RC bridge + recovery coordination (Stage A/B) | `8c34db1` | `atlas_sensor_recovery.py` 5f44cc1f, `atlas_base_maintenance.py`, `atlas_yahboom_rc_report.py` f5165a58, `atlas_rc_readonly_bridge.py` c717ca1b, `Rosmaster_Lib.py` 15391e14, `yahboom_base.py` bb6db3a1 | `~/project-atlas-migration/stage28-recovery-coordination-20261028_000602-745387360/backup`, `…/stage28-rc-bridge-20261028_000743-183372265/backup` |
| Test Lab channel-mapping card | `615b846` | `web/v2/flysky-mapping.js` 71766cb0, `flysky-testlab.html` f1bf848b, `flysky-testlab.js` 18f9b687, `flysky.css` 34d3e404 | `~/project-atlas-migration/stage28-testlab-mapping-20261028_004009/backup` |

**Rolling back the Test Lab card.** These are static files, read on each request, so no restart is needed:
1. Copy the three backed-up files over `~/project_atlas/web/v2/`.
2. Delete `flysky-mapping.js`.

**Rolling back the RC bridge.** This needs a base restart, so it needs owner approval and a CPU-transient bound first. Use the backups listed above.

Evidence archive: `Downloads/atlas_deploy/stage28_flysky_evidence_20261028_final.tgz` (SHA-256 `55a36b9c53c30324…`). It holds:
- the Stage A/B deployer logs;
- the Test Lab state log;
- the signal-loss recordings;
- the Test Lab file backups.

## Verified so far (details: `docs/ATLAS_STAGE28_FLYSKY_LIVE_RESULT_20261028.md`)

- **SBUS link:** LIVE; 0 invalid frames; frame age ≤ 0.17 s.
- **Firmware drive bit:** `DRIVE_DISABLED` present on every 0xE1 report, 0 rejected.
- **Signal loss:** LIVE → FRAME_LOST → FAILSAFE (+0.43 s) → LIVE again after power-on.
- **CH1–CH4:** each swept the full range (240–1807). The stick-to-channel mapping and directions are *not yet confirmed* stick by stick.
- **CH5–CH16:** constant 1024. The board forwards all 16 channels, so the transmitter is sending centre.
- **Xbox:** pad present; `/joy` live at 17 Hz while idle. The drive path was not tested, because that needs an E-STOP reset.

## Resume steps (about 10 minutes, no rover software change)

1. Read-only preflight:
   - E-STOP latched;
   - `/api/flysky/state` LIVE;
   - base and recovery PIDs as above.

   If a PID changed (for example after a reboot), re-verify the live file hashes above before anything else.
2. Start a read-only logger, as on 2026-10-28. The script is `~/project-atlas-migration/stage28-flysky-live-20261028/rc_log.py`, run with `systemd-run --user --collect`.
3. On the FS-i6S, open the tools icon, then **Function**, then **Aux. channels**, and set:
   - CH5 → SwA
   - CH6 → SwB
   - CH7 → SwC
   - CH8 → SwD
   - CH9 → VrA
   - CH10 → VrB

   If CH5 is locked to fly mode, record which channels can be set.
4. In the Test Lab, tap **Defaults**, then **Apply** in *Channel mapping*.
5. Move each control in turn, about 2 s apart:
   - each stick axis to both extremes;
   - each switch through all of its positions;
   - each knob fully both ways.
6. From the log, confirm:
   - every row is Verified;
   - CH1–CH4 directions;
   - switches have 2–3 levels;
   - nothing is "Unassigned, but it changed".
7. Then Stage 28 can be closed.

## Findings to carry forward

- The FS-i6S output is bit-identical at rest: CH1–CH4 sat at exactly 1024 for minutes with zero jitter. The offline `FrozenDetector` in `atlas_flysky_mapping.py` assumes "a real transmitter always has a few counts of jitter". That premise is false for this radio, so it must not be used as a signal-loss detector. The SBUS frame-lost and failsafe flags are the reliable signal, and they were verified live.
- The receiver's failsafe output is currently centre (1024) on every channel. Before any future FlySky-driving stage (not approved), set explicit failsafe values on the transmitter.
- An owner confirmation conflicted with reality: at 00:05 "isolated", at 00:13 "still connected". Ask for actuator isolation as a fresh, specific confirmation immediately before any step that could command an actuator.

**Resolved 2026-10-29:** CH5–CH10 assigned and verified; Stage 28 complete. See `docs/ATLAS_STAGE28_FLYSKY_LIVE_RESULT_20261028.md` (section "Channel verification, 2026-10-29").
