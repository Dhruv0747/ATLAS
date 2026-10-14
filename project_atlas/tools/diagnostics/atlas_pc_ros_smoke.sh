#!/usr/bin/env bash
set -euo pipefail
grep -qi microsoft /proc/sys/kernel/osrelease
export ATLAS_PC_HOST_NET_NS=$(readlink /proc/self/ns/net)
exec unshare --net bash -c '
set -eo pipefail
ip link set lo up
export ROS_DOMAIN_ID=187 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/humble/setup.bash
timeout 50s python3 /mnt/c/Users/Dhruv/Documents/Codex/2026-07-24/h/atlas_pc_ros_smoke.py
'
