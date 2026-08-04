#!/bin/bash
source /opt/ros/humble/setup.bash
mkdir -p ~/maps
ros2 run nav2_map_server map_saver_cli -f /home/jetson/project_atlas/maps/autosave
