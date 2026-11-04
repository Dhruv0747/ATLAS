#!/bin/bash
# Exact-byte install of the producer-capable + type-preload Recovery script. Snapshot stays DISABLED.
# WARNING: Restart=always. Any later crash or reboot starts these bytes. Run only inside a separately
# approved startup window (see README). This script does not restart, reload or reboot.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
[ "$(id -un)" = jetson ] || die 'run as jetson'
( cd "$D" && sha256sum -c --quiet SHA256SUMS ) || die 'package manifest'
[ "$(h $T)" = "$LIVE" ] || die 'live baseline drift (expected 5f44cc1f)'
[ "$(stat -c '%U:%G %a' $T)" = 'jetson:jetson 644' ] || die 'owner/mode drift'
helpers; snapshot_off
mkdir -p "$HOME/atlas_backups"; B=$HOME/atlas_backups/atlas_sensor_recovery.5f44cc1f.$(date +%Y%m%dT%H%M%S).py
cp -p "$T" "$B"; [ "$(h $B)" = "$LIVE" ] || die 'backup mismatch'
put "$D/atlas_sensor_recovery.candidate.py" "$CAND"
stat -c '%U:%G %a %s %y' "$T"; echo "INSTALLED $CAND (snapshot disabled; running PID unchanged; backup $B)"
