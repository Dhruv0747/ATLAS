#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
cmake -S /tmp/replay/amcl_overlay_r3 -B /tmp/replay/amcl_build_r3 \
  -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/tmp/replay/amcl_install_r3
cmake --build /tmp/replay/amcl_build_r3 -j1
cmake --install /tmp/replay/amcl_build_r3
