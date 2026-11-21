#!/bin/bash
# Undo arm.sh before the reboot (or after it). Restores original Recovery bytes if the candidate is
# installed. No daemon-reload, restart or reboot.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
systemctl --user disable --no-reload atlas-boot-evidence.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/atlas-boot-evidence.service" "$D/ARMED"
[ "$(h $T)" = "$CAND" ] && { bash "$D/rollback.sh" || die 'rollback failed'; }
[ "$(h $T)" = "$LIVE" ] || die "Recovery script is neither original nor candidate"
echo "DISARMED: monitor removed, Recovery script $(h $T | cut -c1-8)"
