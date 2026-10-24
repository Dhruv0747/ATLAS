#!/bin/bash
# Dashboard executor ExitStack-removal package. NOT TO BE RUN WITHOUT THE OWNER'S SEPARATE APPROVAL (OWNER_APPROVED=yes).
#   check     read-only: package checksums, live pre-hashes, unchanged atlas_status_web.py; changes nothing
#   apply     monitored install of 2 files + ONE rover-status-web restart; automatic rollback on any failed check
#   rollback  restore the 2 originals from the recorded backup + ONE rover-status-web restart
# Never touches: atlas_status_web.py, voice, white-glass assets, E-STOP, motors, sensors, maps, navigation, camera.
set -uo pipefail
cmd="${1:-}"; PKG="$(cd "$(dirname "$0")" && pwd)"; T="${TARGET:-$HOME/project_atlas/scripts}"; WEBROOT="$(dirname "$T")/web"
REC="${REC:-$HOME/project-atlas-migration/stage32-deploy-20261021/cpurec.py}"; STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${OUT:-$HOME/project-atlas-migration/dashboard-exitstack-$STAMP}"
FILES=(atlas_dashboard_executor_impl.py atlas_dashboard_executor.py)
PRE=(543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1 2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab)
WEB_SHA=acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439
UNITS=(atlas-camera rover-base-telemetry atlas-cmd-vel-mux atlas-ekf atlas-localization atlas-lidar atlas-voice-companion atlas-safety-status atlas-mission-control)
h(){ sha256sum "$1" | cut -d' ' -f1; }
die(){ echo "REFUSE: $*" >&2; exit 2; }
log(){ echo "$*" | tee -a "$OUT/log.txt"; }
ident(){ for u in "${UNITS[@]}"; do echo -n "$u=$(systemctl --user show "$u" -p MainPID -p NRestarts --value 2>/dev/null | tr '\n' ',') "; done; }
webhash(){ (cd "$WEBROOT" && find . -type f \( -name '*.css' -o -name '*.html' -o -name '*.js' \) -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16); }
pkg_ok(){ (cd "$PKG" && sha256sum -c --quiet SHA256SUMS) || die "package checksum failure"; }
pre_ok(){ for i in "${!FILES[@]}"; do [ "$(h "$T/${FILES[$i]}")" = "${PRE[$i]}" ] || die "${FILES[$i]} is not the verified production version"; done
          [ "$(h "$T/atlas_status_web.py")" = "$WEB_SHA" ] || die "atlas_status_web.py changed since this package was built"; }
inst_ok(){ for f in "${FILES[@]}"; do [ "$(h "$T/$f")" = "$(h "$PKG/install/$f")" ] || return 1; done; }
safety(){ curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || die "E-STOP not latched or dashboard unreachable"
  python3 - <<'PY' || die "an Astra/Vision Lab camera process is running"
import os,sys
me={os.getpid(),os.getppid()}
for d in os.listdir('/proc'):
    if d.isdigit() and int(d) not in me:
        try:c=open('/proc/%s/cmdline'%d,'rb').read()
        except OSError:continue
        if b'astra_camera_node' in c or b'atlas_vision3d_runtime.py\x00--worker' in c:sys.exit(1)
PY
}
restart_web(){ systemctl --user restart rover-status-web; for i in $(seq 1 40); do c=$(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:8088/v2/ || true); [ "$c" = 200 ] && break; sleep 1; done; log "rover-status-web $(systemctl --user is-active rover-status-web) /v2/=$c"; }
health(){  # prints failures; returns 0 only when every check passes
  local bad=0
  inst_ok || { log "FAIL installed hashes"; bad=1; }
  curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || { log "FAIL estop"; bad=1; }
  curl -s -m8 http://127.0.0.1:8088/api/status | python3 -c "
import sys,json;d=json.load(sys.stdin);r=d['ros'];p=json.loads(r['control_policy']['value'])
ages={k:r.get(k,{}).get('age') for k in ('lidar','odom','imu_yaw','enc_m1','cmd_vel')}
fresh=sum(1 for v in r.values() if isinstance(v,dict) and isinstance(v.get('age'),(int,float)) and v['age']<3)
err=(r.get('web_error') or {}).get('value'); print('policy',p['manual_only'],p['stop_latched'],'ages',ages,'fresh_keys',fresh,'web_error',err)
sys.exit(0 if p['manual_only'] and p['stop_latched'] and all(a is not None and a<2 for a in ages.values()) and not err and fresh>=int(sys.argv[1]) else 1)" "${MIN_FRESH:-40}" >> "$OUT/log.txt" 2>&1 || { log "FAIL policy/freshness/executor"; bad=1; }
  [ "$(ident)" = "$IDENT_BEFORE" ] || { log "FAIL protected service identity changed"; bad=1; }
  for u in /camera.jpg /v2/ /v2/vision3d /api/vision3d/summary; do [ "$(curl -s -o /dev/null -w '%{http_code}' -m8 http://127.0.0.1:8088$u)" = 200 ] || { log "FAIL route $u"; bad=1; }; done
  [ "$(webhash)" = "$WEB_BEFORE" ] || { log "FAIL white-glass/static assets changed"; bad=1; }
  [ "$(h "$T/atlas_status_web.py")" = "$WEB_SHA" ] || { log "FAIL atlas_status_web.py changed"; bad=1; }
  return $bad; }
