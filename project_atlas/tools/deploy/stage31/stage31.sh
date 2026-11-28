#!/bin/bash
# Stage 31 deployment. NOT TO BE RUN WITHOUT OWNER APPROVAL (OWNER_APPROVED=yes).
#   apply-ui      Home redesign + Vision Lab page (static files only; NO service restart)
#   rollback-ui   restore the previous static files (no restart)
#   apply-astra   private ROS domain for the Astra viewer + Home summary route (restarts ONLY rover-status-web)
#   rollback-astra
# Every apply refuses unless the live files are exactly the 21 Oct 2026 baseline, E-STOP is latched and no
# Astra viewer/driver is running. Backups go to $TARGET/.pre_stage31_<part>_<stamp>; rollback uses the latest one.
set -euo pipefail
cmd="${1:-}"; HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${SRC:-$(cd "$HERE/../../.." && pwd)}"; TARGET="${TARGET:-$HOME/project_atlas}"; STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
h(){ sha256sum "$1" | cut -d' ' -f1; }
die(){ echo "REFUSE: $*" >&2; exit 2; }
UI_REPLACE=(web/v2/index.html web/v2/vision3d.html web/v2/vision3d.js web/v2/vision3d.css)
UI_NEW=(web/v2/home.css web/v2/home-cards.js web/v2/classic.html)
UI_PRE=(f53d68120ecdb82efa0d942ec5519712e283ee511dc02e3b2cbdc88cc12a53c0 2d5b6bf89756b0d8407feacda1bc3459094e21a50b2631fc918720c2ef4eed68
        d27d6907508fc06c49af1c4181fa44cd68f372fc53e33a70e01685fcf2ce9ab8 f422f69e7d391bbfe66d53de0ab06356bd9e7993495fa77e6869c90cdc345cd5)
AS_REPLACE=(scripts/atlas_vision3d_runtime.py scripts/atlas_vision3d_web.py)
AS_PRE=(6a0e9c1cefcf89e1ed3623a786808a5fdd4a67b4ccf6972de71ddab84c19452d b51a1870b0bb4831fbfa00f70a086a24d513ff0df4b02e99ae928ea6aa1e4e36)
UNITS=(atlas-camera rover-base-telemetry atlas-cmd-vel-mux atlas-ekf atlas-localization atlas-lidar)

safety(){
  [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes only after the owner approved this exact step"
  [ "${SKIP_SAFETY_CHECK:-}" = yes ] && return 0
  curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || die "E-STOP is not latched (or dashboard unreachable)"
  ! pgrep -x astra_camera_no >/dev/null || die "an Astra driver is running; stop the viewer first"
  ! pgrep -f 'atlas_vision3d_runtime.py --worker' >/dev/null || die "a Vision Lab worker is running; stop the viewer first"
}
identities(){ [ "${SKIP_SAFETY_CHECK:-}" = yes ] && { echo skipped; return; }; for u in "${UNITS[@]}"; do systemctl --user show "$u" -p MainPID -p NRestarts --value | tr '\n' ' '; done; }
check_pre(){ local -n files=$1 pre=$2; for i in "${!files[@]}"; do [ "$(h "$TARGET/${files[$i]}")" = "${pre[$i]}" ] || die "${files[$i]} differs from the verified baseline"; done; }
backup(){ local part=$1; shift; local b="$TARGET/.pre_stage31_${part}_$STAMP"; mkdir -p "$b"
  for f in "$@"; do if [ -e "$TARGET/$f" ]; then mkdir -p "$b/$(dirname "$f")"; cp -a "$TARGET/$f" "$b/$f"; else mkdir -p "$b/$(dirname "$f")"; : > "$b/$f.absent"; fi; done
  ( cd "$b" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS ); echo "$b" > "$TARGET/.stage31_${part}_last_backup"; echo "backup: $b"; }
install_files(){ for f in "$@"; do [ -f "$SRC/$f" ] || die "package missing $f"; mkdir -p "$TARGET/$(dirname "$f")"; cp "$SRC/$f" "$TARGET/$f.stage31.tmp"; mv "$TARGET/$f.stage31.tmp" "$TARGET/$f"; echo "installed $f $(h "$TARGET/$f" | cut -c1-16)"; done; }
restore(){ local part=$1; shift; local b; b="$(cat "$TARGET/.stage31_${part}_last_backup" 2>/dev/null)" || die "no Stage 31 $part backup recorded"
  ( cd "$b" && sha256sum -c --quiet SHA256SUMS ) || die "backup $b failed its checksum"
  for f in "$@"; do if [ -e "$b/$f.absent" ]; then rm -f "$TARGET/$f"; else cp "$b/$f" "$TARGET/$f.stage31.tmp"; mv "$TARGET/$f.stage31.tmp" "$TARGET/$f"; fi; echo "restored $f"; done; }
restart_web(){ [ "${NO_RESTART:-}" = yes ] && { echo "NO_RESTART=yes: rover-status-web NOT restarted"; return; }
  systemctl --user restart rover-status-web
  for i in $(seq 1 30); do code=$(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:8088/v2/ || true); [ "$code" = 200 ] && break; sleep 1; done
  echo "rover-status-web $(systemctl --user is-active rover-status-web); /v2/ $code"; }

case "$cmd" in
  apply-ui)
    safety; check_pre UI_REPLACE UI_PRE
    for f in "${UI_NEW[@]}"; do [ ! -e "$TARGET/$f" ] || die "$f already exists (already applied?)"; done
    backup ui "${UI_REPLACE[@]}" "${UI_NEW[@]}"; install_files "${UI_REPLACE[@]}" "${UI_NEW[@]}"
    echo "static UI applied; no service restarted" ;;
  rollback-ui)
    [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes"
    restore ui "${UI_REPLACE[@]}" "${UI_NEW[@]}"; echo "static UI rolled back; no service restarted" ;;
  apply-astra)
    safety; check_pre AS_REPLACE AS_PRE
    before="$(identities)"; backup astra "${AS_REPLACE[@]}"; install_files "${AS_REPLACE[@]}"
    ( cd "$TARGET/scripts" && python3 -c "import ast,sys;[ast.parse(open(f).read()) for f in ('atlas_vision3d_runtime.py','atlas_vision3d_web.py')]" ) || { restore astra "${AS_REPLACE[@]}"; die "syntax check failed; restored"; }
    restart_web
    [ "$(identities)" = "$before" ] || echo "WARNING: a protected service identity changed during apply" >&2
    [ "${NO_RESTART:-}" = yes ] || curl -s -m5 http://127.0.0.1:8088/api/vision3d/summary | head -c 300; echo ;;
  rollback-astra)
    [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes"
    ! pgrep -x astra_camera_no >/dev/null || die "an Astra driver is running; stop the viewer first"
    restore astra "${AS_REPLACE[@]}"; restart_web ;;
  *) echo "usage: OWNER_APPROVED=yes $0 apply-ui|rollback-ui|apply-astra|rollback-astra" >&2; exit 64 ;;
esac
