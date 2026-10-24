#!/bin/bash
set -euo pipefail
# Run from repository root, on the PC only. unshare failure must abort.
test "$(uname -m)" = x86_64
test_root="$(pwd)/artifacts/native_entities_20261024"
test -x "$test_root/build/check_entities"
exec unshare --net -- bash -c '
set -euo pipefail
ip link set lo up
exec env -i PATH=/usr/bin:/bin HOME="$1" ROS_DOMAIN_ID=216 ROS_LOCALHOST_ONLY=1 \
RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
LD_LIBRARY_PATH="$1/overlay/opt/ros/humble/lib:/opt/ros/humble/lib" \
timeout --signal=INT --kill-after=2s 40s "$1/build/check_entities" "${@:2}"
' isolated "$test_root" "$@"
