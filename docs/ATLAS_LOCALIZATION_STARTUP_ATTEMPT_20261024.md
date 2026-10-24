# Approved isolated startup attempt — 2026-10-24

Result: **ABORTED at baseline admission; worker never launched.** No retry.

The owner approved one guarded isolated attempt with unchanged limits. Verified
approved v2 archive SHA256
`16032598eef40ef6c919b2e182b5a0fe03329ae661330ceada3d091e9543ab2f`
before and after copying. Extracted manifest matched
`8c52758413d1b671d1df2edf569106343447f23ba3c1888bbbd325d1888376bc`;
supervisor matched `ddf34836d9efbaafbf42bb855ca006a746374e4c98e4b18464df3dcbe3e415c7`.
Runtime package, protected production and guard hashes passed before admission.
Disk check passed. No production files installed.

## Measurements and stop

Four baseline one-second CPU readings:69.2691%,74.6622%,69.4581%,76.2376%.
Fourth sample failed75% ceiling; no ROS worker process or private participant
was created. First three safety samples passed: E-STOP latched, manual-only,
commissioning disabled, commands/output targets zero, sensors fresh, Astra and
recorder OFF. Mission receipt age0.2s and observed rate1Hz throughout captured
receipt samples. CPU failure occurs before other-resource checks for that sample;
do not claim simultaneous RAM/temperature validation at the failing instant.

Cleanup postflight CPU71.0438%, RAM70.0546%, max temperature59.343C. Mission READY,
receipt age0.2s, required sensors fresh, E-STOP latched, commands zero, recorder
and Astra OFF. Largest captured RAM70.1877%, temperature59.406C. Normal safeguards
remain CPU75%,RAM80%,70C. Cleanup is not a second admission or retry.

All11 protected service identities active and unchanged before/after:
camera1858/0,telemetry3351/1,mux1852/0,EKF2982/0,AMCL8060/7,LiDAR7887/12,
Dashboard94624/0,voice108742/0,safety119178/0,monitor275216/0,mission1901/0.
PID/restart counts are historical; none restarted in this attempt. Postflight
protected file hashes passed, including voice and white-glass UI.

## Evidence and remaining issue

Remote directory:
`/home/jetson/project-atlas-migration/localization-startup-once-20261024-fwAnZP/`

- result.json SHA256 `51b83257491dfa8c4740c66ac8efd959235c139ee69d5f23b1e46f2d6f536e3a`
- guard-trace.jsonl SHA256 `3e5250b3c2d05d21415c52a90eedddefa7375ea34bd30e5f8a64f679ce3f8341`

Retrieved private copies match remote hashes:
`artifacts/localization_startup_once_result_20261024.json` and
`artifacts/localization_startup_once_trace_20261024.jsonl`. Raw logs not committed.

No startup stage timing was produced, so this attempt does not diagnose the
previous stale mission status. That cause remains unresolved; resource headroom
blocked the planned experiment. No CPU improvement or localization fix claimed.
Previously passed offline tests reused; unchanged code not re-benchmarked.

No camera, movement, installation, restart or safety-limit changes. No rollback
needed. Retain diagnostic folder and evidence; no autostart was created. Stop
here as requested; further execution needs new owner direction, not an automatic
retry or inherited CPU exception.
