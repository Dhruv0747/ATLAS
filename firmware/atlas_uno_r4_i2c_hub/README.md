# ATLAS UNO R4 WiFi sensor hub

This firmware is the bench-tested replacement sensor hub for Project ATLAS.
It keeps low-bandwidth sensor handling off the Jetson and forwards telemetry
over one persistent USB serial connection at 115200 baud.

## Wiring

| Device | UNO R4 WiFi connection | Current state |
|---|---|---|
| PCA9685 | A4/SDA, A5/SCL, 3.3 V logic, common GND | live at `0x40` |
| AMG8833 | A4/SDA, A5/SCL, 3.3 V, common GND | live at `0x69` |
| BME680 | A4/SDA, A5/SCL, 3.3 V, common GND | live at `0x77` |
| L76K GNSS | module TX to D0/RX, module RX to D1/TX | live at 9600 baud |
| RD-03D radar | module TX to D12/RX; module RX to D11/TX; common GND | 256000 baud; require valid `AA FF 03 00 … 55 CC` frames |
| Rear ultrasonic | TRIG D8, ECHO D9 | live |
| Front ultrasonic | TRIG D2, ECHO D3 | reserved, disabled |
| Left ultrasonic | TRIG D4, ECHO D5 | reserved, disabled |
| Right ultrasonic | TRIG D6, ECHO D7 | reserved, disabled |

All devices must share ground. Do not apply 5 V directly to any 3.3 V-only
signal input. Use a divider or level shifter if an ultrasonic ECHO output is
5 V.

The retired BNO08x is not part of this hub firmware. ATLAS now uses the
calibrated Yahboom motor-controller IMU as its sole canonical system IMU.

## Serial commands

- `SCAN` scans the A4/A5 I2C bus and retries its commissioned devices.
- `STATUS` prints device, UART, ultrasonic, and bus-health state.
- `RADARINIT` sends the RD-03D multi-target-mode request during controlled
  maintenance. It is deliberately not sent automatically: a damaged or
  miswired radar UART must never stall unrelated sensor telemetry.
- `USENABLE,F|L|R|B,0|1` enables or disables one ultrasonic position.

The built-in 12x8 LED matrix cycles through device labels. A check means live,
an X means missing/stale, and a dash means that channel is intentionally
disabled. The display is diagnostic only and cannot bypass ATLAS motion safety.

## Bench validation, 2026-09-02

- Main A4/A5 scan: `0x40`, `0x69`, `0x77` (the retired `0x4B` device may be
  physically absent and is no longer expected).
- BME680, AMG8833, L76K GNSS, PCA9685 discovery, and rear ultrasonic telemetry
  passed their bench checks. Radar UART byte activity alone is not a pass: the
  Jetson decoder must report valid 30-byte RD-03D target frames.

The hub owns the environment, thermal, camera controller, GNSS, radar and
ultrasonic routes only. The Yahboom base process owns `/imu/*`.

## Jetson deployment

Build this sketch with `build_native_usb.sh`. ATLAS uses the RA4M1 native USB
CDC endpoint (`2341:006d`) rather than the UNO R4 WiFi ESP32 CMSIS-DAP serial
bridge (`2341:1002`). The bridge can stay visible to Linux while dropping all
UART telemetry after resets; native USB removes that failure point. The ROS
bridge resolves the native by-id path first and also falls back across Arduino
by-id names after re-enumeration.

The UNO is permanently identified by its USB serial number, not by the changing
`/dev/ttyACM*` index. Install and enable
`project_atlas/systemd/user/atlas-uno-r4-sensor-hub.service`. Disable the old
Mega, Portenta, and direct Jetson PTZ services so only one process owns the
sensor UART and PCA9685 command path. The ROS bridge asserts DTR for native UNO
R4 USB CDC, but does not automatically move the camera during a reconnect.

The commissioned navigation EKF still uses wheel odometry only. Yahboom gyro
fusion remains disabled until a recorded clockwise/counter-clockwise sign and
magnitude test passes. This is a navigation qualification gate, not a missing
sensor warning. Automatic BME680, AMG8833 and PCA9685 recovery is independent
of all IMU handling.

Install `project_atlas/udev/70-project-atlas-uno-r4.rules` with the supplied
root helper before the final endurance run. It prevents ModemManager from
probing this exact Arduino CDC endpoint while leaving the SIMCom 4G/5G modem
untouched. The same rule creates `/dev/atlas-sensor-hub` for local diagnostics.
