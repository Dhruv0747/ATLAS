#!/usr/bin/env bash
set -euo pipefail

stamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p /home/jetson/project_atlas/backups
cp /home/jetson/project_atlas/scripts/rover_dashboard.py "/home/jetson/project_atlas/backups/rover_dashboard_before_logo_${stamp}.py"
mv /home/jetson/project_atlas/scripts/rover_dashboard.py.new /home/jetson/project_atlas/scripts/rover_dashboard.py
pkill -9 -f /home/jetson/project_atlas/scripts/rover_dashboard.py 2>/dev/null || true
nohup bash -lc 'sleep 2; source /opt/ros/humble/setup.bash; SDL_VIDEODRIVER=wayland python3 /home/jetson/project_atlas/scripts/rover_dashboard.py >> /tmp/dashboard.log 2>&1' >/tmp/dashboard_launcher.log 2>&1 &
echo "Dashboard installed"
echo "Backup: /home/jetson/project_atlas/backups/rover_dashboard_before_logo_${stamp}.py"
