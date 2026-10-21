#!/bin/bash
# Stage 32 continuation package. NOT TO BE RUN WITHOUT SEPARATE OWNER APPROVAL (OWNER_APPROVED=yes).
#   apply-ui        U1: Vision Lab status/label fix (static files only). NO restart: /v2 files are read per request.
#   rollback-ui     restore the three replaced static files and remove vision3d_state.js (no restart)
#   apply-config    U2+P: mode note "Infrared: Tested" + device serial for the calibration gate (manifest, geometry) AND the
#                   UNCALIBRATED diagnostic 3D preview (receiver raw-depth route in atlas_vision3d_web.py + the four Vision
#                   Lab static files). Manifest, geometry and receiver are loaded inside rover-status-web, so this RESTARTS
#                   rover-status-web once (camera must be off). The calibrated cloud / metric XYZ gate is unchanged.
#   rollback-config restore all seven U2+P files and restart rover-status-web
# Each part refuses unless its live files equal the verified production hashes, E-STOP is latched and no viewer runs.
set -euo pipefail
cmd="${1:-}"; HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${SRC:-$(cd "$HERE/../../.." && pwd)}"; TARGET="${TARGET:-$HOME/project_atlas}"; STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
UI_REPLACE=(web/v2/vision3d.js web/v2/vision3d.html web/v2/vision3d.css)
UI_PRE=(76f9a20267e7d90a9d4b0a3be7f75a6c0e0ca594ddc1254e337e618215cf3fba a930af8392b0fbaab3380eaf8dbc547780df487f27e44fb4d349ad1447e48c09
        04f98c8c0338b960add11346e84c149ae82dac48954d81ffdd726839b0a6971f)
UI_NEW=(web/v2/vision3d_state.js)
CF_REPLACE=(config/vision3d_live.json scripts/atlas_vision3d_geometry.py scripts/atlas_vision3d_web.py
            web/v2/vision3d.js web/v2/vision3d_state.js web/v2/vision3d.html web/v2/vision3d.css)
CF_PRE=(e27bc0c0551d22babb7a477c551d49c5ab20937e56b6aa4fe8a8ce6aff9f9c9a 75d020120d22fe31d8cc6b741f1ae8b19192047aafb03396a47669ee9d4b4354
        889881c062717d076430414f57825b14f7f0de36ba4cf8c20b0c74fbff9ec1bf
        2c06d110c85671ce4fb02b355e7d3d275e8d0fc59aac30134fe0954a6379f435 641ca00bc4536783e4593d31ce44c859302934114f5ab56e6d09ba275b6162ca
        cf19258b030e4009df9797f43ec5ded3d73a44bbede8760c3bb98583b59e4ff4 e92cf062ca99fdf444e575806b8788cc86c716034c757070ee2703af64ef2800)
