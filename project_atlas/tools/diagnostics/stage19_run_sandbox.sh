#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_root" in /tmp/atlas-stage19-*) ;; *) echo 'Use a fresh reviewed mktemp directory'; exit 2 ;; esac
variant="${1:?A or B required}"
case "$variant" in A|B) ;; *) exit 2 ;; esac
python3 "$task_root/stage19_preflight.py"
export ATLAS_HOST_NET_NS="$(readlink /proc/self/ns/net)"
export ATLAS_HOST_PID_NS="$(readlink /proc/self/ns/pid)"
mkdir -p "$task_root/map" "$task_root/home" "$task_root/roslogs"
# Private copies only; never replace live files.
cp -n /home/jetson/project_atlas/config/atlas_ekf.yaml "$task_root/baseline_ekf.yaml"
cp -n /home/jetson/project_atlas/config/nav2_params.yaml "$task_root/baseline_nav.yaml"
cp -n /home/jetson/project_atlas/maps/atlas_latest.yaml "$task_root/map/atlas_latest.yaml"
cp -n /home/jetson/project_atlas/maps/atlas_latest.pgm "$task_root/map/atlas_latest.pgm"
exec nice -n 15 taskset -c 4,5 bwrap --unshare-net --unshare-pid --die-with-parent \
  --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --bind "$task_root" /tmp/replay \
  --chdir /tmp/replay --setenv ATLAS_STAGE19_SANDBOX 1 \
  --setenv ROS_DOMAIN_ID 187 --setenv ROS_LOCALHOST_ONLY 1 \
  --setenv FASTDDS_BUILTIN_TRANSPORTS UDPv4 --setenv HOME /tmp/replay/home \
  --setenv ROS_LOG_DIR /tmp/replay/roslogs --setenv PYTHONUNBUFFERED 1 \
  -- /bin/bash --noprofile --norc /tmp/replay/stage19_inside.sh "$variant"
