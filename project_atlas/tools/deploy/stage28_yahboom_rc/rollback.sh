#!/usr/bin/env bash
# Stage 28 Jetson rollback: restore the two backed-up files byte-for-byte, remove the two new modules,
# restart rover-base-telemetry only. Usage: OWNER_APPROVED=yes rollback.sh <backup dir>
set -Eeuo pipefail
[[ "${OWNER_APPROVED:-}" == "yes" ]] || { echo "refused: set OWNER_APPROVED=yes"; exit 2; }
BK=${1:?backup dir}
S=${ATLAS_SCRIPTS_DIR:-/home/jetson/project_atlas/scripts}
( cd "$BK" && sha256sum -c SHA256SUMS )
install -m 0644 "$BK/Rosmaster_Lib.py" "$S/Rosmaster_Lib.py"
install -m 0755 "$BK/yahboom_base.py" "$S/yahboom_base.py"
rm -f "$S/atlas_yahboom_rc_report.py" "$S/atlas_rc_readonly_bridge.py"
( cd "$S" && sha256sum Rosmaster_Lib.py yahboom_base.py ) | diff - "$BK/SHA256SUMS" && echo "restored byte-identical"
${ATLAS_RESTART_CMD:-systemctl --user restart rover-base-telemetry.service}
[[ -n "${ATLAS_RESTART_CMD:-}" ]] || { sleep 8; systemctl --user is-active rover-base-telemetry.service; }
