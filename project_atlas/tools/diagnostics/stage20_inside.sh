#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
cp /tmp/replay/tools/diagnostics/stage20_observer_CMakeLists.txt /tmp/replay/tools/diagnostics/CMakeLists.txt
cmake -S /tmp/replay/tools/diagnostics -B /tmp/replay/build
cmake --build /tmp/replay/build -j1
python3 /tmp/replay/tools/diagnostics/stage20_native_smoke.py
