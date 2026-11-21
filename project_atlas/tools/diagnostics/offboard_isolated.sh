#!/usr/bin/env bash
set -euo pipefail
grep -qi microsoft /proc/sys/kernel/osrelease
export ATLAS_PC_HOST_NET_NS=$(readlink /proc/self/ns/net)
task_script_dir=$(cd "$(dirname "$0")" && pwd)
exec unshare --net bash -c '
set -eo pipefail
ip link set lo up
export ROS_DOMAIN_ID=187 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/humble/setup.bash
exec timeout --signal=TERM --kill-after=5s 50s python3 "$@"
' bash "$task_script_dir/test_offboard_native.py" "$@"
