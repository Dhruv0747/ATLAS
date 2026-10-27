#!/usr/bin/env bash
# Candidate, not deployed. Requires separately reviewed deployment + ONE B1 approval.
set -Eeuo pipefail
[[ "${OWNER_APPROVED:-}" == yes && -n "${ATLAS_B1_SESSION:-}" ]] || exit 2
: "${ATLAS_B1_OUT:?Provide a new evidence directory}"
: "${ATLAS_B1_PORT:?Provide verified Yahboom port}"
GATE=/home/jetson/project_atlas/scripts/atlas_b1_interlock.py
HERE=$(cd "$(dirname "$0")" && pwd)
ask() { local answer; read -r -p "$1 Reply DONE: " answer; [[ "$answer" == DONE ]]; }
# No service changes here. Operator starts independent watch before the one approved stop.
# begin-read verifies inactive base and no jobs; pyserial additionally checks port ownership.
python3 "$GATE" begin-read --session "$ATLAS_B1_SESSION"
trap 'python3 "$GATE" abort --session "$ATLAS_B1_SESSION"; echo "Attempt ended. Interlock remains held. Release serial before supervised normal RESET/restoration."' EXIT
ask 'Press and HOLD BOOT0 now.'
ask 'While holding BOOT0, press and release RESET.'
ask 'Now release BOOT0. Do not press any button again.'
python3 "$HERE/atlas_stm32_readback.py" --maintenance-session "$ATLAS_B1_SESSION" \
  --port "$ATLAS_B1_PORT" --out "$ATLAS_B1_OUT" --i-confirm-bootloader-entered
# Only readback success reaches this message. Copies and normal telemetry must still be verified.
echo 'BACKUP COMPLETED AND VERIFIED LOCALLY; Windows copy and restoration pending.'
