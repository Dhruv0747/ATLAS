#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
cmake -S /tmp/replay/ekf_overlay_r3 -B /tmp/replay/ekf_build_r3 \
  -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/tmp/replay/ekf_install
cmake --build /tmp/replay/ekf_build_r3 -j1 --target ekf_node
