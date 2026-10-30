# Timestamp-fixed persistent activation: 2026-10-30

## Observed result

One owner-authorized attempt ran using source b1946bd204584b106c950ce9f9f4c06315b7fc1d and the single-use wrapper prepared in 10141f05faee2e4064abd60064ee91cad284d505. No retry was performed.

At 20:50:34 IST, the exporter was ENABLED and ACTIVE, watchdog ACTIVE, both with NRestarts=0; the independent rollback timer was inactive. This matches the wrapper's acceptance path. Owner-terminal retrieval subsequently confirmed result PASS, persistent ENABLED_ACTIVE and evidence checksums PASS. Grafana PC verification was completed separately as documented below; the immutable wrapper result retains its PENDING PC verification label.

## Verified deployment

All six installed file hashes match the staged manifest:

| File | SHA256 |
|---|---|
| /opt/atlas-monitoring-exporter/atlas_health_exporter.py | 0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d |
| /usr/local/libexec/atlas-monitoring-guard.py | f529dcc643d4745ced5191f303ed30a7dcaf64302823a45baa2465275d387d13 |
| /etc/atlas-monitoring/atlas-monitor.nft | 6453561917e523b527ed6810e1965c774b68751ef69e0ae2c7177056bd1b44e9 |
| atlas-monitoring-exporter.service | efb9dc035ed3c121a246f4d9bb78fdfeee18e3af4b3c7791788f63f69fe98297 |
| atlas-monitoring-firewall.service | cb7f3734a8269b0a5c9da4c8af3d36af611ad0ea81f6a9d2ea6596216b386df6 |
| atlas-monitoring-watchdog.service | 31cf0a563aa0e8b4fa8a56efc3c68d755310ac5baafeb2126a610acc7c72e9c1 |

Listener: 192.168.1.16:9118, exporter PID112521. Guard PID112457. Firewall retains the reviewed source restriction 192.168.1.6/32. Guard verifies exact rules each observation. CPU75%, RAM80%, temperature70C policy unchanged.

## Grafana and freshness

Authenticated Grafana datasource queries at epoch1793373634.739–1793373634.760:

- Prometheus target up=1.
- Observation age12.576731204986572 seconds (not the erroneous 38 minutes).
- CPU61.96257518378259%, temperature63.312C, E-STOP latched=1.
- AtlasTelemetryStale alert result empty.

Dashboard: http://127.0.0.1:3000/d/atlas-health-monitor/atlas-health-monitor (Windows/WSL host only). Live datasource correctness verified; no claim of a new screenshot-based review of every panel. Prior 25-second monitoring-server outage independence evidence is reused, not repeated.

## Actual resource measurements

At host uptime14639.81 seconds:

- Exporter active since14333.203729: cumulative cgroup CPU1.180209 seconds, approximately0.385% of one CPU core; memory11735040 bytes (11.19MiB).
- Watchdog active since14329.576210: cumulative cgroup CPU3.415493 seconds, approximately1.101% of one CPU core; memory10665984 bytes (10.17MiB).
- Combined approximately1.49% of one core; these cumulative figures include startup CPU and are not whole-machine percentage-point overhead or a matched causal baseline comparison.
- Preflight CPU samples62.4204%,59.3537%,61.0282%; RAM62.4288–62.5531%; temperature63.562–63.718C.
- Verified root evidence: baseline60 samples, active290 samples over the bounded five-minute window (processing adds to nominal one-second sampling cadence).

| Measurement | Baseline average / peak | Active average / peak |
|---|---|---|
| Whole-Jetson CPU | 61.59668% / 66.83250% | 61.87556% / 71.31012% |
| RAM | 62.45925% / 62.59204% | 61.35246% / 63.00842% |
| Temperature | 63.60738C / 63.781C | 63.59727C / 63.812C |

Observed CPU-average increase:0.27887 percentage points. Background workload is not controlled, so this is not a causal estimate of exporter-only cost; use the cgroup figures above for direct process accounting. RAM-average decline likewise is not claimed as an optimization. All captured samples passed the unchanged guards.

## Safety and remaining evidence

Direct postflight user-service observations: dashboard PID2098, command mux PID1949, base telemetry PID3258, each active with zero restarts and unchanged identity. The wrapper compares all protected atlas/rover user services before acceptance. Continuous watchdog safety checks remained active; no intentional critical restart, movement, camera start or firmware change was performed.

Evidence: /var/lib/atlas-monitoring-timestamp-retry-20261030 (root-only). Read-only helper summarize_timestamp_retry.py checks stored SHA256 entries and prints result/phase measurements. Two simulated checks passed: valid summary and tamper rejection. No production change made by this helper.

Local-terminal command to retrieve final evidence:

```sh
sudo python3 -I -B /home/jetson/project-atlas-migration/monitoring-timestamp-retry-b1946bd/summarize_timestamp_retry.py
```

Reboot persistence remains UNTESTED. No reboot or PR merge authorized/performed. Actual denied-source path was covered by prior isolated tests; no new remote denied-source device test claimed.

## Rollback (not executed)

```sh
sudo python3 -I -B /usr/local/libexec/atlas-monitoring-guard.py rollback
```

Reviewed helper disables/stops exporter, stops watchdog, proves listener absent, then removes only owned firewall protection. It retains protection on ambiguous shutdown. See RUNBOOK.md for independent rollback. Do not rerun activation automatically.
