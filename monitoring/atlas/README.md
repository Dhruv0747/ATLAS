# ATLAS LAN monitoring (Prometheus + Grafana): read-only

**Timestamp correction:** persistent activation was rolled back due to rounded Unix timestamps. The [offline fix and 86 focused test results](TIMESTAMP_FIX.md) are ready for review; no fixed exporter is active. The previous activation command must not be reused.

**Latest status (2026-10-30):** Ubuntu WSL Prometheus/Grafana are installed on localhost; the final five-minute exporter trial passed and cleaned up. Persistent supervision is implemented and tested offline, not activated. See [persistent/VALIDATION.md](persistent/VALIDATION.md) and [RUNBOOK.md](persistent/RUNBOOK.md). Earlier VM/pending statements below are historical snapshots superseded by this status. The optional supervisor manages only monitoring firewall/service lifecycle; exporter data access remains read-only.

Everything here only *reads*:
- The Jetson exporter has **no ROS node, no ROS subscriber and no camera access**. It sends no commands and answers 405 to POST, PUT and DELETE.
- Alerts only notify. Nothing here can move the rover or change its safety state.
- If the VM is offline, ATLAS runs exactly as before; the only effect is that scraping stops.

## What is collected (exporter `project_atlas/scripts/atlas_health_exporter.py`, every 15 s)

| Area | Metrics | Source |
|---|---|---|
| Jetson | CPU %, load, RAM, swap, disk, every readable thermal zone + max, GPU load %, GPU frequency | /proc, /sys (unreadable thermal zones are skipped, never 0) |
| Services | loaded / active / failed / restart counter for 17 units | `systemctl --user show` |
| Freshness | age, rate and STALE flag for lidar, motor_speed, encoder_health, odom, control_policy, joy, camera_info, imu, ultrasonic, radar, power, drive_pid, thermal | existing rover-status-web cache (`/api/status`), **no new subscribers** |
| Battery | BMS voltage, %, current; base voltage; Jetson power | same cache |
| Encoders | READY, fault count, checksum and write errors, link stale and recovery counters | `encoder_health` |
| Controls | E-STOP latched, selected controller, FlySky gate, teleop running, frame age, failsafe, frame lost, drive state, last drive-command age | `/api/manual_controller` |

**UNAVAILABLE (honestly not emitted):**
- **Pi camera FPS and dropped frames.** Would need a new camera subscriber; only CameraInfo metadata age is available; it does not prove image delivery.
- **Astra RGB/depth.** Not published on this rover; `atlas_source_available{source="astra"}` = 0.
- **GPU throttle flags.** Not in sysfs; watch the GPU frequency.
- **FlySky frame age** while the FlySky teleop is not running.

**Staleness and gaps:**
- A topic older than its limit is emitted with `atlas_topic_stale=1` and its real age.
- A missing source shows as `atlas_source_available{source}=0`, and its metrics are absent: **UNAVAILABLE** in Grafana, never 0.

## Jetson (exporter)

**Measured cost (2026-10-30):** about 0.010 s of CPU per collection (about 0.07 % of one core) and 18 MB RAM. The 5-minute before/after trial is in the PR.

1. **Firewall first:** allow TCP 9118 only from the VM IP, for example `sudo ufw allow from <VM_IP> to any port 9118 proto tcp`.
2. **Run it, bounded:**
   ```bash
   systemd-run --user --unit=atlas-health-exporter -p RuntimeMaxSec=300 -p CPUQuota=10% -p MemoryMax=64M \
     /usr/bin/python3 /home/jetson/project_atlas/scripts/atlas_health_exporter.py --bind 192.168.1.16
   ```
   This is not enabled at boot. Make it permanent only after the trial, with a separate approval.

## Ubuntu VM (Prometheus + Grafana)

1. Put the Jetson in `targets.json`: `[{"targets":["192.168.1.16:9118"],"labels":{"robot":"atlas"}}]`.
2. Create `grafana_admin_password.txt` (mode 600).
3. In this folder, validate first:
   ```bash
   docker run --rm -v $PWD:/etc/prometheus:ro --entrypoint promtool prom/prometheus:v3.5.0 check config /etc/prometheus/prometheus.yml
   docker run --rm -v $PWD:/etc/prometheus:ro --entrypoint promtool prom/prometheus:v3.5.0 check rules /etc/prometheus/alerts.yml
   ```
