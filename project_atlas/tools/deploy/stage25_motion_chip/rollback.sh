#!/bin/bash
# Restores the two pre-Stage-25 files and removes motion-status.js. Static files only; no restart.
set -euo pipefail
TARGET="${TARGET:-$HOME/project_atlas/web/v2}"
BACKUP="${BACKUP:-$(cat "$TARGET/.stage25_last_backup")}"
[ -f "$BACKUP/shell.js" ] && [ -f "$BACKUP/index.html" ] || { echo "no backup at $BACKUP" >&2; exit 2; }
cp -a "$BACKUP/shell.js" "$BACKUP/index.html" "$TARGET/"
rm -f "$TARGET/motion-status.js" "$TARGET/.stage25_last_backup"
echo "rolled back from $BACKUP"; sha256sum "$TARGET/shell.js" "$TARGET/index.html"
