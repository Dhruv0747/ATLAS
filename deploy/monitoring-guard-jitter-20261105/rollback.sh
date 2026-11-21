#!/bin/bash
set -euo pipefail
G=/usr/local/libexec/atlas-monitoring-guard.py
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ -e $G.before-jitter-20261105 ] || { echo "no backup found"; exit 1; }
install -o root -g root -m 0644 $G.before-jitter-20261105 $G
systemctl restart atlas-monitoring-watchdog atlas-monitoring-exporter || true
sha256sum $G
