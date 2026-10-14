# Stage20 installation failure investigation — 14 October 2026

**ROOT CAUSE UNKNOWN** for the original installer exit. **ROOT CAUSE CONFIRMED**
for lost error evidence. **FIXED IN SOURCE**, **TESTED OFFLINE**, **SANDBOX INSTALL
VERIFIED** within the qualifications below. **PRODUCTION INSTALL NOT AUTHORIZED**.
**PRODUCTION DEPLOYED: NO.** Recording remains OFF.

## Evidence and scope

Approved baseline: `663425653c4b99e6454502ca568415fa9db60934`.
The [original installation result](ATLAS_STAGE20_INSTALLATION_ONLY_RESULT.md)
records exit 1 before any payload, optional unit or backup appeared. The temporary
supervisor used `subprocess.run(check=True, capture_output=True)` and allowed the
exception to escape without persisting `stdout`/`stderr`. Its traceback retained
the command and exit code, but not the child exception. This loss was reproduced
with an intentionally failing child process, and the corrected evidence wrapper
preserved exit 7 and sanitized stderr.

The original child process has exited; its captured output is unavailable. The
retained supervisor and capsule, terminal failure report, scratch installation-file
listing and scoped user-journal traceback search did not recover it. No claim is
made that every system log was searched. No production retry was performed.

Current read-only package/hash/dependency/permission/resource/unit-parser checks
pass. That does not reconstruct the historical failure. A transient CPU threshold,
stale safety sample, timeout or permission failure is **unproven**. The original
abort cannot be classified as a legitimate safety refusal versus installer defect.
The error-reporting defect is confirmed independently. No safety guard was relaxed.

## Corrective changes

