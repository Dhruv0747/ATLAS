# Stage20 activation evidence correction — 14 October 2026

**ROOT CAUSE CONFIRMED / ORIGINAL REFUSAL VALUE UNKNOWN / FIXED IN SOURCE /
TESTED OFFLINE / NATIVE VALIDATED (evidence/cleanup logic). NOT DEPLOYED;
NOT RECORDING VERIFIED.** Resource admission itself is not fixed or waived.

## Confirmed defect

Read-only examination of retained attempt directory
`/tmp/atlas-stationary30-avHg8uSb/live-once-800a9dc29463462fa4363642622fb0ad`
found empty monitor.jsonl (0 bytes), production baseline3821 bytes, recovered
result284 bytes. Supervisor called installed `check()` before logging its response;
the validator emitted a generic resource error. Its finally block called `check()`
again before writing result.json, masking primary failure and preventing final
report generation. No raw rejecting value exists in retained evidence. CPU, RAM
or temperature causality is UNKNOWN; earlier/later values cannot recover it.
No collector/grant existed. This was supervisor reporting, not a collector crash.

## Smallest source correction

`stage20_activation_evidence.py`: separate whitelisted observation from evaluation.
Unique exclusive0600 JSONL, UTC timestamp, fsync/flush measurement BEFORE validation,
exact failed field/value/limit, exception/traceback and phase. Preserve independent
/proc/stat CPU values and actual monotonic sampling intervals, cached CPU, RAM,
temperature, free space, policy/command ages, authorization and missing sensors.
Thresholds remain75% CPU,80% RAM,70C,2GiB free,2s safety freshness, latched stop,
zero commands and unarmed commissioning. Dashboard resource measurement age is
explicitly UNKNOWN if upstream omits it; HTTP response age is not substituted.

Sanitized stderr fallback emitted before disk writes; if fsync/write fails admission
fails closed. No guarantee is claimed if both disk and terminal sinks fail. Terminal
must be captured by the future caller. Final observers are individually guarded;
secondary exceptions cannot replace primary error. Final report write failure leaves
durable journal record and terminal fallback. Reuses existing sanitizer.

`stage20_live_capture_supervisor.py`: tracked correction of the failed ad-hoc wrapper,
uses the journal for each resource decision, captures sanitized subprocess stdout/
stderr and timeout output, records sensor preflight, separates final observation
from mandatory admission, tracks grant/start/cleanup state. Explicit one-capture CLI
approval required before actions. Existing exact package, stop/autonomy, quota,
single-use grant and collector guards retained. This is future supervised tooling,
not an installed service. No change to installed collector or75% runtime safeguard.

Owned grant cleanup verifies exclusive inode identity; partial JSON writes can be
revoked even if archiving fails. Changed/unrelated files are never deleted. Existing
bags/backups are untouched. A start attempt is conservatively marked before service
start so an ambiguous subprocess outcome takes the collector-stop cleanup path.

## Focused deterministic tests

18 tests passed on PC (0.152s) and native isolated Jetson (0.037s). Covers:
CPU77.123%, cachedCPU81.2%, RAM81%,71C, disk100bytes, stale policy3s,
unlatched stop, nonzero command, missing scan, missing/invalid authorization,
valid admission without hardware, fsync failure, final-report failure, secondary
observer failure, unique/sanitized outputs, partial owned grant and unrelated grant.
Each rejection retains the original sample before evaluation and exact field;
write failure preserves sanitized fallback. Tests create no service operations.
Wrapper syntax compiled; full live service lifecycle was NOT executed or claimed
validated. Earlier native collector/one-use tests are reused, not rerun.
Native test source only copied into existing isolated scratch; no production code
was installed. No live admission retry or activation performed.

## Current state and deployment preparation

Read-only post-test checks: installed five upgraded hashes unchanged; no grant;
collector static/inactive PID0/restarts0; policy STOPPED/latched, commissioning
false, commands zero, fresh0.1s. No restart, movement, map or estimator change.

Minimal tooling package: the two new supervisor files plus existing sanitized
evidence helper; pin exact Git commit bytes when preparing approved deployment.
No installed production file needs modification. Deploy to a NEW dedicated
operator-tool directory after separate approval, never overwrite the failed
evidence directory or installed capsule. Verify package hashes and Python imports;
keep no autostart or background process. Rollback is stop using that tool directory;
preserve all evidence. Existing ad-hoc wrapper is retained for forensics, not reused.
Deployment preparation does not authorize the `--owner-approved-one-capture` flag.

Remaining approval: permission to deploy corrected supervisor-only tooling, then
separate permission for one bounded recording under fresh checks. No retry now.
Exact resource refusal handling is corrected; actual production headroom and
stationary recording safety remain unverified. Historical EKF/AMCL initialization
gap and moving-localization problem unchanged. Git commit provided in handoff.
