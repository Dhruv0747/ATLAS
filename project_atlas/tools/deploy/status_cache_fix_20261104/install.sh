#!/bin/bash
# Exact-byte install of the non-blocking /api/status cache (live 4b5906f7 -> 68f5379c). No restart.
# WARNING: rover-status-web has Restart=always; the new code runs at its next start (crash, reboot or approved restart).
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
[ "$(id -un)" = jetson ] || die 'run as jetson'
( cd "$D" && sha256sum -c --quiet SHA256SUMS ) || die 'package manifest'
[ "$(h $T)" = "$LIVE" ] || die 'live dashboard drift (expected 4b5906f7)'
[ "$(stat -c '%U:%G %a' $T)" = 'jetson:jetson 644' ] || die 'owner/mode drift'
mkdir -p "$HOME/atlas_backups"; B=$HOME/atlas_backups/atlas_status_web.4b5906f7.$(date +%Y%m%dT%H%M%S).py; cp -p "$T" "$B"; [ "$(h $B)" = "$LIVE" ] || die backup
put "$D/atlas_status_web.candidate.py" "$CAND"; echo "INSTALLED $CAND (running PID unchanged; backup $B)"
