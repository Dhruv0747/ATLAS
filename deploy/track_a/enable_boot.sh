#!/bin/bash
# Track A boot start (owner request 2026-11-12). Run ON THE JETSON after install.sh. Enables, does not start anything:
#   atlas-astra-obstacles          -> starts at boot (private ROS domain 77; sensor + obstacle scan + depth picture)
#   atlas-astra-bridge-starter     -> at boot, starts the bridge when parked and CPU < 72 % (also after every Astra restart; gives up after 2 h)
# The bridge unit itself stays without [Install] and Restart=no. Undo: bash deploy/track_a/disable_boot.sh
set -euo pipefail
# 2026-11-14: re-run the starter whenever the Astra unit (re)starts (e.g. after a mapping session paused it).
mkdir -p ~/.config/systemd/user/atlas-astra-obstacles.service.d
cp "$(dirname "$0")/../../project_atlas/systemd/user/atlas-astra-obstacles.service.d/restart-bridge-starter.conf" \
   ~/.config/systemd/user/atlas-astra-obstacles.service.d/ 2>/dev/null || echo "WARN: drop-in not found next to this script"
systemctl --user daemon-reload
systemctl --user enable atlas-astra-obstacles.service atlas-astra-bridge-starter.service
for u in atlas-astra-obstacles atlas-astra-bridge-starter atlas-astra-bridge; do
  printf "%-28s boot=%s active=%s\n" "$u" "$(systemctl --user is-enabled $u 2>/dev/null)" "$(systemctl --user is-active $u 2>/dev/null)"
done
