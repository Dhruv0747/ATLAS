#!/bin/bash
# Source explicitly on Jetson. Sets only caller environment; starts NOTHING.
# Do NOT source cross-generated setup.bash: its development prefix chain is PC-specific.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Source this file to prepare an isolated Jetson environment; nothing will start.'
  exit 0
fi
atlas_astra_runtime=/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2
if [[ ! -f "$atlas_astra_runtime/manifest.json" || ! -f /opt/ros/humble/setup.bash ]]; then
  echo 'Verified isolated runtime/native Humble missing' >&2
  return 1
fi
source /opt/ros/humble/setup.bash
export AMENT_PREFIX_PATH="$atlas_astra_runtime:${AMENT_PREFIX_PATH:-}"
export LD_LIBRARY_PATH="$atlas_astra_runtime/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$atlas_astra_runtime/local/lib/python3.10/dist-packages:${PYTHONPATH:-}"
unset atlas_astra_runtime
