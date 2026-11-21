# ATLAS status and roadmap

*Last updated: 2026-11-19.* The dated, detailed record of every test lives in the
[current blockers log](audits/ATLAS_CURRENT_BLOCKERS.md). This page is the summary.

## Where ATLAS stands

ATLAS can map the home, localize on the saved map, and drive itself between rooms under supervision with a layered
safety system. It is working through **Stage 3** of the master plan: a supervised autonomous round trip
Dhruv Room → Hall → Dhruv Room with safe-stop and return-home evidence.

## Master plan stages

From the [Phase 0 execution gate](AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md). New feature families wait until all
three stages pass.

| Stage | Goal | Status |
|---|---|---|
| 1 | One bounded 20 cm straight ground run | ✅ PASS: 3-encoder mode, 12/12 runs (2026-11-14) |
| 2 | One bounded gentle left/right turn sequence | 🟡 Turns exercised in many drives; a dedicated evidence run is still to be recorded |
| 3 | Supervised autonomous Dhruv Room → Hall → Dhruv Room round trip, with safe stop and return home | 🟠 In progress; checker: `project_atlas/tools/drive/stage3_autonomy_check.py` |

## Done ✅

**Foundation**
- Jetson Orin Nano Super running ROS 2 Humble, with all services starting at boot as user services.
- Wheel odometry with per-wheel calibration, 3-encoder consensus mode (weak M3 excluded), encoder health monitoring.
- EKF fusing wheel odometry, IMU and LiDAR keyframe-ICP velocity (odometry fix of 2026-11-12).
- Closed-loop speed controller with a dashboard **Speed check** that must pass twice after any base change.

**Mapping and localization**
- LiDAR SLAM mapping with a fail-closed acceptance gate; accepted home map promoted 2026-11-14 after parked review.
- AMCL localization, seeded from a LiDAR-verified pose at every start, with a scan-match check before each drive.
- Saved-map unknown space now loads as unknown, no longer as free (2026-11-16 fix).

**Navigation**
- Nav2 with a Reeds-Shepp Hybrid-A* planner and Regulated Pure Pursuit, allowing reverse, for the 4-wheel-steering chassis.
- Planner penalties retuned to reduce back-and-forth manoeuvres; goal tolerance 20 cm / ~35° for the car-like base.
- Named places, return home, mission status and spoken stop reasons.
- **Virtual obstacles** for LiDAR-invisible furniture, respected by Nav2 and the safety guard.

**Safety**
- Priority velocity mux with remote E-STOP first, watchdog, manual-only default and operator arming.
- LiDAR blind-spot guard with explanations from the map, the Astra depth camera and front/rear ultrasonic.
- Safe stop measured in a real autonomous drive: **0.14 s, 6 mm** (Stage-3 attempt 7).
- **Abort mission** button: manual mode and goal cancel in one press.

**Operator experience**
- Web Command Center v2 (English UI), Readiness checklist, live mapping, LiDAR view, test labs.
- Battery card with time left / time to full and the charger rating.
- Bilingual voice companion, kept at low CPU priority during drives.

## Left to do 🔧

**For Stage 3 (now)**
0. **Deploy the staged wheel-curvature fix** (owner approved; when parked), then two Speed checks. It removes most
   encoder-consensus stops in turns (replay 41 → 14) and makes wheel-odometry yaw agree with the gyro.
1. **Hall door frame:** the dark frame returns no LiDAR echo, so the guard stops the rover in the doorway (~96 % of
   doorway scans in replay). Fix: matte white tape on both faces of the frame at LiDAR height (18 cm).
2. **Side ultrasonic sensors (optional):** software is staged (disabled). Replay shows narrow-cone HC-SR04s cannot
   clear the doorway veto; they would add close-range readings only.
3. ~~Encoder consensus warnings~~: root cause found (wheel-curvature sign); fix staged, see item 0.
4. **Home position** has only 0.26 m clearance; end autonomous returns at the "dhruv room" place (0.49 m clear) and do
   the last metre by remote.
5. **Validation drive** of the 2026-11-16/19 changes (virtual obstacles, planner, goal tolerance), recorded and replayed.
6. **Wi-Fi:** power saving off on the rover and an extender for the hall, so the dashboard never shows "no data".

**After Stage 3**
- ~~Mission-control status on goal pre-emption~~: fix staged (superseded goals are logged only).
- ~~Turn-sign check at 5.8 %~~: explained (owner remote reverse turns and steering swings were counted); the checker
  now counts autonomous turning only. Bags 8 / penalty / room test: 2.9 % / 0.1 % / 1.4 % (pass).
- Pause non-essential AI services during drives to save CPU.
- Guided mapping assistant, phase 1b: live map quality and prompts on the dashboard
  ([design](design/guided_mapping_assistant.md)).

## Roadmap ⏳

In the order set by the master plan, each step only after the previous one has recorded evidence:

1. Finish Stages 1–3.
2. Revalidate IMU / EKF / TF under full workload.
3. Audit Nav2 recovery budgets; no endless retries.
4. Wheel PID, only if feedback quality allows.
5. Camera visual odometry, in shadow mode first.
6. TensorRT object detection, resource-capped.
7. Semantic perception and goals ("go to the sofa").
8. Human-aware navigation using the RD-03D radar ([design](ATLAS_HUMAN_AWARE_NAVIGATION_DESIGN_2026-11-16.md)).
9. Astra features one at a time, only when not driving: follow-me, gestures.