UNITS=(atlas-camera rover-base-telemetry atlas-cmd-vel-mux atlas-ekf atlas-localization atlas-lidar)
h(){ sha256sum "$1" | cut -d' ' -f1; }
die(){ echo "REFUSE: $*" >&2; exit 2; }
safety(){
  [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes only after the owner approved this exact step"
  [ "${SKIP_SAFETY_CHECK:-}" = yes ] && return 0
  curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || die "E-STOP is not latched (or dashboard unreachable)"
  python3 - <<'PY' || die "a camera-side process is running; stop the viewer first"
import os,sys
me={os.getpid(),os.getppid()}
for d in os.listdir('/proc'):
    if d.isdigit() and int(d) not in me:
        try:c=open('/proc/%s/cmdline'%d,'rb').read()
        except OSError:continue
        if b'astra_camera_node' in c or b'atlas_vision3d_runtime.py\x00--worker' in c or b'atlas_vision3d_cloud_node.py' in c:sys.exit(1)
PY
}
identities(){ [ "${SKIP_SAFETY_CHECK:-}" = yes ] && { echo skipped; return; }; for u in "${UNITS[@]}"; do systemctl --user show "$u" -p MainPID -p NRestarts --value | tr '\n' ' '; done; }
check_pre(){ local -n files=$1 pre=$2; for i in "${!files[@]}"; do [ "$(h "$TARGET/${files[$i]}")" = "${pre[$i]}" ] || die "${files[$i]} differs from the verified production hash"; done; }
backup(){ local part=$1; shift; local b="$TARGET/.pre_stage32_${part}_$STAMP"; mkdir -p "$b"
  for f in "$@"; do mkdir -p "$b/$(dirname "$f")"; if [ -e "$TARGET/$f" ]; then cp -a "$TARGET/$f" "$b/$f"; else : > "$b/$f.absent"; fi; done
  ( cd "$b" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS ); echo "$b" > "$TARGET/.stage32_${part}_last_backup"; echo "backup: $b"; }
install_files(){ for f in "$@"; do [ -f "$SRC/$f" ] || die "package missing $f"; mkdir -p "$TARGET/$(dirname "$f")"; cp "$SRC/$f" "$TARGET/$f.s32u.tmp"; mv "$TARGET/$f.s32u.tmp" "$TARGET/$f"; echo "installed $f $(h "$TARGET/$f" | cut -c1-16)"; done; }
restore(){ local part=$1; shift; local b; b="$(cat "$TARGET/.stage32_${part}_last_backup" 2>/dev/null)" || die "no Stage 32 $part backup recorded"
  ( cd "$b" && sha256sum -c --quiet SHA256SUMS ) || die "backup $b failed its checksum"
  for f in "$@"; do if [ -e "$b/$f.absent" ]; then rm -f "$TARGET/$f"; else cp "$b/$f" "$TARGET/$f.s32u.tmp"; mv "$TARGET/$f.s32u.tmp" "$TARGET/$f"; fi; echo "restored $f"; done; }
restart_web(){ [ "${NO_RESTART:-}" = yes ] && { echo "NO_RESTART=yes: rover-status-web NOT restarted"; return; }
  systemctl --user restart rover-status-web
  for i in $(seq 1 30); do code=$(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:8088/v2/vision3d || true); [ "$code" = 200 ] && break; sleep 1; done
  echo "rover-status-web $(systemctl --user is-active rover-status-web); /v2/vision3d $code"; }
case "$cmd" in
  apply-ui)
    safety; check_pre UI_REPLACE UI_PRE
    for f in "${UI_NEW[@]}"; do [ ! -e "$TARGET/$f" ] || die "$f already exists (already applied?)"; done
    node -e "new Function(require('fs').readFileSync('$SRC/web/v2/vision3d.js','utf8'));require('$SRC/web/v2/vision3d_state.js')" 2>/dev/null || echo "note: node not available for a syntax check on this host"
    before="$(identities)"; backup ui "${UI_REPLACE[@]}" "${UI_NEW[@]}"; install_files "${UI_NEW[@]}" "${UI_REPLACE[@]}"
    [ "$(identities)" = "$before" ] || echo "WARNING: a protected service identity changed" >&2
    echo "UI applied; no service restarted" ;;
  rollback-ui)
    [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes"
    restore ui "${UI_REPLACE[@]}" "${UI_NEW[@]}"; echo "UI rolled back; no service restarted" ;;
  apply-config)
    safety; check_pre CF_REPLACE CF_PRE
    ( cd "$SRC/scripts" && env -u ROS_DOMAIN_ID python3 -I -c "import sys,os,json;sys.path.insert(0,'.');os.environ['ATLAS_VISION3D_MANIFEST']='../config/vision3d_live.json';import atlas_vision3d_web as w,atlas_vision3d_geometry as g;m=w.read_manifest();print('manifest ok',m['identity']['device_serial'],m['mode_support']['ir']['state'],g.calibration_state(m)['state']);assert w.DEPTH_RAW_ENCODINGS==('16UC1','32FC1')" ) || die "candidate config/import check failed"
    node -e "new Function(require('fs').readFileSync('$SRC/web/v2/vision3d.js','utf8'));const S=require('$SRC/web/v2/vision3d_state.js');if(S.PREVIEW_LABEL!=='UNCALIBRATED \u2014 DIAGNOSTIC ONLY')process.exit(1)" 2>/dev/null || echo "note: node not available for a syntax check on this host"
    before="$(identities)"; backup config "${CF_REPLACE[@]}"; install_files "${CF_REPLACE[@]}"; restart_web
    [ "$(identities)" = "$before" ] || echo "WARNING: a protected service identity changed" >&2 ;;
  rollback-config)
    [ "${OWNER_APPROVED:-}" = yes ] || die "set OWNER_APPROVED=yes"
    restore config "${CF_REPLACE[@]}"; restart_web ;;
  *) echo "usage: OWNER_APPROVED=yes $0 apply-ui|rollback-ui|apply-config|rollback-config" >&2; exit 64 ;;
esac
