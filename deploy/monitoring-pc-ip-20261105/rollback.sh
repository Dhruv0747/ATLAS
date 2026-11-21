#!/bin/bash
set -euo pipefail
G=/usr/local/libexec/atlas-monitoring-guard.py; N=/etc/atlas-monitoring/atlas-monitor.nft
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
systemctl stop atlas-monitoring-exporter atlas-monitoring-watchdog || true
install -o root -g root -m 0644 $G.before-pc-ip-20261105 $G
install -o root -g root -m 0644 $N.before-pc-ip-20261105 $N
nft delete table inet atlas_monitor 2>/dev/null || true
systemctl restart atlas-monitoring-firewall atlas-monitoring-watchdog atlas-monitoring-exporter
