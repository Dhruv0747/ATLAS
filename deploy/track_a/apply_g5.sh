#!/bin/bash
# Gate G5 ONLY, after shadow test G4 passed and with explicit owner approval. Rover parked, E-STOP latched.
# Validates the merge, backs up nav2_params.yaml, writes the merged file. Restart of atlas-localization (Nav2) is a
# SEPARATE owner action printed below; this script never restarts navigation and never commands motion.
set -euo pipefail
N=~/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml; BK="$N.before-track-a-$(date +%Y%m%d-%H%M%S)"
python3 ~/project_atlas/tools/track_a/check_nav2_merge.py "$N" --write /tmp/nav2_params.track_a.yaml
cp -p "$N" "$BK"; install -m 0644 /tmp/nav2_params.track_a.yaml "$N"
echo "nav2_params.yaml updated. Backup: $BK"
echo "When parked + E-STOP latched, apply with:  systemctl --user restart atlas-localization"
echo "Undo: cp -p $BK $N && systemctl --user restart atlas-localization"
