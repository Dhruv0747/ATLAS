#!/usr/bin/env bash
set -Eeo pipefail

# Never start a map-owning process against an unset boot clock.  Jetson may
# restore time before NTP is reachable, so a sane epoch is the safe invariant.
minimum_epoch=1735689600  # 2025-01-01 UTC
deadline=$((SECONDS + 45))
while (( $(date +%s) < minimum_epoch )); do
  (( SECONDS < deadline )) || { echo "ATLAS navigation clock is not valid" >&2; exit 1; }
  sleep 1
done

for unit in rover-base-telemetry.service atlas-ekf.service atlas-lidar.service atlas-scan-filter.service; do
  deadline=$((SECONDS + 45))
  until systemctl --user is-active --quiet "$unit"; do
    (( SECONDS < deadline )) || { echo "Required navigation unit is not active: $unit" >&2; exit 1; }
    sleep 1
  done
done

source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
export ROS_LOCALHOST_ONLY=1

# A running process is insufficient: require actual fresh odometry and scan
# messages before AMCL/SLAM construct their TF buffers.  Bypass the ROS CLI
# daemon here: a stale daemon previously raised !rclpy.ok() and prevented a
# healthy localization stack from starting after a mode switch or reboot.
timeout 15s ros2 topic echo --no-daemon --once /odom nav_msgs/msg/Odometry >/dev/null
timeout 15s ros2 topic echo --no-daemon --once /scan sensor_msgs/msg/LaserScan >/dev/null
