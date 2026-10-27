# Stage 28 — base-maintenance coordination and RC-bridge deployment package (offline), 2026-10-27

Status: **prepared and simulation-tested offline. NOT deployed.** No production file was changed, no service was
restarted, no ROS participant was started on the Jetson. Read-only diagnostics only (SSH, `systemctl show/cat`,
`journalctl`, `/proc`, dashboard GET APIs).

## 1. Findings that change the plan

| # | Finding | Evidence |
|---|---|---|
| F1 | The 0ce6dd1 manifest's three "helper candidates" are the git files with **CRLF line endings** (Windows checkout). Content is identical to git. | LF→CRLF of git files reproduces exactly `ef1c6eb1…`, `13f8f516…`, `f8196bf9…` |
| F2 | **`atlas_flysky_core.py` must not be replaced.** Live `3e4b379e…` == git LF. The "replacement" would only swap line endings of a working shared file used by the Test Lab. It is now a *must-remain* hash; a changed file is refused, never replaced. | live sha256 vs git blob `a043b96f` |
| F3 | The two modified files rebuild **exactly** from the live baselines with the reviewed insert scripts: `yahboom_base.py` `bb6db3a1…` (+34 lines, 0 removed), `Rosmaster_Lib.py` `15391e14…` (+18, 0 removed). `harden_yahboom_port.py` is not part of the reviewed candidate and is not deployed. | rebuild against live copies |
| F4 | The race is real but **narrower than first reported**. Only one monitor can restart the base (`encoder_health`, 1 attempt / 600 s). During *activating* (board init, before READY) recovery defers to systemd, and that deferral spends the attempt. The competing restart happens when the base is **deactivating** for >2 s (TimeoutStopSec=5 allows it): `restart_pending()` does not treat `deactivating` as a restart, so recovery issues its own `systemctl restart`. | sim s00 (slow stop → `RECOVERING … restarting rover-base-telemetry`), s00b (10 s init → `RECOVERY DEFERRED`, no competition) |
| F5 | The 80 % CPU reading was **`top -bn1`'s first frame**, which is not a valid interval sample. 60 × 1-s `/proc/stat` samples: min 64, median 67, p90 68, max 70 %, 5-s rolling max 67.8 %, 0 samples > 75 %. `top -bn2 -d1`: 69 % then 65 %. Since-boot average 72 % (boot storm, 13 min uptime). | read-only sampling 18:59 IST |
| F6 | The real CPU blocker is the **restart transient**: d1d13a3 rolled back on a first post-restart sample of 98.8 % after restarting only the recovery service. A strict "every 1-s sample ≤ 75 %" rule cannot pass *any* Python ROS node restart at the current 67 % baseline. | `ATLAS_STAGE28_D1D13A3_RESOURCE_ROLLBACK_20261027.md`; sim s02 |
| F7 | `rover-base-telemetry` is `Type=notify`, `WatchdogSec=5`, `Restart=on-failure`: **systemd is a second restarter**, and the watchdog is armed during startup (a >5 s init is killed). | unit file; sim (8 s init was watchdog-killed) |
| F8 | `atlas-tight-recovery` does not restart services. Only `atlas_sensor_recovery.py` issues base restarts in the scripts directory. | grep of live scripts |
| F9 | Stale `__pycache__/atlas_b1_interlock.cpython-310.pyc` remains from the rolled-back attempt (source absent; Python does not import a sourceless `__pycache__` file). Harmless; left untouched. | `find` |
| F10 | Xbox controller: E-STOP reason "REMOTE STOP: joystick unavailable". Xbox coexistence cannot be tested until it is paired. | `/api/estop/state` |
| F11 | Python 3.10 on the Jetson raises `TypeError` (not `OSError`) when reading the unavailable CV thermal zones. Found by the live read-only preflight; fixed (`read_zone`, raw non-blocking read, any failure = not applicable) and regression-tested. | live preflight 19:48 |
| F12 | Encoder counts differed between 19:00 (`[-13,27,-40,16]`) and 19:48 (`[-12,31,-40,9]`) with E-STOP latched; within every 4-s window they were constant. Cause not established (wheel touched vs. count noise); the deployer requires within-window stillness only. | `/api/status` |

## 2. Design

**State is runtime-only.** It lives in `/run/user/<uid>/atlas-base-maintenance/` (tmpfs). A reboot always restores normal
behaviour, so no persistent file can ever stop the base from starting at boot. The B1 design could.

