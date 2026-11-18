# ATLAS system architecture — hardware, software and combined data flow

**Evidence baseline:** repository documentation snapshot dated 16 November 2026, prepared on the documentation branch.
**Purpose:** explain how ATLAS hardware signals become ROS 2 data, how software turns those data into guarded motion commands, and how the operator supervises the rover.

> **Status key:** `ACTIVE / DOCUMENTED` means included in the recorded commissioned baseline; `DISABLED / EXCLUDED` means do not treat as a live input; `PLANNED` means not commissioned; `DESIGN ONLY` means not an implemented capability.
>
> These are system-level block/data-flow diagrams, not pin-to-pin wiring schematics. Exact connector pins, voltage rails, fuse values and cable routing must be taken from the current physical wiring record and verified on the rover. A diagram does not authorize energizing hardware or changing safety configuration.

## 1. Hardware block diagram

This view focuses on physical devices, buses and signal paths. Solid arrows represent documented data/control connections. The battery/power branch is intentionally shown at a high level because this document does not establish every rail and fuse connection.

```mermaid
flowchart TB
  subgraph POWER["POWER — physical power path (high-level; verify wiring sheet)"]
    BAT["Main battery pack"]
    BMS["Daly smart BMS"]
    PWR["Protected power distribution / DC-DC rails"]
    BAT --> BMS --> PWR
    PWR --> JETP["Jetson power input"]
    PWR --> YBP["Yahboom board power"]
    PWR --> UNO_P["UNO R4 / sensor-hub supply"]
    PWR --> CAM_P["Camera / peripheral supply as wired"]
  end

  subgraph COMPUTE["MAIN COMPUTE"]
    JET["NVIDIA Jetson Orin Nano Super 8 GB<br/>Ubuntu 22.04 · ROS 2 Humble"]
    NVME["Jetson NVMe<br/>maps · bags · logs · mission data"]
    JET --- NVME
    JETP --> JET
  end

  subgraph DRIVE["DRIVE, STEERING AND MOTION FEEDBACK"]
    YB["Yahboom ROS Driver Board V3.0<br/>motor controller + primary IMU"]
    MOT["4 × drive motors"]
    ENC["Encoder feedback<br/>M1, M2, M4 selected<br/>M3 excluded"]
    STR["Front + rear steering servos"]
    YBP --> YB
    YB -->|"motor drive outputs"| MOT
    MOT -->|"wheel motion"| ENC
    ENC -->|"USB serial /dev/yahboom"| JET
    YB -->|"IMU telemetry via board link"| JET
    YB -->|"servo control"| STR
  end

  subgraph RANGE["RANGE AND DEPTH SENSORS"]
    LIDAR["RPLIDAR A1<br/>primary 2D ranging"]
    ASTRA["Orbbec Astra Pro<br/>depth + RGB interfaces"]
    ULTRA["Ultrasonic front + rear<br/>ACTIVE · fresh VALID only"]
    SIDE["Ultrasonic left + right<br/>DISABLED"]
    LIDAR -->|"/scan over USB"| JET
    ASTRA -->|"USB depth / RGB streams"| JET
    ULTRA -->|"UNO R4 sensor hub → USB CDC"| JET
    SIDE -. "not a live safety input" .-> JET
  end

  subgraph HUB["SENSOR HUB AND AUXILIARY SENSORS"]
    UNO["Arduino UNO R4 WiFi<br/>sensor aggregation"]
    RADAR["RD-03D V2 radar"]
    THERM["AMG8833 thermal array"]
    ENV["BME680 environment sensor"]
    PAN["PCA9685 pan-tilt control"]
    RGB["Raspberry Pi Camera Module 3 / IMX708<br/>Arducam pan-tilt"]
    UNO_P --> UNO
    RADAR -->|"UART"| UNO
    THERM -->|"I²C"| UNO
    ENV -->|"I²C"| UNO
    UNO -->|"USB CDC"| JET
    UNO -->|"I²C control"| PAN
    PAN -->|"pan / tilt"| RGB
    RGB -->|"CSI camera stream"| JET
  end

  subgraph OPERATOR["OPERATOR AND NETWORK"]
    REMOTE["Manual remote / operator controls"]
    ESTOP["Physical E-STOP"]
    WIFI["Wi-Fi / Tailscale / cellular fallback"]
    UI["Web dashboard on phone / PC"]
    VOICE["ESP32-S3 USB voice interface"]
    REMOTE -->|"manual command input"| JET
    ESTOP -->|"hardware safety stop path"| YB
    JET <-->|"network status / commands"| WIFI
    WIFI <-->|"browser connection"| UI
    VOICE <-->|"USB serial / voice service"| JET
  end

  classDef active fill:#e8f4ff,stroke:#2875b9,color:#123;
  classDef disabled fill:#f1f1f1,stroke:#888,color:#555,stroke-dasharray: 5 5;
  classDef planned fill:#fff5dd,stroke:#b88925,color:#543;
  class JET,JETP,NVME,YB,MOT,ENC,STR,LIDAR,ASTRA,ULTRA,UNO,RADAR,THERM,ENV,PAN,RGB,REMOTE,ESTOP,WIFI,UI,VOICE active;
  class SIDE disabled;
```

