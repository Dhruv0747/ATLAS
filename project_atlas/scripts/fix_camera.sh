#!/bin/bash
# Instantly clears camera delay - run this instead of rebooting
echo "Stopping camera node..."
pkill -f "camera_node" 2>/dev/null || true
sleep 1
echo "Camera stopped. Restarting..."
source /opt/ros/humble/setup.bash
source ~/tortoisebot_ws/install/setup.bash 2>/dev/null || true
export LD_LIBRARY_PATH=/usr/local/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH
nohup ros2 run camera_ros camera_node --ros-args -p width:=640 -p height:=480 -p format:=XRGB8888 > ~/camera_restart.log 2>&1 &
echo "Camera restarted! Delay should be gone in 2-3 seconds."
