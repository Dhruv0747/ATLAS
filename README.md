# Project ATLAS - Autonomous Service Rover

### Ultrasonic validity increment — installed; stationary follow-up open (2026-09-20)

The installed UNO firmware adds atomic sample sequence/age reports; bridge, mux
and the read-only capability view consume `/ultrasonic/validity`. Legacy ONLINE,
no echo, stale/default ranges cannot grant directional safety validity. Existing
LiDAR, manual remote, B-stop/reset, encoder exclusion and autonomy locks remain.
Firmware upload and the paired Jetson deployment succeeded after the operator
entered the bootloader. A subsequent operator power cycle verified autostart and
fresh front/rear ultrasound, BME680, AMG8833, PCA9685 and decoded radar telemetry.
Manual-only, latched stop, zero velocity and M4 exclusion remain unchanged.

Stationary observation exposed intermittent serial-backlog rejection. After
renewed motor/servo-power-OFF confirmation, two narrow bridge corrections were
installed: distinguish a partial next line from complete backlog, and drain
newly arrived bytes within the existing bounded processing cycle. Jetson staging
passes **112/112 offline checks**. No further firmware flash or safety-limit
change was needed. Physical sensor/stopping qualification remains pending; fresh
telemetry is not autonomous permission. See [live results, limitations and
remaining tests](docs/ULTRASONIC_VALIDITY_2026-09-20.md).

Final passive 120-second window: **421 valid front/rear reports, 3 fail-closed
backlog events, zero parse errors/reconnects**. This is improved communication,
not fault-free certification. No motor/servo movement test was run.

Follow-up stationary check: a software communication pause correctly expired
front/rear readings and the commissioning view marked them stale; data returned
after resume. The earlier 50 cm reference was a communication misunderstanding,
not verified ground truth. The operator subsequently confirmed the observed
ultrasonic clearances of approximately **1.35 m front / 0.24 m rear** as plausible.
A simultaneous 20-second comparison measured LiDAR clearance near **2.45 m front /
0.31 m rear** after applying the existing footprint. Different origins, heights
and beam geometry prevent treating those values as interchangeable.

A further 120.15-second passive run produced **418 valid front/rear reports,
6 fail-closed backlog events and zero parse errors**. Ultrasound remains a
secondary close-range source; LiDAR remains primary. Controlled stopping is the
remaining ultrasonic safety test.
The front sensor has now passed stationary close-range screening: all 15 fresh
samples at an operator-set 30–35 cm target measured 31.7–33.2 cm (median 32.8 cm).
It is qualified only for the intended secondary close-range role; the variable
long-range response is advisory. No scale factor or safety limit was changed.

The rear sensor also passes the intended secondary close-obstacle role, with an
accuracy limitation. At an operator-confirmed 30–35 cm target, the first window
measured 28.6–30.7 cm (median 30.6 cm) and the repeated window measured
27.2–28.2 cm (median 28.1 cm). The conservative short bias can trigger warning
earlier. After target repositioning, a confirmation window placed all 15 samples
inside 30–35 cm, measuring 30.1–31.1 cm (median 31.1 cm). Rear close-obstacle
detection passes; this is still not full-range precision. LiDAR remains authoritative.

Physical rear disconnect/reconnect now passes fail-closed behavior. Disconnect
changed rear from valid 31.6 cm to fresh `NO_ECHO` with no retained range while
front stayed valid and motion remained zero. Reconnect created a new sensor-stream
identity and automatically restored fresh rear readings. A subsequent 30.14-second
direct ROS check recorded 102 valid front/rear reports, one fail-closed backlog
report and zero parse errors; rear remained 31.0–33.7 cm. One dashboard request
timed out during recovery, but the direct sensor stream was healthy.

The isolated directional-veto suite also passes **38/38** on Windows and Jetson
staging. Close, missing, stale and no-echo directional data block the applicable
autonomous command. This is logic validation only; the physical stopping-distance
test remains blocked by the existing encoder/autonomy ground-validation gate.

### Capability-aware fallback — read-only first increment, 2026-09-20

Open `/commissioning` → **Sensor authority & fallback readiness** for configured
sensor roles, live cached data age, evidence status and blocked capabilities.
This reuses the existing cache/ledger: no new driver, fusion or control path.
Camera VO is NOT AVAILABLE; IM10A corrected gyro Z is fused as the EKF yaw-rate
source; magnetic heading remains excluded; M4 feedback remains excluded.
No alternate profile or automatic goal resumption is approved. See the
[ordered remaining-work list, audit and safety boundary](docs/CAPABILITY_FALLBACK_WORK_PLAN_2026-09-20.md).

