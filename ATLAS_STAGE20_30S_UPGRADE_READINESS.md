# Stage20 30-second upgrade readiness — 14 October 2026

## Latest: owner-approved CPU-exempt installation-only — SUCCESS, 17:11 UTC

Owner explicitly requested installation ignoring CPU after the rollback. Exception
applied ONLY in the one-shot installer validation, never in installed collector or
runtime preflight. Actual CPU measurements retained; other checks unchanged.
Preflight intervals67.75,67.86,73.64,68.01,68.68%; postflight71.07,67.70,72.99,
67.57,68.21%. Thus observed intervals happened to remain below75%, although approval
waived installation CPU ceiling. RAM70%,59C,394351915008 bytes free postflight.
Five installed hashes exactly match candidate manifest. All328 protected files and
production service PID/start/restart identities unchanged. Unit static/inactive,
PID0/restarts0, no grant, no autostart. E-STOP latched, commands zero. No movement.
Runtime recording75% CPU gate remains byte-identical; activation NOT approved.

Backup/rollback transaction:
`/home/jetson/data/backups/20261014T171133Z-stage20-78070115044743b29df6a4fb030f6204`.
Durable evidence copied into backup:
`upgrade30-install-cff663ae10e7458b9e9ded6be6589238.jsonl`.
Status: **30s diagnostic upgrade DEPLOYED, recording OFF**. Previous failed attempt
below retained; it is not the current installed state.

## Owner-approved installation attempt, 17:10 UTC — ROLLED BACK

Exact approved five-file manifest verified. Preflight CPU intervals68.95,72.79,
69.21,70.00,67.50%; RAM70%,58C,394352947200 free bytes; stop latched/zero commands.
Files installed, optional user manager metadata reloaded only. Postflight CPU
74.54,70.02,71.95,77.35,71.43% exceeded unchanged75% gate. RAM70%,59C.
No attribution of that spike to installation is proved. Recording never started.
Restored all five original hashes; legacy package remains OFF/static/inactive PID0,
restarts0. All production service PID/start/restart identities and328 protected
script/config/map/launch hashes unchanged. Final policy latched STOPPED, zero commands.
No production restart, motion, retry, threshold change or activation performed.

Backup and rollback transaction:
`/home/jetson/data/backups/20261014T171012Z-stage20-061f2b3807ca4425b1dd8a8bcebce2b6`.
Durable full subprocess/error/measurement evidence copied there:
`upgrade30-install-e5228697976d498e801abe988470fc14.jsonl`.
Original evidence also remains under `/tmp/atlas-stationary30-avHg8uSb/`.
**Installation NOT accepted; upgrade NOT deployed. Stop for further instructions.**
The readiness/preparation discussion below is retained as historical context.

**GO for separately approved installation-only, subject to fresh preflight. NO-GO
for recording activation.** No production writes, services, calibration, maps,
steering or control authority changed. Stage17B HOLD. Existing collector OFF.

## Exact package

Source pinned to `04f9ad09025651e954d4e9bab03314a6a3700252`; previous native capture
results reused, not repeated. Builder `stage20_upgrade30_prepare.py` extracts exact
Git blobs, avoiding Windows line-ending conversion. It only prepares a directory.
Machine-readable [manifest](project_atlas/tools/diagnostics/fixtures/stage20_upgrade30_manifest.json)
contains every before/after SHA256 and five unchanged dependency hashes. Prepared
manifest SHA256 `8384037bcb114a912f5955295c0d62032ab21fbcaac60642cba909dc754d425c`.
Package locally `artifacts/upgrade30_candidate`, native sandbox copy
`/tmp/atlas-stationary30-avHg8uSb/upgrade30_candidate`. Raw artifacts not committed.

Exactly five existing files under `/home/jetson` change:

