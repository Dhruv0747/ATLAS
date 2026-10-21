#!/bin/bash
# Stage 27 FlySky Remote Test Lab: adds 5 new files, one Home link, and patches 2 Python files in place, then restarts ONLY
# rover-status-web.  READ-ONLY feature: no publisher, no serial port, no motor/servo/E-STOP/navigation path.
# NOT TO BE RUN WITHOUT OWNER APPROVAL:   OWNER_APPROVED=yes ./apply.sh   (SRC defaults to the repo's project_atlas/)
# Refuses unless the live files are exactly the Stage 26 + Home-shortcut state this package was built against.
set -euo pipefail
[ "${OWNER_APPROVED:-}" = "yes" ] || { echo "REFUSE: set OWNER_APPROVED=yes only after the owner approved this deployment" >&2; exit 2; }
SRC="${SRC:-$(cd "$(dirname "$0")/../../.." && pwd)}"
TARGET="${TARGET:-$HOME/project_atlas}"
STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
BACKUP="$TARGET/.pre_stage27_flysky_$STAMP"
NEW=(scripts/atlas_flysky_core.py scripts/atlas_flysky_web.py web/v2/flysky-testlab.html web/v2/flysky-testlab.js web/v2/flysky.css)
OLD=(scripts/atlas_status_web.py scripts/atlas_web_v2.py web/v2/index.html)       # status_web/web_v2 are PATCHED in place, never copied
HERE="$(cd "$(dirname "$0")" && pwd)"
h16(){ sha256sum "$1" | cut -c1-16; }
want(){ [ "$(h16 "$TARGET/$1")" = "$2" ] || { echo "REFUSE: $1 is $(h16 "$TARGET/$1"), expected $2 (live state changed?)" >&2; exit 2; }; }
want scripts/atlas_status_web.py "${PRE_STATUS_WEB:-6658db9412b85b34}"
want scripts/atlas_web_v2.py     "${PRE_WEB_V2:-c3607f416d49bd9e}"
want web/v2/index.html           "${PRE_INDEX:-a03baf884e43ae1c}"
for f in "${NEW[@]}"; do [ ! -e "$TARGET/$f" ] || { echo "REFUSE: $f already exists (already deployed?)" >&2; exit 2; }; done
for f in scripts/atlas_testlab_web.py scripts/atlas_wifi_web.py; do [ -f "$TARGET/$f" ] || { echo "REFUSE: missing $f (Stage 26 must be installed)" >&2; exit 2; }; done
for f in "${NEW[@]}" web/v2/index.html; do [ -f "$SRC/$f" ] || { echo "REFUSE: package is missing $f" >&2; exit 2; }; done
# 2026-10-21: the repository Home was redesigned later (Stage 31); this package may only ever install its own Home.
[ "$(h16 "$SRC/web/v2/index.html")" = "${PKG_INDEX:-50c0040bad62ec3b}" ] || { echo "REFUSE: package index.html is not the Stage 27 Home (use the 4159f07 archive)" >&2; exit 2; }
if [ "${SKIP_SAFETY_CHECK:-}" != "yes" ]; then
  curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" \
    || { echo "REFUSE: E-STOP is not latched (or the dashboard is unreachable). Latch it with remote B first." >&2; exit 2; }
fi
mkdir -p "$BACKUP"
for f in "${OLD[@]}"; do mkdir -p "$BACKUP/$(dirname "$f")"; cp -a "$TARGET/$f" "$BACKUP/$f"; done
( cd "$BACKUP" && sha256sum "${OLD[@]}" > SHA256SUMS ); echo "backup: $BACKUP"; cat "$BACKUP/SHA256SUMS"
restore(){ for f in "${OLD[@]}"; do cp -a "$BACKUP/$f" "$TARGET/$f"; done; for f in "${NEW[@]}"; do rm -f "$TARGET/$f"; done; }
for f in "${NEW[@]}"; do mkdir -p "$TARGET/$(dirname "$f")"; cp "$SRC/$f" "$TARGET/$f"; done
cp "$SRC/web/v2/index.html" "$TARGET/web/v2/index.html"          # live == repo HEAD pre-state; only the FlySky link + its CSS are added
python3 "$HERE/insert_hooks.py" "$TARGET" || { echo "patch failed: restoring backup" >&2; restore; exit 3; }
( cd "$TARGET/scripts" && python3 -c "import atlas_flysky_core, atlas_flysky_web" 2>/dev/null ) || { echo "import check failed: restoring backup" >&2; restore; exit 4; }
echo "$BACKUP" > "$TARGET/.stage27_last_backup"
if [ "${NO_RESTART:-}" = "yes" ]; then echo "NO_RESTART=yes: files in place, service NOT restarted"; exit 0; fi
systemctl --user restart rover-status-web                         # the ONLY service touched
sleep 4; systemctl --user is-active rover-status-web
code=$(curl -s -o /dev/null -w '%{http_code}' -m10 http://127.0.0.1:8088/v2/flysky-testlab || true); echo "flysky page: $code"
[ "$code" = 200 ] || { echo "page check failed ($code): run ./rollback.sh" >&2; exit 5; }
echo "Applied. Roll back with: $HERE/rollback.sh"
