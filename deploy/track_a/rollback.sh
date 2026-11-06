#!/bin/bash
# Track A rollback: stop + remove the two units, restore files from the last install backup. LiDAR/Nav2 untouched.
# If G5 was applied, also restore nav2_params.yaml from the backup made at that step (printed by apply_g5.sh).
set -uo pipefail
for u in atlas-astra-bridge atlas-astra-obstacles; do systemctl --user disable --now $u 2>/dev/null; rm -f "$HOME/.config/systemd/user/$u.service"; done
systemctl --user daemon-reload
BK=$(cat "$HOME/project-atlas-migration/track-a-last-backup" 2>/dev/null || true)
if [ -n "$BK" ] && [ -d "$BK" ]; then (cd "$BK" && find . -type f ! -name '*.service' -exec install -D -m 0644 {} "$HOME/project_atlas/{}" \;); echo "restored files from $BK"; fi
echo "Track A stopped and removed. Verify: systemctl --user list-units | grep astra"
