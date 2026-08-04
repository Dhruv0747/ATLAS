#!/bin/bash
# Run this after you've driven around and built a SLAM map
# The map will be saved as ~/my_map.pgm and ~/my_map.yaml
source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true
echo "Saving map to ~/my_map..."
ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '/home/jetson/project_atlas/maps/my_map'}}"
echo "Done! Files: ~/my_map.pgm and ~/my_map.yaml"
