# ATLAS status and roadmap

*Last updated: 2026-11-26.* The dated, detailed record of every test lives in the
[current blockers log](audits/ATLAS_CURRENT_BLOCKERS.md). This page is the summary. The live source of truth is the
dashboard board `/v2/plan` (`/api/master_plan`); it shows only recorded test results.

## Where ATLAS stands

ATLAS maps the home, localizes on the saved map and drives itself between rooms under supervision with a layered
safety system. The master-plan entry gate (stages 1–3) is passed: stage 3 by a recorded **owner decision** that
combines two runs, **not** by a single clean checker run. Steps 4–8 of the plan have owner-run PASS/DONE evidence.
Step 9 is half done: semantic perception works, and "go to the object through Nav2" is built and deployed but has
not passed on the rover yet. Step 10 (robot arm) is on hold.

**Honest overall estimate (whole project vision, not just this plan): about 70–75 %.** The plan document itself is
close to complete, but a single-run stage-3 pass, step 9 part B, full-home 3D mapping, human-aware navigation and the
arm remain.

## Master plan

From the [Phase 0 execution gate](AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md).

| Step | Goal | Status (evidence) |
|---|---|---|
| Stage 1 | Bounded 20 cm straight ground run | ✅ PASS: 12/12 runs (2026-11-14); Speed check PASS again after every base change |
| Stage 2 | Bounded gentle left/right turn sequence | ✅ PASS: turn check 2026-11-23 13:37, again 2026-11-26 10:48 |
| Stage 3 | Supervised Dhruv Room → Hall → Dhruv Room round trip, safe stop, return home | ✅ **PASS (owner decision)** 2026-11-23 12:53. It combines the 12:25 run (legs PASS, return home 0.02 m / 15°, turn sign PASS, encoders 0 bad) with the 10:25 safe stop (0.30 s, 0.018 m). **Not a single-run checker PASS**; the last three one-click runs scored 3/5, 4/5 and 4/5 |
| 4 | IMU / EKF / TF revalidation | ✅ PASS: parked 60 s + turns under full workload (2026-11-23) |
| 5 | Nav2 recovery budget audit | ✅ PASS (2026-11-23) |
| 6 | Wheel PID evaluation | ✅ DONE: PID **not advised** (M3 encoder excluded); the validated speed loop stays |
| 7 | Camera visual odometry, shadow mode | ✅ PASS 2026-11-26: parked drift 1.2 cm; turns agree with LiDAR within 2.0° / 3 cm. Feeds nothing |
| 8 | TensorRT YOLO benchmark | ✅ PASS 2026-11-26: 9.9 inferences/s, p95 38 ms, CPU/RAM/temperature limits held under the nav stack |
| 9 | Semantic perception → semantic goals | 🟡 Part A (advisory) PASS 2026-11-26 (chair, after the camera-forward fix). Part B (go to the object through Nav2) deployed; not passed yet (see below) |
| 10 | Robot arm | ⏸️ On hold (owner, 2026-11-26) |

## Done ✅

**Foundation**
- Jetson Orin Nano Super, ROS 2 Humble, all services as user services at boot.
- Wheel odometry with 3-encoder consensus (M3 excluded), debounced consensus (2026-11-23), encoder health monitor.
- EKF fusing wheel odometry, IM10A IMU and LiDAR keyframe-ICP velocity.
- Closed-loop speed control. The wheel-curvature fix was deployed on 2026-11-20 11:26, followed by two Speed check PASSes (11:29, 18:25).

**Mapping and localization**
- LiDAR SLAM with a fail-closed acceptance gate; accepted home map promoted 2026-11-14.
- AMCL seeded from a LiDAR-verified pose; scan/map check before every drive.

**Navigation and safety**
- Nav2 (Hybrid-A* Reeds-Shepp, Regulated Pure Pursuit with reverse) for the 4-wheel-steering chassis.
- Named places, map-tap "Move here", return home, one-click Stage-3 runner with a bounded Go retry budget.
- Priority velocity mux: remote E-STOP first, 0.5 s stale-command cut, manual-only default, operator-PIN arming.
- LiDAR availability guard, ultrasonic guard, CPU budget, Abort mission button.
- Mission-control goal pre-emption fix deployed 2026-11-20.

**Perception**
- Astra depth obstacle scan (private DDS domain 77, bridged) and shadow visual odometry.
- TensorRT YOLO on the IMX708 camera, on demand (Eco mode off by default).
- Step 9 part A: objects named by YOLO, confirmed by LiDAR, placed on the map, stop point worked out (advisory).

**Operator experience**
- Web Command Center v2 (English UI), master-plan board with one locked button per step, readiness checklist.
- Bilingual voice companion with spoken stop reasons.

## Left to do 🔧

**Now**
1. **Step 9 part B** (go to the object through Nav2). The tool works: it refuses stale or moved results, steps back to a
   map-clear stop point, shows why ATLAS stopped, and always ends in Manual. Owner runs so far did not move ATLAS, each
   for a correct safety reason: the LiDAR could not see part of the path; the stop point or ATLAS's own start pose was
   too close to mapped obstacles. Next: start from open floor, chair 1.5–2.5 m ahead, part A, then part B.
2. **Stage 3 as one clean checker run** (no owner decision), ideally twice in a row without physical help.
3. **Camera/LiDAR fusion node** uses forward pan 2300 µs, while navigation centres the camera to the calibrated home
   (1801 µs). The fusion node is therefore always suspended during goals. Nav2 does not use its output. Fix proposed,
   not deployed.
4. **Image quality:** hazy or backlit frames drop YOLO scores sharply; keep the lens clean.

**Housekeeping**
- PR Dhruv0747/ATLAS#22 (this branch → `main`) is large; review it in stages before merging. PR #21 (documentation) is
  separate.
- Wi-Fi: power saving on the rover and hall coverage still to settle.
- Unverified in the hardware list: CrowPanel display and GNSS commissioning evidence.

## Roadmap ⏳

1. Step 9 part B PASS, then a single-run Stage-3 checker PASS.
2. Human-aware navigation using the RD-03D radar ([design](ATLAS_HUMAN_AWARE_NAVIGATION_DESIGN_2026-11-16.md)).
3. Full-home 3D mapping (Astra calibration, RTAB-Map, accepted 3D map).
4. Astra features one at a time, only when not driving: follow-me, gestures.
5. Robot arm (step 10), after the hardware exists and has its own safety plan.
