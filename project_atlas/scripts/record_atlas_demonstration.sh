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

# 2026-11-13: ATLAS_RECORD_PROFILE=mapping_light (set by mission control's light mapping profile) drops the
# heavy topics a manual-mapping replay does not need: Pi camera JPEGs (~11 Hz), AMCL particles/pose (AMCL is off
# while mapping) and the repeated full /map grids. Everything SLAM/EKF/ICP replay uses is kept.
heavy=(/camera/image_raw/compressed /amcl_pose /particle_cloud /map)
if [[ "${ATLAS_RECORD_PROFILE:-full}" == "mapping_light" ]]; then
  heavy=()
fi
echo "Recording ATLAS demonstration to ${output} (profile ${ATLAS_RECORD_PROFILE:-full})"
exec ros2 bag record --storage sqlite3 -o "${output}" \
  "${heavy[@]}" \
  /scan /scan_raw /imu/data /odom /yahboom/odom /lidar/icp_odom /lidar/icp_odom/health /tf /tf_static \
  /cmd_vel /cmd_vel_joy /cmd_vel_web /cmd_vel_teleop /cmd_vel_nav \
  /cmd_vel_commission /cmd_vel_recovery \
  /joy \
  /steering/front_angle_deg /steering/rear_angle_deg /steering/mode \
  /yahboom/encoder/m1 /yahboom/encoder/m2 /yahboom/encoder/m3 /yahboom/encoder/m4 \
  /ultrasonic/front_mm /ultrasonic/left_mm /ultrasonic/right_mm /ultrasonic/status \
  /atlas/autonomy_state /atlas/safety_status /atlas/mission_status /atlas/mode \
  /atlas/recovery_state /atlas/recovery_status /atlas/agent/state \
  /atlas/encoder_health /atlas/encoder_update /atlas/control_policy \
  /im10a/imu/bias_corrected_candidate \
  /bms/status /bms/percent /bms/voltage /bms/current
