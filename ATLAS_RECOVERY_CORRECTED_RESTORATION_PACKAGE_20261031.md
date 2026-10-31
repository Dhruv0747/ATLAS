# Corrected Recovery restoration package — 2026-10-31

GO for separate execution approval, conditional on fresh admission. NOT executed or
staged on Jetson. Recovery remains last verified STOPPED; incident remains open.

## Package and focused validation

Base: 1d81445. Existing builder and bounded supervisor reused. Only subsequent
runtime-template change is a fresh staging path in ExecStart and ExecStopPost.
No Recovery source, permanent unit, safety predicate or cleanup implementation changed.
PC package: `../recovery-restoration-1d81445` (relative to repository).
Future Jetson path: `/home/jetson/project-atlas-migration/recovery-restoration-1d81445`.
SHA256 of SHA256SUMS:
`48ee833a362f37732586548b0e35b6fcd83678bf72457f0e95071f27bf92307b`.

All 9 manifest entries verified. Eight focused tests ran against the BUILT package
on Ubuntu WSL: PASS in 0.097s. Coverage: partial CPU/PID/cgroup retention, skipped
PID classification, real CPU overload rejection, invalid intervals, inventory
bounds, cgroup formats and integrated first rejected startup interval persistence.
Existing native systemd timeout/SIGKILL cleanup evidence is reused, not rerun.
Rollback and safety dependencies have no diff from 1d81445.

Original live Recovery and saved rollback script must BOTH match:
`5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a`.
The actor checks both and aborts on drift; it does NOT replace either file.
Original Restart=always must be present. Snapshot environment/config/output must
be absent. Original unit text is saved before any temporary override.

## One future command — DO NOT RUN before separate approval

First copy the verified PC package into the NEW Jetson directory above, without
reusing any previous evidence/transaction directory. Confirm a local recovery
terminal is available. The command below is for the ordinary `jetson` user; no sudo.
It installs only the temporary supervisor unit, not production Python files.

```bash
bash -eu -o pipefail <<'ATLAS_ONCE'
cd /home/jetson/project-atlas-migration/recovery-restoration-1d81445
printf '%s\n' '48ee833a362f37732586548b0e35b6fcd83678bf72457f0e95071f27bf92307b  SHA256SUMS' | sha256sum -c -
sha256sum -c SHA256SUMS
test ! -e ATTEMPT_USED
test ! -e transaction.json
test ! -e evidence
test "$(id -u)" = 1000
test "$(systemctl --user show atlas-recovery-startup-diagnostic.service -p MainPID --value)" = 0
test ! -e /run/user/1000/systemd/user/atlas-recovery-startup-diagnostic.service
test ! -e /run/user/1000/systemd/user/atlas-sensor-recovery.service.d/99-atlas-snapshot-runtime.conf
install -m 600 atlas-recovery-startup-diagnostic.service /run/user/1000/systemd/user/atlas-recovery-startup-diagnostic.service
systemctl --user daemon-reload
systemctl --user start atlas-recovery-startup-diagnostic.service
ATLAS_ONCE
```

Command return is NOT a PASS: Type=exec starts the supervisor asynchronously.
Read result.json, cleanup.json (if failure), startup journal, evidence/health.json
and service identities afterward. Do not rerun on any error. If unit installation
or daemon-reload fails before launch, remove only the exact matching temporary
unit after confirming it is inactive; no Recovery start is allowed as cleanup.

## Preserved supervision and limits

Three preflight intervals and three observer intervals precede exactly ONE Recovery
start. Independent observation uses existing Dashboard HTTP and /proc/cgroups,
not Recovery, and creates no ROS/DDS node. Dashboard must stay available.
Strict admission CPU<75%, RAM<80%, temperature<70C. Existing continuous CPU>75%,
RAM>80%, temperature>=70C, E-STOP, zero commands, stationary encoders, fresh telemetry,
observer heartbeat and valid sampling-interval rejection remain unchanged.

The 150 ms attribution budget stops further scans; acquired counters are atomically
saved as explicitly partial. Valid aggregate CPU remains subject to the safety gate.
No missing counters are zero-filled. Selected groups and known Recovery PID have
priority. Interval and collector failures are not reported as proven CPU overload.

Supervisor RuntimeMaxSec=60, TimeoutStopSec=30, Restart=no; Recovery start deadline
8s; successful start observed for 20s. READY, PID, source hash, snapshot-disabled,
Astra OFF and unrelated service identities must pass before original policy is
restored and Recovery is left running. No automatic retry or restoration start.

## Exact abort / rollback

`systemctl --user stop atlas-recovery-startup-diagnostic.service`

ExecStopPost independently runs this package's `--cleanup`, including after timeout
or supervisor SIGKILL. On uncommitted failure it stops only Recovery, waits for
PID 0/no job, removes only its owned temporary Restart=no override and restores
original Restart=always with daemon-reload. Original production files were never
changed. On committed success cleanup leaves verified Recovery active.

If quiescence or ownership cannot be established, retain Restart=no and report
cleanup failure; do not remove the bound or start again. After the supervisor is
stopped, manual idempotent cleanup (only if required) is:
`python3 -B /home/jetson/project-atlas-migration/recovery-restoration-1d81445/recovery_startup_diagnostic.py --cleanup`

Only after cleanup/policy are verified and supervisor inactive, remove its exact
matching runtime unit and daemon-reload. Preserve package, ATTEMPT_USED, result and
evidence. Do not delete evidence to make another attempt possible.

## Remaining actual risks / approval

No fresh live safety claim: all checks must run immediately before the future start.
Startup CPU may genuinely exceed 75%; historical spike cause remains UNKNOWN.
Partial attribution cannot prove complete process attribution. Kernel blocking,
invalid sampling interval, storage failure or SIGKILL can still abort or lose the
in-flight sample; completed atomic evidence remains. Dashboard failure aborts.
Cleanup can leave Recovery stopped with Restart=no if it cannot safely quiesce.

Request approval for ONE bounded original-Recovery restoration using this package,
including temporary supervisor installation, user daemon-reload and Recovery-only
Restart=no override. No cameras, inference, movement, firmware changes or PR merge.
No additional benchmark or monitoring architecture is required.