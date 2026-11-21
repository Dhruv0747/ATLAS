#!/usr/bin/env bash
set -euo pipefail
grep -qi microsoft /proc/sys/kernel/osrelease
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 22.04
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
apt-get install -y curl ca-certificates locales software-properties-common python3
locale-gen en_US.UTF-8
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
add-apt-repository -y universe
task_dir=$(mktemp -d /tmp/atlas-ros-source.XXXXXX)
curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest -o "$task_dir/release.json"
task_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_name"])' "$task_dir/release.json")
curl -fL "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${task_version}/ros2-apt-source_${task_version}.jammy_all.deb" -o "$task_dir/ros2-apt-source.deb"
sha256sum "$task_dir/ros2-apt-source.deb"
dpkg -i "$task_dir/ros2-apt-source.deb"
apt-get update
apt-get install -y ros-humble-ros-base ros-humble-rosbag2 ros-humble-rosbag2-storage-default-plugins ros-humble-demo-nodes-cpp ros-humble-demo-nodes-py ros-humble-nav2-msgs python3-psutil
printf 'ATLAS_PC_ROS_INSTALL_COMPLETE\n'