| File (relative to home) | Change |
|---|---|
| project_atlas/tools/stage20_public/tools/diagnostics/stage20_capture.py | explicit stationary30 opt-in, freshness/stop checks, receipt deadline, retained TF-static, bounded writer waits |
| project_atlas/tools/stage20_public/tools/diagnostics/stage20_production_gate.py | separate profile-specific single-use grant |
| project_atlas/tools/stage20_public/tools/diagnostics/stage20_capture_integrity.py | finalized-but-incomplete captures cannot pass completeness |
| project_atlas/tools/stage20_public/atlas-stage20-public-capture.service | optional30s unit payload |
| .config/systemd/user/atlas-stage20-public-capture.service | identical optional30s unit registration copy |

No other runtime files included. Legacy120s CLI profile and source template remain;
optional unit would select30s after upgrade. Restoring old unit selects120s again,
but a30s grant cannot authorize it. No autostart/Install section, Restart=no.
RuntimeMaxSec50, TimeoutStopSec12; writer waits share10s, not a claim that all
checksum/ROS teardown takes at most10s. CPUQuota is not assumed enforceable on this
user manager; existing kernel CPU-time limit is finite. No new safety authority.

Live read-only inspection before and after rehearsal matched all nine installed
payload hashes, including old unit hash
`7360889d419ac2242f26aacb99435849ae4b4fa97726a5d32aafb17a3098db4a`.
User-unit copy matched before preparation. Service remained static/inactive, PID0,
restart count0. E-STOP latched, commands zero, commissioning false. No grants made.

## Rehearsal and regression results

Reuses `stage20_package_transaction.install/rollback/atomic_copy`; not a new live
installer. `stage20_upgrade30_rehearsal.py` requires actual network/PID isolation,
writes only newly created temporary targets, copies exact live baseline and invokes
the existing transaction. Six native cases passed: successful install plus rollback,
and partial failure after writes1,2,3,4,5. All originals restored byte-for-byte;
historical diagnostic sentinel and transaction backups retained. Installed candidate
hashes checked. Native systemd parser passed. Missing grant refused before recording.
No service operations exist in this rehearsal; inactive service state is separately
verified live, not claimed as a simulated systemd-manager test. Previously tested
profile mismatch/one-use protections are reused.106 regression tests:105 pass,
one environment skip. No new capture or drive test performed.

Future supervised installation uses this exact manifest and existing transaction
root `/home/jetson`; backups go to `/home/jetson/data/backups/<transaction>/`,
NOT the previous package's project-relative backup directory. It must not call the
old fresh-install wrapper, which intentionally refuses existing unit collisions.
First verify full allowlist, all five before hashes and unchanged dependencies,
free space, inactive/static unit, no enabled grant, fresh stopped policy/zero commands,
production PID/restart/protected-file snapshot and unchanged resource limits.
Use durable terminal/event logging. Require an all-before state, not a mixed partial
installation, and inspect/recover any earlier transaction before proceeding.
After files verify, `systemctl --user daemon-reload` only (no service restart/start).
Postflight hashes/resource checks and inactive/static state must pass or rollback.
No existing production service restart is required.

Rollback: use saved transaction with existing `rollback(backup, Path('/home/jetson'))`,
then user daemon-reload; verify original hashes and inactive/static unit. Do not
remove recordings/backups. Rollback refuses unexpected later file drift. Preserve
durable errors; no automatic retry. These steps are prepared, NOT executed live.

## Resource-admission decision

| Operating condition | Decision |
|---|---|
| Installation only | Finite file copies, checksums, metadata reload; no continuous collector cost. Keep existing75% CPU/80% RAM/70C/free2GiB checks before/after; approval still required. |
| Parked stationary capture | Adds collector workload; prior admission refusal remains relevant. Current evidence insufficient for activation, despite a quieter current sample. |
| Movement recording | Not supported by this stationary profile: released stop/nonzero commands abort. Requires separately commissioned motion recorder, load/latency and physical safety validation. |