| Mechanism | Blocks | Reused from B1 |
|---|---|---|
| `lease.json`: 0600, O_NOFOLLOW, ≤4 KiB, atomic fsync+rename. Bound to boot_id, owner PID **and** kernel start time, and a CLOCK_BOOTTIME deadline (≤600 s). | — | atomic save, boot binding, session id |
| Verdict NONE / ACTIVE / INVALID. INVALID (corrupt, expired, owner gone, wrong boot/mode/owner) **fails closed**: base restarts stay withheld and the reason is reported until `release`/`abandon` or reboot. Nothing auto-releases. | ambiguity | "no timeout automatically releases" |
| Patched recovery: base-only hold in `maintenance_hold()`. Final lease check **inside `dispatch.lock`**, held for recovery's whole base attempt (restart + 25 s confirm). Per-check ack `{session, in_flight}`. | recovery restarts | dispatch lock held through systemctl |
| Runtime drop-in `ExecCondition=… start-gate` (tmpfs, window only). Admits exactly one start per authorised token (deploy=1, rollback=1, max 2). A skipped condition is not a failure, so `Restart=on-failure` cannot loop. | systemd auto-restart, any other agent's start | one-shot start gate |
| Deployer refuses to arm while recovery holds dispatch (bounded wait, then no change). It restarts only after an ack from the *running* recovery PID with `in_flight=false`. | in-flight recovery | `no_base_jobs`, quiescence |

**Unchanged:** E-STOP, the stop-latch + zero-command restart guard, fault classification and reporting, all other
monitors' recovery, camera hold, thresholds, Nav2/TF/localization/mixer/motor code.

**Zero commands, verified independently of recovery's stop guard.** The deployer reads the status web
(`rover-status-web`, a separate subscriber) at three layers:
- *Commanded:* `/cmd_vel` lin=ang=0, fresh ≤1 s.
- *Applied:* `motor_speed` = 0, `web_drive` = STOP, drive PID inactive.
- *Measured:* encoder counts unchanged across snapshots, odom |vx|,|wz| < 1e-3, serial packet counter strictly increasing.
- *Policy:* `stop_latched`, `manual_only`, `commission_armed=false`, source STOPPED, plus `/api/estop/state` latched.

Every snapshot is saved *before* its decision (b88a569 lesson).

**CPU (owner decision, no default):** `--cpu-rule strict|settle`. The limits themselves are unchanged (75 / 80 / 70).
- Preflight: 30 s, every 1-s sample ≤ 75 %.
- Pre-restart: 10 s, every sample ≤ 75 %.
- `settle` after a restart: the transient may exceed 75 % for at most 120 s, until 5 consecutive 1-s samples ≤ 75 % (Stage 32 U2 precedent). Then a 30-s strict window must pass, or the deployer rolls back.
- `strict` is expected to fail (F6).

## 3. Exact file changes (the Jetson is changed only after separate approval)

| Stage | File | Live baseline | Candidate | Change |
|---|---|---|---|---|
| A | `atlas_base_maintenance.py` | absent | `a768626a…` (see MANIFEST) | new, 0644 |
| A | `atlas_sensor_recovery.py` | `c6b5ac79…` | `5f44cc1f…` | +106 lines, 0 removed (anchor-exact insert) |
| B | `atlas_yahboom_rc_report.py` | absent | `f5165a58…` | new (git LF) |
| B | `atlas_rc_readonly_bridge.py` | absent | `c717ca1b…` | new (git LF); only `FrameForwarder` imported |
| B | `Rosmaster_Lib.py` | `355ac420…` | `15391e14…` | +18, 0 removed |
| B | `yahboom_base.py` | `c551be00…` | `bb6db3a1…` | +34, 0 removed |
| — | `atlas_flysky_core.py`, `atlas_flysky_web.py` | `3e4b379e…`, `f49285fa…` | unchanged | must remain |
| B (runtime) | `/run/user/1000/systemd/user/rover-base-telemetry.service.d/90-atlas-base-maintenance.conf` | absent | ExecCondition gate | window only, removed on release |

Candidates are rebuilt **on the Jetson** from the live files with the reviewed insert scripts, and the deployer refuses
unless every hash matches `project_atlas/tools/deploy/stage28_base_maintenance/MANIFEST.json`. No file comes from the
Codex folder.

## 4. Tests (all offline)

