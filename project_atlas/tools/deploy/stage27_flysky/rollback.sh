#!/bin/bash
# Restores the 3 edited files from the backup, removes the 5 new FlySky files, restarts ONLY rover-status-web.
set -euo pipefail
TARGET="${TARGET:-$HOME/project_atlas}"
BACKUP="${BACKUP:-$(cat "$TARGET/.stage27_last_backup")}"
OLD=(scripts/atlas_status_web.py scripts/atlas_web_v2.py web/v2/index.html)
for f in "${OLD[@]}"; do [ -f "$BACKUP/$f" ] || { echo "no backup of $f at $BACKUP" >&2; exit 2; }; done
for f in "${OLD[@]}"; do cp -a "$BACKUP/$f" "$TARGET/$f"; done
rm -f "$TARGET"/scripts/atlas_flysky_core.py "$TARGET"/scripts/atlas_flysky_web.py "$TARGET"/web/v2/flysky-testlab.html "$TARGET"/web/v2/flysky-testlab.js "$TARGET"/web/v2/flysky.css "$TARGET/.stage27_last_backup"
rm -rf "$TARGET"/scripts/__pycache__/atlas_flysky_*
if [ "${NO_RESTART:-}" != "yes" ]; then systemctl --user restart rover-status-web; sleep 4; systemctl --user is-active rover-status-web; fi
( cd "$BACKUP" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ) && echo "backup checksums intact"
( cd "$TARGET" && sha256sum "${OLD[@]}" )
echo "rolled back from $BACKUP"
