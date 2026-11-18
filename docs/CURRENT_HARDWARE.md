# Project ATLAS commissioned hardware

This is the authoritative hardware list. Software installers and dashboards
must not create health faults for hardware outside this list.

| Function | Current hardware | Active route |
|---|---|---|
| Main computer | NVIDIA Jetson Orin Nano Super 8 GB | Ubuntu 22.04 / ROS 2 Humble |
| Storage | Jetson NVMe | Local maps, missions, bags, and experience database |
| Drive and wheel feedback | Yahboom ROS Driver Board V3.0; M1, M2 and M4 encoder feedback selected; M3 encoder excluded/disabled in the recorded 14–16 Nov configuration | USB serial `/dev/yahboom`; three-channel consensus; any further critical loss fails closed |
| Steering | Front and rear steering servos | Yahboom motor board |
| Primary attitude | Yahboom motor-board 9-axis IMU | Same `/dev/yahboom` link |
| Primary ranging | RPLIDAR A1 (Sensitivity mode recorded 15 Nov) | USB serial and `/scan` |
| Motion radar | RD-03D V2 | Radar UART to Arduino UNO R4, then USB to Jetson |
| RGB vision | Raspberry Pi Camera Module 3 / IMX708 with Arducam pan-tilt | CSI camera; PCA9685 on UNO R4 sensor bus |\n| Depth vision | Orbbec Astra Pro | USB depth/RGB interfaces; calibrated full-home 3D mapping still pending |
| Sensor hub | Arduino UNO R4 WiFi | USB CDC to Jetson |
| Inside thermal | AMG8833 8x8 | UNO R4 I2C |
| Outside environment | BME680 | UNO R4 I2C |
| Near-field ranging | Front and rear ultrasonic channels enabled; left and right channels disabled | UNO R4 GPIO; fresh VALID front/rear samples only; LiDAR remains primary |
| Main battery | Daly smart BMS | Bluetooth telemetry |
| Jetson power | Onboard INA3221 | Linux INA3221 telemetry service |
| Network | Wi-Fi, Tailscale, SIM8230 cellular modem | Local/Tailscale dashboard and 4G/5G fallback |
| GNSS | No verified active GNSS receiver in the 16 Nov evidence snapshot; legacy L76K is archived unless physically re-commissioned | No active GNSS route claimed |
| Voice | ESP32-S3 USB voice interface | USB serial and local/cloud voice service |
| Operator interface | Web dashboard on operator phone/PC; CrowPanel is a planned upgrade, not counted as commissioned hardware | Wi-Fi / Tailscale web interface |

## Permanently retired

Portenta H7, Mega 2560, BNO055, BNO08x, external INA219, Pi UPS HAT, and the
broken 11-inch wired display are not valid fallback devices. Their historical
work remains documented only in `CHANGELOG.md` and old engineering reports.


## Hardware archive and disabled channels

The following items are **not part of the active commissioned hardware baseline**. Keep their historical design notes, calibration records and commits for traceability; do not start their services, expose their topics as live sensors, or list them as fallback devices.

- **Disabled encoder channel:** M3 feedback is excluded in `project_atlas/config/encoder_selection.yaml`; the recorded active subset is M1/M2/M4. This is a feedback-channel exclusion, not permission to remove the physical motor or encoder assembly.
- **Disabled ultrasonic channels:** left and right are DISABLED in the 16 November live check; front and rear were VALID. Do not treat disabled side channels as zero-distance or clear-path evidence.
- **Legacy GNSS:** L76K is not verified as physically fitted/active in the 16 November evidence. Do not start a GPS node or advertise GNSS availability without a new hardware check.
- **Planned display:** CrowPanel Advanced 10.1-inch is a future upgrade, not a commissioned operator display in this snapshot.
- **Retired controller/sensors:** Portenta H7, Mega 2560, BNO055, BNO08x, external INA219 and Pi UPS HAT.
- **Retired display:** broken 11-inch wired display.

Archived hardware history is in [HARDWARE_ARCHIVE.md](HARDWARE_ARCHIVE.md). Re-commissioning any archived item requires physical identification, wiring/power verification, driver/topic verification and a dated acceptance record. Archiving documentation does not itself power down or electrically disconnect hardware.