### Phase 2: evidence and next-step commissioning — 2026-09-20

On `/commissioning`, use **CONTINUE ATLAS COMMISSIONING** to open the next
unresolved gate. It never starts motion. The same SQLite database now retains
scoped test evidence, explains retests after relevant changes, and preserves
valid results across restart. Old telemetry checks do not become physical PASS.
Steering has explicit **RECORD VERIFIED FRONT/REAR SAVED RANGE** controls after
the operator physically verifies and saves through the existing motor owner.
No navigation, encoder-selection, camera-home or IMU-fusion setting is changed.
This is the first bounded Phase 2 increment, not completion of all physical or
fallback work. See [audit, remaining gates and validation](docs/COMMISSIONING_PHASE2_2026-09-20.md).

Camera startup home selected by user on 2026-09-20: pan **1725 µs**, tilt
**1500 µs**. UNO reconnect/startup, web Home, tracker and mission defaults match.

Commissioning Camera page now includes manual left/right/up/down one-tap controls,
25/50/100 µs steps and return to configured home. It reuses the existing camera
owner, stale-controller gate and pulse bounds; it does not set a new boot home.

Steering Master Reset discards unsaved marks only: it preserves saved
calibration, target positions and traction inhibition. The diagram uses live
owner-saved centres; it cannot measure hand-moved wheel positions. PWM servo
torque release is not verified and no UART torque-off command is used.

Steering diagram correction (2026-09-20): top-view wheel rotation now uses
counterclockwise SVG rotation for increasing/left servo commands. This is a
display-only correction, not a change to motor direction or physical feedback.

### Manual steering commissioning — deployed 2026-09-20

Front-left calibration travel is now bounded at 126° (previously 121°).
The normal operating endpoint remains unchanged until the operator marks and
saves a verified limit. Rear and right-side bounds are unchanged.

The commissioning **Steering** page now has independent front/rear 1°/5°
command jogs, mark centre/left/right, explicit permanent save, and exit to saved
centres. It requires the new motor owner online, a fresh latched drive stop and
operator confirmation that wheels are lifted. Browser loss freezes adjustments
after 1.5 seconds and keeps traction inhibited. Re-enter then explicitly exit;
the page never resets the drive stop. Existing endpoint envelopes cannot be
expanded here. Servo command degrees are not physical tyre-angle feedback.
Calibration lives in `project_atlas/config/steering_calibration.json` and is
loaded by the motor owner at startup. Do not edit it while the owner is running.
Web controls and motor owner deployed after lifted-wheel confirmation. Live
enter/timeout/re-enter/exit verified with centres unchanged and stop latched.
Physical jog directions/ranges and operator calibration remain to be checked.

### Commissioning console — 2026-09-20 (first increment)

Open `/commissioning` on the existing dashboard server, or use its
**COMMISSIONING / HARDWARE CHECK** link. Live subsystem pages distinguish
commanded, reported and calculated values. Non-motion hardware checks and
bounded IMU/GNSS/distance observations have persistent result history.
Actuator commissioning and calibration writes remain locked: an exclusive
owner-side control lease and physical verification are still required.
See [plan](docs/WEB_COMMISSIONING_PLAN.md) and
[validation report](docs/WEB_COMMISSIONING_VALIDATION_2026-09-20.md).

### Front ultrasonic — 2026-09-19

UNO R4 front TRIG D2 / ECHO D3 is enabled by the sensor-hub
`front-ultrasonic.conf` drop-in and reapplied after USB reconnect. This enables
telemetry only; navigation qualification and safety policy are unchanged.

### Steering neutral — 2026-09-18

User-requested servo neutral is now front **90°**, rear **90°** (previously
91°/89°). Existing endpoint limits are unchanged. Commanded neutral is not proof
of physical wheel alignment; straight-ground driving needs revalidation.

### On-demand local companion — 2026-09-18

Added a stopped-only, read-only local conversation backend with automatic model
unloading and explicit resource limits. Existing deterministic telemetry replies,
remote emergency stop, navigation gates and cloud fallback are preserved. The
local model has no action tools or motor-command path. Voice recognition still
needs internet; this is **not a fully offline voice assistant**.
See [installation, current deployment evidence and limitations](docs/LOCAL_LLM_2026-09-18.md).

