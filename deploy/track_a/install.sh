#!/bin/bash
# Track A installer (owner-approved, gate G3). Run ON THE JETSON from the repo checkout:  bash deploy/track_a/install.sh
# Copies Track A files into ~/project_atlas and registers the two user units. It NEVER enables or starts them,
# never edits nav2_params.yaml and never touches the LiDAR/Nav2/EKF/AMCL services. Backs up anything it replaces.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"; SRC="$REPO/project_atlas"; DST="$HOME/project_atlas"
UNITS="$HOME/.config/systemd/user"; BK="$HOME/project-atlas-migration/track-a-backup-$(date +%Y%m%d-%H%M%S)"
FILES="scripts/atlas_astra_obstacle_core.py scripts/atlas_astra_obstacle_scan.py launch/atlas_astra_obstacles.launch.py
config/astra_obstacles.yaml config/astra_obstacles_bridge.yaml config/nav2_astra_obstacles_LIVE_SNIPPET.yaml
tools/track_a/check_nav2_merge.py tests/test_track_a.py"
mkdir -p "$BK" "$UNITS"
for f in $FILES; do
  if [ -e "$DST/$f" ]; then mkdir -p "$BK/$(dirname $f)"; cp -p "$DST/$f" "$BK/$f"; fi
  # Never overwrite the owner's measured mount values with the placeholder file.
  if [ "$f" = config/astra_obstacles.yaml ] && [ -e "$DST/$f" ]; then echo "keep existing $f (owner measurements)"; continue; fi
  mkdir -p "$DST/$(dirname $f)"; install -m 0644 "$SRC/$f" "$DST/$f"
done
chmod 0755 "$DST/scripts/atlas_astra_obstacle_scan.py"
for u in atlas-astra-obstacles atlas-astra-bridge; do
  [ -e "$UNITS/$u.service" ] && cp -p "$UNITS/$u.service" "$BK/"
  install -m 0644 "$SRC/systemd/user/$u.service.in" "$UNITS/$u.service"
done
systemctl --user daemon-reload
echo "$BK" > "$HOME/project-atlas-migration/track-a-last-backup"
echo "Installed (NOT enabled, NOT started). Backup: $BK"
if ! ros2 pkg prefix domain_bridge >/dev/null 2>&1; then
  echo "Still needed for the bridge (needs your password):  sudo apt install ros-humble-domain-bridge"
fi
echo "Next: bash deploy/track_a/verify.sh"
