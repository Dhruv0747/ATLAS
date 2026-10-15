# Stage 22: steering-validation recorder profile, 2026-10-15

**Status: BUILT → TESTED → DEPLOYED (13:29:14 IST) → INSTALLED PROFILE VERIFIED → RECORDING OFF →
PHYSICAL VALIDATION PENDING.**

Owner-approved, installation only. One file changed; no service restarted; nothing recorded or
moved.

## 1. GitHub

HEAD `73cbfe4`, equal to the remote, no newer commits. The package's recorder result equals the
HEAD file.

## 2. Preflight (13:27, read-only)

**Safety:**
- `stop_latched: true`, `manual_only: true`, `commission_armed: false`;
- 31 `/cmd_vel` messages, all zero; 0 of 55 wheel-odometry samples moving;
- no Nav2 goal status.

**Recorder state:**
- no recorder process;
- no recorder unit installed, so no autostart path exists;
- `data/diagnostics/motion_capture` does not exist yet, so there are no earlier 6b captures to
  protect. Other evidence directories were untouched.

**Resources:** CPU 64–67% (five 1 s samples), load 14.7, RAM 4.8/7.6 GB, 59–60 °C, 369 GB free.

**Dependencies:** `atlas_motion_recorder_core.py` `c12a735a…` and `atlas_motion_recorder_writer.py`
`3ca1adb5…` are identical to the repository at both `0c1d520` and HEAD.

## 3. Hashes

| | sha256 |
|---|---|
| Live before (= package base `0c1d520`) | `02fcaed2c4350da9a46838356bcf571b408f57dffe33c7275c4168a52d821c80` |
| Live after (= MANIFEST result = HEAD) | `7110961ca9692f6b692a2ad5fccbe08f7775d624127d43b1bf087cffc4c63930` |

## 4. Package

- **Name:** `stage22-recorder-steering-profile`, from `make_package.py`.
- **Range:** `0c1d520..6acb0c0`. The recorder file is identical at `73cbfe4`.
- **Archive:** sha256 `9d3232b55b453afdf235f5bd36f731426547649a168a348a159955e83abf4618`, verified
  in the container, on the PC and on the Jetson.
- **Kept on the Jetson:** `data/diagnostics/stage22_20261015/`.

## 5. Regressions

**Container:** 21/21 tests pass (`test_atlas_motion_recorder`, `test_motion_recorder_writer`,
`test_stage17_recorder_profile`).

**Profile checks:**
- the default `TOPICS` and `REQUIRED` are unchanged against `0c1d520`;
- the new profile adds 16 topics, including `/atlas/encoder_update`, `/im10a/imu/unvalidated` and
  `/particle_cloud`;
- 0 publishers, 0 service clients;
- the only HTTP use is the existing read-only GET of `/api/status`.

**Jetson scratch copy:** 20/21 pass. The one failure is **not the recorder**:
`test_retired_direct_serial_tool_refuses_actuation` runs `scripts/atlas_steering_calibrate.py`,
and the live copy of that tool is the August `926735e` version, not the retired repository version.
See §14.

## 6. Rehearsal (Jetson scratch copy of the live `scripts/`)

- **Install:** scope check passed (only the recorder); result `7110961c…` MATCH; byte-compiles.
- **Behaviour:** both profiles load; the `--record` opt-in guard still refuses.
- **Rollback:** `ROLLBACK.sh` restored `02fcaed2…` byte for byte.

## 7. Installation

13:29:14. A final check just before showed latched, manual-only, no recorder process and the live
hash `02fcaed2…`.

The installer's own scratch rehearsal, backup, apply, byte-compile and scope check all passed:
**MATCH**, live `7110961c…`.

## 8. Profile availability

| Profile | Topics | Required | Post-roll | Notes |
|---|---|---|---|---|
| `default` | 25 | 7 | 10 s | unchanged |
| `steering-validation` | 41 | 20 | 20 s | `--duration` limited to 30–600 s |

The storage cap and writer are unchanged; `MIB` constant identical.

## 9. Recording

**OFF.**
- Running without `--record` is refused.
- No recorder process or ROS node.
- No recorder unit file.

## 10. Production services and safety after install

**Services unchanged** (PID, restarts):

| Service | PID | Restarts |
|---|---|---|
| base | 45674 | 0 |
| EKF | 2802 | 0 |
| mux | 1788 | 0 |
| localization | 4521 | 0 |
| monitor | 1939 | 0 |
| web | 1956 | 0 |
| IM10A | 1802 | 0 |
| LiDAR | 1790 | 0 |
| Foxglove | 1947 | 0 |

**Hashes unchanged:**

| File | Hash |
|---|---|
| Stage 21 `yahboom_base.py` | `c551be00…` |
| `atlas_encoder_selection.py` | `7d457c9f…` |
| EKF | `69dd4479…` |
| Nav2 | `2411371c…` |
| Map | `d957f0fe…` / `4beb26d5…` |
| Steering calibration | `99084dea…` |

**Safety:** latched, manual-only, disarmed; `/cmd_vel` 28 messages, all zero.

## 11. Resources (13:30)

Load 13.1 (1 min), RAM 4.8/7.6 GB, 59–60 °C, 369 GB free. Comparable to the preflight; nothing new
is running.

## 12. Backup and rollback

**Backup:** `~/project_atlas/data/backups/2026-10-15-132914-489060448-stage22-recorder-steering-profile/`.
`orig/` holds `02fcaed2…`.

**Rollback:** `bash <backup>/ROLLBACK.sh`. No restart needed. Rehearsed on the Jetson.

## 13. Commit

This report is in the commit after `73cbfe4`.

## 14. Findings and remaining blockers for the baseline drive

**Finding: an old direct-serial steering tool is on the live tree.**
- **The tool:** live `scripts/atlas_steering_calibrate.py` is the August version (sha256 `6b7b10b2…`).
  It opens `/dev/yahboom` directly, sends `set_motor(0, 0, 0, 0)` and **commands both steering
  servos** (`set_pwm_servo`).
- **The repository version** is retired and refuses to actuate.
- **What happened in rehearsal:** the repository's regression test executes this tool, so it was
  run against a **scratch copy** of the live tool on the Jetson.
- **Why it could not actuate:**
  - `/dev/yahboom` does not exist on the Jetson, so `serial.Serial` failed before any write
    (exit code 1);
  - the running driver holds the real port with `exclusive=True`;
  - the driver logged nothing in that window.

  No servo command was sent.
- **Risk:** the live tool could command the steering if run with a valid port.
- **Recommendation** (separate approval): install the retired repository version. Until then, do
  not run the repository test suite against the live tree.
- The scratch copies were removed.

**Blockers before the supervised baseline drive:**
1. **AMCL unseeded** on this boot (exact-tie refusal). It needs your confirmation of the physical
   location, then an approved seed. Otherwise the AMCL metrics are absent.
2. **Approval to activate the recorder:** `--profile steering-validation`, ≤ 600 s per run, at
   nice 10.
3. **Approval to release the E-STOP and drive manually**, per the readiness report §3.

Candidate B remains not deployed. The Foxglove exposure remains open and deferred.
