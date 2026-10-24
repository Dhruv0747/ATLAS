#!/bin/bash
# make_tree.sh <variant_overlay.py> <live_atlas_status_web.py> <out_tree>
# Offline benchmark tree: repository sibling modules + the LIVE atlas_status_web.py + one executor overlay variant,
# with the repository adapter's OVERLAY_SHA set to that variant (the adapter's integrity check stays active).
set -euo pipefail
IMPL=$1; WEB=$2; T=$3; REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
rm -rf "$T"; mkdir -p "$T/scripts" "$T/tools/perf"
cp "$REPO"/scripts/*.py "$T/scripts/"; cp "$WEB" "$T/scripts/atlas_status_web.py"; cp "$IMPL" "$T/scripts/atlas_dashboard_executor_impl.py"
SHA=$(sha256sum "$IMPL" | cut -d' ' -f1); sed -i "s/^OVERLAY_SHA = '[0-9a-f]*'/OVERLAY_SHA = '$SHA'/" "$T/scripts/atlas_dashboard_executor.py"
grep -q "$SHA" "$T/scripts/atlas_dashboard_executor.py"
cp "$REPO/tools/perf/bench_status_executor.py" "$T/tools/perf/"; cp -r "$REPO/tools/vision3d" "$T/tools/"
echo "tree $T overlay $SHA web $(sha256sum "$WEB" | cut -c1-16)"
