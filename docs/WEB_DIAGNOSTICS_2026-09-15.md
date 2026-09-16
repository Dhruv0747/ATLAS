# ATLAS web diagnostics deployment — 15 September 2026

## Result

The existing port-8088 web dashboard is the main operator diagnostic entry point.
No dashboard redesign, duplicate detector, navigation tuning, or motion command
was required. Visual Cloud remains a separate linked observability tool.

Open **DIAGNOSTICS / LOGS** for service states, restart counts, current-boot logs,
all received dashboard telemetry, USB device identities and snapshot export.
Click a telemetry key to inspect the full value, source, age and measured web
callback rate. These rates are not claimed as source-topic ROS Hz. A missing rate
means insufficient callback samples or a derived/cache value, not a failed sensor.
The generic OLDER threshold is 10 seconds; slow status publishers can normally
exceed this. Sensor-specific health tiles use their own freshness windows.

The backend performs one cached read-only systemd query per 10 seconds. Log
requests are restricted to a fixed service allowlist and 60 current-boot entries,
newest first. There is no arbitrary shell, restart, motor or ROS publish endpoint
in the diagnostics additions. Existing controls and safety priorities are unchanged.
Keep access on LAN/Tailscale, not a publicly forwarded HTTP port.

## GNSS findings and changes

- The live primary source is SIM8230G USB interface 03, not the removed L76K.
- Before this change, the process could retain a deleted ttyUSB descriptor after
  USB reconnection. EAGAIN/empty reads and cached dashboard data concealed this.
- The reader now closes on EOF, detects changed by-id target identity, and retries
  after sustained byte silence. It does not reset the modem or switch routes.
- `/gps/diagnostics` provides source, resolved port, transport state, byte/NMEA/GGA
  ages, fix validity, GSV counts and ages, parse counters and reconnect history.
- Combined GN GGA is preferred over per-system GGA in the same burst. Invalid
  fixes clear immediately; stale data is marked unavailable. Valid zero latitude
  and longitude are preserved.
- Constellation names in NMEA do not prove received satellites or antenna health.
  GSV count zero is displayed as zero with an empty bar. Missing/stale GSV is
  explicitly unavailable. The bars are counts, not signal-strength meters.
- At verification, valid NMEA was live; GPS, GLONASS and BeiDou reported zero
  satellites; position fix remained absent. No position/antenna accuracy pass is claimed.

## Other clarity fixes

- Modem registration and data-session reports are now subscribed and visible.
  Signal quality and an assigned RNDIS IP are not described as Internet proof.
- The selected route uses the kernel route lookup, including the modem's usb0
  interface, without sending probes or changing network configuration.
- Missing voice USB now appears in the health summary.
- Yahboom `/battery/current` is a driver placeholder zero, not a current reading;
  the UI says NOT MEASURED. Main battery SOC comes from Daly BMS.
- Invalid/missing ultrasonic echoes are not labelled clear. Front/left/right are
  currently disabled/uninstalled; rear is separate. No sensors were enabled.
- A live telemetry check is labelled as such, not as a physical encoder test.

## Deployment and validation

- 11 mocked GNSS tests pass: EOF recovery, USB rebind, EAGAIN, checksum rejection,
  zero-count GSV, stale GSV, invalid/stale fix, combined GGA, zero coordinates and
  shutdown. Tests use fake ROS and serial objects, so no test fixes enter DDS.
- 4 diagnostics backend tests pass: service parsing, log allowlist, redaction,
  cache worker deduplication.
- JavaScript syntax/regression checks pass for zero/positive/stale bars, stale
  fixes, zero coordinates and HTML escaping.
- Jetson `colcon build --packages-select atlas_gnss_driver` passed.
- Browser verified GNSS details, search filtering, live rows and service log button.
- `atlas-gnss.service` and `rover-status-web.service` active and boot-enabled.
- Legacy desktop file has Hidden=true and X-GNOME-Autostart-enabled=false.
  `app-project\x2datlas\x2ddashboard@autostart.service` is masked. No running
  `rover_dashboard.py` was found. Wireless-HDMI mode selection and OS desktop
  services were deliberately not modified.
- Pre-change rollback files are under
  `/home/jetson/project-atlas-migration/web-diag-20260915/backup-SqZhQV/`.
  A later verified checkpoint is `backup-BRFNfd/` in the same directory.

No motor, steering, autonomous mission, navigation parameter or hardware power
change was performed. Physical modem unplug/replug was covered by simulated
transport tests, not an intentional live network interruption. Further GPS fix
and navigation reliability tests remain separate from this UI deployment.
