# Ubuntu-only installation result — 2026-10-30

Historical installation snapshot. Subsequent owner-approved network verification identified source 192.168.1.6, and the final five-minute trial passed with verified cleanup. Current persistent-preparation status and pending activation gates are in persistent/VALIDATION.md; the original pending statements below describe installation time only.

PASS: Docker Engine 29.9.2 and Compose 5.6.1 installed from Docker's signed Ubuntu repository; hello-world passed. No existing packages removed or upgraded. Prometheus 3.5.0 and Grafana 12.1.0 deployed from PR #13 under /opt/atlas-monitoring. No Jetson installation, service restart, firmware, E-STOP or controller change.

PASS: Compose config, native Prometheus config (14 rules) and two synthetic alert scenarios. Prometheus readiness HTTP 200; Grafana database healthy and authenticated dashboard API HTTP 200. Browser login and ATLAS HEALTH MONITOR rendering verified; 40 provisioned panels, datasource atlas-prom -> http://prometheus:9090.

Windows URLs:
- http://127.0.0.1:3000/d/atlas-health-monitor/atlas-health-monitor
- http://127.0.0.1:9090

Both container ports bind only 127.0.0.1; Windows LAN-IP requests to 192.168.1.6:3000 and :9090 failed. No public forwarding or firewall rules added.

Admin username: admin. Random password remains only in Ubuntu /opt/atlas-monitoring/grafana_admin_password.txt, owned by Grafana UID 472, mode 0400 (root can read). Never committed or printed in the report. Owner retrieval from PowerShell: `wsl -d Ubuntu-22.04 -- cat /opt/atlas-monitoring/grafana_admin_password.txt`.

One post-start snapshot: Prometheus 0.16% CPU / 23.71 MiB; Grafana 0.22% CPU / 106.1 MiB, each capped at 512 MiB. This is not a sustained-load benchmark. Prometheus retention remains 7 days / 1 GB.

WSL lifecycle: systemd alone did not keep the distro alive between CLI sessions. Started a hidden Windows wsl.exe process, PID 9620, running `sleep infinity` in Ubuntu-22.04. No scheduled task or Windows boot-time autostart added. Keep this session/PC running; sleep, logout or reboot may interrupt monitoring. Verify PID identity before stopping it; PID may be reused.

NAT: confirmed internal 172.31.250.86 via 172.31.240.1; Windows Wi-Fi 192.168.1.6. Jetson-visible source is EXPECTED to be 192.168.1.6 but NOT directly verified. Windows NAT management queries returned invalid class; no Jetson command was run because this authorization limits actions to PC/Ubuntu. Receiver-side read-only connection evidence remains needed before choosing the future exporter firewall source.

Expected pending state: exporter target 192.168.1.16:9118 is DOWN (connection refused), dashboard metrics UNAVAILABLE. No exporter activated. Next gate: separately approved read-only NAT-source verification and optional Jetson exporter/firewall deployment after fresh safety/resource checks. No PR merge.

Rollback: in Ubuntu, `cd /opt/atlas-monitoring && docker compose down` stops only the monitoring stack and preserves volumes. Stop the specifically identified keep-alive process if no longer needed. Docker installation may be retained for other PC work; do not remove shared dependencies or data blindly.

Evidence: /opt/atlas-monitoring/installation-verification.json; local browser screenshot work/grafana-installed.png. No secret included.

Image digests:
- prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996
- grafana/grafana@sha256:6ac590e7cabc2fbe8d7b8fc1ce9c9f0582177b334e0df9c927ebd9670469440f

Installed file SHA256:
- docker-compose.yml: 118bf10ff99f95c3123aa58368d56076b1dd44a1fdfd3ec32f9f3995ed822957
- prometheus.yml: 9796b57f954f24f62df39046a114bf136f853eec02190d52add8ef90f73f083d
- alerts.yml: 07dd8166f790b0648e115d04467fef58ee1e85dcce7d0f2fe842f503eefb6e26
- grafana/dashboards/atlas-health.json: e7a79fd68d243da7da09c70234fc2f3d249617d37da8f7f0e650c91c95719da3
