# ATLAS Mega 2560 Sensor Hub

The Arduino Mega 2560 replaces the Portenta H7 as ATLAS's sensor I/O hub. It
has no motor, navigation, watchdog, or emergency-stop authority. Those remain
local on the Jetson.

## Permanent ownership

The Mega 2560 is the single hardware owner for the low-bandwidth sensor bus:

- BNO08x IMU
- BME680 environment sensor
- AMG8833 8x8 thermal array
- L76K GNSS receiver
- RD-03D motion radar transport
- installed ultrasonic channels

The Jetson runs one `atlas-mega-sensor-hub.service` ROS bridge and the
`rover-radar.service` frame decoder. The legacy direct `atlas-imu`,
`atlas-gnss`, `atlas-thermal`, `atlas-ultrasonic`, and Portenta hub services
must remain disabled/masked to prevent duplicate publishers and polling.

High-bandwidth or safety-critical hardware remains directly owned by the
Jetson: CSI camera, USB LiDAR, Yahboom motor/encoder controller, BMS, camera
pan/tilt controller, and cellular modem. These devices must not be routed
through the Mega.

## Commissioned wiring

| Function | Mega pin | Connect to |
|---|---:|---|
| I2C SDA | 20 | SDA on the 3.3 V I2C bus/level shifter |
| I2C SCL | 21 | SCL on the 3.3 V I2C bus/level shifter |
| GNSS input | RX1 / 19 | L76K TX |
| GNSS output | TX1 / 18 | L76K RX |
| Radar input | RX2 / 17 | RD-03D TX |
| Radar output | TX2 / 16 | RD-03D RX |
| Front ultrasonic | TRIG 28 / ECHO 29 | Front sensor |
| Left ultrasonic | TRIG 24 / ECHO 25 | Left sensor |
| Right ultrasonic | TRIG 26 / ECHO 27 | Right sensor |
| Rear ultrasonic | TRIG 23 / ECHO 22 | Rear sensor |
| Jetson telemetry | USB | Fixed Jetson physical USB path `2.2.3` |

All devices must share ground. The Mega uses 5 V GPIO. Do not put 5 V on a
3.3 V-only sensor input; use a proper bidirectional I2C level shifter when any
attached I2C module is not 5 V tolerant. Confirm every module's supply voltage
from its own datasheet.

The firmware samples the four ultrasonic sensors sequentially to reduce
acoustic crosstalk. `-1` means no valid echo; it does not mean zero distance.

## Live interfaces

- BME680: addresses `0x76` or `0x77`
- AMG8833: addresses `0x68` or `0x69`
- BNO08x: addresses `0x4A` or `0x4B`
- PCA9685: visible in the I2C scan at `0x40`; camera control remains on Jetson
- GNSS: Serial1, 9600 baud by default
- RD-03D radar: Serial2, 256000 baud by default
- Jetson link: USB serial, 115200 baud

The bridge publishes the internal radar transport on `/radar/hub/raw_hex`; the
decoder preserves the established public `/radar/targets` and proximity topics.

The official Nicla Sense Env library is not compatible with the Mega AVR C++
runtime. The Mega reports `NICLAENV,OK=0,REASON=AVR_DRIVER_UNAVAILABLE`; do not
show fabricated Nicla measurements. BME680 remains the environmental source.

## Build

```powershell
arduino-cli compile --fqbn arduino:avr:mega firmware/atlas_mega_2560
```

## Jetson service

The Mega is addressed by its physical Jetson USB path, not by `/dev/ttyUSBN`:

```text
/dev/serial/by-path/platform-3610000.usb-usb-0:2.2.3:1.0-port0
```

The Yahboom base uses physical path `2.4`. This separation is mandatory because
both boards expose the same CH340 VID/PID and cannot safely be distinguished by
USB identity alone.

After deployment and hardware validation:

```bash
systemctl --user daemon-reload
systemctl --user disable --now atlas-portenta-sensor-hub.service
systemctl --user enable --now atlas-mega-sensor-hub.service
```

Do not run the legacy `atlas-ultrasonic.service` at the same time; duplicate ROS
publishers would corrupt sensor selection.
