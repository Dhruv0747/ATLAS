# ATLAS web commissioning audit and staged implementation

Audit: 2026-09-20. Fetched origin; main and working branch base both 6d8f5c0.
Existing uncommitted USB identity changes are preserved, not part of this work.

## Current authority (repository + live units inspected)

| Area | Current implementation / interfaces | Conflicts and limitations |
|---|---|---|
| Web | `atlas_status_web.py`, `rover-status-web.service`, port 8088; existing ROS cache and `atlas_web_diagnostics.py` | Not atlas-status-web.service. Reuse HTTP server; no second dashboard process |
| Drive | teleop → `/cmd_vel_joy` → `atlas_cmd_vel_mux.py` → `/cmd_vel` → `yahboom_base.py` → Rosmaster serial | Individual motor test requires new owner-side mode; never open serial from HTTP |
| Mapping | `atlas_encoder_selection.WHEEL_NAMES`: M1 rear-left, M2 rear-right, M3 front-left, M4 front-right | Old `motor_config.yaml` describes ST3215/Waveshare, NOT current drive. Old encoder YAML locations are outdated |
| Encoder | `/yahboom/encoder/m1..m4`, `/atlas/encoder_health`; M4 excluded, navigation_validated false | Constants in current base driver are live scale source; scales predate replacement motors and need measured verification |
| Steering | Yahboom PWM IDs front 2/rear 1; centre 90/90; front 50..121, rear 64..134 | `/steering/*_angle_deg` is commanded servo angle, not physical feedback. Driver interface accepts integer angle, not microsecond jogs. Old standalone calibration utility has obsolete IDs and must not be launched by web |
| Camera | Existing JPEG `/camera.jpg`; UNO owner `ultrasonic_arduino_bridge.py`; `/camera/{bottom,second}_servo_cmd_us` | PCA reported pulse is NOT measured angle. Joystick/tracker/web share commands; exclusive commissioning lease not implemented. No new encoder pipeline |
| IMU | IM10A `/im10a/dashboard_json` and unvalidated IMU; Yahboom `/imu/data` retained | Current EKF has wheel odometry, no imu0. IM10A monitoring only, mounting/bias/dynamic validation pending. Magnetometer raw values are not microtesla |
| Distance | UNO front/rear live, left/right disabled in current USTAT; LiDAR `/scan`; radar `/radar/targets` | Live does not imply accuracy. Front range jumps seen in stationary test. Radar slots are not permanent person identities |
| GNSS | Hiwonder USB, `/gps/receiver_status`, `/gps/diagnostics`, fix data | NMEA live without fix is not indoor positioning. SIMCOM GNSS label in diagnostic unit list is obsolete |
| Storage | Driver constants, YAML files, camera environment overrides, JSON calibration files | No single authoritative runtime-write calibration format yet. New observation records must NOT rewrite any of these |
| Safety | Mux priorities, joystick-loss/B latched stop; `/atlas/voice/stop` Empty reuses latch; base timeout .45s; web watchdog .35s | Existing web e_stop only publishes web zero and is not an exclusive commissioning interlock. Must not treat as proof of ownership |

## Implementation architecture and order

1. Same-server `/commissioning`: lightweight subsystem cards/pages, cached ROS
   snapshots, command/measured/estimated labels, configuration source hashes.
2. Non-motion hardware check; bounded 10-second stationary IMU/GNSS observation,
   distance comparison; bounded SQLite result history and export. No calibration
   change, no direct serial access, no ROS sensor-rate increase. Current settings
   are read/exported, not falsely marked verified or writable.
3. Add a lease in the existing mux/base and UNO camera owner before actuator
   controls. Require explicit operator entry, stopped rover, session identity,
   physical lift confirmation for per-wheel tests, monotonic heartbeat expiry,
   sequence checking, remote stop priority and stop-before-release. Do NOT auto
   resume autonomous missions. Test owner death, browser loss and restart first.
4. Steering: owner accepts bounded integer-angle jogs (not fake 1-us precision),
   independently persisted asymmetric endpoints and direction. Camera: same
   owner architecture with real microsecond units and existing JPEG.
5. Motor/encoder: owner-side individual bounded PWM/duration; channel/sign checks,
   measured distance workflow, explicit reviewed calibration save. Never bypass
   encoder exclusions or autonomy gates to make a test pass.
6. Unify calibration loaders in the existing owners; atomic versioned saves,
   per-subsystem restore, rollback, restart persistence. No writes until loaded
   authoritative format and range validation are commissioned.

## First increment scope

Read-only pages + non-motion observations only. Actuator commissioning, applied
calibration saves/restores, and physical PASS are explicitly unavailable. The
console exposes this limitation in the UI and rejects unsupported actions.
Latched drive-stop uses the existing stop topic; no reset is offered here.

Validation gates remaining: authenticated actuator lease, timeout/disconnect
fault injection, physical steering/camera ranges, low-speed encoder tests,
calibration reload/reboot and measured browser-open/closed resource comparison.
Do not call the full requested commissioning project complete after increment 1.