### Audit-driven reliability repairs — 2026-09-17

The recovery monitor now parses complete encoder-health JSON instead of treating
truncated messages as faults. Motor-link recovery additionally requires fresh,
sustained zero commands and a fresh latched stop. A fresh, explicitly degraded
three-encoder report is not a serial failure or permission for autonomous driving.
The agent role board now distinguishes communication from autonomous readiness.

“Hey ATLAS” alone now gets a cached local English/Hindi acknowledgement after
recognition. Cloud speech recognition is **still required**; that September 17
repair did not install a local LLM or offline wake-word recognizer. Empty/ignored recordings clear the
transcription stage, and microphone privacy is rechecked before playback.

Visual Cloud now receives retained maps/static-TF after late startup and labels
these snapshots `CACHED`, not live traffic. Its map overlay remains a preview:
map/odom/scan frame alignment and a complete buffered TF tree are still pending.
No navigation tuning, wheel motion, IMU fusion or encoder qualification changed.
See [deployment evidence, limits and local-LLM decision](docs/AUDIT_REPAIRS_2026-09-17.md).

### Three-encoder commissioning — 2026-09-17

M1 rear-left, M2 rear-right and M3 front-left are selected for odometry in
`project_atlas/config/encoder_selection.yaml`. Faulty M4 front-right feedback
is excluded even if it reports counts again; **its motor still operates**.
Three healthy encoders can support autonomous navigation. Four are not a Nav2
requirement, but this changed configuration needs measured distance, turn and
stopping validation before `navigation_validated` may be enabled. Existing
manual-only restrictions and remote stop remain in place. IM10A live EKF fusion
has not been enabled by this change.

Fresh packet age is checked separately from unchanged counts at rest. M4 raw
counts remain diagnostic and are labelled excluded in the dashboard. A fault
in another selected channel or loss of shared feedback blocks autonomy.
Odometry uses per-wheel increments, avoiding cumulative-position jumps when
channels are rejected/reintroduced; rejected intervals do not catch up later.
Steering-based yaw and existing encoder scales remain provisional after motor
replacement. See [commissioning status](docs/THREE_ENCODER_COMMISSIONING_2026-09-17.md).

### Intercom audio and camera USB recovery — 2026-09-17

Intercom playback now sends only valid PCM samples, excluding PyAV plane padding.
The UNO native sensor-hub driver no longer mistakes its CMSIS-DAP debug interface
or another USB ACM device for the sensor application. Dashboard camera commands
require fresh online controller telemetry; an offline report is not a healthy
heartbeat. See [repair evidence and limitations](docs/INTERCOM_CAMERA_REPAIR_2026-09-17.md).

### Voice companion: useful, truthful status — 2026-09-17

- Say **“Hey ATLAS, battery status”**, **“Hey ATLAS, encoder status”**,
  **“Hey ATLAS, IMU status”**, **“Hey ATLAS, why are you stopped?”**, or
  **“Hey ATLAS, बैटरी कितनी है?”**. Answers use fresh local telemetry;
  recognition of the spoken question still requires cloud transcription.
- Local Piper English/Hindi speech provides startup and bounded automatic
  alerts without cloud TTS. Startup distinguishes voice-online from drive-ready;
  it greets Dhruv once per OS boot, not after every USB reconnect/intercom call.
- Announcements cover BMS low charge, high SOC with a charger-verification
  disclaimer, newly stale LiDAR/IM10A/encoder data, remote-stop latch, and
  allowlisted mission events. A ready encoder link at rest is **not** proof
  that every wheel encoder works. No imagined arrival or map completion.
- Dashboard **ATLAS COMPANION → MUTE AI MIC / ENABLE AI MIC** controls a
  persistent software capture mute. The live acknowledgement is shown below
  the LED legend; stale status is explicitly unknown. This is not a physical
  mic disconnect. TALK / LISTEN is a separate explicit intercom session.
- Blue = voice idle, green = capture, white = processing/buffering, pulsing
  blue = speech. Red also represents software mute or a live call, so read
  the dashboard state; colour alone is not a fault diagnosis.
- Wake phrases are checked **after** cloud transcription; active voiced clips
  can leave the device before a wake phrase is recognized. Mute discards new
  microphone audio on the Jetson; an already-sent request cannot be recalled.
  Speech is AI-generated. The current firmware has no physical privacy-mute
  button; Key2 long-press retains its existing shutdown function.
