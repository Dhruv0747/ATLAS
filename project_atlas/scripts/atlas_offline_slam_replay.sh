#!/usr/bin/env bash
set -Eeo pipefail

if (( $# != 3 )); then
  echo "usage: $0 BAG_DIRECTORY EKF_CONFIG OUTPUT_PREFIX" >&2
  exit 2
fi

bag=$1
ekf_config=$2
output=$3
export ROS_DOMAIN_ID="${ATLAS_REPLAY_DOMAIN_ID:-77}"
work="$(mktemp -d)"
cleanup() {
  for pid in "${slam_pid:-}" "${ekf_pid:-}"; do
    [[ -n "$pid" ]] && kill -INT "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  rm -rf -- "$work"
}
trap cleanup EXIT INT TERM

source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true
mkdir -p "$(dirname "$output")"

ros2 run robot_localization ekf_node --ros-args \
  --params-file "$ekf_config" \
  -p use_sim_time:=true \
  -r odometry/filtered:=/odom \
  >"$work/ekf.log" 2>&1 &
ekf_pid=$!

ros2 run slam_toolbox async_slam_toolbox_node --ros-args \
  -p use_sim_time:=true \
  -p odom_frame:=odom -p map_frame:=map -p base_frame:=base_link \
  -p scan_topic:=/scan -p mode:=mapping \
  -p min_laser_range:=0.20 -p max_laser_range:=8.0 \
  -p minimum_time_interval:=0.10 -p minimum_travel_distance:=0.05 \
  -p minimum_travel_heading:=0.10 -p map_update_interval:=1.5 \
  -p scan_queue_size:=30 -p transform_timeout:=1.5 \
  -p tf_buffer_duration:=60.0 -p use_scan_matching:=true \
  -p do_loop_closing:=true \
  >"$work/slam.log" 2>&1 &
slam_pid=$!

sleep 3
ros2 bag play "$bag" --clock 100 --rate 1.0 \
  --topics /scan /yahboom/odom /tf_static
sleep 4

ros2 run nav2_map_server map_saver_cli -f "$output" --ros-args \
  -r map:=/map -p map_subscribe_transient_local:=true \
  -p save_map_timeout:=15.0 -p free_thresh_default:=0.25 \
  -p occupied_thresh_default:=0.65

echo "=== EKF replay warnings ==="
grep -E "Failed|WARN|ERROR" "$work/ekf.log" | tail -20 || true
echo "=== SLAM replay warnings ==="
grep -E "Failed|WARN|ERROR|dropping" "$work/slam.log" | tail -30 || true
echo "Saved offline map: ${output}.yaml"
