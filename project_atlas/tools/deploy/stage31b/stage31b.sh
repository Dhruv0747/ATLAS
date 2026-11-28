#!/bin/bash
# Stage 31b CANDIDATE: >=1 s CPU guard window (75% single-sample fail-closed unchanged) + Vision Lab stale-summary fix.
# NOT TO BE RUN WITHOUT SEPARATE OWNER APPROVAL (OWNER_APPROVED=yes).
#   apply     replace scripts/atlas_vision3d_runtime.py and web/v2/vision3d.js. NO service restart: the guard runs in the
#             viewer worker process, which loads the runtime file fresh at each explicit Start; the page is a static file.
#   rollback  restore both files from the latest Stage 31b backup (no restart).
# Refuses unless both live files equal the deployed Stage 31 baseline, E-STOP is latched and no viewer/driver is running.
set -euo pipefail
cmd="${1:-}"; HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${SRC:-$(cd "$HERE/../../.." && pwd)}"; TARGET="${TARGET:-$HOME/project_atlas}"; STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
FILES=(scripts/atlas_vision3d_runtime.py web/v2/vision3d.js)
BASE_RUNTIME="${BASE_RUNTIME:-a09fc0198e7b479c7e94ed2446cd31c3ccf36f22819023391f1660c33ecd476f}"; BASE_JS="${BASE_JS:-f2939d19fb2ef2278e8837c3f3334174cc51ec5bd96a8664e40540f24a83c53d}"
h(){ sha256sum "$1" | cut -d' ' -f1; }
die(){ echo "REFUSE: $*" >&2; exit 2; }
quiet(){
  [ "${SKIP_SAFETY_CHECK:-}" = yes ] && return 0
  curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || die "E-STOP not latched"
  ! pgrep -x astra_camera_no >/dev/null || die "Astra driver running; stop the viewer first"
  ! pgrep -f 'atlas_vision3d_runtime.py --worker' >/dev/null || die "Vision Lab worker running; stop the viewer first"
}
[ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes only after the owner approved this exact step"
case "$cmd" in
  apply)
    quiet
    [ "$(h "$TARGET/${FILES[0]}")" = "$BASE_RUNTIME" ] || die "${FILES[0]} is not the deployed Stage 31 baseline"
    [ "$(h "$TARGET/${FILES[1]}")" = "$BASE_JS" ] || die "${FILES[1]} is not the deployed Stage 31 baseline"
    B="$TARGET/.pre_stage31b_$STAMP"; mkdir -p "$B"
    for f in "${FILES[@]}"; do mkdir -p "$B/$(dirname "$f")"; cp -a "$TARGET/$f" "$B/$f"; done
    ( cd "$B" && sha256sum "${FILES[@]}" > SHA256SUMS ); echo "$B" > "$TARGET/.stage31b_last_backup"; echo "backup: $B"
    python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$SRC/${FILES[0]}" || die "candidate runtime does not parse"
    for f in "${FILES[@]}"; do cp "$SRC/$f" "$TARGET/$f.s31b.tmp"; mv "$TARGET/$f.s31b.tmp" "$TARGET/$f"; echo "installed $f $(h "$TARGET/$f" | cut -c1-16)"; done
    echo "applied; no service restarted" ;;
  rollback)
    quiet
    B="$(cat "$TARGET/.stage31b_last_backup" 2>/dev/null)" || die "no Stage 31b backup recorded"
    ( cd "$B" && sha256sum -c --quiet SHA256SUMS ) || die "backup $B failed its checksum"
    for f in "${FILES[@]}"; do cp "$B/$f" "$TARGET/$f.s31b.tmp"; mv "$TARGET/$f.s31b.tmp" "$TARGET/$f"; echo "restored $f $(h "$TARGET/$f" | cut -c1-16)"; done
    echo "rolled back; no service restarted" ;;
  *) echo "usage: OWNER_APPROVED=yes $0 apply|rollback" >&2; exit 64 ;;
esac
