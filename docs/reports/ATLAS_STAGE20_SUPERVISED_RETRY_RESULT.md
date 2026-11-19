# Stage20 single supervised installation retry — 14 October 2026

**Final result: installation completed, postflight resource gate FAILED, then
rollback VERIFIED. The package is not currently installed. Recording never ran.**
One attempt only; no automatic retry or threshold change.

Owner approved installation only of candidate associated with
`ba66f3f03bf36acc02f44811dbcb2fd672ee4aa8`, manifest SHA256
`a99fc59d5860b40bfe1b1945fdcc721580e367e820ed5d700c50c770b9e8aa1e`.
All installer/payload hashes, protected live hashes, dependencies, target absence,
unit parsing, writable backup paths and free-space checks passed before invocation.

## Actual attempt and failure

At 14:17:48 UTC, the corrected installer returned exit 0:
`files_installed_not_activated`, `activated=false`, `autostart=false`, no services
enabled or restarted. Native user-manager daemon-reload succeeded. The nine files
and optional user unit were installed with the exact expected hashes below.

The supervisor's immediate postflight `stage20_public_preflight.check()` then
raised `ValueError: diagnostic headroom unavailable`. Its traceback identifies
the CPU/RAM/temperature threshold check. **The precise failing sample was not
retained by that helper**, so it is not possible to name which threshold or its
exact value at that instant. A subsequent read-only sample during rollback showed
CPU **79.7%**, above the unchanged **75%** ceiling. This establishes insufficient
CPU headroom then, not the exact earlier value or a causal explanation for load.
No claim is made that the inactive collector caused it or that this explains the
older aborted installation.

Installation acceptance was therefore refused and only this transaction's new
diagnostic targets were rolled back. The optional unit was confirmed **static,
inactive, PID 0, start timestamp 0** before removal. There was no activation grant,
collector process, recording or motion command from this procedure.

## Hashes verified after installation and before rollback

Paths below are relative to `~/project_atlas/tools/stage20_public/`.

| File | SHA256 |
| --- | --- |
| tools/diagnostics/stage20_capture.py | `082284d40b2f5c6c7e829dba8054ac0dbc6b06b95c95fb5d7143312d30ab9862` |
| tools/diagnostics/stage19_contract.py | `ace61dce76fe8c39f5524e93cd57139f3645f32b7b799fd06c8eac9491d6a965` |
| tools/diagnostics/stage20_production_gate.py | `5e5451db2acce9bb056abc6492ab09df677d9f80a48ee214959b45de4d5ed3a9` |
| tools/diagnostics/stage20_capture_integrity.py | `976cc31a64264fa3c3c4eee591498198a2ab0603df729671428ecee97f0011d1` |
| tools/diagnostics/stage20_public_preflight.py | `36b8bcc2f90b44cd3d46add5610f357c7ea765d22155117a7b676a6417f3fa2a` |
| scripts/atlas_motion_recorder.py | `7110961ca9692f6b692a2ad5fccbe08f7775d624127d43b1bf087cffc4c63930` |
| scripts/atlas_motion_recorder_core.py | `c12a735ad05c61e659f405541dc3dbeb6e1c5706aacb44484f0d9f7af87b0e01` |
| scripts/atlas_motion_recorder_writer.py | `3ca1adb5aa77875c32d99a7af117329da9bfa36eb692099c06788cfc4811a112` |
| atlas-stage20-public-capture.service | `7360889d419ac2242f26aacb99435849ae4b4fa97726a5d32aafb17a3098db4a` |

The user-unit copy matched the last hash. All nine payload files and the user-unit
copy are now absent after rollback; empty directories and evidence were preserved.
The full candidate identity remains in [the retry manifest](ATLAS_STAGE20_INSTALL_RETRY_MANIFEST.json).

## Safety, production and resources

| Observation | Before | After rollback |
| --- | --- | --- |
| E-STOP | Latched | Latched, REMOTE STOP: B pressed; age 0.1 s |
| Motor command | Zero | lin=0, ang=0; age 0.2 s |
| CPU | 70.7% | 79.7% |
| RAM | 71% | 71% |
| Temperature | 59°C | 59°C |
| Disk free | 394,557,353,984 bytes at initial check | 394,556,129,280 bytes |
| Optional unit | Absent/inactive | Absent/inactive, PID 0, start timestamp 0 |
| Nav2/exploration | Inactive | Inactive |

All listed ATLAS/rover production service states, PIDs, restart counts and start
timestamps match the recorded pre-install snapshot after rollback. Key services:

| Service | Before/after PID | Before/after restarts |
| --- | ---: | ---: |
| atlas-ekf | 3234 | 0 |
| atlas-localization | 11868 | 17 |
| rover-base-telemetry | 3364 | 1 |
| atlas-cmd-vel-mux | 1913 | 0 |
| atlas-remote | 1963 | 0 |
| atlas-safety-status | 1977 | 0 |

Protected production hashes and dependency pins still match. Accepted maps,
calibration, navigation/fusion settings and private estimator binaries were not
changed. No production service restart, reboot, steering, E-STOP release or
autonomous movement occurred. Rollback stopped only the already-inactive optional
unit and reloaded unit definitions; it did not restart existing services.

## Preserved backup and diagnostic evidence

Backup/transaction directory:
`/home/jetson/project_atlas/data/backups/20261014T141748Z-stage20-f194331e2176414cbbb95d19b41bbc53/`

It retains `transaction.json`, `unit_transaction.json` and these copied logs:

- `retry-supervisor-3bda3a6a18a64d15a2eaed3648bdfded.jsonl`
- `retry-installer-3bda3a6a18a64d15a2eaed3648bdfded.jsonl`
- `retry-rollback-3bda3a6a18a64d15a2eaed3648bdfded.jsonl`

Original logs and exact candidate remain under
`/tmp/atlas-stage20-install-audit-lt7tOutp/`; copies also exist in the PC repository's
untracked `artifacts/` folder. Raw logs are not published to GitHub. The ledgers
preserve subprocess stdout/stderr, installer success, supervisor traceback and
successful rollback output. Rollback used the verified candidate's
`stage20_public_install.py --rollback <exact directory above> --owner-approved-install`.
No further rollback is required; the new files have already been removed.

**Wait for further owner instructions.** Do not repeat installation, activate
recording or change resource thresholds. Before another proposed attempt, preserve
the actual resource sample in the postflight failure record and investigate available
headroom read-only if authorized. This attempt verifies that file installation and
unit registration can succeed; it is not an accepted deployment or localization fix.
