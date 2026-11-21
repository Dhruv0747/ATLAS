#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
export LD_LIBRARY_PATH="/tmp/replay/ekf_build_r3:/tmp/replay/amcl_install_r3/lib:$LD_LIBRARY_PATH"
export AMENT_PREFIX_PATH="/tmp/replay/amcl_install_r3:$AMENT_PREFIX_PATH"
exec python3 /tmp/replay/tools/diagnostics/stage20_end_to_end.py
