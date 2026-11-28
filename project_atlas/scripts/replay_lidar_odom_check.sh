#!/usr/bin/env bash
set -eo pipefail

bag=${1:?usage: replay_lidar_odom_check.sh BAG}
result=$(mktemp /tmp/atlas-rf2o-replay-result.XXXXXX)
rf2o_pid=""
collector_pid=""

cleanup() {
  [[ -z "$collector_pid" ]] || kill "$collector_pid" 2>/dev/null || true
  [[ -z "$rf2o_pid" ]] || kill "$rf2o_pid" 2>/dev/null || true
  systemctl --user start atlas-lidar-odom.service atlas-lidar-odom-gate.service atlas-ekf-lidar-candidate.service
  rm -f "$result"
}
trap cleanup EXIT

systemctl --user stop atlas-ekf-lidar-candidate.service atlas-lidar-odom-gate.service atlas-lidar-odom.service
source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash

ros2 run rf2o_laser_odometry rf2o_laser_odometry_node --ros-args \
  -r __node:=atlas_rf2o_replay_check \
  -p laser_scan_topic:=/analysis/scan \
  -p odom_topic:=/analysis/lidar/odom_raw \
  -p base_frame_id:=base_link \
  -p odom_frame_id:=odom \
  -p publish_tf:=false \
  -p init_pose_from_topic:=/analysis/initial_pose_unused \
  -p freq:=10.0 >/tmp/atlas-rf2o-replay.log 2>&1 &
rf2o_pid=$!

# Supply a zero initial pose because the upstream RF2O CLI cannot represent an
# empty-string parameter override reliably on ROS 2 Humble.
ros2 topic pub --once /analysis/initial_pose_unused nav_msgs/msg/Odometry \
  '{pose: {pose: {orientation: {w: 1.0}}}}' >/dev/null

/usr/bin/python3 /home/jetson/project_atlas/scripts/atlas_odom_topic_check.py \
  --topic /analysis/lidar/odom_raw --timeout 110 --idle-timeout 3 >"$result" &
collector_pid=$!
sleep 2
ros2 bag play "$bag" --topics /scan --remap /scan:=/analysis/scan
wait "$collector_pid"
collector_pid=""
cat "$result"
