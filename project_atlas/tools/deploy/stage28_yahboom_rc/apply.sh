#!/usr/bin/env bash
# Stage 28 Jetson side (PROPOSAL; run only with separate owner approval, gate G-J).
# Adds the read-only RC report path to the base driver. Dormant until the ATLAS-patched firmware is
# flashed (factory 3.6 never sends packet 0xE1). One restart of rover-base-telemetry, E-STOP latched.
# Does NOT install udev rules, does NOT touch firmware, does NOT change motor/E-STOP/mixer/Nav2 code.
set -Eeuo pipefail
[[ "${OWNER_APPROVED:-}" == "yes" ]] || { echo "refused: set OWNER_APPROVED=yes after approval"; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
S=${ATLAS_SCRIPTS_DIR:-/home/jetson/project_atlas/scripts}
STAMP=$(date +%Y%m%d_%H%M%S)
BK=${ATLAS_BACKUP_ROOT:-/home/jetson/project-atlas-migration}/stage28_rc_$STAMP
declare -A PRE=(
  [Rosmaster_Lib.py]=355ac42041e41df216316167ab73bda72eed9129c849222ec07aaba4f7c00371
  [yahboom_base.py]=c551be0053a43755578fc8e60b534338818a690411322c63a293376e6e560141
  [atlas_flysky_core.py]=3e4b379e656788c25521a7f8e588f3fd5e7974be19d9234a9028d064859f8ad4
)
for f in "${!PRE[@]}"; do
  got=$(sha256sum "$S/$f" | cut -d' ' -f1)
  [[ "$got" == "${PRE[$f]}" ]] || { echo "refused: $f hash $got != expected ${PRE[$f]}"; exit 3; }
done
for f in atlas_yahboom_rc_report.py atlas_rc_readonly_bridge.py; do
  [[ ! -e "$S/$f" ]] || { echo "refused: $S/$f already exists"; exit 4; }
done
curl -s -m5 "${ATLAS_ESTOP_URL:-http://127.0.0.1:8088/api/estop/state}" | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" \
  || { echo "refused: E-STOP is not latched (or the dashboard is unreachable). Latch it with Xbox B first."; exit 5; }
mkdir -p "$BK"; cp -p "$S/Rosmaster_Lib.py" "$S/yahboom_base.py" "$BK/"
( cd "$BK" && sha256sum Rosmaster_Lib.py yahboom_base.py > SHA256SUMS )
echo "backup: $BK"; cat "$BK/SHA256SUMS"
T=$(mktemp -d); cp "$S/Rosmaster_Lib.py" "$S/yahboom_base.py" "$T/"
python3 "$HERE/insert_rosmaster_rc.py" "$T/Rosmaster_Lib.py"
python3 "$HERE/insert_rc_hooks.py" "$T/yahboom_base.py"
python3 "$HERE/harden_yahboom_port.py" "$T/yahboom_base.py"
install -m 0644 "$HERE/../../../scripts/atlas_yahboom_rc_report.py" "$S/atlas_yahboom_rc_report.py"
install -m 0644 "$HERE/../../../scripts/atlas_rc_readonly_bridge.py" "$S/atlas_rc_readonly_bridge.py"
( cd "$T" && PYTHONPATH="$S" python3 -c "import Rosmaster_Lib, sys; sys.path.insert(0,'$S'); import atlas_yahboom_rc_report, atlas_rc_readonly_bridge; compile(open('yahboom_base.py').read(),'yahboom_base.py','exec')" )
install -m 0644 "$T/Rosmaster_Lib.py" "$S/Rosmaster_Lib.py"
install -m 0755 "$T/yahboom_base.py" "$S/yahboom_base.py"
echo "files installed; restarting rover-base-telemetry ONLY"
${ATLAS_RESTART_CMD:-systemctl --user restart rover-base-telemetry.service}
if [[ -z "${ATLAS_RESTART_CMD:-}" ]]; then
  sleep 8
  systemctl --user is-active rover-base-telemetry.service
  journalctl --user -u rover-base-telemetry -n 20 --no-pager | grep -E "Yahboom board ready|RC report|Traceback" || true
fi
echo "rollback: OWNER_APPROVED=yes $HERE/rollback.sh $BK"
