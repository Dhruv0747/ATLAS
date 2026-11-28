#!/bin/bash
# 2026-11-15: deploy the three-encoder consensus rule (coherent pair when only 3 channels are valid) to the base.
# Run ON THE JETSON, only with the rover parked AND the E-STOP latched (owner confirms). Restarts the base node only.
# Rollback: bash deploy_20261115_three_encoder_rule.sh --rollback
set -euo pipefail
S=/home/jetson/project_atlas/scripts
SRC=${SRC:-/tmp/encrule}
TAG=before-3enc-20261115
FILES="atlas_encoder_selection.py yahboom_base.py test_encoder_selection.py"
if [ "${1:-}" = "--rollback" ]; then
  for f in $FILES; do cp -p "$S/$f.$TAG" "$S/$f"; done
  systemctl --user restart rover-base-telemetry.service; echo "rolled back"; exit 0
fi
/usr/bin/python3 "$S/atlas_astra_bridge_parked_check.py" || { echo "NOT parked: abort"; exit 1; }
for f in $FILES; do python3 -m py_compile "$SRC/$f"; done
for f in $FILES; do [ -e "$S/$f.$TAG" ] || cp -p "$S/$f" "$S/$f.$TAG"; cp "$SRC/$f" "$S/$f"; done
(cd "$S" && python3 -m unittest -q test_encoder_selection)
systemctl --user restart rover-base-telemetry.service
sleep 8
systemctl --user is-active rover-base-telemetry.service
set +u; source /opt/ros/humble/setup.bash; set -u
timeout 6 ros2 topic echo --once /atlas/encoder_health 2>/dev/null | grep -o '"policy": "[^"]*"\|"state": "[^"]*"' | head -2