settle(){ python3 - "$OUT/trace.jsonl" "$1" <<'PY'
import json,sys,time
path,t0=sys.argv[1],float(sys.argv[2]); end=time.time()+120
while time.time()<end:
    rows=[json.loads(l) for l in open(path)][1:]; run=0
    for r in rows:
        if r['wall']<=t0: continue
        run=run+1 if r['busy']<=75 else 0
        if run==5: print('%.1f'%(r['wall']-t0)); sys.exit(0)
    time.sleep(2)
print('NOT_SETTLED')
PY
}
case "$cmd" in
  check) pkg_ok; pre_ok; echo "CHECK OK: package intact, live files are the verified production versions, atlas_status_web.py unchanged" ;;
  apply)
    [ "${OWNER_APPROVED:-}" = yes ] || die "owner approval required"; mkdir -p "$OUT"; pkg_ok; pre_ok; safety
    IDENT_BEFORE="$(ident)"; WEB_BEFORE="$(webhash)"; log "identities_before $IDENT_BEFORE"; log "static_assets $WEB_BEFORE"
    B="$(dirname "$T")/.pre_dashboard_exitstack_$STAMP"; mkdir -p "$B"; for f in "${FILES[@]}"; do cp -a "$T/$f" "$B/$f"; done
    (cd "$B" && sha256sum "${FILES[@]}" > SHA256SUMS); echo "$B" > "$(dirname "$T")/.dashboard_exitstack_last_backup"; log "backup $B"
    systemd-run --user --unit=dash-exitstack-rec-$STAMP --collect python3 "$REC" "$OUT/trace.jsonl" 260 >> "$OUT/log.txt" 2>&1
    sleep 20; MIN_FRESH="${MIN_FRESH:-40}" health > /dev/null 2>&1; log "pre-restart health rc=$? (informational)"
    for f in "${FILES[@]}"; do cp "$PKG/install/$f" "$T/$f.dexs.tmp"; mv "$T/$f.dexs.tmp" "$T/$f"; log "installed $f $(h "$T/$f" | cut -c1-16)"; done
    t_restart=$(date +%s.%N); log "restart_at=$t_restart"; restart_web
    s=$(settle "$t_restart"); log "settle_s=$s"; sleep 15
    if [ "$s" != NOT_SETTLED ] && health; then log "result=DASHBOARD_EXITSTACK_DEPLOYED"
    else log "ROLLING BACK"; for f in "${FILES[@]}"; do cp "$B/$f" "$T/$f.dexs.tmp"; mv "$T/$f.dexs.tmp" "$T/$f"; done; restart_web
         for i in "${!FILES[@]}"; do [ "$(h "$T/${FILES[$i]}")" = "${PRE[$i]}" ] || log "ROLLBACK HASH MISMATCH ${FILES[$i]}"; done; log "result=ROLLED_BACK"; fi
    cat "$OUT/log.txt" ;;
  rollback)
    [ "${OWNER_APPROVED:-}" = yes ] || die "owner approval required"; mkdir -p "$OUT"
    B="$(cat "$(dirname "$T")/.dashboard_exitstack_last_backup" 2>/dev/null)" || die "no backup recorded"
    (cd "$B" && sha256sum -c --quiet SHA256SUMS) || die "backup checksum failure"
    for f in "${FILES[@]}"; do cp "$B/$f" "$T/$f.dexs.tmp"; mv "$T/$f.dexs.tmp" "$T/$f"; done; restart_web
    for i in "${!FILES[@]}"; do [ "$(h "$T/${FILES[$i]}")" = "${PRE[$i]}" ] && log "restored ${FILES[$i]}" || log "MISMATCH ${FILES[$i]}"; done ;;
  *) echo "usage: [OWNER_APPROVED=yes] $0 check|apply|rollback" >&2; exit 64 ;;
esac
