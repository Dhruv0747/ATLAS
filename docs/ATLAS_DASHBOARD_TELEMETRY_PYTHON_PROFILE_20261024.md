# Bounded Dashboard and telemetry Python profiling

## Follow-up: owner attempt aborted; offline correction

The owner executed the original staged package. Evidence `evidence-yucgejc9`
contains only result.json (364 bytes) and empty telemetry.jsonl; no Python profile.
The first invocation aborted before sampling; shell `&&` prevented telemetry.
Confirmed cause: the wrapper added short name `rover-status-web` to G.UNITS,
but systemd returns canonical `Id=rover-status-web.service`. Read-only systemctl
confirmed this with PID 94624, NRestarts 0, active state. The strict parser
correctly rejected an unrecognized identity. This is a diagnostic wrapper bug,
not evidence of a production service or CPU fault.

Offline correction changes ONLY that protected-unit name to its canonical form.
The helper's separate Dashboard target lookup intentionally still uses its
existing short-name key; no helper or production parser changes. Six Linux
tests pass, including reproduction of the exact original failure, acceptance
of all eleven canonical IDs and rejection of missing, duplicate or unknown IDs.
The original three tests checked configuration but missed parser integration.
The corrected wrapper hash is in the updated manifest. It has NOT been copied
to Jetson or executed under this offline-only request. The staged original is
still faulty: do not rerun it. Next action requires staging this diagnostic-only
correction and a new owner-run capture. No CPU savings can be inferred from this
aborted run; previous native profiles do not establish Python hot functions.

All production features, services and limits remain unchanged. No install,
restart, camera activation, movement or retry occurred. Failed evidence remains
on Jetson; rollback is simply retaining the previous diagnostic package, never
changing production files. The preparation record below describes the original
package; its command must not be rerun until the corrected package is staged.

Prepared, not executed. No production installation or service restart.

The ranked native capture identified substantial Python execution but could not
name Python functions. Its whole-system observer also consumed considerable CPU.
This diagnostic reuses the hash-pinned single-PID observer instead: Dashboard,
then base telemetry, sequentially. Each capture uses py-spy at 20 Hz for 10 seconds,
GIL-held frames, thread tags, nonblocking reads and no local-variable capture.
This does not measure GIL-released native work; correlate with retained native
evidence rather than treating Python sample percentages as whole-Jetson CPU.

Each invocation independently checks current service identity, exact production
hashes, Astra OFF, resource measurements, stop state, commands, freshness and
all eleven protected service identities. CPU is measured/report-only solely for
this diagnostic. RAM 80%, temperature 70 C and all production limits remain
unchanged. Five baseline and five postflight samples bound observer comparison.
No ROS participant is added. Each evidence directory is private and unique.

## Owner command

Keep ATLAS stopped. The second command runs only when the first returns success.
Each wrapper has a 45-second outer bound; the owned py-spy child has its own
13-second timeout and cleanup. No automatic retries. Password entry is local.

```bash
set -o pipefail; cd /home/jetson/project-atlas-migration/dashboard-telemetry-python-20261024 && sha256sum -c SHA256SUMS && sudo /bin/bash -c '/usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B dashboard_telemetry_cpu_once.py dashboard --diagnostic-cpu-report-only && /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B dashboard_telemetry_cpu_once.py telemetry --diagnostic-cpu-report-only' 2>&1 | tee -a launch-output.log
```

## Validation and boundaries

Three Linux unittest cases pass: strict argument/target allowlist; both target
configurations, inherited integrity/guard setup, finite CPU validation and bounded
Python command; corrupt helper rejection before execution. Live read-only hashes
confirmed for Dashboard, yahboom_base, voice, safety, white-glass CSS and guards.
Package hashes are in dashboard_telemetry_SHA256SUMS. The reviewed helper is
unchanged. No CPU savings or completed live capture is claimed.

Files: new fixed-target wrapper, three-case test, manifest and this plan;
README/CHANGELOG links. Stage only in the migration diagnostic directory.
Rollback requires no production restoration: this package has no service,
autostart or production configuration. Preserve evidence for analysis.
