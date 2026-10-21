#!/bin/bash
# Stage 25 Dashboard motion-chip fix: copies 3 static web files into the live V2 directory.
# Display only. No service restart, no ROS node, no config, no safety path is touched.
# Usage: SRC=<repo>/web/v2 TARGET=~/project_atlas/web/v2 ./apply.sh   (both default as shown)
set -euo pipefail
SRC="${SRC:-$(cd "$(dirname "$0")/../../../web/v2" && pwd)}"
TARGET="${TARGET:-$HOME/project_atlas/web/v2}"
STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
BACKUP="$TARGET/.pre_stage25_motion_chip_$STAMP"
# Expected pre-state (commit 113b9aa). Refuse to overwrite anything that is not exactly that.
EXPECT_SHELL=6a843ec277c2f8bd
EXPECT_INDEX=e0291f844ea16474
h() { sha256sum "$1" | cut -c1-16; }
[ "$(h "$TARGET/shell.js")" = "$EXPECT_SHELL" ] || { echo "REFUSE: live shell.js is not the expected pre-state" >&2; exit 2; }
[ "$(h "$TARGET/index.html")" = "$EXPECT_INDEX" ] || { echo "REFUSE: live index.html is not the expected pre-state" >&2; exit 2; }
[ ! -e "$TARGET/motion-status.js" ] || { echo "REFUSE: motion-status.js already present" >&2; exit 2; }
mkdir "$BACKUP"; cp -a "$TARGET/shell.js" "$TARGET/index.html" "$BACKUP/"
echo "backup: $BACKUP"; sha256sum "$BACKUP"/*
cp "$SRC/motion-status.js" "$SRC/shell.js" "$SRC/index.html" "$TARGET/"
echo "applied:"; sha256sum "$TARGET/motion-status.js" "$TARGET/shell.js" "$TARGET/index.html"
echo "$BACKUP" > "$TARGET/.stage25_last_backup"
