#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
exec python3 /tmp/replay/stage19_native_replay.py \
 /home/jetson/project_atlas/data/demonstrations/hall_to_dhruv_20261009-20261009-122252 \
 /tmp/replay/baseline_ekf.yaml /tmp/replay/baseline_nav.yaml /tmp/replay/map/atlas_latest.yaml \
 "/tmp/replay/hall_native_${1}" --variant "$1"
