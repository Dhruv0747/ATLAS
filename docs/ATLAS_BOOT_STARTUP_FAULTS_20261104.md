# Boot startup faults and remaining boot CPU (2026-11-04, read-only analysis)

Boots: -1 bfa7996c (before), 0 33363f37 (after the optional-AI correction 5c2e9f6). No service, servo,
camera or config change was made for this analysis.

## Yahboom base exits once at boot: ROOT CAUSE
`rover-base-telemetry` -> yahboom_base.py `open_verified('yahboom')` (atlas_usb_identity.py 7cafcc21) takes the shared
flock `$XDG_RUNTIME_DIR/atlas-usb-discovery.lock` NON-blocking by design ("callers retry later"). The only other
user is atlas-im10a (`open_verified('imu')`, own 3 s retry). Both start at +17.6 s; Yahboom reached the probe at
+26.5 s while the IMU probe held the lock -> OSError "USB discovery busy; retry later" -> exit 1 -> systemd
Restart=on-failure (3 s) -> opened /dev/ttyUSB0 at +42.3 s, ready +44.8 s. Seen on boots -1 and 0; boot -2 opened
first time (race). Fail-closed and self-healing; cost ~2.4 CPU-s. No change made: Yahboom is on HOLD and the
existing restart is the designed retry.

## atlas-ptz-home I2C Remote I/O error: ROOT CAUSE
/etc/systemd/system/atlas-ptz-home.service (2026-07-25) runs /home/jetson/home.py (53699a34): PCA9685 at Jetson
I2C bus 7 address 0x40, first write (MODE1 sleep) NACKs -> Errno 121, on boots -1 and 0. The camera pan-tilt
PCA9685 is now driven through the Arduino UNO R4 hub over USB serial (ultrasonic_arduino_bridge.py,
camera_route 'Arduino UNO R4 PCA9685'; /atlas pca_status live: pca=1 cam1_us=2300 cam2_us=1500). Nothing answers
at bus 7/0x40. home.py is a stale July Arducam-on-header script; no ATLAS script or doc references it. It cannot
move anything. Bus 1 0x40 is the INA3221 (kernel-bound) - home.py must never be pointed there.
Optional owner action (sudo): `sudo systemctl disable atlas-ptz-home.service`; rollback `sudo systemctl enable ...`.

## Remaining boot CPU contributors (boot 0, measured; method stated)
Startup excess = cgroup total CPU-s - (steady rate over 20 s at ~815 s uptime x lifetime). Assumes a constant
steady rate; sum of positive excess 209.7 CPU-s.
- +16.7 s: ~45 ATLAS user services start together; each 4-10 CPU-s of startup (python/rclpy/DDS), none dominant:
  atlas-remote 9.7, mission-control 6.7, daly-bms 6.1, mode-manager 6.0, im10a 5.2, scan-filter 5.0,
  camera-joystick 4.9, radar 4.7, laser-tf 4.7, frame-bridge 4.6, lidar-odom-gate 4.3, ekfs 4.3/4.2, lidar 4.2,
  tight-recovery 4.1. Non-robot system: udevd 8.4, packagekit 5.9 (48.9 CPU-s total, 5.5 % one core steady),
  GitHub actions runner 5.0, polkit 4.1. This is the 16-64 s saturation.
- +60.6 s: atlas-localization (Nav2/AMCL/EKF stack) 54.4 CPU-s startup excess, the largest single item;
  coincides with the 60-125 s tail (92 -> 86 -> 81 %).
Reordering ATLAS starts would not remove work; it could only spread it by delaying safety/control/telemetry
services, so no ordering change is proposed. Localization is out of scope (no speculative Nav2/AMCL/EKF change).
