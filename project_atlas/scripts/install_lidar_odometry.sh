#!/usr/bin/env bash
set -euo pipefail

# Reproducibly install the RF2O dependency used by ATLAS's shadow LiDAR-odometry
# path. This script does not promote the candidate to /odom or change Nav2.

ATLAS_HOME="${ATLAS_HOME:-/home/jetson/project_atlas}"
ATLAS_WS="${ATLAS_WS:-/home/jetson/project_atlas_ws}"
RF2O_DIR="${ATLAS_WS}/src/rf2o_laser_odometry"
RF2O_REPOSITORY="https://github.com/Adlink-ROS/rf2o_laser_odometry.git"
RF2O_COMMIT="313bb4c4123bcc0cc2e042f278312b19a3c46f31"

source /opt/ros/humble/setup.bash

mkdir -p "${ATLAS_WS}/src"
if [[ ! -d "${RF2O_DIR}/.git" ]]; then
  git clone --branch humble-devel --single-branch "${RF2O_REPOSITORY}" "${RF2O_DIR}"
fi

current_origin="$(git -C "${RF2O_DIR}" remote get-url origin)"
if [[ "${current_origin}" != "${RF2O_REPOSITORY}" ]]; then
  echo "Refusing unexpected RF2O origin: ${current_origin}" >&2
  exit 1
fi

if [[ -n "$(git -C "${RF2O_DIR}" status --porcelain)" ]]; then
  echo "Refusing to overwrite local RF2O changes in ${RF2O_DIR}" >&2
  exit 1
fi

git -C "${RF2O_DIR}" fetch origin humble-devel
git -C "${RF2O_DIR}" checkout --detach "${RF2O_COMMIT}"

cd "${ATLAS_WS}"
colcon build --symlink-install --packages-select rf2o_laser_odometry

mkdir -p "${HOME}/.config/systemd/user"
install -m 0644 "${ATLAS_HOME}/systemd/user/atlas-lidar-odom.service" "${HOME}/.config/systemd/user/"
install -m 0644 "${ATLAS_HOME}/systemd/user/atlas-lidar-odom-gate.service" "${HOME}/.config/systemd/user/"
install -m 0644 "${ATLAS_HOME}/systemd/user/atlas-ekf-lidar-candidate.service" "${HOME}/.config/systemd/user/"

systemctl --user daemon-reload
systemctl --user enable --now \
  atlas-lidar-odom.service \
  atlas-lidar-odom-gate.service \
  atlas-ekf-lidar-candidate.service

echo "ATLAS shadow LiDAR-odometry candidate installed at ${RF2O_COMMIT}."
echo "Authoritative /odom and Nav2 remain unchanged."
