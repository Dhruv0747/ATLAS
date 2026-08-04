#!/bin/bash
source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash
exec ros2 launch tortoisebot_bringup nav2_rover.launch.py