Implementation commit:
[`0d216ec387fdd2e433805feb311b2336534cd25e`](https://github.com/Dhruv0747/ATLAS/commit/0d216ec387fdd2e433805feb311b2336534cd25e)
on `agent/sync-developer-20261011`.

- `stage20_install_evidence.py` replaces reliance on outer-wrapper terminal output
  with exclusive mode-0600, flushed/fsynced JSONL records. It captures UTC time,
  named phase, package identity, child exit code, sanitized output/traceback,
  exact target states, write attempts and rollback results. It redacts common
  credential formats and never reads credentials or logs the process environment.
- Installation CLI requires a reviewed manifest SHA256 and a new evidence path.
  Missing arguments or manifest mismatch stop before installation. Existing logs
  are never overwritten. Errors are preserved before they propagate to the caller.
- Installer and whole-file transaction emit phase and rollback events. A failure
  of the evidence sink during installation cannot prevent attempted rollback.
  The original failing phase is retained separately from the subsequent rollback.
- The new evidence module is an installer companion, **not a production payload**.
  All nine runtime files, optional unit, default-OFF behavior, one-use capture grant,
  resource thresholds, live-hash checks and backup rules remain byte-identical.

Target net change and transient write attempts are reported separately. A rollback
can restore every target while retaining a backup and empty directories. If evidence
storage itself becomes unavailable, later log records cannot be guaranteed; rollback
still runs and the terminal exception remains a necessary fallback. Do not interpret
missing evidence as success.

Before: the outer wrapper showed only a `CalledProcessError`/exit 1.
After: manifest refusal and subprocess/registration failures retain the specific
phase, exception/exit, sanitized diagnostic text and rollback outcome. The changes
improve diagnosis; they do **not** prove the unknown historical trigger is repaired.

## Tests and rehearsal

PC: `unittest discover -s project_atlas/tools/diagnostics -p 'test_stage20*.py'`
ran **84 tests: 83 passed, 1 skipped** (native unprivileged POSIX permissions).
Jetson: **19/19 targeted tests passed**, including that actual chmod-based permission
refusal. No ROS subscriber, recorder, actuator, production manager reload or restart
was invoked by these tests.

| Case | Result and classification |
| --- | --- |
| Correct package into fake root | All nine installed hashes match; activation/autostart false |
| Missing approval | Refused before writes; valid authorization guard |
| Wrong manifest / payload / installer hash | Refused; manifest failure persisted with phase |
| Missing dependency | Refused; valid drift guard |
| Permissions | Injected EACCES and actual Jetson unprivileged directory refusal pass |
| Existing target / repeated installation | Unrelated contents preserved; duplicate unit refused |
| Low disk | Injected below-2-GiB reserve refused; guard unchanged |
| Resource threshold | CPU 76% fixture refused; 75% maximum unchanged |
| Registration failure | Injected failed reload restores payload and optional-unit baseline |
| Partial installation | Failure on third copy restores earlier copies, preserving evidence |
| Evidence sink failure | Rollback proceeds even when rollback event writes also fail |
| Child failure / secret redaction | Exit, phase, stderr and traceback retained; tested credentials redacted |
| Existing evidence destination | Refused without overwriting old evidence |

Native persistent rehearsal directory:
`/tmp/atlas-stage20-install-audit-lt7tOutp/`.
`result.json` and `rehearsal.jsonl` retain the rehearsal result and event ledger;
raw logs are not committed. Fake-project backup:
`fake_project/data/backups/20261014T141133Z-stage20-66057149f32646b9977a493f5f8851fd/`.

The exact candidate unit passes native `systemd-analyze --user verify`.
`systemctl --root <fake-system> --global is-enabled` reports **static**. There is
no `[Install]` section and no autostart link. The production manager was never
contacted for mutation: **daemon-reload was simulated** in the sandbox. Thus this
is verified file installation/rollback plus native offline unit validation, not a
claim that live unit registration has already passed. No start command was issued;
no optional process or recording existed. An evidence sentinel retained its exact
bytes through installation, duplicate refusal and rollback. Backups remain available.

## Package identity

Original qualified capsule remains untouched:
`/tmp/atlas-stage20-complete-EW8kVA07/public_capsule_v5`.
Original manifest SHA256:
`8f805a9958291a9ed685aeb0fe6a4fa5a662b3bdf8c73dfbdcec3935449b7e32`.

Proposed retry capsule: `/tmp/atlas-stage20-install-audit-lt7tOutp/candidate`.
Manifest SHA256:
`a99fc59d5860b40bfe1b1945fdcc721580e367e820ed5d700c50c770b9e8aa1e`.
The [retry manifest](ATLAS_STAGE20_INSTALL_RETRY_MANIFEST.json) records every
runtime and installer file hash. Runtime source remains
`aa0bb06cde7cdabdbf80ae382024e8954173efb1`; revised installer source is commit
`0d216ec387fdd2e433805feb311b2336534cd25e` above. Its `installer_revision` metadata
marks renewed approval as pending. No owner approval is inferred from the manifest.

| Installer file | Exact candidate SHA256 |
| --- | --- |
| stage20_public_install.py | `1f13835d355644a6d4c711123696226034f54621be871ad108ec57a908e7ed1f` |
| stage20_public_package.py | `9fb252f302f496cacae0d1fb6d0b2c5b7846078a7202c437dd4feb7401f36f77` |
| stage20_package_transaction.py | `f8ea5b77aa5551f972ced9979f61ffe450f74b75ea4b9cce3c52db1acfbb8ff6` |
| stage20_install_evidence.py | `5090bf2759cd38a913b37c8a77b77e2e2842c614ff7507f688f1ae31e0986032` |
| stage20_install_guard.py | `7553457b8713c65cfe3fb18996da585640eeab85f54bf64d254b76f8f2d30954` |
| stage20_public_preflight.py | `36b8bcc2f90b44cd3d46add5610f357c7ea765d22155117a7b676a6417f3fa2a` |

The persistent successful native rehearsal used this exact candidate manifest and
files. Failure fixtures changed only isolated copies or injected declared failures.
The manifest's historical collector qualification still describes the unchanged
runtime; the new installer qualification is the test evidence in this report.

## Current production read-only verification

14 October post-rehearsal: stop latched, command zero, Nav2/exploration inactive.
CPU **70.6%**, RAM **68%**, temperature **59°C**, free **394,567,008,256 bytes**.
Limits remain CPU <=75%, RAM <=80%, temperature <=70°C and free >=2 GiB.
No motor test is proposed, so charger disconnection was not required or requested.

All approved protected file hashes and dependency pins match; accepted maps,
EKF/Nav2 parameters and installation/backup directory permissions pass. The payload
directory, capture-output directory, optional unit and activation grant are absent;
there are no production Stage20 backup directories. No production install occurred.

| Service | PID | Restarts | Start monotonic timestamp |
| --- | ---: | ---: | ---: |
| atlas-ekf | 3234 | 0 | 32433038 |
| atlas-localization | 11868 | 17 | 558750640 |
| rover-base-telemetry | 3364 | 1 | 35518626 |
| atlas-cmd-vel-mux | 1913 | 0 | 17083677 |
| atlas-remote | 1963 | 0 | 17150268 |
| atlas-safety-status | 1977 | 0 | 17161349 |

These values match this investigation's initial check; the previously reported five
core PIDs/counters also match the original attempt. The actual motor service name
is `rover-base-telemetry.service`; `atlas-base.service` is absent, not a failed motor
owner. Optional unit remains not-found/inactive. No service restart, reboot, stop
release, calibration, map, estimator, steering or motor change was made.

## Exact next approval and procedure

**Wait for explicit approval to retry installation only of the candidate identified
above, feature OFF.** No production retry is authorized by the current instruction.
No drive, air lift or route recording is required from the owner.

After that approval, recheck the same fresh stop/command/headroom, protected hashes,
dependencies, service identities, free space, target absence and rollback paths.
Abort on any mismatch; do not tune thresholds or retry in a loop. Verify candidate
manifest and all installer hashes before executing its entrypoint. Select a fresh
exclusive evidence path in the preserved scratch directory. The required additional
CLI arguments are `--expected-manifest-sha256` with the digest above and
`--evidence-output` with that new path. Use installation approval only; omit both
activation flags. Do not reuse the old temporary supervisor against the old capsule.

The transaction preserves timestamped rollback metadata, writes only the nine new
payload files and optional user unit, and reloads unit definitions. It must not
start/enable recording or restart existing services. Compare installed hashes,
static/disabled plus inactive unit state, production PIDs/counters and map/config
hashes immediately afterward. Preserve all logs and backups. On a verified failure,
restore only this transaction's matching new files; keep diagnostic evidence.

Existing explicit rollback interface remains `--rollback <verified-backup-path>
--owner-approved-install`; it stops only the optional collector and restores its
own files. It must not be invoked against an unverified or unrelated backup.
The next approved attempt should retain its terminal output as well as the new
durable ledger, including rollback output. Recording activation and private
EKF/AMCL instrumentation remain separately unauthorized. Localization is unresolved.
