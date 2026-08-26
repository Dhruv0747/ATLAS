#!/usr/bin/env bash
set -Eeuo pipefail

source_file=/home/jetson/project_atlas/config/atlas-ros-environment.conf
target_dir=/home/jetson/.config/environment.d
target_file=${target_dir}/90-project-atlas-ros.conf

install -d -m 0755 "${target_dir}"
install -m 0644 "${source_file}" "${target_file}"
systemctl --user set-environment ROS_LOCALHOST_ONLY=1

printf '%s\n' \
  "Installed ${target_file}" \
  "ROS 2 discovery is now Jetson-local; Foxglove/web TCP access is unchanged." \
  "Restart ATLAS user services or reboot once to apply it to every ROS process."
