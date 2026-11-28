#!/bin/bash
# Undo enable_boot.sh: Track A no longer starts at boot. Leaves running services as they are.
set -uo pipefail
systemctl --user disable atlas-astra-obstacles.service atlas-astra-bridge-starter.service
systemctl --user daemon-reload
echo "Track A boot start disabled. To stop now: systemctl --user stop atlas-astra-bridge atlas-astra-obstacles"
