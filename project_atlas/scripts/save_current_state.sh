#!/usr/bin/env bash
set -euo pipefail

stamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p /home/jetson/project_atlas/backups
tar -czf "/home/jetson/project_atlas/backups/web_control_dashboard_saved_${stamp}.tgz" \
  /home/jetson/project_atlas/scripts/atlas_status_web.py \
  /home/jetson/project_atlas/scripts/rover_dashboard.py \
  /home/jetson/.config/systemd/user/rover-status-web.service \
  /home/jetson/.config/autostart/rover-dashboard.desktop \
  2>/dev/null
echo "/home/jetson/project_atlas/backups/web_control_dashboard_saved_${stamp}.tgz"
