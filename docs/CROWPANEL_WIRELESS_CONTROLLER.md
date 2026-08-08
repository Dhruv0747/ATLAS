# CrowPanel wireless controller plan

## Decision

ATLAS will replace its broken 11-inch display with a removable, camera-equipped 10.1-inch CrowPanel Advanced ESP32-P4 HMI. The panel is a wireless user interface, not a replacement for the Jetson or the rover safety controller.

## Fully wireless operation

- The finished controller must require no data cable during normal operation.
- The CrowPanel will run from its own rechargeable battery; USB is used only for charging, initial programming and wired recovery.
- Wi-Fi credentials and a unique ATLAS pairing identity will be stored securely during commissioning.
- At power-on, the panel must automatically join the ATLAS control network, discover the Jetson gateway, authenticate, synchronize current state and open the dashboard without operator setup.
- The interface must clearly show `CONNECTING`, `ONLINE`, `DEGRADED` or `OFFLINE` and the measured link quality/latency.
- After a temporary outage it must reconnect automatically and resynchronize telemetry, but it must not resume an interrupted motion command.
- The panel must enter read-only/offline mode and command zero velocity whenever its heartbeat is lost.
- A local setup screen will allow authorized replacement of Wi-Fi credentials without reflashing firmware.

For dependable use away from the home router, ATLAS should provide a dedicated WPA2/WPA3 control access point. If the Jetson's primary Wi-Fi interface must remain connected to another network, use a separate supported USB Wi-Fi adapter for the private controller link. Tailscale remains useful for the Jetson but is not the primary CrowPanel transport.

## Responsibilities

The CrowPanel will provide:

- Touch and optional physical-joystick manual driving
- Camera pan/tilt and AI controls
- Mapping, navigation-goal, map-save and return-home controls
- Rover camera view with a lightweight AI overlay
- LiDAR, RD-03D radar and ultrasonic awareness views
- AMG8833 8x8 thermal view and environmental graphs
- BMS, power, GPS, cellular, CPU, GPU, RAM and temperature telemetry
- Encoder, odometry, IMU, service-health, fault and filtered-log views
- Voice input, audible alerts, microSD logging and OTA firmware updates
- Local camera functions such as operator recognition, QR setup and video communication

The Jetson will remain the authority for:

- Motor control and command multiplexing
- Emergency-stop and obstacle-safety enforcement
- ROS 2, SLAM, localization, Nav2 and mission execution
- AI inference using the rover IMX708 camera
- Hardware drivers, diagnostics and autonomous recovery

## Safety requirements

- Wireless motion commands must use `/cmd_vel_teleop` through the existing command mux.
- A 250-500 ms command watchdog must stop the rover after link or command loss.
- Touch driving must require a held dead-man control.
- Dangerous commands must require hold-to-confirm.
- The physical rover emergency stop must remain independent of Wi-Fi and the CrowPanel.
- The panel must never write directly to the motor controller or bypass the Jetson supervisor.
- Maintenance access must be authenticated and limited to approved operations; no unauthenticated shell or back door is permitted.
- ATLAS must continue its safe core operation when the panel is powered off or disconnected.

## CrowPanel features to retain

- 1024x600 IPS capacitive touchscreen
- ESP32-P4 processing and wireless companion module
- Wi-Fi, Bluetooth, USB, UART, I2C and GPIO
- Camera, microphone, audio output and backlight control
- microSD storage and battery charging support

## Installation-day checklist

1. Photograph the package label, panel PCB, camera module and every supplied cable.
2. Confirm the exact model number, camera sensor, voltage requirements and connector orientation.
3. Do not connect power until polarity and voltage are verified.
4. Bench-power the panel separately from the rover and confirm its factory demonstration.
5. Record the factory firmware version and save available vendor examples.
6. Test touchscreen, camera, microphone, speakers, Wi-Fi, Bluetooth, microSD and battery charging.
7. Join the ATLAS Wi-Fi network and measure stable range and latency.
8. Power-cycle both devices and verify automatic discovery, authentication, dashboard restoration and reconnect after a forced Wi-Fi interruption.
9. Begin with a read-only telemetry page; do not enable motion commands first.
10. Add watchdog-protected manual control only after telemetry and disconnect behavior pass.
11. Design the enclosure, battery, physical joysticks, dead-man trigger and separate emergency-stop hardware after electrical validation.

## Initial software phases

1. Hardware validation and reproducible firmware build
2. Secure Jetson telemetry gateway and connection indicator
3. Overview, sensor, camera and diagnostic pages
4. Camera/gimbal and non-motion controls
5. Watchdog-protected manual drive controls
6. Mapping, navigation and mission controls
7. Local camera, voice, logging and OTA functions

## AI/MCP companion interface

The Jetson also provides `project_atlas/scripts/atlas_mcp_server.py` for a
trusted local AI client. MCP and CrowPanel commands converge only at the
commissioned ROS mission controller and command mux. Neither interface may
open the Yahboom serial device or publish to the motor driver directly.

The default MCP commissioning profile is read-only plus stop actions. Mapping
and return-home remain locked until `ATLAS_MCP_ENABLE_MOTION=1` is deliberately
set after status, camera, link-loss and emergency-stop tests pass. Every
motion-capable call additionally requires an explicit clear-area confirmation.
