#!/bin/bash
# Guided mapping assistant deploy (2026-11-26; first install 13:31, upgrade-safe since 16:30). Runs ON the Jetson from a
# staging dir that holds the repo subset (scripts/, web/v2/, systemd/user/). Needs the owner's "Yes, deploy".
# Fail-closed preflight: no mapping session, no active Nav2 goal, E-STOP latched, Manual.
# Touches only the files listed below. Restarts only rover-status-web (dashboard) and atlas-guided-mapping.
# Every file is backed up if it existed; rollback restores exactly the previous state (files that did not exist are
# removed, the unit is removed only if it did not exist before).
#   bash deploy_guided_1b.sh STAGING_DIR            deploy (first install or upgrade)
#   bash deploy_guided_1b.sh --rollback BACKUP_DIR  restore the backup
set -euo pipefail
LIVE=${ATLAS_LIVE:-/home/jetson/project_atlas}                  # overrides exist only for the sandbox test
UNIT_DIR=${ATLAS_UNIT_DIR:-/home/jetson/.config/systemd/user}
BACKUP_ROOT=${ATLAS_BACKUP_ROOT:-/home/jetson/atlas_backups}
SESSION=${ATLAS_SESSION_FILE:-/home/jetson/.config/project_atlas/mapping_session.json}
UNIT=atlas-guided-mapping.service
# path relative to LIVE (or "UNIT") -> stored in the backup as a flat name
FILES="scripts/atlas_map_quality_core.py scripts/atlas_invisible_objects_core.py scripts/atlas_guided_mapping_engine.py
scripts/atlas_guided_mapping.py scripts/atlas_status_web.py web/v2/mapping-quality.js web/v2/mapping.html"
flat() { echo "$1" | tr '/' '__'; }

if [ "${1:-}" = "--rollback" ]; then
  B="$2"; [ -d "$B" ] || { echo "no backup dir $B"; exit 1; }
  for f in $FILES; do
    if [ -e "$B/$(flat "$f")" ]; then cp -p "$B/$(flat "$f")" "$LIVE/$f"; else rm -f "$LIVE/$f"; fi
  done
  # Older backups (13:31 / 16:15 layout) stored atlas_status_web.py and mapping.html under their plain names.
  [ -e "$B/atlas_status_web.py" ] && cp -p "$B/atlas_status_web.py" "$LIVE/scripts/atlas_status_web.py"
  [ -e "$B/mapping.html" ] && cp -p "$B/mapping.html" "$LIVE/web/v2/mapping.html"
  if [ -e "$B/$UNIT" ]; then
    cp -p "$B/$UNIT" "$UNIT_DIR/$UNIT"; systemctl --user daemon-reload; systemctl --user restart "$UNIT"
  else
    systemctl --user disable --now "$UNIT" 2>/dev/null || true; rm -f "$UNIT_DIR/$UNIT"; systemctl --user daemon-reload
  fi
  systemctl --user restart rover-status-web.service
  echo "ROLLED BACK from $B"; exit 0
fi

SRC="${1:?staging dir}"
api() { curl -s -m 3 "http://127.0.0.1:8088$1"; }
# ---- preflight (fail closed)
[ ! -e "$SESSION" ] || { echo "REFUSED: mapping session file exists"; exit 2; }
api /api/map | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("nav_active") is False else 1)' \
  || { echo "REFUSED: Nav2 goal active or dashboard unreadable"; exit 2; }
api /api/status | python3 -c 'import json,sys; d=json.load(sys.stdin); p=json.loads(d["ros"]["control_policy"]["value"]); sys.exit(0 if p.get("stop_latched") is True and p.get("manual_only") is True else 1)' \
  || { echo "REFUSED: E-STOP not latched (press B) or not Manual"; exit 2; }
for f in $FILES; do [ -e "$SRC/$f" ] || { echo "REFUSED: staging misses $f"; exit 2; }; done
for f in $FILES; do case "$f" in *.py) python3 -m py_compile "$SRC/$f";; esac; done
# ---- backup (only what exists now)
B=$BACKUP_ROOT/backup_guided_$(date +%Y%m%d_%H%M%S)
mkdir -p "$B"
for f in $FILES; do [ -e "$LIVE/$f" ] && cp -p "$LIVE/$f" "$B/$(flat "$f")" || true; done
[ -e "$UNIT_DIR/$UNIT" ] && cp -p "$UNIT_DIR/$UNIT" "$B/$UNIT" || true
cp -p "$0" "$B/deploy_guided_1b.sh"
(cd "$B" && md5sum * > MD5SUMS)
echo "backup: $B"
# ---- install
for f in $FILES; do cp "$SRC/$f" "$LIVE/$f"; done
cp "$SRC/systemd/user/$UNIT" "$UNIT_DIR/$UNIT"
systemctl --user daemon-reload
systemctl --user enable "$UNIT"
systemctl --user restart "$UNIT"            # restart (not only enable --now): an upgrade must load the new code
systemctl --user restart rover-status-web.service
# ---- verify
sleep ${ATLAS_VERIFY_WAIT_S:-15}
systemctl --user is-active "$UNIT" rover-status-web.service
api /api/map | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d.get("mapping_quality"); print("mapping_quality:", None if q is None else {k: q.get(k) for k in ("state","verdict_text")}); sys.exit(0 if "mapping_quality" in d else 1)'
curl -s -m 3 -o /dev/null -w "mapping-quality.js HTTP %{http_code}\n" http://127.0.0.1:8088/v2/mapping-quality.js
for f in $FILES; do md5sum "$LIVE/$f"; done
echo "DEPLOYED. Rollback: bash $B/deploy_guided_1b.sh --rollback $B"
