#!/bin/bash
# Restore exact live bytes 4b5906f7 (jetson:jetson 644, original mtime). Refuses unknown bytes. No restart.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
[ "$(id -un)" = jetson ] || die 'run as jetson'
cur=$(h $T); [ "$cur" = "$CAND" ] || [ "$cur" = "$LIVE" ] || die "unknown bytes $cur"
B=$(ls -1t $HOME/atlas_backups/atlas_status_web.4b5906f7.*.py 2>/dev/null | head -1); [ -n "$B" ] && [ "$(h $B)" = "$LIVE" ] || die 'verified backup not found'
put "$B" "$LIVE"; echo "ROLLED BACK to $LIVE (no restart)"
