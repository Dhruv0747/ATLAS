# ATLAS LAN monitoring — repository implementation, NOT live deployed

All components are optional and read-only. No ROS publishers, camera subscriptions, raw depth processing, motor commands, firmware flashing, service restarts, or changes to E-STOP, watchdog, control mux or RC fallback.

## Jetson
First check deployed service states and collect a 5-minute baseline. Confirm a private Jetson LAN IPv4 and allow port 9118 *only* from Ubuntu VM source IP. Then from repository checkout:
```bash
python3 -m py_compile project_atlas/scripts/atlas_health_exporter.py
python3 project_atlas/scripts/atlas_health_exporter.py --bind YOUR_JETSON_LAN_IP
```
Run as standalone optional process only; no auto-start installation. Exporter collects /proc memory, disk, thermal and limited systemd status. It returns 503 when collection is unavailable or stale, 404 on non-metrics paths. It does not issue commands. If VM is offline, only outbound scraping stops; rover remains independent.

## Ubuntu VM
Replace placeholder in monitoring/atlas/targets.json. Create a strong-password file at monitoring/atlas/grafana_admin_password.txt and chmod 600. In monitoring/atlas:
```bash
docker compose config --quiet
docker compose up -d
```
Grafana: http://127.0.0.1:3000 (on VM). Prometheus: http://127.0.0.1:9090. Use SSH tunnel for Windows-host access, not public binding. Dashboard is 'ATLAS Health — read only'. Retention is 7 days or 1GB, memory bound 512MB per server container. No Alertmanager configured; alerts are evaluated locally but no notifications are delivered.

## Known gaps
CPU usage, GPU usage/throttling, camera FPS/drop/disconnect, LiDAR/MCU freshness, FlySky SBUS/Xbox/active control/command age, ROS graph status, battery voltage and encoder faults are not yet sourced from authoritative live collectors. Missing measurements remain absent; don't present them as zero. Service active is not proof of sensor health. The 75C alert and other example thresholds require confirmation against ATLAS deployed limits and baselines, not safety controls. 15-second scrapes won't capture every brief event; preserve existing counters and journal/rosbag evidence.

## Verification gates, not yet completed
- Validate with promtool check config and promtool check rules in VM.
- Check Grafana dashboard sources, no-data display and time alignment.
- Measure matched before/after idle samples: Jetson CPU, RAM, temperature, camera FPS/drops and ROS response.
- Verify LAN source-IP firewall, simulated VM/network loss, recovery and unchanged rover safety.
- Check real deployed endpoint and service/unit names before declaring coverage.

## Rollback
Stop the optional Jetson exporter process. VM: docker compose down (data preserved), or docker compose down -v (data erased). No critical rover service needs restart.
