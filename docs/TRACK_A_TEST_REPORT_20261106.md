# Track A test report — 2026-11-06 (software only)

Environment: Jetson Orin Nano Super (100.87.208.71), ROS 2 Humble, Python 3.10, NumPy 1.21.5, OpenCV 4.5.4.
Tests ran in throw-away folders under /tmp (removed afterwards). The production ROS domains 0 and 77 were not
used; the end-to-end test ran in isolated, localhost-only domain 91. No camera, motor, actuator or service was
started. The production `nav2_params.yaml` was byte-identical before and after (sha256 prefix `2411371c89751eba`).

## Automated tests: `tests/test_track_a.py`, 25 / 25 PASS

| Group | Tests | Result |
|---|---|---|
| Config gate: shipped config refuses unmeasured mount; implausible / NaN / bool / string values; height band, ranges, frame, resolution, stale and valid-fraction bounds | 4 | PASS |
| Calibration gate (real `tools/vision3d/calibration_validation.py`): missing file; not validated; no evidence; serial, size, frame, source mismatch; malformed K; valid doc accepted | 3 | PASS |
| Geometry (ray-cast synthetic depth): wall at 1.5 m within 2 cm; floor only gives no obstacles; ceiling above rover ignored; 10 cm box detected; < 0.35 m and > 3 m ignored; 15° tilt; side offset + yaw; optical rotation equals the launch file's static TF chain | 8 | PASS |
| Invalid data: NaN / ±inf / 0 never become obstacles; mixed valid and invalid; blinded camera gives BLINDED (no scan); stale, NaN, inf and negative ages give STALE; wrong shape / encoding raise | 5 | PASS |
| Nav2 merge against the LIVE `nav2_params.yaml` copy: all 13 checks pass (LiDAR layer byte-identical, separate astra_layer, inflation last, global costmap unchanged); validator rejects `inf_is_valid:true` and a dropped LiDAR layer | 2 | PASS |
| ROS end-to-end (real node, synthetic publisher, domain 91): fresh frames give scans (base_link, 1.5 m); 10 Hz cap; blinded gives no scan + BLINDED; 2 s-old frames give no scan + STALE; publisher stopped (camera loss) gives no scan + STALE; preflight exits 78 on the shipped config, 0 on a valid one | 3 | PASS |

Extra checks: the launch file refuses domain 0 and builds (4 actions, not executed) in domain 77 with a valid
config; refuses on unmeasured mount. Shell syntax OK for all deploy scripts. Python compile OK.

## Performance on the real Jetson (scanner core, synthetic 160x120 frames, 10 Hz, nice 10, 30 s)

| Metric | Value |
|---|---|
| Per frame | median 7.2 ms, p95 15.1 ms, max 25.4 ms |
| Scanner CPU | 5.6 % of one core = **0.94 % of the Jetson** |
| Whole Jetson during run | 60.3 % (limit 75 %) |
| RAM | 36 MB RSS, **0.0 MB growth** over 3,000 further frames |
| Astra depth driver (measured 5 Nov) | about 1 % of the Jetson |

NOT TESTED on hardware: the real Astra driver in this pipeline, the domain_bridge (not installed), the bridge's
domain-0 join spike (gate G3), and the Nav2 costmap behaviour with the real layer (gates G4/G5).

## Deployment run (2026-11-06 16:36)

- Owner installed `ros-humble-domain-bridge` (apt).
- `install.sh` run from bundle `~/ATLAS-track-a`: files in place, units registered as *static* (no [Install]), NOT enabled, NOT started. Backup `track-a-backup-20261106-163609`.
- `verify.sh`: files PASS, domain_bridge PASS, Nav2 merge dry-run PASS, nav2_params.yaml unchanged; G1/G2 BLOCKED (no calibration, mount unmeasured).
- Early-start test found a defect: `ExecStartPre` refusal was retried by `Restart=on-failure` (RestartPreventExitStatus only covers the main process). Fixed with `ExecCondition`; retest: unit skipped, 0 restarts, inactive.
