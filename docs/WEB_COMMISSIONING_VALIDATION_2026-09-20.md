# Commissioning increment 1 — validation and deployment

## Delivered

Existing port 8088 now serves `/commissioning`. Nine subsystem pages reuse the
existing ROS cache, camera JPEG and diagnostics. They distinguish commands,
sensor reports and calculated estimates. Fresh packets are not physical PASS.
Stationary observations store configuration hashes and results in a bounded
SQLite history (500 results; API returns latest 100). Actuator and calibration
write requests are rejected. The stop button requests the existing mux latch;
it is not a separate hardware emergency-stop circuit.

## Tests

- 14 commissioning unit tests passed, including stale/invalid data, disabled
  sensors, result persistence, calibration rejection and no hardware imports.
- Existing camera-link (6) and remote-stop (10) tests passed.
- Python compilation, JavaScript syntax and diff whitespace checks passed.
- Live API: motor and calibration requests returned 403; hardware observation
  returned 202 and completed as ATTENTION REQUIRED, not physical PASS.
- Browser: overview and encoder pages displayed fresh telemetry; camera page
  displayed the existing live JPEG without overlapping its controls.
- No motor, steering, camera-motion, navigation or stop command was issued in
  these checks. Only `rover-status-web.service` was restarted.

## Deployment / rollback

Five console/web files were installed in `/home/jetson/project_atlas/scripts`.
The existing web service is active. Prior web/diagnostics files are backed up in
`/home/jetson/project-atlas-migration/commissioning-20260920/backup`.
Rollback: restore those two backed-up files to scripts and restart only
`systemctl --user restart rover-status-web.service`. Added console files can
remain unused. Result DB is under `project_atlas/data/commissioning`.

## Remaining, not verified

This is not the complete requested manual commissioning console. Exclusive
actuator ownership, authenticated leases, disconnect fault injection, bounded
motor/servo jogging, applied calibration saves/restores and reboot validation
remain. Physical wheel directions, new CPR values and steering alignment need
operator-observed tests. M4 remains excluded; navigation validation remains
false. Resource overhead has not yet been benchmarked. No GitHub push was made
as part of this increment. Existing unrelated USB/driver edits were preserved.
