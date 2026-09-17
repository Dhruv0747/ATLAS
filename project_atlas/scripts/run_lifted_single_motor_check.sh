#!/usr/bin/env bash
# Operator must confirm all wheels lifted. Never enabled at boot.
set -euo pipefail
motor="${1:?Specify motor 1-4}"
case "$motor" in 1|2|3|4) ;; *) exit 2 ;; esac
systemctl --user is-active --quiet rover-base-telemetry.service
trap 'systemctl --user start rover-base-telemetry.service' EXIT
systemctl --user stop rover-base-telemetry.service
if fuser /dev/ttyUSB0 >/dev/null 2>&1; then
  echo 'Serial port still busy; no test issued'
  exit 1
fi
# SIGINT causes Python finally to issue zero outputs if timeout interrupts it.
timeout --signal=INT --kill-after=3 12 python3 -u /home/jetson/project_atlas/scripts/test_yahboom_motors_lifted.py 50 0.5 1 "$motor"
