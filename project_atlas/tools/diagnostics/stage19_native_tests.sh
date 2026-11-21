#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
cd /tmp/replay
python3 -m unittest test_atlas_fusion_replay test_stage19_contract