- Voice stop requests use stop-only `/atlas/voice/stop` and latch the existing
  command mux stop. **Remote B remains the immediate stop**; speech recognition
  is not a safety-rated emergency stop and may need Internet. Voice cannot
  reset the latch. Existing neutral/LB-hold/release remote reset is unchanged.
- Wheel-driving voice actions remain uncommissioned by default
  (`ATLAS_VOICE_MOTION_ENABLED=0`). Even if separately commissioned, fresh mux
  policy, no remote latch, autonomous readiness and encoder health are required;
  existing safety and manual-only restrictions cannot be bypassed.

Tests: `python3 -m unittest discover -s project_atlas/scripts -p test_voice_status.py`.
`verify_voice_stationary.py` synthesizes both languages with HTTP calls forbidden
and observes status/command topics; it publishes no goals or velocity commands.
This feature changes no navigation parameters, IMU authority, or camera firmware.

### IM10A isolated EKF comparison — 2026-09-17

`project_atlas/scripts/atlas_im10a_shadow_test.py` runs a bounded 60-second
wheel-only versus wheel-plus-gyro comparison in `/atlas_imu_shadow`.
Both filters disable TF publication; live `/odom` and its EKF configuration
are unchanged. Only gyro Z is selected; magnetic/Euler heading, acceleration
and the disabled historical bias correction are not used. Stale, invalid or
non-increasing IMU messages are rejected. The test stops its own filters on
exit and saves results outside Git. It is not an autostart service and does
not qualify ATLAS for autonomous operation with the faulty M4 encoder.

### Camera remote — 2026-09-17

D-pad left/right pans and up/down tilts the camera; Y returns it to saved
home (pan 2300 us, tilt 1500 us). LB is not required for camera operation.
Camera commands use a 40 ms minimum interval and only transmit changed axes;
actual responsiveness depends on joystick delivery, the hub and servo speed.
Held movement uses bounded 400-us/s increments, and delayed hub reports are
ignored during an active hold, including at the configured servo limits.
The hub uses bounded batch reads instead of one serial line per 50 ms.
`/arduino/serial_diagnostics` exposes unread USB/parser bytes and processed
line counts. Old pulse reports cannot overwrite a newer unacknowledged target,
even between button presses. Reported pulses are not physical servo feedback.
B is exclusively the rover stop and suppresses camera input in that packet.
Manual camera input pauses automatic camera tracking. Existing 700–2300 us
limits are preserved; no wheel commands are published by this node.
Only `atlas-camera-joystick.service` runs; duplicate `atlas-camera-remote.service`
is disabled. Five mapping tests passed; physical directions need user confirmation.

### Manual commissioning and remote software stop — 2026-09-17

Remote and motor services are enabled at boot. Mux startup is latched stopped:
Xbox B (verified button index 1) latches a zero-output stop for every mux source.
Missing joystick messages for 0.5 s also latch stopped. Releasing B does not
restart motion. Release all buttons and centre sticks, hold LB alone for
2 seconds, then release it to reset. Press LB again with deliberate stick
input to drive. All other buttons must remain released throughout; stick
movement, B, RB or a message gap cancels the gesture. LB is verified Xbox
joystick index 4 (`remote_reset_button`). The complete physical reset gesture
still requires operator verification; the earlier Start/Menu reset was replaced.
Alternatively, after one second fully neutral, deliberately call
`/atlas/remote_stop/reset` (`std_srvs/srv/Trigger`).
Hold LB to drive; release LB to stop manual drive. This software stop is NOT
a substitute for an independent physical motor-power emergency switch.

Live deployment uses `40-manual-commissioning.conf` with
`ATLAS_MANUAL_ONLY=1`: non-REMOTE sources are rejected while commissioning
continues. The passive encoder observer is disabled to avoid serial contention;
the normal base driver publishes feedback. The former commissioning condition
file was retained as `.conf.disabled` and backed up, not deleted. M4 encoder
and rear ultrasonic reliability remain unresolved; autonomy is not released.
Ten stop-state unit tests and live zero-output startup observation passed.
Physical button-to-wheel stopping and remote motion still require operator
validation. No powered movement test was issued as part of this deployment.

### Wheel mapping — 2026-09-17

Steering centres are front 91 and rear 89 (visually confirmed). Steering
limits are unchanged and require checking relative to the new centres.

