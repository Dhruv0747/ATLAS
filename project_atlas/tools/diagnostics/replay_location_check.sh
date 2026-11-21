#!/usr/bin/env bash
# Isolated replay of the REAL localization monitor + CHECK MY LOCATION against a saved bag.
# Private DDS domain, localhost only, private HOME (live state files are never written), sim time.
# Nothing is published on the live graph; no AMCL, Nav2, mux or motor process is involved.
#
#   replay_location_check.sh <scripts_dir_with_stage_installed> <bag_dir> <out_dir> [with-amcl]
# Without "with-amcl" the bag's /amcl_pose is withheld, reproducing an un-seeded AMCL.
set -euo pipefail
SCRIPTS=$(realpath "$1"); BAG=$(realpath "$2"); OUT=$(realpath -m "$3"); MODE=${4:-no-amcl}
[ "${ROS_DOMAIN_ID:-0}" != 0 ] || { echo "refusing: set a private ROS_DOMAIN_ID"; exit 2; }
[ "${ROS_LOCALHOST_ONLY:-0}" = 1 ] || { echo "refusing: ROS_LOCALHOST_ONLY=1 required"; exit 2; }
mkdir -p "$OUT"; FAKE=$OUT/home; rm -rf "$FAKE"; mkdir -p "$FAKE/project_atlas/maps" "$FAKE/.config/project_atlas" "$FAKE/.local/state/project_atlas"
MAP=$HOME/project_atlas/maps/atlas_latest.yaml
cp -L "$MAP" "$FAKE/project_atlas/maps/"; cp -L "$(dirname "$MAP")/$(awk -F': *' '/^image:/{print $2}' "$MAP")" "$FAKE/project_atlas/maps/"
echo suggest > "$FAKE/.config/project_atlas/relocalize_mode"
set +u; source /opt/ros/humble/setup.bash; set -u   # ROS setup reads unset variables
PIDS=()
cleanup(){ for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  # `ros2 run` leaves its child behind when the wrapper is killed; match this run's private map path only.
  pkill -f -- "yaml_filename:=$FAKE/" 2>/dev/null || true
  sleep 1; for p in "${PIDS[@]}"; do kill -9 "$p" 2>/dev/null || true; done; }
pgrep -f -- "nav2_map_server/map_server .*use_sim_time" >/dev/null && { echo "refusing: a replay map_server is still running"; exit 2; }
trap cleanup EXIT
ros2 run nav2_map_server map_server --ros-args -p yaml_filename:="$FAKE/project_atlas/maps/atlas_latest.yaml" -p use_sim_time:=true > "$OUT/map_server.log" 2>&1 & PIDS+=($!)
sleep 4; ros2 lifecycle set /map_server configure >/dev/null; ros2 lifecycle set /map_server activate >/dev/null
python3 - > "$OUT/policy.log" 2>&1 <<'EOF' & PIDS+=($!)
import rclpy, time
from std_msgs.msg import String
rclpy.init(); n = rclpy.create_node('replay_stop_policy'); p = n.create_publisher(String, '/atlas/control_policy', 10)
while True:
    p.publish(String(data='{"stop_latched": true, "stop_reason": "replay"}')); time.sleep(0.2)
EOF
TOPICS="/scan /tf /tf_static /odom /imu/data /cmd_vel"; [ "$MODE" = with-amcl ] && TOPICS="$TOPICS /amcl_pose"
ros2 bag play "$BAG" --clock 1000 --loop --topics $TOPICS > "$OUT/bag.log" 2>&1 & PIDS+=($!)
HOME=$FAKE python3 "$SCRIPTS/atlas_localization_monitor.py" --ros-args -p use_sim_time:=true > "$OUT/monitor.log" 2>&1 & PIDS+=($!)
STATE=$FAKE/.local/state/project_atlas/manual_location_check.json
for i in $(seq 1 60); do [ -f "$STATE" ] && ros2 service list 2>/dev/null | grep -q /atlas/location_check/start && break; sleep 1; done
sleep 6   # let scans, TF and odometry buffers fill and the parked window settle
T0=$(date +%s.%N)
ros2 service call /atlas/location_check/start std_srvs/srv/Trigger > "$OUT/start_reply.txt" 2>&1 || true
for i in $(seq 1 80); do s=$(python3 -c "import json;print(json.load(open('$STATE')).get('state'))" 2>/dev/null || true)
  case "$s" in CHECKING|IDLE|"") sleep 0.5;; *) break;; esac; done
python3 - "$STATE" "$T0" > "$OUT/result.json" <<'EOF'
import json, sys, time
d = json.load(open(sys.argv[1])); r = d.get('result') or {}; e = d.get('evidence') or {}
print(json.dumps(dict(state=d.get('state'), reason=d.get('reason'), calculation_s=d.get('calculation_s'),
    wall_s=round(time.time() - float(sys.argv[2]), 2), amcl_status=e.get('amcl_status'), amcl_reason=e.get('amcl_reason'),
    lidar_pose=r.get('lidar_pose'), best_fit=r.get('best_fit'), margin=r.get('margin'), candidates=(r.get('candidates') or [])[:3],
    amcl_pose=r.get('amcl_pose'), xy_disagreement_m=r.get('xy_disagreement_m'),
    stages={k: v.get('status') for k, v in (e.get('stages') or {}).items()}, last_block=d.get('last_block'),
    navigation_authorized=d.get('navigation_authorized'), correction_enabled=d.get('correction_enabled')), indent=1))
EOF
cat "$OUT/result.json"
