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
| BNO08x | **Qwiic/Wire1 only**, 3.3 V, common GND | move required; expected at `0x4B` |
| L76K GNSS | module TX to D0/RX, module RX to D1/TX | live at 9600 baud |
| RD-03D radar | module TX to D12/RX; D11/TX optional | live at 256000 baud |
| Rear ultrasonic | TRIG D8, ECHO D9 | live |
| Front ultrasonic | TRIG D2, ECHO D3 | reserved, disabled |
| Left ultrasonic | TRIG D4, ECHO D5 | reserved, disabled |
| Right ultrasonic | TRIG D6, ECHO D7 | reserved, disabled |

All devices must share ground. Do not apply 5 V directly to any 3.3 V-only
signal input. Use a divider or level shifter if an ultrasonic ECHO output is
5 V.

The BNO08x must not share A4/A5 with the other sensors. Its I2C behavior can
hold the shared bus low during initialization. The firmware deliberately
initializes it only on the isolated Qwiic `Wire1` bus so an IMU fault cannot
take the environment, thermal, or camera-controller devices offline. The
BNO08x LED confirms power only; `BNO,OK=1` with changing quaternion/gyro data
is the functional pass condition.

## Serial commands

- `SCAN` scans both I2C buses and retries all configured devices.
- `STATUS` prints device, UART, ultrasonic, and bus-health state.
- `USENABLE,F|L|R|B,0|1` enables or disables one ultrasonic position.

The built-in 12x8 LED matrix cycles through device labels. A check means live,
an X means missing/stale, and a dash means that channel is intentionally
disabled. The display is diagnostic only and cannot bypass ATLAS motion safety.

## Bench validation, 2026-09-02

- Main A4/A5 scan: `0x40`, `0x4B`, `0x69`, `0x77`.
- Isolated Qwiic scan: empty because the BNO08x has not yet been moved.
- BNO08x: powered and acknowledging on the wrong bus, but 0 valid packets from
  71 reports; not operational until physically moved to Qwiic.
- BME680, AMG8833, L76K GNSS, RD-03D radar, PCA9685 discovery, and rear
  ultrasonic telemetry passed their bench checks.

It may be installed as the Jetson's authoritative telemetry hub while the
BNO08x is offline because the commissioned EKF does not currently fuse that
IMU. Keep the offline state visible and complete the Qwiic move before treating
the IMU channel or orientation redundancy as commissioned.

## Jetson deployment

The UNO is permanently identified by its USB serial number, not by the changing
`/dev/ttyACM*` index. Install and enable
`project_atlas/systemd/user/atlas-uno-r4-sensor-hub.service`. Disable the old
Mega, Portenta, and direct Jetson PTZ services so only one process owns the
sensor UART and PCA9685 command path. The ROS bridge asserts DTR for native UNO
R4 USB CDC, but does not automatically move the camera during a reconnect.

The BNO08x may remain offline temporarily because the commissioned navigation
EKF currently uses wheel odometry rather than IMU yaw. Autonomous operation
must continue to report the missing IMU, and the motor-controller attitude
topics are comparison telemetry—not a silently substituted navigation source.

Install `project_atlas/udev/70-project-atlas-uno-r4.rules` with the supplied
root helper before the final endurance run. It prevents ModemManager from
probing this exact Arduino CDC endpoint while leaving the SIMCom 4G/5G modem
untouched. The same rule creates `/dev/atlas-sensor-hub` for local diagnostics.