Confirmed controller order: M1 rear-left, M2 rear-right, M3 front-left,
M4 front-right. Forward PWM signs are `[-,+,-,+]`; validated encoder forward
signs for M1–M3 are `[-,+,+]`. M4 encoder remains faulty/unvalidated. Updated
driver mapping does not authorize driving: commissioning inhibits remain,
and previous metric encoder scales require revalidation after replacements.

### IM10A commissioning — 2026-09-16

The initial stationary bias passed a holdout check, but failed a later recheck
and is now disabled. Magnetometer and sensor Euler heading are diagnostics-only,
excluded from navigation. Sensor internal fusion mode was not changed. Gyro
fusion remains disabled pending measured-turn validation. See
[bias recheck](docs/IM10A_BIAS_RECHECK_2026-09-16.md) and
[turn review](docs/IM10A_TURN_REVIEW_2026-09-17.md).

Hiwonder GPS is now the primary live GPS. IM10A and passive four-channel encoder
monitoring are deployed with autostart and dashboard data. **IMU/navigation
fusion and driving remain inhibited pending physical commissioning.** USB paths
are socket-specific; keep devices in their assigned sockets. See
[commissioning report](docs/IM10A_COMMISSIONING_2026-09-16.md).

### Automatic networking — 2026-09-15

`atlas-network-fallback.service` prefers home Wi-Fi Internet, selects SIM8230G
RNDIS Internet after repeated Wi-Fi failures, and activates **ATLAS-Rescue** if
both Internet checks fail repeatedly. The local-only rescue dashboard is
`http://10.42.0.1:8088/`. Its WPA2 password is provisioned on the Jetson only;
no password is stored in this repository. The normal dashboard NETWORK panel
shows the mode, per-interface Internet checks and hotspot state.
The AP's captive portal opens the dashboard through a supported phone's Wi-Fi
login prompt; tap **Sign in to network** if it does not open automatically.
Direct local links still work. No Internet or automatic motion is implied.

The single radio cannot be a Wi-Fi client and AP simultaneously. Rescue clients
are not disconnected for automatic Wi-Fi recovery; with no clients, home Wi-Fi
is retried every three minutes. See [network setup and test record](docs/NETWORK_FALLBACK_2026-09-15.md).

### Main operator diagnostics — 2026-09-15

Use `http://100.87.208.71:8088/` (Tailscale) or `http://192.168.1.14:8088/`
(current LAN address). **DIAGNOSTICS / LOGS** opens the read-only workbench:
current service state, restart counters, current-boot logs, searchable telemetry,
last-update age, observed callback rates, USB identities and JSON snapshot export.
Visual Cloud remains linked for the ROS graph and mission history. Service state
does not prove sensor validity; a stationary encoder heartbeat is not a motion test.

GNSS now separates communication, satellites in view and position fix. Zero-count
GSV sentences no longer create misleading "DETECTED" bars. `/gps/diagnostics`
identifies the current SIM8230G USB receiver, stale data and serial reconnects.
EOF, changed USB identity and sustained silence reopen only the NMEA reader;
they do not reset the modem, network, motor board or navigation stack.

The unused legacy HDMI dashboard has `Hidden=true`, autostart disabled, and its
generated user unit masked on Jetson. Source remains available as a manual fallback.
The web dashboard and GNSS service remain enabled at boot. Do not expose port 8088
to the public Internet; use the private LAN or Tailscale. See
[deployment and test notes](docs/WEB_DIAGNOSTICS_2026-09-15.md).

### Primary GPS — 2026-09-15

SIM8230G USB GNSS now supplies the existing `/gps/*` topics. The disconnected
L76K/J12 receiver is no longer selected by `atlas-gnss.service`. The NMEA port
uses its USB by-id identity (interface 03), and `atlas-sim8230-usb.service`
restores the option driver binding at boot. Dashboard labels follow this source.
Deployed and built on Jetson; live checksum-validated NMEA verified, but zero
satellites and no position fix at commissioning. Position accuracy remains unverified.

### Steering commissioning checkpoint — 2026-09-09

