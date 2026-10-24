#!/bin/bash
# runs INSIDE the private network namespace: loopback only, multicast on lo, unused ROS domain 216
set -euo pipefail
ENV=$1; shift
ip link set lo up; ip link set lo multicast on; ip route add 224.0.0.0/4 dev lo 2>/dev/null || true
if ip -o link show | grep -qv ': lo:'; then echo 'refusing: namespace has a non-loopback interface' >&2; exit 3; fi
export ROS_DOMAIN_ID=216 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PATH="$ENV/bin:$PATH" AMENT_PREFIX_PATH="$ENV"
exec "$ENV/bin/python" -I -B "$@"
