#!/usr/bin/env bash
set -euo pipefail
systemctl --user is-active --quiet rover-base-telemetry.service
trap 'systemctl --user start rover-base-telemetry.service' EXIT
systemctl --user stop rover-base-telemetry.service
if fuser /dev/ttyUSB0 >/dev/null 2>&1; then
  echo 'Serial still busy; steering test cancelled'
  exit 1
fi
timeout --signal=INT --kill-after=3 10 python3 -u /home/jetson/project-atlas-migration/test_front_steering_small.py
