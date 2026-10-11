#!/usr/bin/env bash
# Rebuild the four 2026-10-11 stage packages from their exact commit ranges (see docs/deploy).
set -euo pipefail
OUT=${1:?output dir}; cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
M=project_atlas/tools/deploy/make_package.py; S=project_atlas/scripts/atlas_status_web.py
rm -rf "$OUT"; mkdir -p "$OUT"
python3 $M stage1-safety adcf823 bd76afb "$OUT" -- $S@adcf823..a7e2299 $S@e0e2156^..e0e2156 $S@bd76afb^..bd76afb
python3 $M stage1b-estop-reset bd76afb e65fe67 "$OUT" -- $S@bd76afb..e65fe67 project_atlas/scripts/atlas_estop_reset.py
python3 $M stage2-glass-ui-v2 aa93355 36a2b95 "$OUT" -- project_atlas/web/v2 project_atlas/scripts/atlas_web_v2.py $S@aa93355..adcf823
python3 $M stage3-executor-split 254fdb6 d681142 "$OUT" -- $S
python3 $M stage4-visual-cloud aa93355 0cd9d95 "$OUT" -- project_atlas/scripts/atlas_visual_cloud_agent.py \
  project_atlas/scripts/atlas_visual_cloud_core.py project_atlas/scripts/atlas_visual_cloud_server.py project_atlas/config/atlas_visual_cloud.json
python3 $M stage5-v2-default e5c1976 5b49f25 "$OUT" -- project_atlas/scripts/atlas_web_v2.py $S \
  project_atlas/web/v2/index.html project_atlas/web/v2/mapping.html project_atlas/web/v2/commissioning.html project_atlas/web/v2/wifi.html
