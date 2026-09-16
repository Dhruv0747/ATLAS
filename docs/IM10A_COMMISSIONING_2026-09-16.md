# IM10A and Hiwonder GPS commissioning

## Integration update (16:08 local)

- Reboot restored sensor USB acquisition. GPS is now primary on the dedicated
  physical USB path ending 2.2.4.3; IM10A uses 2.2.4.1; Yahboom uses 2.4.
  These bind to sockets, not serial numbers: keep devices in these sockets.
- Hiwonder GPS service built and deployed with source metadata. Dashboard
  verified FIXED, 9 satellites used, HDOP 1.4 and fresh fix messages.
- IM10A observer deployed/autostart enabled on isolated unvalidated topics.
  Dashboard now selects /im10a/dashboard_json, with fusion explicitly disabled.
- Passive encoder observer deployed/autostart enabled. All four counters fresh
  at approximately 24 Hz, currently zero while stationary. Not a dynamic pass.
- Base service has corrected physical port and fail-closed explicit path lookup.
  It remains inhibited by persistent 99-sensor-commissioning.conf. No motion,
  steering, odometry calibration, EKF changes, or GPS localization fusion done.
  Before restoring drive, stop/disable atlas-encoder-observer.service and validate
  current channel mapping, polarities, scale and live IMU mounting. Remove both
  runtime and persistent commissioning conditions only during controlled validation.
- Dashboard labels updated: M1 BL, M2 BR, M3 FL, M4 FR. Motor odometry geometry
  and per-channel calibration still need revalidation following motor replacements.
- Tests: 11 GPS lifecycle/parser tests passed; four passive encoder parser/no-write
  tests passed; Python compile and colcon atlas_gnss_driver build passed.
- Backups: /home/jetson/project-atlas-migration/pre-hiwonder-integration.
- No GitHub push performed. Current autostart has not been reboot-tested.

Earlier commissioning observations follow for traceability.

Status: **not enabled for navigation**. No motor commands issued.

IM10A previously passed a 30-second read-only baseline at 10 Hz with no
checksum failures, 0.9953 g acceleration magnitude and 0.055 degree yaw change.
Subsequent ROS observer trial failed to open the same USB device: kernel USB
control timeouts (-110), ttyUSB1 modem-status failures and I/O error 5.
This means sustained connection reliability has NOT passed. Reconnect/check
the IMU USB path before proceeding; root hardware cause is not confirmed.

`atlas_im10a_observer.py` is a staged read-only observer using separate
unvalidated topics, no TF or EKF changes and no device writes. Python compile
passed on Jetson. Runtime acquisition validation is blocked by USB errors.
The trial copy is in /home/jetson/project-atlas-migration; no autostart enabled.
Mounting orientation, axis signs, dynamic response, covariances and interference
remain validation gates. Magnetic orientation is deliberately not published.

GPS direct USB test: 20 seconds, 9600 baud, zero NMEA checksum failures.
20 GGA and 20 RMC messages received. GGA quality 0, satellites used 00,
RMC V: **no fix**. Latest GSV: GPS one satellite (C/N0 26), BeiDou one
(C/N0 28), GLONASS zero. Receiver reports ANTENNA OK; that does not prove
good reception or a position fix. No GPS source switching performed.

The motor service uses a generic CH340 by-id identity that currently aliases
the IMU, rather than the motor board. A temporary runtime startup condition
keeps that service stopped. It expires on reboot. Persistent physical-port
assignment and motor-board identity validation are required before driving.
