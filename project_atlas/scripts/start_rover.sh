#!/bin/bash
# Rover Node Startup Script
# Run: bash ~/start_rover.sh
echo "Starting all rover nodes..."
systemctl --user start rover-imu.service rover-ups.service rover-tof.service rover-gimbal.service rover-motors.service
sleep 2
systemctl --user status rover-imu.service rover-ups.service rover-tof.service rover-gimbal.service rover-motors.service --no-pager | grep -E "Active|●"
echo "Logs: /tmp/rover-*.log"
