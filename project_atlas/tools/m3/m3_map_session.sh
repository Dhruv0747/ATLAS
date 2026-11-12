#!/bin/bash
# M3 step 2: 3D mapping session while the OWNER drives by hand. This script never commands motion.
# Start (parked only): pause the approved extras, bridge /odom+/tf 0->77, start RTAB-Map + live dashboard feed.
# Runs until: `touch /tmp/m3_stop`, MAX_S seconds, or CPU >= 85 % for 3 consecutive 10 s samples (auto-stop).
# End: stop everything, export the map (PLY), RESTORE every paused unit (also on error / signal via trap).
MAX_S=${1:-900}
D=$(cd "$(dirname "$0")" && pwd); TS=$(date +%Y%m%d-%H%M%S)
OUT=$HOME/project_atlas/maps3d; mkdir -p $OUT; DB=$OUT/m3_session_$TS.db
# Default (2026-11-12 localization drive): keep the LiDAR-odometry trio and the localization monitor RUNNING so their
# output is recorded; pause only non-safety extras. Override with M3_PAUSE="unit unit ...".
PAUSE=${M3_PAUSE:-"atlas-voice-companion atlas-camera-joystick atlas-gnss atlas-agent-supervisor atlas-local-llm atlas-visual-cloud-agent atlas-camera"}
BAG_TOPICS="/scan /odom /tf /tf_static /amcl_pose /particle_cloud /map /initialpose /set_pose /cmd_vel /imu/data /yahboom/imu/data_calibrated /yahboom/odom /yahboom/encoder/m1 /yahboom/encoder/m2 /yahboom/encoder/m3 /yahboom/encoder/m4 /atlas/encoder_health /lidar/odom /lidar/odom_raw /odom/lidar_fused_candidate /lidar/odom/health /astra/obstacle_scan"
PAUSED=""; BPG=""; LPG=""; RPG=""; BAG=$OUT/m3_session_${TS}_bag; rm -f /tmp/m3_stop
cpu(){ read -r _ a b c d e f g h _ < /proc/stat; t1=$((a+b+c+d+e+f+g+h)); i1=$((d+e)); sleep $1; read -r _ a b c d e f g h _ < /proc/stat; t2=$((a+b+c+d+e+f+g+h)); i2=$((d+e)); echo $(( 100*((t2-t1)-(i2-i1))/(t2-t1) )); }
stopgroup(){ local g=$1; [ -z "$g" ] && return 0; kill -INT -- -$g 2>/dev/null
  for i in $(seq 1 30); do kill -0 -- -$g 2>/dev/null || return 0; sleep 0.5; done
  kill -TERM -- -$g 2>/dev/null; sleep 3; kill -KILL -- -$g 2>/dev/null; sleep 1; return 0; }
restore(){
  echo "=== $(date +%T) RESTORE"
  stopgroup "$LPG"; stopgroup "$RPG"; stopgroup "$BPG"; LPG=""; RPG=""; BPG=""
  for u in $PAUSED; do systemctl --user start $u; done
  sleep 3; bad=""; for u in $PAUSED; do systemctl --user is-active --quiet $u || bad="$bad $u"; done
  echo "restored: $(echo $PAUSED | wc -w) units | not active:${bad:- none}"; PAUSED=""
  echo "leftover mapping processes: $(ps -eo args | grep -cE '[r]tabmap_slam/rtabmap|[a]tlas_map3d_live|[p]oint_cloud_xyz|[m]3_odom_bridge|[m]3_rtabmap.launch|[r]os2 bag record')"
}
trap restore EXIT
source /opt/ros/humble/setup.bash
python3 $HOME/project_atlas/scripts/atlas_astra_bridge_parked_check.py || { echo "ABORT: not parked at start"; exit 1; }
systemctl --user is-active --quiet atlas-astra-obstacles || { echo "ABORT: Astra (Track A) not running"; exit 1; }
for u in $PAUSE; do systemctl --user is-active --quiet $u && { systemctl --user stop $u && PAUSED="$PAUSED $u"; }; done
echo "$(date +%T) paused:$PAUSED"
setsid nice -n 5 ros2 run domain_bridge domain_bridge $D/m3_odom_bridge.yaml > /tmp/m3_bridge.log 2>&1 & BPG=$!
# 2D map source: record LiDAR + odometry + TF in production domain 0 (listen only; the 2D map is built afterwards)
ROS_DOMAIN_ID=0 setsid nice -n 5 ros2 bag record -o $BAG $BAG_TOPICS > /tmp/m3_bag.log 2>&1 & RPG=$!
sleep 10
ROS_DOMAIN_ID=77 M3_DB=$DB M3_KEEP_UNLINKED=false setsid nice -n 5 ros2 launch $D/m3_rtabmap.launch.py > /tmp/m3_launch.log 2>&1 & LPG=$!
sleep 15
pgrep -f "rtabmap_slam/rtabmap" >/dev/null || { echo "ABORT: RTAB-Map did not start"; tail -10 /tmp/m3_launch.log; exit 1; }
echo "$(date +%T) MAPPING LIVE — owner may drive now (db $DB)"
T0=$(date +%s); HOT=0; MAXC=0
while :; do
  [ -f /tmp/m3_stop ] && { echo "$(date +%T) stop requested"; break; }
  [ $(( $(date +%s)-T0 )) -ge $MAX_S ] && { echo "$(date +%T) time limit reached"; break; }
  pgrep -f "rtabmap_slam/rtabmap" >/dev/null || { echo "$(date +%T) RTAB-Map exited unexpectedly"; break; }
  C=$(cpu 10); [ $C -gt $MAXC ] && MAXC=$C
  if [ $C -ge 85 ]; then HOT=$((HOT+1)); else HOT=0; fi
  N=$(grep -c "rtabmap (" /tmp/m3_launch.log); L=$(grep "rtabmap (" /tmp/m3_launch.log | tail -1 | grep -oE "WM=[0-9]+" )
  O=$(curl -s -m 2 http://127.0.0.1:8088/api/status | python3 -c "import sys,json;o=json.load(sys.stdin)['ros']['odom']['value'];print('x %.2f y %.2f v %.2f'%(o['x'],o['y'],o['vx']))" 2>/dev/null)
  echo "$(date +%T) cpu ${C}% | updates $N $L | odom $O"
  [ $HOT -ge 3 ] && { echo "$(date +%T) AUTO-STOP: CPU >= 85 % for 30 s"; break; }
done
echo "=== session $(( $(date +%s)-T0 )) s, peak CPU ${MAXC}%"
T1=$(date +%s); stopgroup "$LPG"; LPG=""; echo "RTAB-Map stopped after $(( $(date +%s)-T1 )) s"
stopgroup "$RPG"; RPG=""; echo "2D recording: $(du -sh $BAG 2>/dev/null | cut -f1) in $BAG"; ros2 bag info $BAG 2>/dev/null | grep -E "Duration|Topic:" | cut -c1-120
echo "database $(ls -la $DB | awk '{print $5}') bytes"
rtabmap-export --output_dir $OUT --output m3_session_$TS $DB > /tmp/m3_export.log 2>&1; tail -4 /tmp/m3_export.log | cut -c1-200
ls -la $OUT/m3_session_$TS* | awk '{print $5, $9}'
P=$(ls $OUT/m3_session_${TS}*.ply 2>/dev/null | head -1); [ -n "$P" ] && head -c 600 "$P" | grep -a "element vertex"
