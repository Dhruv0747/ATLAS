#!/bin/bash
set -euo pipefail
export ATLAS_HOST_NET_NS=$(readlink /proc/self/ns/net)
export ATLAS_HOST_PID_NS=$(readlink /proc/self/ns/pid)
exec bwrap --unshare-net --unshare-pid --die-with-parent --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp \
 --bind /tmp/atlas-stage20-complete-EW8kVA07 /tmp/replay --chdir /tmp/replay \
 --setenv ATLAS_STAGE19_SANDBOX 1 --setenv ROS_DOMAIN_ID 187 --setenv ROS_LOCALHOST_ONLY 1 \
 --setenv FASTDDS_BUILTIN_TRANSPORTS UDPv4 --setenv HOME /tmp/replay/home \
 --setenv ROS_LOG_DIR /tmp/replay/roslogs -- /bin/bash --noprofile --norc -c \
 'source /opt/ros/humble/setup.bash; exec python3 tools/diagnostics/stage20_public_stress.py "$@"' sandbox "$@"
