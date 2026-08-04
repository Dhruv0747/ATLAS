#!/usr/bin/env bash
set -eo pipefail

LOG=/home/jetson/project_atlas/logs/map_autosave.log
STAMP="$(date --iso-8601=seconds 2>/dev/null || date)"

{
  echo "===== ${STAMP} map autosave ====="

  source /opt/ros/humble/setup.bash
  source /home/jetson/project_atlas_ws/install/setup.bash

  export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  mkdir -p /home/jetson/project_atlas/maps

  if ! timeout 10 ros2 topic list | grep -qx "/map"; then
    echo "No /map topic yet; skipping this autosave."
    exit 0
  fi

  if timeout 30 ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '/home/jetson/project_atlas/maps/autosave'}}"; then
    echo "Saved /home/jetson/project_atlas/maps/autosave through /slam_toolbox/save_map"
    exit 0
  fi

  echo "slam_toolbox save failed; trying nav2 map_saver_cli fallback"
  timeout 30 ros2 run nav2_map_server map_saver_cli -f /home/jetson/project_atlas/maps/autosave
  echo "Saved /home/jetson/project_atlas/maps/autosave through map_saver_cli"
} >>"$LOG" 2>&1
