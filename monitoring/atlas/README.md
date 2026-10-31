# ATLAS LAN monitoring (Prometheus + Grafana): read-only

**Current status (2026-10-31 12:36 IST, verified):**
- **PC stack RUNNING:** Prometheus 3.5.0 (`127.0.0.1:9090`) and Grafana 12.1.0 (`127.0.0.1:3000`, health `database: ok`), both in the owner's Windows WSL2 Docker. They are deliberately bound to localhost and not published on the LAN.
- **Scrape target:** job `atlas-jetson` → `http://192.168.1.16:9118/metrics`, 15 s interval, 3 s timeout, from `/etc/prometheus/targets.json`. Prometheus retention is 1 week / 1 GiB.
- **Proven path:** Prometheus recorded `up=1` from 2026-10-30 20:50 to 21:45 IST, while the Jetson port-9118 firewall admitted only 192.168.1.6. WSL scrapes therefore reach the Jetson from source 192.168.1.6.
- **Jetson side STOPPED, target `down`** (connection refused): the monitoring watchdog latched a fault on 2026-10-30. Recovery attempt 1 (`-20261031`) failed closed. The single-use attempt 2 (`-20261031-2`) is approved but not yet executed. See [RECOVERY_TRANSACTION.md](persistent/RECOVERY_TRANSACTION.md).

**Grafana dashboard UI: COMPLETE / PASS (2026-10-31 13:47 IST, owner's browser).**
- Deployed file: `/opt/atlas-monitoring/grafana/dashboards/atlas-health.json`, SHA256 `2b598f1c…6a3e`, from commit 8e3c785. Backup: `atlas-health.json.bak-20261031-pre-8e3c785`.
- Verified: 40 panels, 30 s refresh, readable series names (0 raw `metric{…}` labels), UNAVAILABLE shown while the exporter is off, history kept with gaps left visible. Loaded by file provisioning with no restart.

**Monitoring recovery: OPEN.** The Jetson exporter is OFF and the watchdog fault latch is retained. See [RECOVERY_TRANSACTION.md](persistent/RECOVERY_TRANSACTION.md).

*Superseded 2026-10-30 status, kept for history:* timestamp-fixed persistent monitoring is ENABLED and ACTIVE. The guarded five-minute activation and evidence checksums passed. See [final live review](persistent/FINAL_REVIEW_20261030.md) and [activation measurements](persistent/TIMESTAMP_RETRY_RESULT_20261030.md). Reboot recovery is PENDING; Windows logon task is not registered. Earlier dated trial/preparation sections below are historical, not current deployment instructions.
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

Use only the reviewed [persistent runbook](persistent/RUNBOOK.md). Do not start a second exporter or rerun consumed activation commands. An allow-only UFW rule does not restrict an ACCEPT-default firewall; the deployed dedicated nft table explicitly drops every non-approved source on TCP9118.
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

- **Jetson persistent monitoring:** use the ordered root helper `sudo python3 -I -B /usr/local/libexec/atlas-monitoring-guard.py rollback`; it stops/verifies the exporter before removing only owned protection. See RUNBOOK.md. The historical user-unit stop command does not stop the current system service.
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

*Superseded 2026-10-31: the PC stack is deployed and running in Windows WSL2 Docker; see the current status at the top. The original note is kept for history:* Deployment PENDING: no monitoring VM address/access was supplied or verified; PC WSL has no Docker. The checked-in targets file is intentionally a placeholder. Owner must provide the VM endpoint, configure its target/secret and restrict Jetson port 9118 to that VM before a separately approved exporter/stack trial. Native Grafana rendering, Compose startup, authenticated access and end-to-end scraping remain unverified. No notification transport/Alertmanager is configured. Monitoring alerts are informational, never substitutes for production safety guards.

Rollback: revert this candidate commit for repository changes; deployment rollback remains stopping only the optional exporter/monitoring stack as described above. No rover service or safety configuration changes are required.
# Persistent deployment preparation

The unchanged trial exporter now has an optional firewall verifier, stationary safety watchdog, bounded systemd units and inactive Windows/WSL startup preparation. See [persistent/RUNBOOK.md](persistent/RUNBOOK.md) for exact approval-gated commands, [validation evidence](persistent/VALIDATION.md) and [source hashes](persistent/SHA256SUMS). Offline validation passed; Jetson persistent activation and reboot tests remain pending. No production activation or PR merge is implied.

