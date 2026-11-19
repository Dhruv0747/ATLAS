# Object Detection / read-only Target Tracking installation — FAIL, rolled back

One owner-approved installation attempt of commit
`52d6b153ddebceadd27f548dfec176ec13d2dd48` was performed on 2026-10-30.
No retry, camera activation, inference, motor/servo operation, firmware change,
controller change or PR merge was performed.

## Verification and outcome

All 16 reviewed artifact checksums passed on Jetson. SHA256SUMS SHA256:
`a75bbd94a2f6218be9170507ac1a1c6267cadcca03e401477a2bfb0373a086e1`.
The three live baselines exactly matched package rollback copies; seven additional
destinations were absent. All ten reviewed files were installed, with enabled=false.
Verified exact-byte backups were created before mutation.

Fresh preflight passed E-STOP latched, manual-only, zero commands, fresh LIVE
telemetry, zero encoder deltas, recorder OFF, Astra OFF/driver stopped and resource
limits. Initial read-only samples: CPU61.00–62.44%, RAM61.24–61.31%, maximum63.312C.
The transaction repeated admission immediately before installation.

Only rover-status-web was restarted. systemd reported restart completion before
the HTTP endpoint was ready. Immediate postflight raised connection refused and
triggered rollback. The rollback restart likewise returned before HTTP readiness,
so the initial result correctly recorded FILES VERIFIED with a health-check error,
not a full successful rollback health result.

An independent one-second resource sample also rejected CPU79.1453% (>75%).
Restart start monotonic22145.477145353; rejected sample22146.439868794;
systemctl return22147.613828001. Sample interval1.000281028s, RAM61.8452%,
maximum temperature63.312C. The HTTP exception was the reported primary exception;
the saved resource rejection independently prevents approval. No per-process
attribution or sustained-load claim can be made from this single rejected sample.
The resource sampler ceased on rejection; it does not cover the entire rollback.

## Rollback and subsequent read-only verification

All three original file hashes restored:

| File | Restored SHA256 |
| --- | --- |
| scripts/atlas_vision3d_web.py | 2551d6578aa9429ac8f4fd5ff35f2c16a185c3cd027fafc563b7fff339857190 |
| web/v2/vision3d.html | 6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57 |
| web/v2/vision3d.js | 82d846cd09570d53ef984adc97bf51bed4be4d0ab629bf33b2386544e9d9084e |

All seven new candidate files were removed and absence verified. Protected
atlas-/rover- service identities, active states and restart counts matched the
pre-install snapshot. Web PID2098 changed to182915, active, NRestarts0; journal
records the authorized installation restart and rollback restart only.

After rollback, homepage and Vision Lab returned HTTP200. Fresh safety preflight
passed, CPU60.34–63.12%, RAM62.0%, temperature maximum63.718C. Encoder telemetry
was LIVE/fresh with all four deltas zero; E-STOP remained latched, source STOPPED,
manual-only true, commissioning false, FlySky driving false and commands zero.
No Astra/OpenNI/vision-feature worker was found in the process inventory.

Camera summary is OFF but driver_stopped=false after web restart. Existing
RuntimeSession.status() returns only state/reason when child is None; existing
summary converts the missing driver_stopped field to false. This is a pre-existing
startup-status representation gap, not evidence that a camera was started.
Do not relabel that API boolean as a passed driver-stop check. No camera application
code was changed to work around it.

## Evidence and tests

Private full evidence, package, execution log and rollback backups:
`/home/jetson/project-atlas-migration/object-target-install-52d6b15/`.
Windows copy: sibling `work/object-target-install-evidence-52d6b15`.
Evidence manifest SHA256:
`c462b26c8d3b1a7dcc9792d7492df666057a016969994e0b5d4e90e493b7dea9`.
Single-use installer SHA256:
`20edda47e7e3b15ba0f3990044a04cfd05701d59e4a4677c657691876e8c0d03`.
Raw telemetry/logs/backups are retained privately and excluded from Git.

Package16/16 checks PASS; installer Python syntax and browser-verifier JavaScript
syntax PASS. Previous21 focused offline backend tests reused. New API and browser
functional checks NOT REACHED because postflight failed; no claim of API readiness
or inference performance. Restored routes were checked read-only.

## Next gate — NO-GO for a live Object Detection test

Backend is not retained. Prepare and offline-test bounded web HTTP readiness and
rollback-readiness handling, preserving fail-closed resource rejection and recording
the observer outage honestly. Preserve primary and secondary guard errors together.
Resolve the existing idle driver-status ambiguity using authoritative process
ownership, without camera activation or fabricated status. Investigate the recorded
restart CPU rejection before proposing a new installation. No thresholds may change.
Another deployment needs separate approval; the consumed attempt must not be rerun.
Only after a separately approved installation passes may one30s Object test be
proposed. No test is authorized by this report.

Restored Lab: http://192.168.1.16:8088/v2/vision3d . Existing white-glass/static
six-panel UI remains; no functional detection/target backend is deployed.
