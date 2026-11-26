#!/bin/bash
# Guided mapping assistant phase 1b deploy (2026-11-26). Runs ON the Jetson from a staging dir that holds the repo
# subset (scripts/, web/v2/, systemd/user/). Needs the owner's "Yes, deploy". Fail-closed preflight: no mapping session,
# no active Nav2 goal, E-STOP latched. Touches only: 4 new scripts + atlas_status_web.py, mapping-quality.js +
# mapping.html, the new unit. Restarts only rover-status-web (dashboard) and starts atlas-guided-mapping.
#   bash deploy_guided_1b.sh STAGING_DIR            deploy
#   bash deploy_guided_1b.sh --rollback BACKUP_DIR  restore the backup, stop + remove the new unit and files
set -euo pipefail
LIVE=/home/jetson/project_atlas
UNIT_DIR=/home/jetson/.config/systemd/user
NEW_SCRIPTS="atlas_map_quality_core.py atlas_invisible_objects_core.py atlas_guided_mapping_engine.py atlas_guided_mapping.py"

if [ "${1:-}" = "--rollback" ]; then
  B="$2"; [ -d "$B" ] || { echo "no backup dir $B"; exit 1; }
  systemctl --user disable --now atlas-guided-mapping.service 2>/dev/null || true
  rm -f "$UNIT_DIR/atlas-guided-mapping.service"
  for f in $NEW_SCRIPTS; do [ -e "$B/new_$f" ] || rm -f "$LIVE/scripts/$f"; done
  rm -f "$LIVE/web/v2/mapping-quality.js"
  cp -p "$B/atlas_status_web.py" "$LIVE/scripts/atlas_status_web.py"
  cp -p "$B/mapping.html" "$LIVE/web/v2/mapping.html"
  systemctl --user daemon-reload
  systemctl --user restart rover-status-web.service
  echo "ROLLED BACK from $B"; exit 0
fi

SRC="${1:?staging dir}"
api() { curl -s -m 3 "http://127.0.0.1:8088$1"; }
# ---- preflight (fail closed)
[ ! -e /home/jetson/.config/project_atlas/mapping_session.json ] || { echo "REFUSED: mapping session file exists"; exit 2; }
api /api/map | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("nav_active") is False else 1)' \
  || { echo "REFUSED: Nav2 goal active or dashboard unreadable"; exit 2; }
api /api/status | python3 -c 'import json,sys; d=json.load(sys.stdin); p=json.loads(d["ros"]["control_policy"]["value"]); sys.exit(0 if p.get("stop_latched") is True and p.get("manual_only") is True else 1)' \
  || { echo "REFUSED: E-STOP not latched (press B) or not Manual"; exit 2; }
for f in $NEW_SCRIPTS atlas_status_web.py; do python3 -m py_compile "$SRC/scripts/$f"; done
# ---- backup
B=/home/jetson/atlas_backups/backup_guided1b_$(date +%Y%m%d_%H%M%S)
mkdir -p "$B"
cp -p "$LIVE/scripts/atlas_status_web.py" "$B/"; cp -p "$LIVE/web/v2/mapping.html" "$B/"
for f in $NEW_SCRIPTS; do [ -e "$LIVE/scripts/$f" ] && cp -p "$LIVE/scripts/$f" "$B/new_$f" || true; done
md5sum "$B"/* > "$B/MD5SUMS"
echo "backup: $B"
# ---- install
for f in $NEW_SCRIPTS atlas_status_web.py; do cp "$SRC/scripts/$f" "$LIVE/scripts/$f"; done
cp "$SRC/web/v2/mapping-quality.js" "$SRC/web/v2/mapping.html" "$LIVE/web/v2/"
cp "$SRC/systemd/user/atlas-guided-mapping.service" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now atlas-guided-mapping.service
systemctl --user restart rover-status-web.service
# ---- verify
sleep 15
systemctl --user is-active atlas-guided-mapping.service rover-status-web.service
api /api/map | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d.get("mapping_quality"); print("mapping_quality:", None if q is None else {k: q.get(k) for k in ("state","verdict_text","samples")}); sys.exit(0 if "mapping_quality" in d else 1)'
curl -s -m 3 -o /dev/null -w "mapping-quality.js HTTP %{http_code}\n" http://127.0.0.1:8088/v2/mapping-quality.js
md5sum "$LIVE/scripts/atlas_status_web.py" "$LIVE/scripts/atlas_guided_mapping.py" "$LIVE/web/v2/mapping.html"
echo "DEPLOYED. Rollback: bash $0 --rollback $B"
