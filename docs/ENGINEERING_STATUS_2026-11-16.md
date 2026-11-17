# ATLAS — Engineering status snapshot

**Evidence cutoff:** 16 November 2026  
**Prepared:** 17 November 2026  
**Scope:** software, recorded test evidence and operator-reported live deployment evidence available in the repository. This is not a fresh physical inspection of the rover.

## Executive status

ATLAS has progressed from a basic rover with unreliable encoder/TF/odometry foundations to a multi-sensor ROS 2 platform with a corrected EKF heading path, accepted 2D map revision, RTAB-Map 3D prototypes, guarded Nav2 goals, dashboard mission controls and a measured safe-stop response.

It is **not yet accepted for reliable autonomous room-to-room operation or unattended use**. The Stage-3 supervised Dhruv Room → Hall → Dhruv Room attempt on 16 November failed its route, encoder and turn-sign criteria, despite passing the safe-stop measurement.

## Capability status

| Capability | Status at evidence cutoff | What the evidence supports |
|---|---|---|
| ROS 2 / Jetson base | Commissioned baseline | Ubuntu 22.04, ROS 2 Humble, Jetson Orin Nano Super documented |
| Manual control / E-STOP | Operational with safeguards | Existing command mux and physical stop remain required |
| Encoder feedback | Degraded / qualification ongoing | M3 excluded in latest recorded configuration; Stage-3 attempt 7 recorded one CRITICAL sample |
| EKF heading | Scoped fix applied and checked | Velocity-only wheel input + IM10A yaw; offline replay median heading error 1.3°, controlled turn within about 3° of LiDAR |
| Full-drive localization | Not accepted | Hall pose/map mismatch and route-level corrections remain in evidence |
| 2D mapping | Remap 13 promoted | Owner-approved parked review; previous map retained. Review disclosed per-capture-time freshness deviation |
| 3D mapping | Prototype / partial route outputs | RTAB-Map parked test, dashboard point cloud, coloured and route clouds; calibration and full-home acceptance remain open |
| Nav2 / named places | Guarded, partial | Goals and map paths demonstrated; complete round trip failed |
| Closed-loop speed | Two checks passed | Requested 0.15 m/s; measured means 0.116 and 0.096 m/s |
| Safe stop | PASS in Stage-3 attempt 7 | 0.14 s and 0.006 m in the recorded B-stop test |
| Mission abort | Owner-verified | Autonomy OFF, Nav2 cancel acknowledged and stopped status displayed |
| Human-aware navigation | Design only | No complete person-fusion/navigation behaviour implementation or acceptance |
| Unattended operation | NOT APPROVED | Stage-3 round trip and repeated acceptance campaign still required |

## Open blockers — priority order

### P0 — Complete a repeatable supervised round trip

The 16 November attempt failed at the Hall door and required owner assistance. The right-side no-echo region must be handled through validated sensor coverage and the existing fail-closed safety policy, not by suppressing or widening away the obstacle gate.

Acceptance evidence should include:
- Dhruv Room → Hall → Dhruv Room with no physical assistance.
- No encoder CRITICAL samples during motion.
- Turn-sign error within the existing 5% gate.
- Fresh localization and scan/map fit throughout both legs.
- Physical E-STOP available and an independently recorded stop while Nav2 is moving.
- Repeated passes on the same frozen hardware/configuration baseline.

### P0 — Resolve encoder and turn-sign failures

The latest Stage-3 record reports one CRITICAL encoder sample and a 5.8% turn-sign result. Determine whether remote-assist samples contaminated the cmd_vel comparison; do not assume this explanation. Repeat with clearly separated Nav2 and remote-command channels and preserve the raw bag.

### P0 — Measure CPU during actual drives

The 16 November parked/charging sample totalled 371% across six cores and load average around 19–20, with the owner reporting CPU reaching 100% during drives and the dashboard becoming unresponsive. Profile the drive workload using timestamped per-process, ROS loop-rate and freshness evidence. Optional AI/vision services must not starve localization, controller or safety processing. Do not infer a fix from idle measurements.

### P1 — Revalidate localization on the promoted map

The EKF heading correction is meaningful, but it does not prove global position accuracy. Repeat slow, instrumented drives and compare AMCL against independent LiDAR/map evidence. Retain the accepted-map identity and map-bound named places.

### P1 — Finish calibrated whole-home 3D mapping

The RTAB-Map prototype and point-cloud artifacts are real progress, but a final map still needs verified Astra intrinsics/extrinsics, stable TF, depth-to-RGB alignment where colour is used, full room/hall coverage, loop closure, duplicate-wall review and a reproducible export.

### P2 — Human-aware navigation

The 16 November design is explicitly design-only. Benchmark YOLO on the Jetson, collect labelled supervised recordings, validate person/radar/depth association and test in shadow mode before any navigation integration. The person layer may only slow, stop, wait or add obstacle cost; it must never grant motion or bypass LiDAR, costmap, ultrasonic, mux or E-STOP protections.

## Recommended next sequence

1. Freeze and record the exact deployed commit/configuration and map identity.
2. Capture a clean Stage-3 bag with separate Nav2 and remote-command topics plus front/rear ultrasonic validity.
3. Reproduce and diagnose the encoder CRITICAL and 5.8% turn-sign result.
4. Profile CPU, AMCL/controller loop rates, TF age and dashboard latency during the same drive.
5. Fix only the evidenced Hall no-echo coverage gap without weakening fail-closed behavior.
6. Run the full supervised round trip; repeat until acceptance is reproducible.
7. Resume full-home calibrated 3D mapping and then the human-aware perception roadmap.

## Safety boundary

This status report does not authorize motion, firmware flashing, safety-threshold changes, service restarts or deployment. All physical tests require explicit owner approval, a clear test area and access to the physical E-STOP. Preserve manual fallback and fail-closed behavior.
