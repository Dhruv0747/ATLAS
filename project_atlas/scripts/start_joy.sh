#!/bin/bash
# Start joystick + teleop for rover dual-stick control
# Left stick Y = forward/backward (axis 1)
# Right stick X = steering (axis 3)

source /opt/ros/humble/setup.bash

# Fix gamepad permissions (remove after adding dhruv to input group + relogin)
# sudo setfacl -m u:dhruv:rw /dev/input/event1

# Kill any existing instances
pkill -f "joy joy_node" 2>/dev/null
pkill -f "teleop_twist_joy teleop_node" 2>/dev/null
sleep 1

# Start joy_node
ros2 run joy joy_node --ros-args -p device_id:=0 &> /tmp/joy.log &
sleep 2

# Start teleop
ros2 run teleop_twist_joy teleop_node --ros-args \
  -p require_enable_button:=false \
  -p axis_linear.x:=1 \
  -p scale_linear.x:=0.3 \
  -p axis_angular.yaw:=3 \
  -p scale_angular.yaw:=1.0 \
  -p enable_turbo_button:=5 \
  -p scale_linear_turbo.x:=0.5 &> /tmp/teleop.log &

echo "Joy + teleop started. Logs: /tmp/joy.log /tmp/teleop.log"
