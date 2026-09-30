# ATLAS AI/Robotics Adaptation — Phase 0 Baseline and Execution Gate

Date: 2026-09-30  
Status: **PHASE 0 COMPLETE IN SOURCE; FEATURE IMPLEMENTATION NOT STARTED**

This document supersedes stale *current-state* statements in earlier dated
commissioning plans. Those older documents remain historical evidence and must
not be rewritten as though their observations were made today.

## Objective

Use *Artificial Intelligence for Robotics, 2nd Edition* as a source of ideas,
not as an ATLAS implementation. Preserve the existing ROS 2 Humble, Nav2,
SLAM, deterministic safety mux, remote stop, health gates, driver ownership and
fail-closed behavior.

No book example may publish to an ATLAS motor command topic. An AI/LLM may
resolve **what** goal is intended; Nav2 and the local safety chain decide **how**
the rover moves.

## Preserved source baseline

- Working branch: `agent/fix-mapping-footprint`
- Phase-0 starting commit: `577aac9`
- GitHub comparison at audit time: local branch 10 commits ahead, remote 0
  commits ahead. Do not reset or replace the local branch.
- The historical September 20 capability plan still describes the former
  M1/M2/M3 selection and must not be interpreted as current runtime policy.
- Generated output, credentials, private keys, logs, bags and models remain
  excluded from source control.

## Current ATLAS truth

| Area | Current authority/status |
|---|---|
| Drive motors | Four motors operational; motor operation is distinct from encoder authority. |
| Encoder policy | M1 rear-left, M2 rear-right and M4 front-right selected. Weak M3 front-left is diagnostic-only. |
| Encoder safety | Validated three-channel policy, 50% degraded scale, stale/fewer-than-three feedback fails closed. |
| Closed-loop wheel PID | Disabled and uncommissioned. `drive_pid.yaml` is a separate gate and remains false. |
| Steering | Front and rear steering installed and commissioned for commanded position. Physical tyre-angle feedback is not installed. |
| Steering PID | Not possible from commanded PWM alone; do not label a command as measured angle. |
| LiDAR | RPLIDAR A1 is primary mapping, geometry and collision source. RF2O LiDAR odometry remains a shadow candidate. |
| IM10A | Live monitoring candidate. Navigation/EKF authority was revoked after the 2026-09-25 stationary drift regression and requires requalification. Magnetic/Euler heading remains excluded. |
| Camera VO/VIO | Not installed or validated. A camera stream is not visual odometry. |
| YOLO | Optional TensorRT YOLO implementation already exists. Benchmark/audit it; do not rebuild it from the book. |
| Sensor authority | Capability registry, dynamic encoder selection and fail-closed assessment already exist. Extend rather than duplicate. |
| Recovery | Existing bounded recovery/agent logic exists. Audit it before adding another recovery owner. |
| GNSS | Diagnostics/outdoor position only; it is not indoor room-navigation authority. |
| Radar/ultrasonic | Secondary/advisory or direction-specific safety sources according to their validated gates; neither replaces LiDAR localization. |
| BME680/AMG8833 | Environmental/thermal monitoring only. |
| AI companion | Non-safety supervision/intent layer; it cannot bypass Nav2, the mux, owner rules or emergency stop. |

## Reference-code classification

Reference snapshot inspected: Packt repository commit `ab072d6` dated
2024-06-04. The inspected examples retain older ROS 1/Python-era assumptions;
several files are illustrative rather than production-ready.

