#!/usr/bin/env bash
set -euo pipefail

source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true

echo '=== daemon-independent discovery ==='
timeout 15 ros2 node list --no-daemon
timeout 15 ros2 topic list -t --no-daemon

echo '=== CLI daemon ==='
ros2 daemon stop || true
rm -rf "${ROS_HOME:-$HOME/.ros}/ros2cli/daemon" 2>/dev/null || true
ros2 daemon start
sleep 2
timeout 15 ros2 node list
timeout 15 ros2 topic list -t

echo 'ROS CLI graph discovery passed with and without the daemon.'
