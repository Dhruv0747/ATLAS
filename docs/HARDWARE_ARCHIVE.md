# ATLAS hardware archive

**Purpose:** record hardware removed from the active commissioned baseline or disabled in the 16 November 2026 evidence snapshot. This is an archive index, not an instruction to physically remove hardware.

## Disabled or excluded channels

| Item | Archive state | Evidence / rule |
|---|---|---|
| M3 encoder feedback | Excluded from active consensus | `project_atlas/config/encoder_selection.yaml` records `excluded_encoders: [3]`; M1/M2/M4 selected. A further critical loss remains fail-closed. |
| Left ultrasonic | Disabled | 16 Nov live check reported DISABLED for all 204 samples. |
| Right ultrasonic | Disabled | 16 Nov live check reported DISABLED for all 204 samples. |
| L76K GNSS | Not commissioned / not verified fitted | Do not claim GNSS service or availability until physically checked and recommissioned. |
| CrowPanel Advanced 10.1-inch | Planned, not commissioned | Keep out of the current installed hardware inventory until installation and acceptance. |

## Retired hardware

The following hardware is excluded from active installers, service dependencies, dashboard sensor inventory and fallback architecture:

- Arduino Portenta H7
- Arduino Mega 2560
- BNO055 IMU
- BNO08x IMU
- External INA219 power monitor (onboard INA3221 is the recorded Jetson power source)
- Raspberry Pi UPS HAT
- Broken 11-inch wired display

## Preservation policy

- Preserve source history, old wiring notes, calibration records and dated test reports.
- Do not delete historical commits or old evidence just because hardware was retired.
- Do not launch archived drivers or publish archived sensor topics as live data.
- Do not use missing/disabled sensor values as zero, clear path, healthy or available.
- Re-enable an item only after physical presence, power/wiring, USB/I2C/UART identity, driver, topic freshness, dashboard semantics and safety impact have been checked and a new dated commissioning record is accepted.

**Important:** M3 encoder exclusion is not motor removal. The physical M3 motor remains part of the drive assembly; only its unreliable feedback channel is excluded. Archiving this record does not itself power down or disconnect any physical device.
