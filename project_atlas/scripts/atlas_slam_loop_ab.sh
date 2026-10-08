#!/usr/bin/env bash
# Diagnostic only. Input MUST be produced by atlas_prepare_slam_comparison.py.
set -Eeo pipefail
if (( $# != 2 )); then
  echo "usage: $0 FILTERED_BAG NEW_OUTPUT_DIRECTORY" >&2
  exit 2
fi
bag=$1
output=$2
export ROS_DOMAIN_ID=177 ROS_LOCALHOST_ONLY=1
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
source /opt/ros/humble/setup.bash
mkdir "$output"
slam_pid=''
record_pid=''
cleanup() {
  for pid in "$record_pid" "$slam_pid"; do
    if [[ -n "$pid" ]]; then kill -INT "$pid" 2>/dev/null || true; fi
  done
  wait || true
}
trap cleanup EXIT
# No motor driver, Nav2, or command topics are launched in this domain.
for variant in true false; do
  /opt/ros/humble/lib/slam_toolbox/async_slam_toolbox_node --ros-args \
    -r __node:=slam_toolbox -p use_sim_time:=true \
    -p odom_frame:=odom -p map_frame:=map -p base_frame:=base_link \
    -p scan_topic:=/scan -p mode:=mapping \
    -p min_laser_range:=0.20 -p max_laser_range:=8.0 \
    -p minimum_time_interval:=0.10 -p minimum_travel_distance:=0.05 \
    -p minimum_travel_heading:=0.10 -p map_update_interval:=1.5 \
    -p scan_queue_size:=20 -p transform_timeout:=1.5 \
    -p tf_buffer_duration:=30.0 -p use_scan_matching:=true \
    -p do_loop_closing:="$variant" >"$output/slam_$variant.log" 2>&1 &
  slam_pid=$!
  sleep 3
  # The installed Humble async executable starts processing without lifecycle
  # transitions. Check the logs and output counts before trusting the result.
  ros2 bag record -o "$output/result_$variant" /tf /map /scan >"$output/record_$variant.log" 2>&1 &
  record_pid=$!
  sleep 3
  timeout 480 ros2 bag play "$bag" --clock 50 --rate 0.5 --topics /scan /tf /tf_static >"$output/play_$variant.log" 2>&1
  sleep 3
  cleanup
  slam_pid=''
  record_pid=''
done
