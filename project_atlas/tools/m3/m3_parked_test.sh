#!/bin/bash
# M3 step 1: parked RTAB-Map test in "3D mapping mode" (owner option B). Rover must stay parked; no motion commands.
# Pauses the approved extras, runs RTAB-Map in domain 77 for MAP_S seconds, measures, exports, then RESTORES every
# paused unit (also on error / Ctrl-C via trap). Usage: bash m3_parked_test.sh [MAP_S]
MAP_S=${1:-60}
D=$(cd "$(dirname "$0")" && pwd); TS=$(date +%Y%m%d-%H%M%S)
OUT=$HOME/project_atlas/maps3d; mkdir -p $OUT; DB=$OUT/m3_parked_$TS.db
PAUSE="atlas-voice-companion atlas-localization-monitor atlas-lidar-odom atlas-lidar-odom-gate atlas-ekf-lidar-candidate atlas-camera-joystick atlas-gnss atlas-agent-supervisor atlas-local-llm atlas-visual-cloud-agent atlas-camera"
PAUSED=""; BPG=""; LPG=""
cpu(){ read -r _ a b c d e f g h _ < /proc/stat; t1=$((a+b+c+d+e+f+g+h)); i1=$((d+e)); sleep $1; read -r _ a b c d e f g h _ < /proc/stat; t2=$((a+b+c+d+e+f+g+h)); i2=$((d+e)); echo $(( 100*((t2-t1)-(i2-i1))/(t2-t1) )); }
pt(){ awk '{print $14+$15}' /proc/$1/stat 2>/dev/null || echo 0; }
restore(){
  echo "=== $(date +%T) RESTORE"
  [ -n "$LPG" ] && kill -INT -- -$LPG 2>/dev/null; [ -n "$BPG" ] && kill -INT -- -$BPG 2>/dev/null
  sleep 4; [ -n "$LPG" ] && kill -KILL -- -$LPG 2>/dev/null; [ -n "$BPG" ] && kill -KILL -- -$BPG 2>/dev/null
  for u in $PAUSED; do systemctl --user start $u; done
  sleep 3; bad=""; for u in $PAUSED; do systemctl --user is-active --quiet $u || bad="$bad $u"; done
  echo "restored: $(echo $PAUSED | wc -w) units | not active:${bad:- none}"
}
trap restore EXIT
source /opt/ros/humble/setup.bash
python3 $HOME/project_atlas/scripts/atlas_astra_bridge_parked_check.py || { echo "ABORT: not parked"; PAUSED=""; exit 1; }
systemctl --user is-active --quiet atlas-astra-obstacles || { echo "ABORT: Astra (Track A) not running"; exit 1; }
echo "=== $(date +%T) baseline CPU (15 s): $(cpu 15) %"
for u in $PAUSE; do systemctl --user is-active --quiet $u && { systemctl --user stop $u && PAUSED="$PAUSED $u"; }; done
echo "paused:$PAUSED"; sleep 5
echo "=== mapping-mode CPU before RTAB-Map (15 s): $(cpu 15) %"
setsid nice -n 5 ros2 run domain_bridge domain_bridge $D/m3_odom_bridge.yaml > /tmp/m3_bridge.log 2>&1 & BPG=$!
sleep 8
ROS_DOMAIN_ID=77 M3_DB=$DB setsid nice -n 5 ros2 launch $D/m3_rtabmap.launch.py > /tmp/m3_launch.log 2>&1 & LPG=$!
sleep 20
RT=$(pgrep -f "rtabmap_slam/rtabmap" | head -1); PC=$(pgrep -f "rtabmap_util/point_cloud_xyz" | head -1); BR=$(pgrep -f "domain_bridge/domain_bridge .*m3_odom" | head -1)
echo "pids rtabmap=$RT cloud=$PC bridge=$BR"
[ -z "$RT" ] && { echo "RTAB-Map did not start:"; tail -15 /tmp/m3_launch.log | cut -c1-200; exit 1; }
HZ=$(getconf CLK_TCK); r1=$(pt $RT); c1=$(pt $PC); b1=$(pt $BR)
W=$((MAP_S-20)); [ $W -lt 20 ] && W=20
ALL=$(cpu $W)
r2=$(pt $RT); c2=$(pt $PC); b2=$(pt $BR)
pc(){ echo "scale=2; ($2-$1)/$HZ/$W*100/6" | bc; }
echo "=== mapping CPU over $W s: whole Jetson $ALL % | rtabmap $(pc $r1 $r2) % | depth->cloud $(pc $c1 $c2) % | odom/tf bridge $(pc $b1 $b2) % (of the 6-core Jetson)"
echo "RSS: rtabmap $(awk '/VmRSS/{print int($2/1024)}' /proc/$RT/status) MB, cloud $(awk '/VmRSS/{print int($2/1024)}' /proc/$PC/status) MB | tj $(awk '{printf "%.1f", $1/1000}' $(grep -l tj-thermal /sys/class/thermal/thermal_zone*/type | sed 's/type/temp/')) C"
ROS_DOMAIN_ID=77 timeout 10 ros2 topic hz /astra/depth_cloud --window 10 2>&1 | grep -m1 average | sed 's/^/depth cloud: /'
grep -iE "error|warn" /tmp/m3_launch.log | grep -viE "invalid type|deprecated" | sort | uniq -c | sort -rn | head -6 | cut -c1-200
kill -INT -- -$LPG 2>/dev/null; for i in $(seq 1 40); do pgrep -f "rtabmap_slam/rtabmap" >/dev/null || break; sleep 0.5; done; LPG=""
echo "RTAB-Map closed after $((i/2)) s"
echo "=== database $(ls -la $DB | awk '{print $5}') bytes"
rtabmap-info $DB 2>/dev/null | grep -iE "Nodes|Total|Map|Links" | head -6
rtabmap-export --output_dir $OUT --output m3_parked_$TS $DB > /tmp/m3_export.log 2>&1; ls -la $OUT/m3_parked_$TS* 2>/dev/null | awk '{print $5, $9}'
P=$(ls $OUT/m3_parked_$TS*.ply 2>/dev/null | head -1); [ -n "$P" ] && head -c 400 "$P" | grep -a "element vertex"
tail -3 /tmp/m3_export.log | cut -c1-200