4. Start the stack: `docker compose up -d`.
5. Open Grafana at `http://127.0.0.1:3000` on the VM (use an SSH tunnel from Windows), dashboard **ATLAS HEALTH MONITOR**.

Ports bind to 127.0.0.1 only. Retention is 7 days / 1 GB. There is no Alertmanager: alerts show in Prometheus and Grafana but nothing is pushed.

**Dashboard:** `grafana/build_dashboard.py` generates `dashboards/atlas-health.json`. Edit the generator, not the JSON.

## Rollback

- **Jetson:** `systemctl --user stop atlas-health-exporter`. Nothing else to undo; no rover service is touched.
- **VM:** `docker compose down` keeps the data; `docker compose down -v` erases it.

## Jetson trial, 2026-10-30 17:29–17:40 (transient; it stopped itself)

| | Baseline (5 min, 60 samples) | With exporter (5 min, 56 samples) |
|---|---|---|
| CPU mean (range) | 60.7 % (59.4–61.9) | 60.5 % (58.8–61.7) |
| RAM mean | 60.7 % | 60.9 % (exporter about 11 MB) |
| Temperature mean / max | 62.34 / 62.53 C | 62.37 / 62.56 C |
| Topic age max: lidar, motor_speed, joy, encoder_health, camera_info | 0.60, 0.60, 0.10, 0.10, 1.10 s | 0.70, 0.60, 0.10, 0.10, 1.10 s |

- `/metrics` answered 200 with 188 lines at both checks.
- No measurable difference: everything is within the sampling noise.
- The exporter was not left running: no VM IP was available yet for the firewall rule.


## Review completion (2026-10-30)

Added signed BMS watts and raw M1–M4 encoder counts from verified existing cache keys; no calibration or encoder authority is inferred. Added Jetson watts, encoder READY, serial-write/recovery and drive-enabled panels. Missing/invalid safety booleans are omitted, never mapped to clear. Policy and FlySky status require finite nonnegative age <=1 s; stale values are omitted. Topic age validation rejects NaN, infinity, negative and boolean ages. Existing topic limits are respected for numeric metrics.

Availability and freshness now have separate mappings; current-value tables use instant queries. Dashboard generation is repeatable. CameraInfo is explicitly metadata, not actual frame delivery. No verified Astra frame-health source exists here, so its display remains UNAVAILABLE. Frequency changes alone do not prove throttling. Raw encoder counts are gauges, not monotonic counters or a motion-safety judgment.

Validation: 24 focused Python tests PASS in PC WSL; Prometheus 3.5.0 native promtool accepts config and 14 rules. Two synthetic rule scenarios PASS (70 C boundary, missing LiDAR/control policy; healthy negative case). Release binary verified against official release SHA256 manifest. For config validation only, absolute container paths were translated in an isolated temporary config. Production config is unchanged by that translation. Run `promtool test rules alerts.test.yml` from this directory.

Read-only live schema inspection confirmed cache fields on Jetson 192.168.1.16. No exporter installed, services restarted or camera/motion commands sent during this review. E-STOP was released in the inspected snapshot; no live trial was attempted. Existing trial figures above are historical author evidence, not a measurement of this revised candidate.

Deployment PENDING: no monitoring VM address/access was supplied or verified; PC WSL has no Docker. The checked-in targets file is intentionally a placeholder. Owner must provide the VM endpoint, configure its target/secret and restrict Jetson port 9118 to that VM before a separately approved exporter/stack trial. Native Grafana rendering, Compose startup, authenticated access and end-to-end scraping remain unverified. No notification transport/Alertmanager is configured. Monitoring alerts are informational, never substitutes for production safety guards.

Rollback: revert this candidate commit for repository changes; deployment rollback remains stopping only the optional exporter/monitoring stack as described above. No rover service or safety configuration changes are required.
# Persistent deployment preparation

The unchanged trial exporter now has an optional firewall verifier, stationary safety watchdog, bounded systemd units and inactive Windows/WSL startup preparation. See [persistent/RUNBOOK.md](persistent/RUNBOOK.md) for exact approval-gated commands, [validation evidence](persistent/VALIDATION.md) and [source hashes](persistent/SHA256SUMS). Offline validation passed; Jetson persistent activation and reboot tests remain pending. No production activation or PR merge is implied.
