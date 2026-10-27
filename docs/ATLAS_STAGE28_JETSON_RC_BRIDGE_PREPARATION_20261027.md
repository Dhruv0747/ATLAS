# Stage 28 — Jetson RC bridge preparation, 2026-10-27

## Confirmed cause
Read-only SSH inspection of 192.168.1.16: rover-base-telemetry active, PID 1921, NRestarts 0 at final check. Its ExecStart runs /home/jetson/project_atlas/scripts/yahboom_base.py. Exact live base has no RC hook; live Rosmaster_Lib.py has no 0xE1 storage/getter. The three forwarding helpers are absent. Dashboard previously displayed /atlas/rc/frames (no publisher), zero frames, failsafe not observable. Firmware was verified on Windows; Jetson-side proposal was never deployed. Normal motor-board telemetry and RC forwarding are separate capabilities.

No production writes, restart, ROS participant, serial-port opening, flashing or movement performed. Journal reports board ready and calibration loaded; that alone is not a fresh E-STOP/command validation or full sensor health pass. Do not infer current firmware full version from legacy journal string 3.6.

## Candidate prepared, NOT installed
Reused existing insert_rc_hooks.py and insert_rosmaster_rc.py against exact live downloaded files, preserving every existing source line. Two modified files: yahboom_base.py and Rosmaster_Lib.py. Three added helpers: atlas_yahboom_rc_report.py, atlas_rc_readonly_bridge.py, atlas_flysky_core.py.

Only FrameForwarder is imported from the bridge; its standalone serial main MUST NOT be launched. Existing USB owner stores 0xE1 payloads; 10 Hz timer forwards new fresh validated frames to /atlas/rc/frames. Drive-enabled firmware reports are rejected. No new command subscriptions or actuator writes are added. Existing driver startup/control behavior is retained, not independently recertified.

Exact hashes: ATLAS_STAGE28_JETSON_RC_BRIDGE_MANIFEST.json.
Local package: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-jetson-rc-bridge-20261027 (baseline, candidate, manifest, additive diffs, replay result). Package must be regenerated/compared if live hashes change. Do not replace with repository's full base file.

## Validation
55 existing tests PASS in WSL: test_yahboom_rc_report.py, test_stage28_yahboom_hooks.py, test_flysky_core.py. Candidate files compile. Exact-live patches remove no source lines. Live baseline hashes independently rechecked via SSH.
Saved raw session replay: 21953 reports, 7318 forwarded with simulated 10 Hz polling, every forwarded CH1-CH10 equals recorded values; LIVE, FRAME_LOST and FAILSAFE observed, LOST after silence. No real ROS runtime started. Jetson runtime load, callback scheduling and dashboard reception remain unvalidated. No CPU saving claim.

## Approval-gated deployment and rollback
Approval required to install these five hash-verified files and restart ONLY rover-base-telemetry. Do not proceed under current read-only approval. Before deployment: fresh E-STOP, zero commands, manual-only, transmitter OFF, physical actuator isolation, CPU <=75%, RAM <=80%, temperature <70C, sensor freshness, protected PID checks and exact-live hashes. Review sensor-recovery coordination so restart cannot race another owner; do not silently stop it.
Back up both originals and record absence/presence of all helper destinations, hashes, ownership and mode. Stage and compile all candidates before atomic file replacements. Keep the complete verified backup local to Jetson and PC. No map/calibration/firmware changes.
After approved restart: verify normal telemetry, unchanged safety behavior and other service PIDs; with transmitter OFF verify fresh RC reports carrying failsafe/frame-lost, correct firmware drive-disabled flag, dashboard receipt and no drive enablement. Abort on mismatch or stale safety data.
Rollback under reviewed deployment authorization: restore both exact originals and helper prior state, verify hashes, controlled base-only restart with recovery coordination, verify telemetry and safety. If unsafe or ambiguous, keep actuators isolated and stop for owner recovery assistance; no repeated restart loop.

No live receiver test or service restart is authorized by this preparation. The dashboard's generic claim that Yahboom cannot forward SBUS is stale for the patched board; it should stop appearing once the publishing path works. No unrelated UI rewrite proposed.
