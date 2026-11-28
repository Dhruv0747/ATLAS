#!/bin/bash
# 2026-11-15: closed-loop AUTONOMOUS speed (3-encoder consensus) in the base. PARKED deploy, owner-confirmed.
# Run ON THE JETSON, only with the rover parked AND the E-STOP latched. Every mode restarts the base node only.
#
#   ATLAS_OWNER_CONFIRM=parked-estop-latched bash deploy_20261115_speed_loop.sh            install, loop DISABLED
#   ATLAS_OWNER_CONFIRM=parked-estop-latched bash deploy_20261115_speed_loop.sh --enable   loop ON (non-REMOTE)
#   ATLAS_OWNER_CONFIRM=parked-estop-latched bash deploy_20261115_speed_loop.sh --disable  loop OFF (legacy map)
#   ATLAS_OWNER_CONFIRM=parked-estop-latched bash deploy_20261115_speed_loop.sh --rollback restore pre-deploy files
#
# Install with the loop disabled is behaviour-neutral: the base keeps the legacy open-loop map. REMOTE is never
# routed through the loop. Manual-only is not touched. The staged candidate tree (SRC) must contain
# scripts/, tests/ and config/ as copied from the repo; its tests run before anything is installed.
set -euo pipefail
P=/home/jetson/project_atlas
S=$P/scripts
CFG=$P/config/speed_loop.yaml
SRC=${SRC:-/tmp/speedloop_cand}
TAG=before-speedloop-20261115
FILES="yahboom_base.py atlas_speed_loop.py"
MODE=${1:-install}

[ "${ATLAS_OWNER_CONFIRM:-}" = "parked-estop-latched" ] || {
  echo "Refusing: set ATLAS_OWNER_CONFIRM=parked-estop-latched (owner confirms rover parked + E-STOP latched)"; exit 1; }
/usr/bin/python3 "$S/atlas_astra_bridge_parked_check.py" || { echo "NOT parked: abort"; exit 1; }

set_enabled() {   # $1 = true|false ; edits only the enabled: line of the live config
  sed -i -E "s/^(  enabled:) *(true|false)\b/\1 $1/" "$CFG"
  grep -q "^  enabled: $1" "$CFG" || { echo "could not set enabled: $1 in $CFG"; exit 1; }
}

restart_and_verify() {
  systemctl --user restart rover-base-telemetry.service
  sleep 8
  systemctl --user is-active rover-base-telemetry.service
  journalctl --user -u rover-base-telemetry.service --since "-20 s" --no-pager \
    | grep -i "closed-loop autonomous speed" || echo "(no speed-loop log line: loop disabled -> legacy map)"
  grep -E "^  enabled:" "$CFG" || echo "(no $CFG: legacy map)"
}

case "$MODE" in
  --rollback)
    for f in $FILES; do
      if [ -e "$S/$f.$TAG" ]; then cp -p "$S/$f.$TAG" "$S/$f"; elif [ "$f" = atlas_speed_loop.py ]; then rm -f "$S/$f"; fi
    done
    rm -f "$CFG"; [ -e "$CFG.$TAG" ] && cp -p "$CFG.$TAG" "$CFG"
    restart_and_verify; echo "rolled back"; exit 0 ;;
  --enable)  [ -e "$CFG" ] || { echo "install first"; exit 1; }; set_enabled true;  restart_and_verify; exit 0 ;;
  --disable) [ -e "$CFG" ] || { echo "nothing installed"; exit 1; }; set_enabled false; restart_and_verify; exit 0 ;;
  install) ;;
  *) echo "unknown mode $MODE"; exit 1 ;;
esac

for f in $FILES; do python3 -m py_compile "$SRC/scripts/$f"; done
# candidate tests run against the staged files (scripts/ there symlinks the remaining live modules)
(cd "$SRC" && python3 -m unittest -q tests.test_speed_loop tests.test_speed_loop_base tests.test_speed_loop_ground_check)
(cd "$SRC" && python3 -m pytest -q tests/test_opposite_steering_geometry.py tests/test_yahboom_lifted_owner.py \
   tests/test_yahboom_diagnostic_cadence.py)
grep -q "^  enabled: false" "$SRC/config/speed_loop.yaml" || { echo "staged config must ship disabled"; exit 1; }
for f in $FILES; do
  if [ -e "$S/$f" ] && [ ! -e "$S/$f.$TAG" ]; then cp -p "$S/$f" "$S/$f.$TAG"; fi
  cp "$SRC/scripts/$f" "$S/$f"
done
if [ -e "$CFG" ]; then [ -e "$CFG.$TAG" ] || cp -p "$CFG" "$CFG.$TAG"   # pre-existing config: keep a copy
else cp "$SRC/config/speed_loop.yaml" "$CFG"; fi
set_enabled false
restart_and_verify
echo "installed with the speed loop DISABLED; enable with --enable (separate owner OK)"
