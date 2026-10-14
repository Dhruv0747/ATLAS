# Stage20 activation evidence correction — 14 October 2026

## Latest deployment — 14 October2026 22:57 IST

Owner-approved installation-only from exact commit e35006a completed. Status:
**DEPLOYED AND VERIFIED (tooling only), recording OFF**. The source-only statements
below describe the preceding development stage, not current deployment status.
Installed in `/home/jetson/project_atlas/tools/stage20_activation_supervisor_e35006a`.
Exact Git-blob SHA256 (not Windows working-copy CRLF bytes):
- stage20_activation_evidence.py: `88dc0aa66e89e20e18d6058225e6a2345d99e2702ee4f8eb3f48bc4e630d960b`
- stage20_live_capture_supervisor.py: `ed53570078ff715855d2416733ca74e328d2d57bf2c12e20e23ecf2365cd9945`
- stage20_install_evidence.py: `5407a3a648be19db960f24bf36ba5a246a16a928b141bbcc261d8a739dda98b9`

Archive SHA256 `77f3aa4ce9087eaab5653bc217df5e6e69c1f1089f0839e30c3e12f5822de5b6`.
Fresh pre/post installation admission passed unchanged75% CPU safeguard. Postflight
CPU68.60,71.35,68.98,68.97,67.48%; RAM68%,58C,394320609280 free bytes.
Stop latched, commands zero, commissioning false. Installed recorder capsule hashes,
protected production files and service PID/start/restart identities unchanged.
No grant, recording, production restart, reboot, autostart or motion.
No-approval supervisor invocation refused before any action. Installed evidence
module preserved a synthetic76.123% refusal exactly in durable JSONL (fixture, not
an actual CPU measurement). Future runtime activation remains separately approved.

Backup/source archive, exact manifest, measurements and durable event/result files:
`/home/jetson/project_atlas/data/backups/supervisor-e35006a-834bb41002014f03aa33a095819ba060`.
Target previously absent; rollback is to move only this verified new tooling
directory into that backup and stop using it, preserving evidence. No production
restore or service restart required. Existing temporary manifest/probe dependencies
must be rechecked before any separately approved invocation.

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
