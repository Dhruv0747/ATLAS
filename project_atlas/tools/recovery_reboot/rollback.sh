#!/bin/bash
# Restore the exact pre-install bytes 5f44cc1f with jetson:jetson 644 and the original mtime. No restart.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
[ "$(id -un)" = jetson ] || die 'run as jetson'
( cd "$D" && sha256sum -c --quiet SHA256SUMS ) || die 'package manifest'
cur=$(h $T); [ "$cur" = "$CAND" ] || [ "$cur" = "$LIVE" ] || die "unknown bytes $cur; not overwriting"
put "$D/atlas_sensor_recovery.rollback.py" "$LIVE"
stat -c '%U:%G %a %s %y' "$T"; echo "ROLLED BACK to $LIVE (no restart performed)"