Physical front steering is Yahboom channel 2, with user-confirmed lifted center
81 degrees. Physical rear is channel 1, with user-confirmed lifted center
114 degrees. Both centers are saved in the boot-enabled base driver.
Front-right operating limit is 50 degrees, approved by the user after the
lifted 81 -> 50 -> 81 test; this is not a measured mechanical hard stop.
Front-left operating limit is 121 degrees, approved after the lifted
81 -> 121 -> 81 test. Rear-right operating limit is 64 degrees, approved after
the lifted 114 -> 64 -> 114 test. Rear-left operating limit is 134 degrees,
approved after the lifted 114 -> 134 -> 114 test. These are user-approved
servo command limits, not measured wheel angles or mechanical hard stops.
Front/rear software labels were corrected while
retaining the existing numeric endpoint envelope per channel. Do not infer that
turn directions, endpoints or ground drift are validated; keep commissioning
lifted until directional checks are complete. Older standalone
steering test scripts may contain obsolete channel/center constants; do not run
them without reviewing them against this checkpoint.

## Secure live-call intercom

ATLAS now has mutually exclusive AI Voice and on-demand WebRTC Live Call
modes. A live call requests browser echo cancellation/noise suppression, turns
the ESP32 speaker LED red, and automatically returns USB audio ownership to the
AI companion when the call ends. The server binds to loopback and must be
published only through authenticated Tailscale HTTPS—not the public Internet.

**Creator: Dhruv Kaushik**

Project ATLAS is an open robotics development project for a four-wheel autonomous service rover. It runs ROS 2 Humble on Ubuntu 22.04 with an NVIDIA Jetson Orin Nano Super 8GB and combines LiDAR SLAM, Nav2 autonomous navigation, wheel odometry, IMU sensor fusion, bounded recovery behaviours, AI vision, voice control, Foxglove, and wireless dashboards.

The Jetson web command center uses a 70%-transparent glass interface. Its live
camera automatically reconnects after a stalled frame request, and the hardware
panel performs a post-boot and continuous health evaluation of sensor feeds,
including individual M1 front-right, M2 front-left, M3 back-right, and M4
back-left encoder message age and count readings.

This repository is the searchable engineering record for ATLAS: ROS 2 source code, launch files, robot parameters, hardware integration, safety controls, autonomous mapping, recovery logic, diagnostics, operating documentation, and commissioning evidence.

The read-only [ATLAS Visual Cloud](docs/ATLAS_VISUAL_CLOUD.md) integration adds
an authenticated ROS graph/traffic agent, historical API and real-time browser
view. It has no cloud-to-velocity or cloud-to-motor interface; all safety and
control authority remains local on the Jetson.

**Search terms:** Project ATLAS rover, Dhruv Kaushik, autonomous rover, ROS 2 Humble, Jetson Orin Nano Super, Nav2, SLAM Toolbox, Explore Lite, LiDAR mapping, Ackermann steering, service robot, autonomous navigation, robot recovery, Foxglove, MCP robotics.

## Current autonomy maturity

- Core navigation foundation: operational with ROS 2, Nav2, LiDAR SLAM, encoder odometry and IMU/EKF fusion.
- Deterministic recovery: implemented for no-progress detection, LiDAR-validated bounded reverse, costmap clearing and replanning.
- Autonomous mapping: functional and under controlled endurance testing.
- Current engineering gate: repeatable TF/odometry reliability and 20/20 controlled dead-end recovery trials.
- Unattended operation is not yet approved; ground tests require a clear area and an operator at the physical emergency stop.

ATLAS uses its 360-degree LiDAR as the primary navigation and obstacle sensor. Ultrasonic sensors provide close-range secondary protection. AI may select high-level goals, but it cannot bypass the deterministic command mux, watchdog or emergency stop.

## Hardware

- Four-wheel rover with wheel encoders and Yahboom motor controller
- RPLIDAR A1, calibrated Yahboom motor-board IMU, ultrasonic sensors, and
  RD-03D radar
- Arduino UNO R4 WiFi sensor hub carries the I2C sensors, RD-03D radar,
  camera PCA9685, and four sequentially sampled ultrasonic channels.
  See [`firmware/atlas_uno_r4_i2c_hub/README.md`](firmware/atlas_uno_r4_i2c_hub/README.md).
- The L76K GNSS uses the Jetson J12 UART directly: L76K RX to header pin 8
  (TX), L76K TX to pin 10 (RX), and common ground; Linux exposes it as
  `/dev/ttyTHS1` at 9600 baud.
- IMX708 Camera Module 3 on a pan/tilt platform
- GNSS, BMS, BME680, AMG8833 8x8 thermal sensor, Wi-Fi, and cellular connectivity
- Jetson onboard INA3221 power telemetry; the removed external INA219 and Pi
  UPS HAT are not part of the commissioned system.

