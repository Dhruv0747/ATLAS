#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
for i in 1 2 3 4 5 6
do
  echo "==== GPS_CHECK_$i ===="
  timeout 5 ros2 topic echo /gps/satellites --once 2>/dev/null || true
  timeout 5 ros2 topic echo /gps/constellations --once 2>/dev/null || true
  timeout 5 ros2 topic echo /gps/fix --once 2>/dev/null | grep -E 'status:|latitude:|longitude:|altitude:' || true
  sleep 20
done
