#!/usr/bin/env bash
# ATLAS B1: read-only firmware/settings backup of the Yahboom board. PROPOSAL; run only after the
# owner approves B1. Interactive: the owner must be at the rover for the physical steps.
#
# What it changes: stops rover-base-telemetry for a few minutes and starts it again. Nothing else.
# What it never does: flash, erase, unprotect, write option bytes, touch udev, motors, TF, Nav2 or E-STOP.
# No automatic retries: any failure stops the script and tells you how to restore normal operation.
set -Eeuo pipefail
[[ "${OWNER_APPROVED:-}" == "yes" ]] || { echo "refused: set OWNER_APPROVED=yes after B1 approval"; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
STAMP=$(date +%Y%m%d_%H%M%S)
OUT=${ATLAS_B1_OUT:-/home/jetson/project-atlas-migration/b1_firmware_backup_$STAMP}
CFG=/home/jetson/project_atlas/config
S=/home/jetson/project_atlas/scripts
PORT=/dev/ttyUSB0
VENDOR_HEX=${ATLAS_VENDOR_HEX:-$HERE/rosmaster_V3.6.5.hex}

ask() { read -r -p "$1 Type YES to continue: " a; [[ "$a" == "YES" ]] || { echo "stopped by operator"; exit 2; }; }
restore_hint() {
  echo; echo "== To return to normal operation =="
  echo "  1. Make sure BOOT0 is released. Board main switch ON (it should never have been off). Press RESET once."
  echo "  2. systemctl --user start rover-base-telemetry.service"
  echo "  3. journalctl --user -u rover-base-telemetry -n 5 | grep 'Yahboom board ready'"
}
SERVICE_STOPPED=0
trap 'echo "B1 stopped at line $LINENO"' ERR
# After the base service is stopped, ANY exit (error, operator "no", Ctrl-C) prints the restore steps.
# The service is deliberately NOT auto-started: the board may still be in the bootloader.
trap '[[ $SERVICE_STOPPED == 1 ]] && restore_hint' EXIT

# 0. Preconditions the software can check
curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)" \
  || { echo "refused: E-STOP not latched (latch with Xbox B)"; exit 2; }
loc=$(python3 -c "from serial.tools import list_ports;print(next((p.location for p in list_ports.comports() if p.device=='$PORT'),'none'))")
[[ "$loc" == "1-2.2.3" ]] || { echo "refused: $PORT is at USB $loc, expected 1-2.2.3 (Yahboom board)"; exit 2; }
[[ -f "$VENDOR_HEX" ]] && (cd "$(dirname "$VENDOR_HEX")" && echo "088af51933e98e51105412a0dbf4f5d078dbc3bcff7664105a094d073e12b55b  $(basename "$VENDOR_HEX")" | sha256sum -c -) \
  || { echo "refused: vendor 3.6.5 hex missing or hash mismatch"; exit 2; }

# 1. Jetson-side backup first (calibration lives on the Jetson, not the board)
mkdir -p "$OUT/jetson_config"
cp -p "$CFG"/steering_calibration.json "$CFG"/drive_pid.yaml "$CFG"/encoder_calibration.yaml \
      "$CFG"/encoder_selection.yaml "$CFG"/yahboom_imu_calibration.yaml "$OUT/jetson_config/"
( cd "$OUT/jetson_config" && sha256sum * > SHA256SUMS )
( cd "$S" && sha256sum Rosmaster_Lib.py yahboom_base.py atlas_usb_identity.py ) > "$OUT/jetson_scripts.sha256"
journalctl --user -u rover-base-telemetry --no-pager | grep -E "Yahboom board ready" | tail -3 > "$OUT/last_board_ready.txt" || true
echo "Jetson backup:"; cat "$OUT/jetson_config/SHA256SUMS"

# 2. Physical isolation (owner)
ask "Wheels lifted; all four M1-M4 motor/encoder connectors unplugged at board; S1-S4 and serial-servo J10 empty/disconnected; CAN J11 and RGB J15 empty/disconnected; no actuator has another power/control path. Keep these disconnected through normal-firmware restoration."
ask "Transmitter OFF. If receiver remains connected: verified original SBUS header only, powered only by board, no external receiver supply or other output connections. Stock SBUS control bypasses host E-STOP; transmitter OFF is NOT actuator isolation."
ask "Board main switch ON and battery connected throughout. Power wiring and peripheral inventory physically checked against B1 section 8; LTC3780 input traced to battery/BMS side; stable supply confirmed. No switch-OFF or USB-only operation."

# 3. Release the port (the only service change)
systemctl --user stop rover-base-telemetry.service
SERVICE_STOPPED=1
sleep 2
if fuser "$PORT" >/dev/null 2>&1; then echo "port still held; stopping"; exit 4; fi

# 4. Bootloader entry (owner)
ask "Hold BOOT0, press and release RESET, then release BOOT0 (the board's LED stops its normal blink)."

# 5. Read-only backup
set +e
python3 "$HERE/atlas_stm32_readback.py" --port "$PORT" --out "$OUT/stm32" --vendor-hex "$VENDOR_HEX" \
        --i-confirm-bootloader-entered | tee "$OUT/readback.log"
rc=${PIPESTATUS[0]}
set -e
echo "readback exit code: $rc   (0 ok, 3 read-protected, 4 protocol stop, 5 pass mismatch; script exits 6 if the base is not confirmed back)"

# 6. Return to normal (owner + one start)
ask "BOOT0 released. Board main switch ON. Press RESET once now."
START=$(date +%s)
systemctl --user start rover-base-telemetry.service
# Firmware 3.3+ waits ~10 s for IMU init after RESET, and the driver may need a systemd restart
# (RestartSec=3) before discovery succeeds, so poll up to 60 s for a line logged after START.
ready=""
for _ in $(seq 60); do
  ready=$(journalctl --user -u rover-base-telemetry --since "@$START" --no-pager | grep -E "Yahboom board ready.*firmware=3\.6, car_type=5" | tail -1 || true)
  [[ -n "$ready" ]] && break
  sleep 1
done
systemctl --user is-active rover-base-telemetry.service || true
if [[ -n "$ready" ]]; then
  echo "$ready" > "$OUT/after_board_ready.txt"
  SERVICE_STOPPED=0
  echo "base driver is back: board ready, firmware 3.6, car type 5"
else
  echo "WARNING: no 'board ready firmware=3.6, car_type=5' within 60 s. Is BOOT0 released and RESET pressed? Do not reconnect actuators."
  [[ "$rc" == 0 ]] && rc=6   # backup fine but base not confirmed back: non-zero so it cannot be missed
fi
echo "Leave ALL actuators disconnected and transmitter OFF; E-STOP stays latched. Reconnection requires a separate reviewed plan: stock SBUS can bypass host E-STOP. B1 does not authorize reconnection."
trap - ERR
( cd "$OUT" && find . -type f ! -name SHA256SUMS.all -exec sha256sum {} + > SHA256SUMS.all )
echo "backup folder: $OUT"
exit "$rc"