The commissioned sensor transport now uses an Arduino UNO R4 WiFi. It forwards
the PCA9685 (`0x40`) discovery state, BME680 (`0x76`/`0x77`), AMG8833
(`0x68`/`0x69`), RD-03D frames and four
ultrasonic ranges over a fixed Jetson USB physical path. The Jetson bridge
republishes the original ROS 2 topic names, so Nav2, EKF, dashboards and
Foxglove do not depend on the physical bus.

The local web dashboard also consumes a small atomic UNO snapshot as a
read-only fallback when DDS discovery is delayed during simultaneous service
restarts. Fresh ROS messages always take precedence; the fallback carries no
control commands and cannot affect motor or navigation safety.
- ESP32-S3 voice interface and 11-inch touchscreen dashboard

The web Command Center includes both a conventional 2D RD-03D radar scope and
a lightweight **3D PEOPLE** digital-twin view. The latter places up to three
avatars using live radar X/Y coordinates, distance and speed. It is an operator
visualization, not a depth-camera body scan, and it does not alter navigation or
motor commands.

## Mobile notifications

ATLAS can notify Dhruv's Android or iOS phone through the ntfy app when the
rover boots, when the main DALY BMS reaches 20%, and when charging remains at
99% or higher for three consecutive BMS readings. Alert state includes
hysteresis to avoid repeated notifications near a threshold. Notification HTTP
work runs in a separate worker and cannot block ROS motion control.

On the Jetson, run:

```bash
bash /home/jetson/project_atlas/scripts/setup_mobile_notifications.sh
```

Install the ntfy app on the phone and subscribe to the private random topic
printed by the setup helper. The private topic is stored only in
`~/.config/project-atlas/notifications.env`; it must not be committed.

## Planned wireless controller upgrade

The broken 11-inch Jetson-connected display will be replaced by a removable 10.1-inch CrowPanel Advanced ESP32-P4 HMI with its optional camera. It will operate as ATLAS's wireless dashboard and manual controller while the Jetson remains responsible for motors, safety, ROS 2, navigation and AI. See `docs/CROWPANEL_WIRELESS_CONTROLLER.md` for the approved architecture and installation checklist.

## Repository layout

- `project_atlas_ws/src/`: ROS 2 packages and launch/configuration files
- `project_atlas/scripts/`: operational nodes, dashboard, diagnostics, voice, and recovery tools
- `project_atlas/config/`: robot configuration
- `project_atlas/maps/`: current mapping assets

## Citation and authorship

Project ATLAS was created by **Dhruv Kaushik**. Academic papers, articles and derived projects should cite the repository using the metadata in [`CITATION.cff`](CITATION.cff).

Suggested attribution:

> Dhruv Kaushik, Project ATLAS: ROS 2 Autonomous Service Rover, 2026.

## AI and MCP control

`project_atlas/scripts/atlas_mcp_server.py` exposes a small MCP interface for
status, sensors, camera snapshots, navigation stop, emergency stop, mapping and
return-home. It uses the commissioned Jetson gateway and ROS 2 mission/mux
interfaces; it never accesses the motor controller directly.

Motion-capable tools are locked by default. Commission status, sensor, camera
and stop behavior first. Only then set `ATLAS_MCP_ENABLE_MOTION=1` in the MCP
client environment while an operator has access to the physical emergency stop.
The MCP process uses stdio and must be launched by the trusted MCP client. It is
not a standalone systemd daemon or an unauthenticated network API.

Install its isolated dependency set with:

```bash
python3 -m venv /home/jetson/project_atlas/.venv-mcp
/home/jetson/project_atlas/.venv-mcp/bin/pip install \
  -r /home/jetson/project_atlas/requirements-mcp.txt
```

Generated ROS directories, local environments, models, logs, credentials, and historical backups are intentionally excluded.

## Engineering policy

Reliability and safety come before new capability. Implement one feature at a time, build and test it, update documentation, and commit it. Emergency stop must override manual, web, voice, and autonomous commands.

## Development baseline

1. Verify hardware diagnostics and TF.
2. Validate wheel odometry and IMU fusion.
3. Validate localization and Nav2.
4. Tune perception and human-aware behavior only after navigation is stable.

## Commissioned navigation baseline - 2026-08-06

The Jetson migration and primary navigation commissioning sequence are complete.

