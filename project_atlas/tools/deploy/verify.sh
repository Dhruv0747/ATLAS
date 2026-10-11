#!/usr/bin/env bash
# Read-only post-install checks for ATLAS staged packages. Sends GET requests only; never POSTs,
# never restarts, never commands motion.
#   bash verify.sh capture      # BEFORE install: saves V1 page bodies and legacy-DB identity
#   bash verify.sh stage1|stage2|stage3|stage4
set +e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
B=http://127.0.0.1:8088; CAP=$HOME/project_atlas/data/staging/verify_capture
pass(){ echo "PASS $*"; }; fail(){ echo "FAIL $*"; FAILED=1; }
code(){ curl -s -o /dev/null -m 5 -w '%{http_code}' "$1"; }
cpu60(){ local p=$1 hz=$(getconf CLK_TCK) a b; a=$(awk '{print $14+$15}' /proc/$p/stat); sleep 60; b=$(awk '{print $14+$15}' /proc/$p/stat)
         python3 -c "print(round(100*($b-$a)/$hz/60,1))"; }
v1_pages(){ for p in / /mapping /commissioning /wifi /diagnostics.js /commissioning.js; do
              n=$(echo "$p" | tr '/.' '__'); curl -s -m 5 "$B$p" -o "$1/page$n"; done; }
case "$1" in
capture)
  mkdir -p "$CAP"; v1_pages "$CAP"
  stat -c '%s %Y' $HOME/project_atlas/data/visual_cloud/history.sqlite3 > "$CAP/legacy_db.stat" 2>/dev/null
  echo "captured V1 pages and legacy DB identity in $CAP";;
stage1|stage2|stage3)
  systemctl --user is-active --quiet rover-status-web && pass "rover-status-web active" || fail "rover-status-web not active"
  for p in / /mapping /commissioning /wifi /api/status /api/map; do c=$(code "$B$p"); [ "$c" = 200 ] && pass "GET $p 200" || fail "GET $p $c"; done
  if [ -d "$CAP" ]; then T=$(mktemp -d); v1_pages "$T"
    for f in "$CAP"/page*; do n=$(basename "$f"); cmp -s "$f" "$T/$n" && pass "V1 $n unchanged" || echo "CHECK V1 $n differs from the pre-install capture (V1 pages are not meant to change): inspect"; done; fi
  age=$(curl -s -m 5 "$B/api/status" | python3 -c "import sys,json;r=json.load(sys.stdin)['ros'];print(r.get('odom',{}).get('age'), r.get('control_policy',{}).get('age'))")
  echo "INFO odom/control_policy age: $age"
  ;;&
stage2)
  for p in /v2/ /v2/mapping /v2/commissioning /v2/wifi /v2/glass.css /v2/base.css /v2/pages.css /v2/command.js /v2/shell.js /v2/estop.js /v2/assets/icons.svg /v2/assets/atlas-logo-96.webp; do
    c=$(code "$B$p"); [ "$c" = 200 ] && pass "GET $p 200" || fail "GET $p $c"; done
  for p in /v2/../logo.png /v2/.hidden /v2/assets/ /v2/notes.md; do c=$(code "$B$p"); [ "$c" = 404 ] && pass "GET $p 404" || fail "GET $p $c"; done
  ;;
stage3)
  source /opt/ros/humble/setup.bash >/dev/null 2>&1
  nodes=$(timeout 15 ros2 node list 2>/dev/null); echo "$nodes" | grep -qx /atlas_web_control && pass "node /atlas_web_control" || fail "node /atlas_web_control missing"
  echo "$nodes" | grep -qx /atlas_web_status && pass "node /atlas_web_status" || fail "node /atlas_web_status missing"
  P=$(systemctl --user show rover-status-web -p MainPID --value); echo "INFO rover-status-web CPU over 60 s: $(cpu60 $P)% of one core (before: ~57%)"
  ;;
stage4)
  for s in atlas-visual-cloud-server atlas-visual-cloud-agent; do systemctl --user is-active --quiet $s && pass "$s active" || fail "$s not active"; done
  since=$(systemctl --user show atlas-visual-cloud-agent -p ActiveEnterTimestamp --value)
  n=$(journalctl --user -u atlas-visual-cloud-agent --since "$since" -o cat | grep -c "cloud unavailable"); [ "$n" = 0 ] && pass "no failed uploads since restart" || fail "$n failed uploads"
  journalctl --user -u atlas-visual-cloud-agent --since "$since" -o cat | grep -m1 "upload mode"
  if [ -f "$CAP/legacy_db.stat" ]; then [ "$(stat -c '%s %Y' $HOME/project_atlas/data/visual_cloud/history.sqlite3)" = "$(cat $CAP/legacy_db.stat)" ] && pass "legacy 25 GB history unchanged" || fail "legacy history changed"; fi
  P=$(systemctl --user show atlas-visual-cloud-agent -p MainPID --value); echo "INFO agent idle CPU over 60 s: $(cpu60 $P)% of one core (before: ~11%)"
  echo "INFO opening the live view for 25 s (GET /api/v1/robots each second)"
  for i in $(seq 1 25); do curl -s -o /dev/null http://127.0.0.1:8095/api/v1/robots; sleep 1; done
  curl -s http://127.0.0.1:8095/api/v1/robots | python3 -c "import sys,json;d=json.load(sys.stdin);print('PASS live view has data' if d and d[0].get('traffic') else 'FAIL live view empty')"
  ls -la $HOME/project_atlas/data/visual_cloud/
  ;;
*) echo "usage: verify.sh capture|stage1|stage2|stage3|stage4"; exit 2;;
esac
exit ${FAILED:-0}