### Hardware notes

- **Drive feedback:** M1, M2 and M4 are selected in the recorded configuration. M3 feedback is excluded; this does not mean the physical M3 motor is removed.
- **Ranging:** RPLIDAR A1 is the primary 2D ranging source. Only fresh, valid front/rear ultrasonic readings are eligible for the documented coverage logic. A short ultrasonic reading is not proof that the path beyond it is clear.
- **Depth / RGB:** Astra Pro connects over USB; the IMX708 camera uses CSI. The camera pan-tilt mechanism is controlled through the PCA9685/UNO path.
- **UNO sensor hub:** RD-03D radar arrives over UART; AMG8833 and BME680 use I²C; aggregated data reaches Jetson over USB CDC.
- **Operator safety:** keep the physical E-STOP accessible. Software stop and dashboard status do not replace the physical stop.
- **Not active:** left/right ultrasonic channels are disabled; legacy L76K GNSS is not verified active; CrowPanel display is planned, not commissioned. Retired hardware is listed in [HARDWARE_ARCHIVE.md](HARDWARE_ARCHIVE.md).

## 2. Software block diagram

This view follows the information from ROS 2 drivers through state estimation, mapping/localization, navigation and the final safety-controlled command path.

```mermaid
flowchart TB
  subgraph INPUT["1 · SENSOR AND CONTROL INPUTS"]
    SCAN["RPLIDAR driver<br/>/scan"]
    ENC_T["Yahboom board interface<br/>wheel encoder feedback"]
    IMU_T["Yahboom primary IMU<br/>IM10A telemetry"]
    DEPTH_T["Astra driver<br/>depth / RGB"]
    UNO_T["UNO sensor bridge<br/>radar · ultrasound · thermal · BME680"]
    CAM_T["CSI camera driver<br/>IMX708"]
    MANUAL["Manual remote input"]
    VOICE["Voice command service<br/>spoken stop / E-STOP intent"]
  end

  subgraph ROS["2 · ROS 2 HUMBLE CORE ON JETSON"]
    ODOM["Wheel odometry"]
    EKF["robot_localization EKF<br/>wheel velocity + IM10A yaw"]
    TF["TF transforms / robot frames"]
    SLAM["SLAM Toolbox<br/>2D map creation"]
    AMCL["AMCL localization<br/>pose on accepted 2D map"]
    RTAB["RTAB-Map / point-cloud pipeline<br/>3D prototype; calibration incomplete"]
    COST["Nav2 costmaps<br/>LiDAR + validated obstacle inputs"]
    NAV["Nav2 planner / controller"]
    MISSION["Mission / named-place manager"]
  end

  subgraph SAFETY["3 · COMMAND AUTHORITY AND SAFETY"]
    MUX["Command mux / source arbitration<br/>manual vs autonomy"]
    GUARD["Safety guards<br/>sensor freshness · encoder health<br/>speed / command-age / stop conditions"]
    ESTOP["Physical E-STOP + software stop state"]
    DRIVER["Yahboom motor / steering interface"]
  end

  subgraph OBS["4 · SUPERVISION, RECORDING AND OPTIONAL SERVICES"]
    DASH["Web dashboard<br/>status · map · mission · camera"]
    LOG["Logs / rosbag / diagnostics<br/>timestamped evidence"]
    HEALTH["Read-only health monitoring<br/>CPU · RAM · temperature · device freshness"]
    PERCEPT["Optional perception / AI annotation<br/>advisory only; no motion authority"]
    HUMAN["Human-aware navigation<br/>DESIGN ONLY — not an active autonomy feature"]
  end

  SCAN --> SLAM
  SCAN --> COST
  ENC_T --> ODOM --> EKF
  IMU_T --> EKF
  EKF --> TF
  TF --> SLAM
  TF --> AMCL
  SLAM -->|"map"| AMCL
  AMCL --> MISSION
  MISSION --> NAV
  COST --> NAV
  DEPTH_T --> RTAB
  TF --> RTAB
  UNO_T --> COST
  UNO_T --> LOG
  CAM_T --> PERCEPT
  DEPTH_T --> PERCEPT
  PERCEPT -. "advisory observations only" .-> COST
  HUMAN -. "future design; not implemented" .-> PERCEPT

  MANUAL --> MUX
  VOICE -->|"stop request only"| GUARD
  NAV -->|"autonomous velocity request"| MUX
  MUX --> GUARD
  ESTOP --> GUARD
  GUARD -->|"permitted command or zero/stop"| DRIVER
  DRIVER -->|"motor + steering outputs"| ODOM

  EKF --> DASH
  AMCL --> DASH
  SLAM --> DASH
  MISSION --> DASH
  GUARD --> DASH
  DRIVER --> LOG
  EKF --> LOG
  NAV --> LOG
  HEALTH --> DASH
  HEALTH --> LOG
  PERCEPT --> DASH
```

