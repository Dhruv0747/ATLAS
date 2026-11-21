#!/bin/bash
# Manual isolated build ONLY. No apt install, root operation, driver start or production change.
set -euo pipefail
stage="${ATLAS_ASTRA_STAGE:-/home/jetson/project-atlas-migration/astra-20261021}"
test "$(realpath "$stage")" = /home/jetson/project-atlas-migration/astra-20261021
set +u  # Humble setup.bash intentionally reads optional unset trace variables.
source /opt/ros/humble/setup.bash
set -u
export CMAKE_PREFIX_PATH="$stage/deps/opt/ros/humble:${CMAKE_PREFIX_PATH:-}"
export AMENT_PREFIX_PATH="$stage/deps/opt/ros/humble:${AMENT_PREFIX_PATH:-}"
export PKG_CONFIG_PATH="$stage/deps/usr/lib/aarch64-linux-gnu/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$stage/deps/opt/ros/humble/lib:$stage/deps/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH:-}"
export LIBRARY_PATH="$stage/deps/usr/lib/aarch64-linux-gnu:${LIBRARY_PATH:-}"
export MAKEFLAGS=-j1
cd "$stage/ws"
test "$(git -C src/ros2_astra_camera rev-parse HEAD)" = f7e71d9ce806e788cb48d8580aac2c778fba4214
exec colcon build --executor sequential --packages-select astra_camera_msgs astra_camera \
  --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  --event-handlers console_direct+
