#!/bin/bash
# Stage 32 CANDIDATE: Vision Lab infrared view + mode matrix, calibration-gated XYZ PointCloud2 foundation.
# NOT TO BE RUN WITHOUT SEPARATE OWNER APPROVAL (OWNER_APPROVED=yes).
#   apply     back up, then install the files below. Restarts ONLY rover-status-web (the Vision Lab receiver runs inside it).
#             Installs no calibration file, so the point cloud stays CALIBRATION BLOCKED. Does not start the camera,
#             change autostart, or touch any other service.
#   rollback  restore every file from the latest Stage 32 backup (new files removed), restart rover-status-web.
# Refuses unless every replaced file equals the deployed Stage 31B baseline, E-STOP is latched and no viewer/driver runs.
set -euo pipefail
cmd="${1:-}"; HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${SRC:-$(cd "$HERE/../../.." && pwd)}"; TARGET="${TARGET:-$HOME/project_atlas}"; STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
REPLACE=(scripts/atlas_vision3d_runtime.py scripts/atlas_vision3d_web.py web/v2/vision3d.html web/v2/vision3d.js web/v2/vision3d.css config/vision3d_live.json)
PRE=(077edc293a163c6bf7fc925901810e1a5d2f8cfccb34e29f37b19da7337d8a6b 6b9a28c5f6a159f6b1e8cd3baa33845c9b63a47d83579a65e9b806eee2d45107
     47380d1bd2379a6c69df956d8c14b866df20894df8dd66a69aacfb795a0fef83 05b83020d67f2db4aa50c10a97c8c44f08bf58a6fa56328fbb49fdc3d96b4a69
     339e810203a4e50d03d02a8e01232d786180218849bfce514cd65108494ce105 d815940f95d9595ede60372a810aed95314ce44ac7ceeeea06421277dd8e6209)
NEW=(scripts/atlas_vision3d_geometry.py scripts/atlas_vision3d_cloud_node.py tools/vision3d/calibration_validation.py tools/vision3d/checkerboard_calibration.py)
UNITS=(atlas-camera rover-base-telemetry atlas-cmd-vel-mux atlas-ekf atlas-localization atlas-lidar)
h(){ sha256sum "$1" | cut -d' ' -f1; }
die(){ echo "REFUSE: $*" >&2; exit 2; }
safety(){
  [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes only after the owner approved this exact step"
  [ "${SKIP_SAFETY_CHECK:-}" = yes ] && return 0
  curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || die "E-STOP is not latched (or dashboard unreachable)"
  ! pgrep -x astra_camera_no >/dev/null || die "an Astra driver is running; stop the viewer first"
  ! pgrep -f 'atlas_vision3d_runtime.py --worker' >/dev/null || die "a Vision Lab worker is running; stop the viewer first"
  ! pgrep -f 'atlas_vision3d_cloud_node.py' >/dev/null || die "a point cloud node is running"
}
identities(){ [ "${SKIP_SAFETY_CHECK:-}" = yes ] && { echo skipped; return; }; for u in "${UNITS[@]}"; do systemctl --user show "$u" -p MainPID -p NRestarts --value | tr '\n' ' '; done; }
restart_web(){ [ "${NO_RESTART:-}" = yes ] && { echo "NO_RESTART=yes: rover-status-web NOT restarted"; return; }
  systemctl --user restart rover-status-web
  for i in $(seq 1 30); do code=$(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:8088/v2/vision3d || true); [ "$code" = 200 ] && break; sleep 1; done
  echo "rover-status-web $(systemctl --user is-active rover-status-web); /v2/vision3d $code"; }
restore(){ local b; b="$(cat "$TARGET/.stage32_last_backup" 2>/dev/null)" || die "no Stage 32 backup recorded"
  ( cd "$b" && sha256sum -c --quiet SHA256SUMS ) || die "backup $b failed its checksum"
  for f in "${REPLACE[@]}" "${NEW[@]}"; do
    if [ -e "$b/$f.absent" ]; then rm -f "$TARGET/$f"; else cp "$b/$f" "$TARGET/$f.s32.tmp"; mv "$TARGET/$f.s32.tmp" "$TARGET/$f"; fi; echo "restored $f"; done; }
case "$cmd" in
  apply)
    safety
    for i in "${!REPLACE[@]}"; do [ "$(h "$TARGET/${REPLACE[$i]}")" = "${PRE[$i]}" ] || die "${REPLACE[$i]} differs from the deployed Stage 31B baseline"; done
    for f in "${NEW[@]}"; do [ ! -e "$TARGET/$f" ] || die "$f already exists (already applied?)"; done
    [ ! -e "$TARGET/config/astra_calibration" ] || die "a calibration directory exists; review it before applying"
    ( cd "$SRC" && python3 -c "import ast,sys;[ast.parse(open(f).read()) for f in sys.argv[1:]]" scripts/atlas_vision3d_runtime.py scripts/atlas_vision3d_web.py "${NEW[@]}" ) || die "candidate does not parse"
    ( cd "$SRC/scripts" && env -u ROS_DOMAIN_ID python3 -I -c "import sys;sys.path.insert(0,'.');import atlas_vision3d_geometry as g,atlas_vision3d_web as w,json;print('import ok',g.calibration_state(json.load(open('../config/vision3d_live.json')))['state'])" ) || die "candidate import failed"
    before="$(identities)"; B="$TARGET/.pre_stage32_$STAMP"; mkdir -p "$B"
    for f in "${REPLACE[@]}" "${NEW[@]}"; do mkdir -p "$B/$(dirname "$f")"; if [ -e "$TARGET/$f" ]; then cp -a "$TARGET/$f" "$B/$f"; else : > "$B/$f.absent"; fi; done
    ( cd "$B" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS ); echo "$B" > "$TARGET/.stage32_last_backup"; echo "backup: $B"
    for f in "${REPLACE[@]}" "${NEW[@]}"; do mkdir -p "$TARGET/$(dirname "$f")"; cp "$SRC/$f" "$TARGET/$f.s32.tmp"; mv "$TARGET/$f.s32.tmp" "$TARGET/$f"; echo "installed $f $(h "$TARGET/$f" | cut -c1-16)"; done
    restart_web
    [ "$(identities)" = "$before" ] || echo "WARNING: a protected service identity changed during apply" >&2
    [ "${NO_RESTART:-}" = yes ] || curl -s -m5 http://127.0.0.1:8088/api/vision3d/status | python3 -c "import sys,json;d=json.load(sys.stdin);print('calibration',d['calibration_state']['state'],'| modes',{k:v['state'] for k,v in d['mode_support'].items()})" ;;
  rollback)
    [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes"
    ! pgrep -x astra_camera_no >/dev/null || die "an Astra driver is running; stop the viewer first"
    restore; restart_web ;;
  *) echo "usage: OWNER_APPROVED=yes $0 apply|rollback" >&2; exit 64 ;;
esac