### Software notes

- **State estimation:** wheel odometry and the primary IMU feed the EKF. The recorded corrected configuration uses wheel velocity with IM10A yaw; the heading correction is not proof of full-route position accuracy.
- **Mapping and localization:** SLAM Toolbox creates/updates the 2D map; AMCL localizes against the selected map. RTAB-Map produces 3D point-cloud prototypes, but whole-home calibrated 3D acceptance remains open.
- **Navigation:** the mission manager selects a named place; Nav2 plans and controls a path using localization and costmaps.
- **Safety authority:** manual and autonomous requests pass through command arbitration and safety guards before reaching the motor interface. The E-STOP remains an independent physical safety mechanism.
- **Voice:** voice may request a stop; it must not bypass the safety guards or independently grant motion.
- **AI / human-aware perception:** optional perception can provide advisory observations only. The human-aware navigation document is a design, not an implemented autonomy capability.
- **Monitoring:** health monitoring is read-only. Missing or stale sensor values must be shown as unavailable/stale, never silently converted to zero or clear.

## 3. Combined hardware + software data-flow diagram

This is the end-to-end view: **physical sensor → interface/driver → ROS data → state/map/planning → safety arbitration → actuator → feedback**, with the operator and monitoring paths alongside it.

```mermaid
flowchart LR
  subgraph PHYS["A · PHYSICAL WORLD / HARDWARE"]
    WORLD["Room / hall / obstacles / people"]
    L["RPLIDAR A1"]
    A["Astra Pro depth"]
    C["IMX708 RGB"]
    U["Front + rear ultrasound"]
    R["RD-03D radar"]
    W["Wheels + M1/M2/M4 feedback"]
    I["Primary IMU"]
    Y["Yahboom board"]
    S["Steering servos"]
    E["Physical E-STOP"]
    WORLD --> L
    WORLD --> A
    WORLD --> C
    WORLD --> U
    WORLD --> R
    W -->|"rotation feedback"| Y
    I --> Y
    E --> Y
  end

  subgraph LINK["B · HARDWARE INTERFACES / DRIVERS"]
    LD["USB LiDAR driver"]
    AD["USB Astra driver"]
    CD["CSI camera driver"]
    UD["UNO R4 bridge<br/>UART / I²C / USB CDC"]
    YD["Yahboom USB serial interface"]
    MD["Manual remote interface"]
    VD["ESP32-S3 voice interface"]
  end

  subgraph DATA["C · ROS 2 DATA AND ESTIMATION"]
    TOP["ROS topics / sensor messages"]
    EKF["Odometry + EKF + TF"]
    MAP["SLAM Toolbox / accepted 2D map"]
    LOC["AMCL localization"]
    CLOUD["RTAB-Map / 3D point cloud"]
    COST["Nav2 costmaps"]
  end

  subgraph DECIDE["D · MISSION AND MOTION DECISION"]
    TASK["Mission / named goal"]
    NAV["Nav2 planner + controller"]
    MAN["Manual command"]
    MUX["Command mux"]
    SAFE["Safety guards + freshness checks"]
    STOP["E-STOP / stop state"]
  end

  subgraph ACT["E · ACTUATION AND CLOSED-LOOP FEEDBACK"]
    CMD["Yahboom motor / servo outputs"]
    MOTOR["Drive motors"]
    STEER["Steering servos"]
    RESULT["Physical rover motion"]
  end

  subgraph HUMAN["F · OPERATOR AND EVIDENCE"]
    DASH["Dashboard: map · pose · mission · camera · faults"]
    LOG["rosbag · logs · diagnostics"]
    MON["Read-only health metrics"]
    OP["Operator / remote"]
  end

  L --> LD --> TOP
  A --> AD --> TOP
  C --> CD --> TOP
  U --> UD --> TOP
  R --> UD
  Y --> YD --> TOP
  I --> Y
  W --> Y
  TOP --> EKF
  TOP --> MAP
  EKF --> LOC
  MAP --> LOC
  TOP --> CLOUD
  TOP --> COST
  LOC --> TASK
  TASK --> NAV
  COST --> NAV
  OP --> MD --> MAN
  OP --> VD --> STOP
  MAN --> MUX
  NAV --> MUX
  MUX --> SAFE
  E --> STOP --> SAFE
  SAFE -->|"command only when permitted; otherwise stop/zero"| CMD
  CMD --> Y
  Y --> MOTOR --> RESULT
  Y --> STEER --> RESULT
  RESULT --> WORLD
  RESULT --> W
  TOP --> DASH
  EKF --> DASH
  LOC --> DASH
  TASK --> DASH
  SAFE --> DASH
  DASH --> OP
  TOP --> LOG
  NAV --> LOG
  SAFE --> LOG
  MON --> DASH
  MON --> LOG
```

