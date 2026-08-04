#!/usr/bin/env bash
source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash

echo "===== nodes ====="
timeout 8 ros2 node list | grep -E 'foxglove|motor|slam|map_autosaver|camera|rplidar' || true

echo
echo "===== control/sensor topics ====="
timeout 8 ros2 topic list | grep -E 'cmd_vel|camera/image_raw|scan|map|tf' || true

echo
echo "===== foxglove node info ====="
timeout 8 ros2 node info /foxglove_bridge || true

echo
echo "===== port 8765 ====="
ss -ltnp 2>/dev/null | grep ':8765' || true

echo
echo "===== service status ====="
systemctl status tortoisebot.service --no-pager | sed -n '1,18p'
