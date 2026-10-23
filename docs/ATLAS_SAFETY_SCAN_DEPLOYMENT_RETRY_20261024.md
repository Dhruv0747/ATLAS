# Safety scan deployment retry — installed and health verified

Owner explicitly approved a new installation attempt with CPU report-only for
installation, safety-status-only restart, unchanged voice/UI and no camera or
movement. This supersedes the earlier attempt's strict CPU admission only for
this one run, not the production guard. Previous rollback evidence49dc8d5 remains.

## Scope and tests

Installed ONLY `/home/jetson/project_atlas/scripts/atlas_safety_status.py`.
The reviewed candidate rotates each valid scan ray once instead of repeatedly
per sector. All sector comparisons/priority/range validation/timestamps and
other methods remain unchanged. No rate reduction or clearance-policy change.

The diagnostic installer now accepts one explicit
`--installation-cpu-report-only` flag. Without it,75% CPU remains fail-closed.
Even with it, invalid/nonfinite/out-of-range/stale CPU monitoring fails. RAM80%,
temperature70C, E-STOP, zero commands, sensor freshness, Astra/recorder OFF,
protected services and file hashes remain checked. No production guard edited.

Six offline tests passed, including explicit/narrow CPU policy, rejection of
unknown flags/invalid CPU values, restart scope/rollback checks,335 equivalence
cases, unchanged other methods and baseline rejection/full-source compilation.
Deployment-contract tests are static/unit checks, not hardware fault simulation.

## Hashes and installation

- Original/backup SHA256:
  `57262f6e55aef3f28ba285805619a86f6131643e41cebf20dc49be86d3cf2e1e`.
- Candidate/installed SHA256:
  `94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4`.
- Exact-live transformer SHA256:
  `21e4da2b74abf8e76e9491b67f8ef791713f05baa255edce83ea995ecea1b277`.
- Run installer SHA256:
  `bc68b494b74e2b295964c29fbcf5ba991c0323ea56d682eb31a67e6b81d15bba`.

Verified protected voice/Dashboard/white-glass/guard/probe hashes, live baseline,
candidate, free disk394160840704bytes, backup integrity and safety before atomic
replacement. Only `atlas-safety-status.service` restarted once. Persistent1-second
CPU trace started before baseline and continued through restart/settling/post.
No automatic retry, unrelated restart, calibration/map change or USB change.

## Measurements

Matched parked20sample windows,~23.8s each, before and after10settling checks:

|Metric|Before|After|
|---|---:|---:|
|Whole-Jetson CPU mean (health-window samples)|70.7230%|71.3597%|
|Whole-Jetson CPU peak (health-window samples)|73.9865%|75.5337%|
|Safety reporter CPU, percent of one core|13.5663%|13.1037%|
|Window elapsed|23.809s|23.734s|

Observed reporter reduction0.4626percentage points (~3.41%relative). Short
non-simultaneous windows are sensitive to background work; causal/stable savings
are not established. Whole-system mean increased0.6367points, so **no useful
whole-Jetson headroom demonstrated**. Prior isolated callback41.26% savings must
not be described as whole-process/system savings.

Full continuous trace restart sample81.29%;settling peak100%. Overall maxRAM70.2115%,
max temperature60.281C. Spikes are preserved, not excluded from the report.
All continuous post-phase samples mean71.33% differs slightly from71.36% above
because health checks select a subset of the persistent1-second samples.

CPU report-only was solely the owner-approved installation exception. Actual
production75%CPU/80%RAM/70C limits and Astra admission remain unchanged.
Post peak75.53% means stable Astra admission is still NOT established.

## Postflight

Result `DEPLOYED_HEALTH_VERIFIED`;final installed hash independently rechecked.
Safety reporterPID119178,NRestarts0,active,Resultsuccess;ready journal message.
The previous reporter logged an exit failure during explicit shutdown, as in
earlier attempts; this is not evidence the new steady-state callback failed.

Unchanged protected identities/restarts:PiCamera1858/0,motor3351/1,mux1852/0,
EKF2982/0,localization8060/7,LiDAR7887/12,Dashboard94624/0,voice108742/0.
Required sensor freshness passed;E-STOP latched,manual-only true,commissioning
false,commands zero,mission READY,recorder OFF,Astra OFF. Voice privacy MUTED
preserved. No acoustic interaction test or autonomous reliability claim.
White-glass CSS and voice/Dashboard files hash-verified unchanged.

## Evidence / rollback

Directory:
`/home/jetson/project-atlas-migration/scan-cpu-retry-20261024-LT3djX/evidence-qfjwh3am/`

- Backup `atlas_safety_status.original`,original hash above independently verified.
- `result.json` SHA256 `9138e7cd33253b2f866097b5fa95c65f08e09ab6950bfd6d3b875f50b135a582`.
- `trace.jsonl` SHA256 `74b8e4815bed967f3ba7520ec9def17292bdc1e83a7720f4f58a8a3ad26a737c`.
- Local raw copies:`artifacts/safety_scan_retry_result_20261024.json` and
  `artifacts/safety_scan_retry_trace_20261024.jsonl` (not committed).

Rollback retained but not needed for this run:verify current candidate and backup
hashes, restore original preserving metadata, restart ONLY safety-status under
approval, recheck safety/sensors/protected identities. Do not remove shared helpers
or change any other service. Installer default remains strict; this run's flag
does not grant future CPU exceptions.

Next engineering priority is broader measured CPU contention, not another Astra
start or automatic service change. Deployment success does not mean CPU headroom
or real3D-preview readiness is resolved.
