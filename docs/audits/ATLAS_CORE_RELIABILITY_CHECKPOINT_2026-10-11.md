# Core reliability — new evidence checkpoint

11 October 2026, after deployment `eb4c88c`. Owner added CHECK MY LOCATION during
this investigation; its implementation is tracked separately. No live changes.

## Guard provenance, not a relaxed permission policy

New `audit_lidar_guard_coverage.py` reuses the installed guard and existing paired
scan capture format. Five classification regressions pass. It rejects unmatched
payloads and never labels infinity free or proves an out-of-range cause.

| Capture | Paired scans | Finite rays | Raw positive infinity | Geometry permits F/R/L/R |
| --- | ---: | ---: | ---: | --- |
| Existing payload-preserving recording | 26 | 5,416 | 3,944 | 0 / 0 / 0 / 0 |
| New parked capture | 18 | 3,845 | 2,635 | 0 / 0 / 0 / 0 |

No finite raw reading was removed in either set. Missing observations originate
upstream of the self-filter. This does **not** distinguish missed detection,
occlusion, reflectivity, angle-compensation gaps or true out-of-range surfaces.
The fresh capture had 21 sampled records; three did not have usable TF/projection
evidence and were excluded, not treated as free. Source ages 0.132–0.395 seconds.
The audit replays geometry with synthetic fresh timestamps: it does not claim
a reproduction of historical timing or controller behavior.

First historical missing bins: 30,31,33,43,51,58,67 (five-degree laser bearings
rotated 180 degrees). Thus a turn's blanket 72-bin requirement is not a physical
swept-volume model. Narrowing it alone would not establish observed free space.
The guard remains unchanged. Full footprint/steering/stopping-envelope
qualification and candidate controller replay remain pending.

## Settled resource window

20.089-second /proc delta measurement, six logical CPUs, no old replay/probe
processes found beforehand. No camera quality or service change.

- CPU busy excluding idle/iowait: **70.35%** machine total; iowait 0.025%.
- RAM: **5,442.83 MiB**, MemTotal minus MemAvailable (not summed RSS).
- Dashboard: 40.27% of one core = **6.71% of six cores**, RSS 168.39 MiB.
- Camera: 34.05% of one core = 5.67% machine, RSS 180.16 MiB.
- Motor owner: 25.69% of one core = 4.28% machine, RSS 73.27 MiB.
- Mux: 15.23% of one core = 2.54% machine, RSS 72.41 MiB.
- Probe: 0.20% of one core = 0.033% machine, RSS 17.36 MiB.
- Subsequent local HTTP 200: root 7 ms, status 66 ms, LiDAR view 28 ms.
- Temperature snapshot: 59.94 C. Free filesystem storage: 369 GiB.

Earlier 70.8→79.1 CPU / 5364→5948 MB windows were different workloads and may
use different memory units. This window rejects attributing that whole rise to
the guard; it is NOT an A/B measurement of guard overhead. Moving workload and
operator-network responsiveness were not tested.

Direct ROS final verification: 86 zero commands, 187 latched-stop policies, no
unsafe event; final receipt ages odom .055, policy .082, IMU .085, scan .047 s.
These are receipt ages, not acquisition latency. Mux/motor/BMS PIDs unchanged,
zero service restarts for these units. Nav2/explore units inactive; localization
launch still hosts Nav2 components. No goals, resets or commands were issued.

## BMS and consolidated status

BMS PID 268412 remains single owner with connection timeout about every130 s.
BlueZ powered, not discovering; passive btmon denied `Operation not permitted`.
sudo inspection permits noninteractive shutdown only, not HCI tracing. No
pairing/restart/network experiment performed. Current advertising, peripheral
rejection and RF coexistence cause remain unverified. Wi-Fi→cellular→AP unchanged.

| Area | Root cause | Correction / tests | Deployment | Physical validation |
| --- | --- | --- | --- | --- |
| LiDAR coverage | Missing rays already raw +inf; physical reason unknown | New paired audit, 5 tests; swept-volume candidate unfinished | Prior guard retained | Not passed |
| BMS Bluetooth | Connect-stage timeout; deeper cause unknown | Bounded log/permission check; no decoding claim | Single-owner fix retained | Connectivity/endurance unresolved |
| Wheel odometry | Historical under-reporting, cause unresolved | No arbitrary multiplier or encoder-fault assumption | Unchanged | Loaded metric qualification pending |
| IMU/EKF | Historical disagreement unresolved | No calibration change | Unchanged | Motion fusion qualification pending |
| Moving AMCL | Still unresolved | New location-check lifecycle is not a localization fix | Suggest monitor retained | No new drive requested |
| Corridor map | Recorded duplicated/offset walls; prior safe candidate no material gain | Existing rejected candidates preserved; no repeated replay | Accepted map unchanged | Targeted corridor evidence later if needed |
| Scan/map overlay | Combined overlay still absent | Existing LiDAR view remains live; no camera dependency | Unchanged | Combined view not passed |

Private evidence: existing Jetson scratch directory, `guard_coverage_fresh_1828.json`,
`guard_parked_1830.json`, `settled_resources_1826.json`. No raw house geometry in Git.
New diagnostic programs have no control publishers and no automatic service.

Previous live rollback packages unchanged:
- `data/backups/2026-10-11-180447-354595945-stage11b-lidar-guard/ROLLBACK.sh`
  under `/home/jetson/project_atlas`.
- `data/backups/2026-10-11-180717-342176253-stage12-inflation-contract/ROLLBACK.sh`
  under `/home/jetson/project_atlas`.
- `data/backups/2026-10-11-180829-571179806-stage12-inflation-contract/ROLLBACK.sh`
  under `/home/jetson/project_atlas_ws/src/tortoisebot_bringup`.

No new controller deployment or autonomous readiness is claimed. Next guard
step is ray-level observed swept-volume analysis, not treating invalid returns
as unlimited range. BMS needs authorized passive HCI evidence of an existing
retry. Location feature next steps are in its separate implementation report.
