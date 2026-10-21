#!/bin/bash
# Isolated PC cross-build. No target activation, services or host ROS replacement.
set -euo pipefail
root=/root/atlas-stage29
scripts=$(cd "$(dirname "$0")" && pwd)
test "$(git -C "$root/source/ros2_astra_camera" rev-parse HEAD)" = f7e71d9ce806e788cb48d8580aac2c778fba4214
if git -C "$root/source/ros2_astra_camera" apply --check "$scripts/vendor_arm64.patch" 2>/dev/null; then
  git -C "$root/source/ros2_astra_camera" apply "$scripts/vendor_arm64.patch"
else
  git -C "$root/source/ros2_astra_camera" apply --reverse --check "$scripts/vendor_arm64.patch"
fi
set +u
source /opt/ros/humble/setup.bash
set -u
export ATLAS_ARM64_SYSROOT="$root/target"
export ATLAS_ARM64_INSTALL="$root/cross-install"
export CMAKE_PREFIX_PATH="$root/target/opt/ros/humble:$root/target/usr"
export AMENT_PREFIX_PATH="$root/target/opt/ros/humble"
export PKG_CONFIG_SYSROOT_DIR="$root/target"
export PKG_CONFIG_LIBDIR="$root/target/usr/lib/aarch64-linux-gnu/pkgconfig:$root/target/usr/share/pkgconfig"
export PKG_CONFIG_PATH=
export MAKEFLAGS=-j2
cd "$root"
exec colcon --log-base cross-log build --base-paths source/ros2_astra_camera \
  --build-base cross-build --install-base cross-install --merge-install \
  --executor sequential --parallel-workers 1 --packages-select astra_camera_msgs astra_camera \
  --cmake-args -DCMAKE_TOOLCHAIN_FILE="$scripts/arm64_toolchain.cmake" \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=/usr/bin/python3 \
  -DPYTHON_SOABI=cpython-310-aarch64-linux-gnu \
  -DPKG_CONFIG_EXECUTABLE=/usr/bin/pkg-config \
  "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$root/target/usr/lib/aarch64-linux-gnu/blas -Wl,-rpath-link,$root/target/usr/lib/aarch64-linux-gnu/lapack" \
  -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=FALSE \
  -DCMAKE_SKIP_RPATH=ON \
  --event-handlers console_direct+
