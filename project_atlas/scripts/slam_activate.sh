#!/bin/bash
source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true
for i in {1..40}; do
    STATE=$(ros2 lifecycle get /slam_toolbox 2>/dev/null)
    if echo "$STATE" | grep -q "unconfigured"; then
        ros2 lifecycle set /slam_toolbox configure && sleep 3 && ros2 lifecycle set /slam_toolbox activate && echo "activated" && exit 0
    elif echo "$STATE" | grep -q "inactive"; then
        ros2 lifecycle set /slam_toolbox activate && echo "activated" && exit 0
    elif echo "$STATE" | grep -q "active"; then
        echo "already active" && exit 0
    fi
    sleep 3
done
