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
ask 'Confirm physical STM32F103RCT6 marking, all actuators disconnected, transmitter OFF, main switch ON and approved power/SBUS isolation.'
# begin-read verifies inactive base and no jobs; pyserial additionally checks port ownership.
python3 "$GATE" begin-read --session "$ATLAS_B1_SESSION" --port "$ATLAS_B1_PORT"
trap 'python3 "$GATE" abort --session "$ATLAS_B1_SESSION"; echo "Attempt ended. Interlock remains held. Release BOOT0 only if held; do not press RESET. Await verified port-release and recovery guidance."' EXIT
python3 "$GATE" check-read --session "$ATLAS_B1_SESSION"
ask 'Press and HOLD BOOT0 now.'
python3 "$GATE" check-read --session "$ATLAS_B1_SESSION"
ask 'While holding BOOT0, press and release RESET.'
python3 "$GATE" check-read --session "$ATLAS_B1_SESSION"
ask 'Now release BOOT0. Do not press any button again.'
python3 "$HERE/atlas_stm32_readback.py" --maintenance-session "$ATLAS_B1_SESSION" \
  --port "$ATLAS_B1_PORT" --out "$ATLAS_B1_OUT" --i-confirm-bootloader-entered --i-confirm-stm32f103rct6-marking
# Only readback success reaches this message. Copies and normal telemetry must still be verified.
echo 'BACKUP COMPLETED AND VERIFIED LOCALLY; Windows copy and restoration pending.'
