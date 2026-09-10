# Project ATLAS commissioned hardware

This is the authoritative hardware list. Software installers and dashboards
must not create health faults for hardware outside this list.

| Function | Current hardware | Active route |
|---|---|---|
| Main computer | NVIDIA Jetson Orin Nano Super 8 GB | Ubuntu 22.04 / ROS 2 Humble |
| Storage | Jetson NVMe | Local maps, missions, bags, and experience database |
| Drive and wheel feedback | Yahboom ROS Driver Board V3.0, four traction motors and four encoders | USB serial `/dev/yahboom` |
| Steering | Front and rear steering servos | Yahboom motor board |
| Primary attitude | Yahboom motor-board 9-axis IMU | Same `/dev/yahboom` link |
| Primary ranging | RPLIDAR A1 | USB serial and `/scan` |
| Motion radar | RD-03D V2 | Radar UART to Arduino UNO R4, then USB to Jetson |
| Vision | Raspberry Pi Camera Module 3 / IMX708 with Arducam pan-tilt | CSI camera; PCA9685 on UNO R4 sensor bus |
| Sensor hub | Arduino UNO R4 WiFi | USB CDC to Jetson |
| Inside thermal | AMG8833 8x8 | UNO R4 I2C |
| Outside environment | BME680 | UNO R4 I2C |
| Near-field ranging | Installed ultrasonic channels | UNO R4 GPIO; LiDAR remains primary |
| Main battery | Daly smart BMS | Bluetooth telemetry |
| Jetson power | Onboard INA3221 | Linux INA3221 telemetry service |
| Network | Wi-Fi, Tailscale, SIM8230 cellular modem | Local/Tailscale dashboard and 4G/5G fallback |
| GNSS | L76K (when physically fitted) | Jetson J12 UART `/dev/ttyTHS1` |
| Voice | ESP32-S3 USB voice interface | USB serial and local/cloud voice service |
| Operator display | Elecrow CrowPanel Advanced 10.1-inch ESP32-P4 | Wireless web dashboard |

## Permanently retired

Portenta H7, Mega 2560, BNO055, BNO08x, external INA219, Pi UPS HAT, and the
broken 11-inch wired display are not valid fallback devices. Their historical
work remains documented only in `CHANGELOG.md` and old engineering reports.