- Physical footprint: 0.50 x 0.36 m; Nav2 footprint is `[+/-0.25, +/-0.18]`.
- Costmap inflation radius: 0.28 m with cost scaling factor 15.0.
- Wheel order: M1 front-right, M2 front-left, M3 back-right, M4 back-left.
- Installed 125 mm wheels use independently calibrated encoder counts per revolution:
  M1 4048.7, M2 3300.6, M3 4080.1 and M4 2697.8.
- LiDAR centre is 0.30 m behind the front chassis edge, placing it 0.05 m behind
  `base_footprint`; the authoritative static transform is x=-0.05 m, z=0.18 m,
  yaw=pi.
- `/yahboom/odom` is encoder-distance-derived and is fused by the EKF onto `/odom`.
- The Yahboom motor-board IMU is the sole canonical system IMU and has a
  separately recorded stationary calibration.
  Raw controller measurements are available on
  `/yahboom/imu/data_uncalibrated`; software-zeroed attitude, gyro and
  accelerometer measurements are available on `/yahboom/imu/data_calibrated`.
  Its yaw is zeroed relative to each driver start because the controller's
  absolute magnetic origin is not yet trusted. The calibrated values also own
  the standard `/imu/*` dashboard, logging, and health topics. Gyro data is
  deliberately excluded from the EKF until a recorded
  clockwise/counter-clockwise yaw comparison against wheel odometry passes.
- Nav2 uses the one-shot fail-stop behavior tree. It does not accumulate recovery
  movement after a failed short goal.
- Explore Lite holds one frontier goal until completion, abort or genuine
  no-progress timeout. It no longer preempts goals as the frontier boundary moves.
- Exploration stop automatically saves `maps/atlas_latest.yaml` and
  `maps/atlas_latest.pgm`.
- Reboot/autostart verification passed for the base, sensors, SLAM, Nav2, command
  mux, remote, camera, AI, mission controls, Foxglove and dashboard. Autonomous
  exploration remains off after boot until explicitly requested.

Ground autonomous tests always require a clear area and an operator at the
physical emergency stop. The priority command chain remains REMOTE > WEB >
FOXGLOVE > NAV2, with stale-command stopping.

## Safety-constrained mission agent

`atlas_agent_supervisor.py` adds an observe-plan-act-verify layer above the
commissioned ROS 2 stack. It accepts natural mission requests on
`/atlas/agent/command`, creates a maximum four-step plan from a fixed tool
allowlist, publishes its operator-visible state, requires confirmation for
motion, rechecks live safety data, dispatches only high-level mission topics,
and verifies the resulting status. It never publishes velocity commands.

The service is commissioned in `MONITOR_ONLY` mode. In that mode cloud or
offline planning can be tested, but no physical action is dispatched. Runtime
execution can be enabled through `/atlas/agent/set_execution_enabled`; motion
plans still require `/atlas/agent/confirm_plan` and must pass the deterministic
LiDAR, odometry, SLAM, manual-control and battery preflight.

Useful interfaces:

- `/atlas/agent/state`, `/status`, `/plan`, `/decision`, `/response`: dashboard
  and Foxglove visibility
- `/atlas/agent/command` (`std_msgs/String`): natural mission request
- `/atlas/agent/confirm_plan`, `/cancel_plan`: explicit operator gate
- `/atlas/agent/set_execution_enabled`: monitor-only/active selection
- Persistent bounded event memory:
  `~/.config/project_atlas/agent_memory.json`

## Retired hardware

The Portenta H7, Mega 2560, BNO055/BNO08x, external INA219, Pi UPS HAT, and
old 11-inch wired display have been removed from the active source and Jetson.
Their history remains in `CHANGELOG.md`; they must not be reintroduced by an
installer or used as fallback sensor/control paths.
# Dashboard battery indicator

The web header now displays main DALY BMS percentage and net charging/discharging
state. Tap it for telemetry details. Missing or stale BMS data is explicitly marked;
the indicator does not substitute the motor-board voltage estimate.
# Dashboard shutdown

Use **SHUT DOWN** beside Diagnostics / Logs and confirm to power off the Jetson.
Wait for shutdown before removing power. Physical motor/battery power is separate.
This does not reboot or automatically power ATLAS back on.
# Remote startup dependency

`atlas-remote.service` is enabled under `default.target` but must not be ordered
after that target. Camera joystick units may start after the remote. An explicit
service stop is not automatically reversed by `Restart=always`.
