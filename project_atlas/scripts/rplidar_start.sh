#!/bin/bash
source /opt/ros/humble/setup.bash
exec ros2 run rplidar_ros rplidar_composition --ros-args \
  -p serial_port:=/dev/rplidar \
  -p serial_baudrate:=115200 \
  -p frame_id:=laser_frame \
  -p angle_compensate:=true \
  -p scan_mode:=Standard
