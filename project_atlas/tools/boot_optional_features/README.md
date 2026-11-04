# Optional AI features OFF at boot until requested (prepared 2026-11-04, NOT deployed)

Evidence: baseline boot bfa7996c (2026-11-04 08:16 IST). Whole-Jetson CPU 99-100 % from +16 s to ~+140 s; 107/107
post-Recovery samples >= 75 %. The 8 feature-on-demand units consumed 157.6 CPU-s that boot (journal "Consumed"):
ai-annotator 28.8, agent-team 27.9, active-vision 21.4, vision-lidar-fusion 20.7, person-sensor-fusion 18.0,
follow-person 16.4, experience-store 14.2, camera-tracker 10.3. Seven were started by systemd at +16-17 s
(enabled, WantedBy=default.target); the manager started experience-store at +53 s because "nothing received yet" and
mission 'STARTING' (published at 1 Hz until READY at +34.9 s) count as autonomy demand. All 8 stopped at +339-358 s.

## Correction (two parts, both needed)
1. Remove the 8 default.target.wants links (`disable --no-reload`). Unit files unchanged; the manager and mission
   control still start them with `systemctl --user start`.
2. Manager 5bcd4f08 (live b0fb5b43 + 15 lines): `startup_input_wait_s` (default 120 s). Within it, a never-received
   input or mission 'STARTING' is not autonomy demand. Received inputs, explicit requests (ai_object, follow,
   tracking, active_vision) and a fresh manual_only=false policy act at once. After it, fail-open as before.
   `timing: startup_input_wait_s: 0` in the existing YAML restores the old behaviour exactly.

Unchanged: Recovery, mux, telemetry, localization, safety, E-STOP, camera, voice (never managed here), unit files,
manager unit (Restart=always, fail-open ExecStopPost restore-all: a manager crash still starts all 8), boot grace.

## Apply / rollback (no restart, reload or reboot; effective at the next separately approved boot)
apply.sh pins: manager b0fb5b43 jetson:jetson 755, manager unit 4e74deeb, each [Install] exactly
WantedBy=default.target, all 8 links present. rollback.sh restores b0fb5b43 bytes, mode and mtime, re-enables the 8
links and checks them against the recorded originals; refuses unknown bytes.

## Recorded fault (no action taken)
atlas-ptz-home.service (system unit) failed at 08:16:32 on boot bfa7996c: smbus2 write_byte_data
OSError [Errno 121] Remote I/O error (pan-tilt I2C device did not acknowledge). No homing retry or servo command was
issued. Previous-boot journal is not persisted, so whether this repeats every boot is UNKNOWN. The owner moved the
wheels and repositioned the pan-tilt by hand after this boot; those movements are not faults.
