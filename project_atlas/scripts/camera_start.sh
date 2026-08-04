#!/bin/bash
LOG=/home/jetson/project_atlas/logs/camera_start.log
exec > >(tee -a "$LOG") 2>&1
echo "=== $(date) === starting camera after sleep ==="
sleep 5
source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true
export LD_LIBRARY_PATH=/usr/local/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH
echo "Launching camera_ros..."
exec ros2 run camera_ros camera_node --ros-args -p width:=640 -p height:=480 -p format:=XRGB8888 -p framerate:=8.0