| Book concept/code | Classification | ATLAS decision |
|---|---|---|
| Chapter 1 control-loop timing and feedback | **USEFUL — SHOULD ADAPT** | Reuse the target/measurement/error concept and timing metrics. Do not port ROS 1 loops or the Adafruit motor protocol. |
| `robotMotorControl.ino` heartbeat | **ATLAS IMPLEMENTATION IS BETTER** | Preserve the existing watchdog, mux ownership and remote stop. The example's heartbeat check is partly commented out and is not an ATLAS safety design. |
| Chapter 4 object detection | **ALREADY IMPLEMENTED / AUDIT** | Existing TensorRT YOLO is optional. Measure FPS, latency, CPU/GPU/RAM and temperature under Nav2 load. |
| Chapter 5 arm kinematics/optimization | **USEFUL LATER** | No arm motion until confirmed hardware is installed. Future Pi 5 arm controller may communicate through ROS 2. |
| Chapter 7 CNN navigation | **OUTDATED — DO NOT USE FOR CONTROL** | The example uses ROS 1/Keras and publishes direct `cmd_vel`. Only free-space/terrain/disagreement concepts may be evaluated in advisory shadow mode. |
| Camera visual motion | **USEFUL LATER** | Evaluate a ROS 2-compatible VO/VIO option only after current autonomy gates pass; begin shadow-only. |
| Chapter 8 A*/search/decision logic | **ATLAS IMPLEMENTATION IS BETTER** | Audit Nav2 planner/controller/costmaps/BT and recovery budgets; do not replace Nav2 with educational A*. |
| Chapter 9 personality/NLP | **OUTDATED — CONCEPT ONLY** | Preserve ATLAS's English/Hindi companion and truthful KNOWN/UNKNOWN/STALE/UNAVAILABLE reporting. |
| Book-specific Albert/xArm hardware | **NOT RELEVANT NOW** | Do not import drivers, chassis assumptions or direct control paths. |

## Mandatory entry gate before Phase 2 features

Do not add PID, VO/VIO, new semantic perception or semantic navigation until
the current configuration passes all three stages below:

1. One bounded 20 cm straight ground run.
2. One bounded gentle left/right turn sequence.
3. One supervised autonomous Dhruv Room -> Hall -> Dhruv Room round trip,
   including safe stop and return-home evidence.

Latest straight-run evidence remains **PARTIAL**, not PASS: a 0.20 m request
stopped safely on timeout at 0.134 m LiDAR clearance progress and 0.101 m wheel
odometry; M1/M2/M4 remained available and M3 remained weak. Repeat only after a
fresh acceptable BMS reading, charger disconnection, clear path and remote stop
readiness.

## Approved execution order

1. **Baseline preservation and gap analysis** — this document.
2. **Finish the three physical validation stages above** without changing
   unrelated tuning.
3. **Revalidate IM10A/EKF/TF** using stationary bias, controlled turns and full
   workload timing. Promote no IMU field without covariance and drift evidence.
4. **Audit Nav2 recovery budgets** and mission checkpoint ownership. Prevent
   endless retry loops; never replay a stale `Twist`.
5. **Evaluate wheel PID only if feedback quality permits.** PID requires a
   trustworthy measured variable. Steering PID requires actual angle feedback.
6. **Evaluate camera VO/VIO in shadow mode** with rate, age, confidence and
   GOOD/DEGRADED/LOST states.
7. **Benchmark the existing TensorRT YOLO path**, optional and resource-capped.
8. **Add advisory semantic perception**, then semantic goal resolution through
   Nav2 only after recorded validation.
9. **Defer arm integration** until hardware exists and has its own safety plan.

## Change acceptance and rollback contract

Every implementation increment must record:

- baseline commit and configuration hash;
- one bounded hypothesis and one primary change;
- exact PASS/PARTIAL/FAILED/NOT TESTED criteria;
- message rate, age, dropouts and stale/invalid samples;
- pose, heading, stopping and path error where relevant;
- CPU, GPU, RAM, temperature, FPS and latency for compute features;
- emergency-stop, watchdog and ownership behavior;
- physical test conditions and rosbag/log reference;
- deployed files/services and an explicit rollback procedure.

No successful single run proves reliability. No software test claims a physical
PASS. No dashboard freshness label grants navigation authority.

## Phase 0 result

**BOOK IDEA:** feedback control, perception, search, recovery and staged testing.  
**CURRENT ATLAS:** already has a stronger ROS 2/Nav2/safety architecture and
partial implementations of most proposed management layers.  
**CHANGE:** documentation-only corrected baseline and ordered execution gate.  
**BENEFIT:** prevents stale encoder/IMU facts, duplicate subsystems and premature
AI/PID work from destabilizing current autonomy commissioning.  
**RISK:** none to runtime; no service, parameter or actuator was changed.  
**TEST:** repository/config inspection plus direct review of the named reference
files. The focused Windows offline regression ran 75 tests successfully with
five existing environment-dependent skips. A separate hardware-oriented
steering test was not counted because the Windows virtual environment lacks
`pyserial`; no actuator test was appropriate for this documentation-only phase.  
**STATUS:** **PASS — DOCUMENTATION/PLANNING ONLY**.

