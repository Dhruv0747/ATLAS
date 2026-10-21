#!/bin/bash
# Stage 26 Motor & Encoder Test Lab: adds 5 new files, adds a link to index.html and patches 2 Python files in place, then restarts ONLY rover-status-web.
# DOES NOT touch the base driver, its environment, calibration, E-STOP, mux, steering, localization or navigation.
# Refuses to run without explicit owner approval. Pulse controls stay locked until the owner separately enables the
# lifted interface in the BASE driver (see README: base_dropin/ is shipped disabled and is NOT applied by this script).
#   OWNER_APPROVED=yes ./apply.sh        (SRC defaults to the repo, TARGET to ~/project_atlas)
set -euo pipefail
[ "${OWNER_APPROVED:-}" = "yes" ] || { echo "REFUSE: set OWNER_APPROVED=yes only after the owner approved this deployment" >&2; exit 2; }
SRC="${SRC:-$(cd "$(dirname "$0")/../../.." && pwd)}"
TARGET="${TARGET:-$HOME/project_atlas}"
STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
BACKUP="$TARGET/.pre_stage26_testlab_$STAMP"
NEW=(scripts/atlas_testlab_core.py scripts/atlas_testlab_web.py web/v2/testlab.html web/v2/testlab.js web/v2/testlab.css)
OLD=(scripts/atlas_status_web.py scripts/atlas_web_v2.py web/v2/index.html)   # status_web/web_v2 are PATCHED in place, never copied
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(sha256sum "$TARGET/web/v2/index.html" | cut -c1-16)" = 61f3a12e59bf1237 ] || { echo "REFUSE: live index.html is not the expected pre-state" >&2; exit 2; }
for f in "${NEW[@]}"; do [ ! -e "$TARGET/$f" ] || { echo "REFUSE: $f already exists (already deployed?)" >&2; exit 2; }; done
for f in "${OLD[@]}" scripts/atlas_drive_pid_lifted.py scripts/atlas_wifi_web.py; do [ -f "$TARGET/$f" ] || { echo "REFUSE: missing $f" >&2; exit 2; }; done
# the new module imports the live commissioning state machine: it must be the repo version (same limits)
cmp -s "$SRC/scripts/atlas_drive_pid_lifted.py" "$TARGET/scripts/atlas_drive_pid_lifted.py" || { echo "REFUSE: live atlas_drive_pid_lifted.py differs from the repo" >&2; exit 2; }
for f in "${NEW[@]}"; do python3 - "$SRC/$f" <<'PY'
import sys; p=sys.argv[1]
if p.endswith('.py'): compile(open(p).read(), p, 'exec')
PY
done
mkdir -p "$BACKUP"
for f in "${OLD[@]}"; do mkdir -p "$BACKUP/$(dirname "$f")"; cp -a "$TARGET/$f" "$BACKUP/$f"; done
( cd "$BACKUP" && sha256sum "${OLD[@]}" > SHA256SUMS ); echo "backup: $BACKUP"; cat "$BACKUP/SHA256SUMS"
for f in "${NEW[@]}"; do cp "$SRC/$f" "$TARGET/$f"; done
cp "$SRC/web/v2/index.html" "$TARGET/web/v2/index.html"      # index.html: live == repo HEAD pre-state (61f3a12e...), only a link is added
python3 "$HERE/insert_hooks.py" "$TARGET" || { echo "patch failed: restoring backup" >&2; for f in "${OLD[@]}"; do cp -a "$BACKUP/$f" "$TARGET/$f"; done; for f in "${NEW[@]}"; do rm -f "$TARGET/$f"; done; exit 3; }
echo "$BACKUP" > "$TARGET/.stage26_last_backup"
systemctl --user restart rover-status-web
sleep 4
systemctl --user is-active rover-status-web
curl -s -o /dev/null -w "testlab page %{http_code}\n" http://127.0.0.1:8088/v2/testlab
curl -s http://127.0.0.1:8088/api/testlab/state?history=0 | head -c 200; echo
echo "Applied. Roll back with: ./rollback.sh"
