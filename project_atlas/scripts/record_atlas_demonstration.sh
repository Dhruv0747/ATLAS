#!/usr/bin/env bash
set -Eeo pipefail

label="${1:-operator_demonstration}"
label="${label//[^a-zA-Z0-9_-]/_}"
stamp="$(date +%Y%m%d-%H%M%S)"
root="/home/jetson/project_atlas/data/demonstrations"
output="${root}/${label}-${stamp}"
mkdir -p "${root}"

source /opt/ros/humble/setup.bash
source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true

echo "Recording ATLAS demonstration to ${output}"
exec ros2 bag record --storage sqlite3 -o "${output}" \
  /camera/image_raw/compressed \
  /scan /imu/data /odom /yahboom/odom /amcl_pose /particle_cloud /map /tf /tf_static \
  /cmd_vel /cmd_vel_joy /cmd_vel_web /cmd_vel_teleop /cmd_vel_nav \
  /joy \
  /steering/front_angle_deg /steering/rear_angle_deg /steering/mode \
  /yahboom/encoder/m1 /yahboom/encoder/m2 /yahboom/encoder/m3 /yahboom/encoder/m4 \
  /ultrasonic/front_mm /ultrasonic/left_mm /ultrasonic/right_mm /ultrasonic/status \
  /atlas/autonomy_state /atlas/safety_status /atlas/mission_status /atlas/mode \
  /atlas/recovery_state /atlas/recovery_status /atlas/agent/state \
  /bms/status /bms/percent /bms/voltage /bms/current
