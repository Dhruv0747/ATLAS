# Bounded Dashboard and telemetry Python profiling

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