One bounded read-only five-sample observation (not a repeated admission-until-pass):
dashboard CPU70.8,70.8,71.1,71.1,69.7%; RAM67%;58–59C. Six CPU cores confirmed.
HTTP response24.6–74.6ms; policy age0–0.1s, command0–0.2s, odom0–0.1s.
The queried `ros.scan` field was absent; this is unavailable evidence, NOT proof
of a missing LiDAR. Dashboard sampling/caching is not independent CPU admission
or motor-loop scheduling latency. No physical E-STOP response latency measured.

Prior isolated collector cost14.931 CPU seconds/31.056s =48.08% ONE core (~8.01
whole-machine points on six cores, an estimate not a live additive guarantee).
RAM72.375MiB and logical53.18MiB/30s. Physical disk-write measurement remains
unavailable; logical bytes are not physical I/O. Baseline historical mean~70%,
max81.9%, refusal79.496% retained. Average estimated combined load~78% already
exceeds75%; spikes may be worse. These data do NOT justify a higher threshold.
No resource-policy change proposed or implemented. Keep admission unchanged.

Smallest defensible path: install OFF if preflight passes, then obtain genuinely
verified resource headroom through separately approved measured nonessential-work
optimization. Do not disable working ROS services or lower essential sensor rates.
Any future alternative admission proposal needs measured critical-loop latency,
queue delay and end-to-end stop response under load, not dashboard response alone.
It requires separate approval; current evidence does not support it.

## Future activation procedure — DO NOT EXECUTE now

1. Obtain separate stationary-recording approval after installation and headroom
   qualification. Park, latch stop, zero commands; confirm sensor availability.
2. Record boot ID, exact nine post-upgrade runtime hashes, config/map identity,
   production PIDs/restarts, disk space and five independent resource intervals.
   Fail closed on any stale/unknown evidence or original threshold violation.
3. Create a fresh UUID single-use grant in the existing approval location with
   enabled/owner_approved/deployment_ready=true, mode=read_only_partial_public,
   capture_profile=stationary_30_v1, exact source commit, current boot session,
   runtime_identity and identity hashes required by `stage20_production_gate`.
   Installation approval never creates this grant. Preserve consumed grant markers.
4. Start ONLY `atlas-stage20-public-capture.service` once; never enable. Receipt
   window <=30s; E-STOP/zero-command/freshness/resource guards stop on violations.
   Sensor preflight10s; overall unit50s then12s stop timeout. No automatic retry.
5. Before/during/after record independent CPU/RAM/temp/free disk, policy/command
   ages, sensor source/receipt ages and queue occupancy. Capture callback timings
   and backlog; exact queue residence latency is not currently instrumented and
   must not be reported as measured. Queue occupancy is only its proxy. Preserve
   worker failure/overflow data, SQLite integrity, checksums, source/receipt ledger.
6. Confirm inactive PID0, no enabled unit, grant consumed, no production restart,
   zero commands and unchanged protected files. Archive full/incomplete results.
   Missing event-driven AMCL/particle samples can correctly mark capture incomplete;
   do not force AMCL activity merely to pass. Revoke grant after completion/refusal.

Remaining risks: production overhead and exact queue latency unverified; physical
I/O measurement unavailable; event-driven source availability; TF-age check covers
first transform, not every chain. Public capture does not restore internal EKF/AMCL
state. These limits prohibit claiming recording safety or localization improvement.

## Localization next evidence, unchanged

Minimal candidate only removes wheel XY pose fusion, retains velocity and corrected
gyro. Not deployed. Shortest faithful EKF comparison requires actual initialization
and complete selected input/reference/TF history from a separately approved normal
startup, or a genuine restorable state/covariance/reference checkpoint. No reboot
authorized here. AMCL failure reproduction additionally requires its initialization,
particles/weights/RNG/events. Stationary public30s cannot supply missing old private
state. Do not rerun Stage18/19 or request another house loop without new evidence.

## Approval requested

Approve **installation-only of the exact five-file diagnostic upgrade**, with
recording OFF, no grant, no autostart and unchanged safeguards; abort/rollback on
any pre/postflight failure. Recording activation is a separate NO-GO until resource
and monitoring gaps are resolved. No motion or fusion deployment included.
