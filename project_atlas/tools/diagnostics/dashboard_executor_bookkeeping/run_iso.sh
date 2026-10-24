#!/bin/bash
# usage: run_iso.sh <conda_env_prefix> <script> [args]   (PC/cloud workstation only; never on the Jetson)
# Private network namespace with ONLY an up, multicast-enabled loopback; ROS domain 216. Cannot reach ATLAS.
set -euo pipefail
ENV=$1; shift
exec unshare --net -- "$(cd "$(dirname "$0")" && pwd)/iso_inner.sh" "$ENV" "$@"
