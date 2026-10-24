# Localization executor installation: rolled back, 2026-10-24

## Authorization and outcome

Owner authorized one installation with CPU report-only, retaining RAM80%,
temperature70C and all safety checks. Production CPU75% policy was not changed.
Only `scripts/atlas_localization_monitor.py` was replaced. Only
`atlas-localization-monitor.service` was restarted, once for installation and
once for rollback. No camera, recording, movement or other service restart.

Result: **ROLLED_BACK**. During post-restart settling the required
`mission_status` freshness check failed. No automatic retry. The original file
was restored and its SHA256 verified. This is an observed freshness failure,
not proof the executor candidate caused it; restart contention is a hypothesis.

## Measurements

- Matched baseline health samples: CPU mean73.9269%, peak80.6723%; monitor
  process15.1026% of one CPU core over24.04seconds.
- Continuous baseline trace (24 one-second samples): mean73.6821%, peak80.6723%.
  This differs from the20 health-sampled measurements above by sampling cadence.
- Restart CPU sample88.1072%; settling11 samples mean93.7297%, peak100%.
- Rollback9 samples mean93.6174%, peak100%.
- No completed candidate post window: no valid before/after savings claim.
- Rollback health RAM69.3046%, maximum temperature60.375C.
- Subsequent read-only recovery check: CPU76.9616% (still above normal75%),
  RAM69.9852%, temperature60.375C. Required sensors fresh, mission READY,
  E-STOP latched, manual-only, commands/wheel outputs zero, recorder/Astra OFF.

All protected services retained their PIDs/restart counts: Pi Camera1858/0,
telemetry3351/1, mux1852/0, EKF2982/0, AMCL8060/7, LiDAR7887/12,
Dashboard94624/0, voice108742/0, safety119178/0. Restored monitor is active,
PID275216, automatic restart count0 (manual restarts are separately recorded).
Voice privacy remained muted. Voice, white-glass UI and safety-file hashes match.
No functional voice or steering exercise was performed.

## Files, tests and integrity

Added bounded installer `project_atlas/tools/diagnostics/deploy_localization_executor_once.py`
and three installer tests. Six tests passed including the existing three candidate
contracts; `git diff --check` passed. No repeated sensor benchmark.
Installer enforces exact baseline/candidate/protected hashes,512MiB free disk,
verified backup, continuous CPU logging, fresh safety checks and owned rollback.
Free disk measured393604796416bytes.

- Installer SHA256: `0a2d23b834d152fa29d671bdd797ea00b02769f0acb9556d33daee9ccda8c40d`
- Candidate: `58e5d86b21e59546cd44e5fcc87d99df910e4e9e9220d1701e24080de393a4da`
- Original/restored: `cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b`

Evidence and backup directory:
`/home/jetson/project-atlas-migration/localization-install-20261024-Odaewk/evidence-pk1vh1ss/`

Backup: `atlas_localization_monitor.original`; preserved for recovery. Rollback
already completed; do not run another restore/restart without authorization.

- result.json: `83fe49f44815ead1143d45923ff946808f40cd5e356b2571ec7b447f7d83dd17`
- trace.jsonl: `e2e41788a7a52f9d21ef5cc67189fa64d408b8f5d39992d2f0b5d43d9f04b8a5`

Retrieved private copies under `artifacts/localization_install_20261024/` match
remote hashes. Raw diagnostic files and backups are not committed.

## Remaining work

Candidate remains undeployed. Review retained restart/freshness evidence offline
before proposing another attempt. CPU headroom and full live candidate behavior
are unverified; no Astra readiness claim. Installation-only CPU exception does
not authorize camera tests or a production policy change.
