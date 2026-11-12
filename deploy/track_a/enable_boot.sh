#!/bin/bash
# Track A boot start (owner request 2026-11-12). Run ON THE JETSON after install.sh. Enables, does not start anything:
#   atlas-astra-obstacles          -> starts at boot (private ROS domain 77; sensor + obstacle scan + depth picture)
#   atlas-astra-bridge-starter     -> at boot, starts the bridge ONCE when parked and CPU < 72 % (gives up after 15 min)
# The bridge unit itself stays without [Install] and Restart=no. Undo: bash deploy/track_a/disable_boot.sh
set -euo pipefail
systemctl --user daemon-reload
systemctl --user enable atlas-astra-obstacles.service atlas-astra-bridge-starter.service
for u in atlas-astra-obstacles atlas-astra-bridge-starter atlas-astra-bridge; do
  printf "%-28s boot=%s active=%s\n" "$u" "$(systemctl --user is-enabled $u 2>/dev/null)" "$(systemctl --user is-active $u 2>/dev/null)"
done
