#!/bin/bash
# Stage 32 U2 with restart monitoring. NOT TO BE RUN WITHOUT THE OWNER'S SEPARATE CONFIRMATION (OWNER_APPROVED=yes).
# 1. passive 1-Hz per-process /proc recorder (stage31_cpurec.py, no ROS participant, no CLI) started 20 s BEFORE the restart
# 2. stage32_ui.sh apply-config (installs manifest + geometry, restarts rover-status-web only; refuses unless camera off,
#    E-STOP latched and live hashes are the verified production values)
# 3. waits for the restart transient to settle: 5 consecutive 1-s whole-machine samples <= 75 % within 120 s.
#    This is a deployment observation only; the camera guard is unchanged and no camera is started here.
# 4. verifies: E-STOP latched, policy manual-only, sensor freshness, protected identities unchanged, Pi Camera 200,
#    Vision Lab reports Infrared "verified" and the device serial. Any failure -> rollback-config (one more restart).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="${OUT:-$HOME/project-atlas-migration/stage32-u2-$(date +%Y%m%d_%H%M%S)}"; mkdir -p "$OUT"
REC="${REC:-$HOME/project-atlas-migration/stage32-deploy-20261021/cpurec.py}"
[ "${OWNER_APPROVED:-}" = yes ] || { echo "REFUSE: owner confirmation required"; exit 2; }
ident(){ for u in atlas-camera rover-base-telemetry atlas-cmd-vel-mux atlas-ekf atlas-localization atlas-lidar; do systemctl --user show $u -p MainPID -p NRestarts --value | tr '\n' ' '; done; }
before="$(ident)"; echo "identities_before $before" > "$OUT/log.txt"
systemd-run --user --unit=s32rec-u2 --collect python3 "$REC" "$OUT/trace.jsonl" 200 >> "$OUT/log.txt" 2>&1
sleep 20; date -Iseconds >> "$OUT/log.txt"; echo restart_at=$(date +%s.%N) >> "$OUT/log.txt"
OWNER_APPROVED=yes bash "$HERE/stage32_ui.sh" apply-config >> "$OUT/log.txt" 2>&1; rc=$?
echo "apply_rc=$rc" >> "$OUT/log.txt"
settle=$(python3 - "$OUT/trace.jsonl" "$(grep restart_at "$OUT/log.txt" | cut -d= -f2)" <<'PY'
import json,sys,time
path,t_restart=sys.argv[1],float(sys.argv[2]); deadline=time.time()+120; run=0
while time.time()<deadline:
    rows=[json.loads(l) for l in open(path)][1:]
    after=[r for r in rows if r['wall']>t_restart]
    run=0; first=None
    for r in after:
        run=run+1 if r['busy']<=75 else 0
        if run==5: first=r['wall']; break
    if first: print('%.1f'%(first-t_restart)); sys.exit(0)
    time.sleep(2)
print('NOT_SETTLED')
PY
)
echo "settle_s=$settle" >> "$OUT/log.txt"
ok=yes
curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" || { echo "FAIL estop" >> "$OUT/log.txt"; ok=no; }
curl -s -m5 http://127.0.0.1:8088/api/status | python3 -c "
import sys,json;d=json.load(sys.stdin);r=d['ros'];p=json.loads(r['control_policy']['value'])
ages={k:r.get(k,{}).get('age') for k in ('lidar','odom','imu_yaw','enc_m1')};print('policy',p['manual_only'],p['stop_latched'],'ages',ages)
sys.exit(0 if p['manual_only'] and p['stop_latched'] and all(a is not None and a<2 for a in ages.values()) else 1)" >> "$OUT/log.txt" 2>&1 || { echo "FAIL policy/freshness" >> "$OUT/log.txt"; ok=no; }
[ "$(ident)" = "$before" ] || { echo "FAIL protected identity changed" >> "$OUT/log.txt"; ok=no; }
[ "$(curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:8088/camera.jpg)" = 200 ] || { echo "FAIL pi camera" >> "$OUT/log.txt"; ok=no; }
curl -s -m5 http://127.0.0.1:8088/api/vision3d/summary >/dev/null
curl -s -m5 http://127.0.0.1:8088/api/vision3d/status | python3 -c "
import sys,json;d=json.load(sys.stdin);print('ir_mode',d['mode_support']['ir']['state'],'calibration',d['calibration_state']['state'])
sys.exit(0 if d['mode_support']['ir']['state']=='verified' else 1)" >> "$OUT/log.txt" 2>&1 || { echo "FAIL vision3d status" >> "$OUT/log.txt"; ok=no; }
[ "$rc" = 0 ] && [ "$settle" != NOT_SETTLED ] || ok=no
if [ "$ok" != yes ]; then echo "ROLLING BACK" >> "$OUT/log.txt"; OWNER_APPROVED=yes bash "$HERE/stage32_ui.sh" rollback-config >> "$OUT/log.txt" 2>&1; fi
echo "result=$([ $ok = yes ] && echo U2_DEPLOYED || echo U2_ROLLED_BACK)" >> "$OUT/log.txt"; cat "$OUT/log.txt"