- **36 unit tests** (`project_atlas/tests/test_base_maintenance.py`) pass on Python 3.13 and **3.10** (the Jetson's version). They cover:
  - the lease validity matrix and unsafe files/roots;
  - token single-use and budget, and gate errors;
  - arm vs dispatch races;
  - the real `recover()` body with a lease armed between the early and final checks: no restart;
  - ack/in-flight behaviour, a missing module, insert-only diff and refusal on other input or a second run;
  - each safety predicate, motion and stalled packets;
  - strict and settle CPU rules;
  - candidate rebuild, the CRLF identification, and the refusal of a changed shared file;
  - unreadable thermal zones.
- **94 existing** FlySky / Stage 28 tests still pass.
- **16 end-to-end scenarios on a real systemd 255 user manager** (15 gating, all PASS in the final run; s00 is an observation) (`sim/run_sim.py`), all under Python 3.10. The units are fakes; `atlas_sensor_recovery.py` is the real original or candidate file under a stub rclpy; the deployer is the real tool:

| Scenario | Result |
|---|---|
| s00 original recovery, slow stop (3 s) | observation: competing `RECOVERING … restarting rover-base-telemetry` reproduced in 2 of 3 full runs; deferred in the third (timing-dependent) |
| s00b original recovery, 10 s init | deferred, no competition (F4) |
| s01 stage A install | PASS: only recovery restarted, base PID unchanged, coordination loaded, lease→ack→release proven |
| s02 stage A, strict CPU rule, 98.8 % transient | fails and restores the original recovery (F6) |
| s03 stage B deploy, slow init + 4 s post-READY data gap | PASS: exactly 1 base start, recovery HELD, no competing restart, protected PIDs unchanged, drop-in and lease removed |
| s04 recovery mid-restart when deploy starts | refused, no change, no overlapping starts |
| s04b recovery in its confirm loop | deployer waited; base restarted 3.3 s after `RECOVERED` |
| s05 candidate crashes 1 s after READY | systemd auto-restart withheld (no loop); originals restored; exactly 1 rollback start; ROLLED_BACK |
| s06 CPU never settles | ROLLED_BACK, 2 starts total |
| s07 stop latch released before restart | no restart; files restored |
| s08 deployer dies holding the lease | INVALID reported; recovery and systemd do not restart; `abandon` restores normal behaviour |
| s09 lease expires | INVALID; gate withholds |
| s10 unrelated LiDAR stale during the hold | recovered normally |
| s11 module missing + lease present | base restart withheld (fail closed) |
| s12 no lease, stop guard broken | `STOP REQUIRED`, unchanged behaviour |
| s13 no lease, guard OK | normal bounded base recovery, unchanged behaviour |

- **Live read-only preflight on the Jetson** (19:50 IST, package run from `/tmp`, evidence in `/tmp/stage28ev/`):
  - **GO**;
  - both stages' candidates rebuilt from the LIVE files, all hashes match;
  - 14/14 safety predicates true ×3; encoders constant; packets 102827→102929;
  - CPU 30 × 1 s mean 65.45 %, max 68.02 %; RAM 62.58 %; max 64.4 °C;
  - base PID 1921 and recovery PID 1947 unchanged, NRestarts 0; no maintenance state created.

Not validated offline: real rclpy/DDS timing, real Jetson CPU transient size, real board init time after a service
restart (must stay < WatchdogSec=5), and Test Lab reception of real frames.

## 5. Resource impact (estimates; Jetson not measured)

- RC forwarding: `RcReportForwarder.handle` 22.6 µs per call and JSON 4 µs on a Xeon 2.8 GHz. At ≤10 Hz, about 3–4× slower on Orin, that is ≈1 ms CPU/s, about 0.1 % of one core. Plus ≤10 Hz publish of ~100-byte strings and one Test Lab subscriber.
- Recovery: `evaluate()` 2.4 µs per 2-s check with no lease.
- Gate: one ~60 ms (x86) python start per authorised base start, only during the window.
- No persistent new process.
- The restart transients themselves (one recovery restart in A, one base restart in B) are the material cost (F6).

## 6. Rollback plan

| Situation | Action (all scripted in `deploy_rc_bridge.py`, evidence under `~/project-atlas-migration/stage28-*`) |
|---|---|
| Any gate fails before files change | lease released, drop-in removed; **no change** |
| B fails after file install, before restart | originals restored from the verified backup (hash-checked); **no restart** |
| B fails after restart | originals restored; wait for systemd quiescence; ONE authorised rollback start; verify board ready + telemetry + packets; release |
| Rollback start fails | STOP. Fail-closed hold stays (no restart loop, recovery and systemd withheld). Report `ROLLBACK_INCOMPLETE_OWNER_ACTION`. Owner inspects, then `OWNER_APPROVED=yes deploy_rc_bridge.py abandon`, then starts the base manually |
| Stage A fails | original recovery restored, module removed, ONE recovery restart, READY verified |
| Remove stage A later (owner choice) | restore `backup/atlas_sensor_recovery.py` (c6b5ac79), delete `atlas_base_maintenance.py`, one recovery restart. When no lease exists the patch is dormant and behaves exactly as before (s12, s13) |
| Reboot at any moment | tmpfs lease and drop-in vanish; files stay as last installed (backup in evidence) |

Backups: `backup/` + `backup.tar` + `meta.json` (sha256, mode, uid) + `SHA256SUMS.all` in each evidence directory,
verified before any write.

## 7. Required approvals, in order (none granted by this document)

1. Owner decision on `--cpu-rule settle` (F6).
2. Stage A: install the coordination plus ONE `atlas-sensor-recovery` restart.
3. Stage B: deploy plus ONE `rover-base-telemetry` restart.
4. Separately: the live transmitter test.

Each runs detached from SSH:

```
systemd-run --user --unit=atlas-stage28-A --collect --wait --pipe -E OWNER_APPROVED=yes \
  python3 <pkg>/deploy_rc_bridge.py install-recovery --cpu-rule settle \
  --owner-confirms-transmitter-off --owner-confirms-actuators-disconnected
```

Known open item for the live test (unchanged by this work): B4 showed CH5–CH10 constant 1024 regardless of switches;
the cause is unproven (likely transmitter assignment). See `ATLAS_STAGE28_B4_SIGNAL_FIRST_CH5_DIAGNOSIS_20261027.md`.
