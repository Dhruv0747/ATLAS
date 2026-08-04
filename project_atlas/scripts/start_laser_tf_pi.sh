#!/bin/bash
source /opt/ros/humble/setup.bash
exec ros2 run tf2_ros static_transform_publisher 0 0 0.18 3.14159265 0 0 base_footprint laser_frame