## 4. Read the system in 6 simple steps

1. **Sense:** LiDAR, depth/RGB, IMU, encoders, radar and enabled front/rear ultrasound observe the rover and its surroundings.
2. **Transport:** each device reaches Jetson through its documented interface — USB, CSI, UART/I²C through UNO R4, or the Yahboom serial link.
3. **Understand position:** ROS 2 drivers publish data; odometry + EKF + TF estimate motion; SLAM builds the 2D map and AMCL estimates the rover's pose on that map.
4. **Plan:** the mission manager requests a named destination; Nav2 plans a path using localization and costmaps. RTAB-Map is the separate 3D mapping prototype.
5. **Authorize motion:** manual/autonomous requests are arbitrated; safety guards check freshness and fault conditions; E-STOP can stop motion. Only then does a command reach the motor/steering interface.
6. **Close the loop:** wheel feedback and sensor data return to ROS 2; dashboard, logs and read-only health monitoring let the operator inspect what happened.

## 5. Current limitations shown by the diagrams

- The Stage-3 supervised Dhruv Room → Hall → Dhruv Room route had **not passed** as of 16 November 2026. Safe-stop measurement passed, but the full round trip failed.
- Encoder qualification remains degraded; M3 feedback is excluded and one CRITICAL encoder sample was recorded during the failed Stage-3 attempt.
- Full-drive localization and Hall-door sensor coverage still need repeatable validation.
- Full-home calibrated 3D mapping is not complete.
- Human-aware navigation is design-only.
- Unattended autonomy is **NOT APPROVED**.

## 6. Related engineering records

- [Current commissioned hardware](CURRENT_HARDWARE.md)
- [Engineering status and open acceptance gates](ENGINEERING_STATUS_2026-11-16.md)
- [Hardware archive and disabled/retired items](HARDWARE_ARCHIVE.md)
- [Stage-3 acceptance result](ATLAS_STAGE3_ACCEPTANCE_20261116.md)
- [Human-aware navigation — design only](ATLAS_HUMAN_AWARE_NAVIGATION_DESIGN_2026-11-16.md)
