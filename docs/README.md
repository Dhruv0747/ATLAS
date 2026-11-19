# ATLAS documentation map

Start with the guides below, then browse by topic. Folders: `audits/` investigations and the live blockers log ·
`reports/` dated engineering reports · `design/` upcoming features · `deploy/` deployment records ·
`history/` archived project log · `assets/` maps and photos.

## Start here

| Guide | What it answers |
|---|---|
| [STATUS.md](STATUS.md) | What is done, what is left, the roadmap |
| [COMMANDS.md](COMMANDS.md) | Every dashboard page and command, explained |
| [SAFETY.md](SAFETY.md) | How ATLAS stays safe; rules for working on it |
| [CURRENT_HARDWARE.md](CURRENT_HARDWARE.md) | The commissioned hardware list |
| [audits/ATLAS_CURRENT_BLOCKERS.md](audits/ATLAS_CURRENT_BLOCKERS.md) | Dated log of every test, finding and fix (newest first) |
| [audits/ATLAS_MASTER_FAILURE_ANALYSIS.md](audits/ATLAS_MASTER_FAILURE_ANALYSIS.md) | Long-running failure analysis |
| [history/README_ARCHIVE_2026-11-19.md](history/README_ARCHIVE_2026-11-19.md) | The former README: day-by-day project log up to 2026-11-19 |

## Handovers and project history (16)

<details><summary>Show documents</summary>

- [ATLAS continuation status — 2026-10-11](ATLAS_CONTINUATION_STATUS.md)
- [ATLAS developer handover — 2026-11-04 (snapshot 09:54 IST)](ATLAS_DEVELOPER_HANDOVER_20261104.md)
- [ATLAS final developer handover — 4 November 2026](ATLAS_DEVELOPER_HANDOVER_20261104_FINAL.md)
- [Owner-approved deployment — 11 October 2026, IST](ATLAS_MASTER_DEPLOYMENT_2026-10-11.md)
- [Onboard mapping continuation — 2026-11-02](ATLAS_ONBOARD_MAPPING_CONTINUATION_20261102.md)
- [ATLAS controlled rollout — 2026-10-11](ATLAS_ROLLOUT_2026-10-11.md)
- [ATLAS developer handoff, 2026-10-11 15:10 IST](HANDOFF_2026-10-11.md)
- [Full 2D remap plan (next session)](REMAP_PLAN_NEXT_SESSION.md)
- [Project ATLAS - Autonomous Service Rover](history/README_ARCHIVE_2026-11-19.md)
- [ATLAS — 3-day pause handover](reports/ATLAS_3_DAY_PAUSE_HANDOVER.md)
- [ATLAS takeover, Astra resource-block root cause and recovery (Stage 31)](reports/ATLAS_NEW_DEVELOPER_HANDOVER_AND_RECOVERY.md)
- [ATLAS next-session handoff (written 2026-10-11 20:45 IST)](reports/ATLAS_NEXT_SESSION_HANDOFF.md)
- [PC recorder checkpoint — 14 October 2026](reports/ATLAS_PC_RECORDER_MORNING_HANDOFF.md)
- [ATLAS Recovery incident handover — 2026-10-31](reports/ATLAS_RECOVERY_INCIDENT_HANDOVER_20261031.md)
- [ATLAS single-developer recovery handoff, 2026-10-15](reports/ATLAS_SINGLE_DEVELOPER_RECOVERY_HANDOFF.md)
- [ATLAS Stage32 — final developer handover](reports/ATLAS_STAGE32_DEVELOPER_HANDOVER.md)

</details>

## Safety, mux and remote control (15)

<details><summary>Show documents</summary>

- [Protected publisher gates — preparation only, 2026-11-02](ATLAS_PROTECTED_PUBLISHER_GATES_20261102.md)
- [Exact-live provenance integration — preparation only](ATLAS_PUBLISHER_INTEGRATION_20261102.md)
- [Encoder safety validation — 2026-09-10](ENCODER_SAFETY_VALIDATION_2026-09-10.md)
- [Intercom and camera-control repair — 2026-09-17](INTERCOM_CAMERA_REPAIR_2026-09-17.md)
- [Named-place dry-run safety correction — 2026-10-31](audits/ATLAS_LOCALIZATION_DRY_RUN_GUARD_20261031.md)
- [Approved navigation guard validation — 11 October 2026](audits/ATLAS_NAVIGATION_GUARD_DEPLOYMENT_2026-10-11.md)
- [Proposal: tolerate encoder jitter in the monitoring guard (NOT INSTALLED)](proposals/monitoring-guard-encoder-jitter.md)
- [ATLAS FlySky full integration and Xbox cutover: status report](reports/ATLAS_FLYSKY_FULL_INTEGRATION_AND_CUTOVER.md)
- [ATLAS FlySky SBUS Remote Test Lab (Stage 27): offline build, NOT installed](reports/ATLAS_FLYSKY_SBUS_TEST_LAB.md)
- [Recovery CPU attribution: guarded isolated test preparation — 2026-10-31](reports/ATLAS_RECOVERY_ATTRIBUTION_GUARDED_TEST_20261031.md)
- [End-to-end recovery snapshot runtime safety preparation — 2026-10-31](reports/ATLAS_SNAPSHOT_RUNTIME_SAFETY_READY_20261031.md)
- [Stage 31b candidate: 1-second CPU guard window and Vision Lab stale-summary fix (NOT INSTALLED)](reports/ATLAS_STAGE31B_GUARD_WINDOW_CANDIDATE.md)
- [Stage 32 approved startup guard deployment — 21 October 2026](reports/ATLAS_STAGE32_STARTUP_GUARD_DEPLOYMENT.md)
- [Restart safety controls — offline validation PASS](reports/ATLAS_WEB_RESTART_SAFETY_PACKAGE_20261030.md)
- [ATLAS E-STOP and dashboard safety review: prepared change (2026-10-11)](security/ATLAS_ESTOP_SAFETY_REVIEW_2026-10-11.md)

</details>

## Localization and odometry (44)

<details><summary>Show documents</summary>

- [ATLAS saved-scan odometry diagnostic (2026-10-09)](ATLAS_SCAN_ODOM_DIAGNOSTIC_2026-10-09.md)
- [IM10A stationary bias recheck](IM10A_BIAS_RECHECK_2026-09-16.md)
- [IM10A and Hiwonder GPS commissioning](IM10A_COMMISSIONING_2026-09-16.md)
- [IM10A EKF eligibility check](IM10A_EKF_GATE_2026-09-16.md)
- [IM10A manual left-turn result](IM10A_MANUAL_LEFT_TURN_2026-09-17.md)
- [IM10A manual right-turn check](IM10A_MANUAL_RIGHT_TURN_2026-09-17.md)
- [IM10A lifted motor disturbance screen](IM10A_MOTOR_SCREEN_2026-09-17.md)
- [IM10A isolated EKF result](IM10A_SHADOW_EKF_2026-09-17.md)
- [IM10A stationary verification — awaiting replacement M4](IM10A_STATIONARY_VERIFICATION_2026-09-17.md)
- [IM10A turn disagreement investigation](IM10A_TURN_REVIEW_2026-09-17.md)
- [ATLAS LiDAR Odometry Fusion](LIDAR_ODOMETRY_FUSION.md)
- [Localization: EKF heading diagnosis and fix (2026-11-12)](LOCALIZATION_HEADING_DIAGNOSIS_20261112.md)
- [ATLAS final manual round trip: wrong map pose after return (2026-10-09)](audits/ATLAS_AMCL_FINAL_ROUNDTRIP_2026-10-09.md)
- [ATLAS live round-trip AMCL replication — 2026-10-09](audits/ATLAS_AMCL_LIVE_ROUNDTRIP_2026-10-09.md)
- [Bounded pose diversity while parked: AMCL core experiment](audits/ATLAS_AMCL_PARKED_DIVERSITY_EXPERIMENT_2026-10-10.md)
- [Parked pose diversity across six recordings](audits/ATLAS_AMCL_PARKED_DIVERSITY_MULTIDRIVE_2026-10-10.md)
- [AMCL stationary particle-support finding](audits/ATLAS_AMCL_PARTICLE_COLLAPSE_2026-10-09.md)
- [AMCL replay fidelity, continued from `99bd418`](audits/ATLAS_AMCL_REPLAY_FIDELITY_2026-10-09.md)
- [ATLAS AMCL internal trace — stationary diagnostic](audits/ATLAS_AMCL_SHADOW_TRACE_2026-10-09.md)
- [Stationary AMCL update-policy experiment](audits/ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md)
- [Survival of the low-weight room hypothesis](audits/ATLAS_AMCL_WEAK_HYPOTHESIS_TRACE_2026-10-10.md)
- [Competing map locations versus scans and travel history](audits/ATLAS_COMPETING_POSE_EVIDENCE_2026-10-09.md)
- [Hall cold start localized as Dhruv Room: investigation, 2026-10-10](audits/ATLAS_HALL_COLDSTART_LOCALIZATION_2026-10-10.md)
- [ATLAS localization cross-bag and isolated AMCL audit — 2026-10-09](audits/ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md)
- [Localization during motion: investigation, 2026-10-10](audits/ATLAS_LOCALIZATION_MOTION_INVESTIGATION_2026-10-10.md)
- [Moving localization failure after a verified start: 2026-10-10 18:30](audits/ATLAS_MOVING_LOCALIZATION_FAILURE_2026-10-10.md)
- [Localization recovery, voice fix and startup evidence, 2026-10-11 20:00–20:15 IST](deploy/ATLAS_LOCALIZATION_RECOVERY_2026-10-11_EVENING.md)
- [CHECK MY LOCATION after a restart: UNAVAILABLE root cause and fix (stage 13), 2026-10-11](deploy/ATLAS_LOCATION_CHECK_NO_AMCL_2026-10-11.md)
- [Separate AMCL initial-pose investigation — 2026-10-31](reports/ATLAS_AMCL_INITIAL_POSE_FINDINGS_20261031.md)
- [AMCL ambiguity and manual verification plan — 2026-10-31](reports/ATLAS_AMCL_PLACE_VERIFICATION_PLAN_20261031.md)
- [ATLAS core localization fix: deployment plan (2026-10-15)](reports/ATLAS_CORE_LOCALIZATION_FIX_DEPLOYMENT_PLAN.md)
- [ATLAS core localization resumption — 14 October 2026](reports/ATLAS_CORE_LOCALIZATION_RESUMPTION_REPORT.md)
- [Minimal wheel-pose fusion candidate — Track B](reports/ATLAS_MINIMAL_WHEEL_POSE_FUSION_EVALUATION.md)
- [ATLAS moving localization: upstream yaw evidence and fix gate](reports/ATLAS_MOVING_LOCALIZATION_ROOT_CAUSE_AND_FIX.md)
- [ATLAS next localization milestone — 14 October 2026](reports/ATLAS_NEXT_LOCALIZATION_MILESTONE.md)
- [PC–Jetson connectivity and localization next action](reports/ATLAS_PC_JETSON_CONNECTIVITY_AND_LOCALIZATION_NEXT.md)
- [Stage 17 — steering/yaw validation prepared](reports/ATLAS_STAGE17_STEERING_YAW_VALIDATION.md)
- [Stage 18 — wheel model and independent motion evidence](reports/ATLAS_STAGE18_ODOMETRY_SENSOR_FUSION_REPORT.md)
- [Stage 19 — native replay exposes an initial-state fidelity gap](reports/ATLAS_STAGE19_NATIVE_EKF_AMCL_REPLAY.md)
- [Stage 20 — checkpoint capture development checkpoint](reports/ATLAS_STAGE20_EKF_AMCL_CHECKPOINT_CAPTURE.md)
- [Stage 24: owner confirmation, AMCL seed and parked validation, 2026-10-15 20:49–21:06 IST](reports/ATLAS_STAGE24_AMCL_SEED_VALIDATION.md)
- [Stage 24: live deployment and startup localization recovery, 2026-10-15 20:05–20:12 IST](reports/ATLAS_STAGE24_LOCALIZATION_DEPLOYMENT.md)
- [Stage 24: startup localization after the 19:15 reboot, 2026-10-15](reports/ATLAS_STAGE24_STARTUP_LOCALIZATION.md)
- [Tight-recovery and localization validation — 2026-08-24](validation/2026-08-24-tight-recovery-localization.md)

</details>

## Mapping and maps (14)

<details><summary>Show documents</summary>

- [Mandatory standalone ATLAS mapping architecture](ATLAS_ONBOARD_MAPPING_READINESS_20261030.md)
- [ATLAS RTAB-Map isolated PC preparation](ATLAS_RTABMAP_OFFLINE_20261030.md)
- [LiDAR Acquisition-Time Correction (2026-10-04)](LIDAR_SCAN_TIMING_FIX_2026-10-04.md)
- [M1: CPU budget for the full-time Astra and 3D mapping (2026-11-05, read-only)](M1_MAPPING_CPU_BUDGET_20261105.md)
- [M3 step 1: RTAB-Map parked test (2026-11-12 11:31-11:37, rover parked, E-STOP latched)](M3_3D_MAPPING_STEP1_20261112.md)
- [Mapping31b4542 installation-only preparation](MAPPING_INSTALLATION_PREP_20261102.md)
- [ATLAS manual-mapping session forensics — 2026-10-04](MAPPING_SESSION_FORENSICS_2026-10-04.md)
- [Candidate-map acceptance gate](MAP_ACCEPTANCE_GATE.md)
- [ATLAS Remap Attempt — Rejected Safely (2026-10-04)](REMAP_REJECTION_2026-10-04.md)
- [ATLAS SLAM turn-correction analysis — 2026-10-08](SLAM_TURN_CORRECTION_ANALYSIS_2026-10-08.md)
- [ATLAS sensing and localization reliability investigation](audits/ATLAS_LIDAR_PROVENANCE_2026-10-11.md)
- [Local map repair analysis — Dhruv Room → Hall (2026-10-10)](audits/ATLAS_LOCAL_MAP_REPAIR_DHRUV_HALL_2026-10-10.md)
- [Guided Mapping Assistant — design (2026-11-16)](design/guided_mapping_assistant.md)
- [Standalone onboard mapping implementation — offline candidate](reports/ATLAS_ONBOARD_MAPPING_IMPLEMENTATION_20261030.md)

</details>

## 3D vision, cameras and AI (40)

<details><summary>Show documents</summary>

- [ATLAS Agent Supervisor Deployment — 2026-08-08](AGENT_SUPERVISOR_DEPLOYMENT_2026-08-08.md)
- [ATLAS AI/Robotics Adaptation — Phase 0 Baseline and Execution Gate](AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md)
- [Jetson-local RGB-D recording completion — 2026-11-02](ASTRA_RGBD_RECORDING_SPRINT_20261102.md)
- [ATLAS — 3D preview and CPU headroom validation (24 Oct 2026, 21:20–21:50 IST)](ATLAS_3D_PREVIEW_CPU_HEADROOM_VALIDATION.md)
- [ATLAS: Astra Pro depth for obstacle awareness and navigation](ATLAS_3D_VISION_NAV_INTEGRATION_PLAN.md)
- [Real Astra RGB-D capture readiness — 2026-11-02](ATLAS_ASTRA_REAL_CAPTURE_READINESS_20261102.md)
- [Camera settings — issue #11 (25 Oct 2026)](ATLAS_CAMERA_SETTINGS_ISSUE11.md)
- [Issue #12, M1: depth validation log](ATLAS_ISSUE12_M1_DEPTH_VALIDATION.md)
- [Object Detection / read-only Target Tracking — 2026-11-02](ATLAS_OBJECT_TARGET_READINESS_20261102.md)
- [Project ATLAS Offline Agent Team and Experience Plan](ATLAS_OFFLINE_AGENT_TEAM_PLAN_2026-08-10.md)
- [Existing-session RGB-D recording integration](ATLAS_RGBD_RECORDING_INTEGRATION_20261102.md)
- [Independent Vision host — offline result, 2026-11-04](ATLAS_VISION_HOST_OFFLINE_RESULT_20261104.md)
- [Vision Lab primary task / Neural trial closure — 2026-11-04](ATLAS_VISION_HOST_PREPARATION_20261104.md)
- [Inactive Vision host staging — 2026-11-04, 12:28–12:30 IST](ATLAS_VISION_HOST_STAGING_20261104.md)
- [3D Vision Lab: Object Detection + Target Tracking live (2026-11-04/05)](ATLAS_VISION_LAB_LIVE_20261105.md)
- [ATLAS Visual Cloud](ATLAS_VISUAL_CLOUD.md)
- [Visual Cloud CPU and ROS timing measurement — 24 Oct 2026, 22:16–22:36 IST (owner-approved Option 1, read-only](ATLAS_VISUAL_CLOUD_CPU_MEASUREMENT_20261024.md)
- [Camera-path stationary CPU containment — 2026-10-04](CAMERA_PATH_CPU_2026-10-04.md)
- [On-demand local companion — 2026-09-18](LOCAL_LLM_2026-09-18.md)
- [Track A: Astra depth for navigation obstacles (STAGED, inactive)](TRACK_A_DEPTH_NAV.md)
- [Visual Cloud stationary-load optimization — 2026-10-04](VISUAL_CLOUD_IDLE_CPU_2026-10-04.md)
- [ATLAS voice companion — deployment and verification](VOICE_COMPANION_UPDATE_2026-09-17.md)
- [Voice companion idle-ingress optimization — 2026-10-04](VOICE_IDLE_CPU_2026-10-04.md)
- [ATLAS Visual Cloud: read-only audit (2026-10-11)](audits/ATLAS_VISUAL_CLOUD_AUDIT_2026-10-11.md)
- [ATLAS local voice recognition evaluation](audits/ATLAS_VOICE_ASR_EVALUATION_PLAN.md)
- [ATLAS read-only 3D Vision Lab deployment — 21 October 2026](reports/ATLAS_3D_VISION_LAB_LIVE_DEPLOYMENT.md)
- [ATLAS Astra Pro 3D Vision Lab — 21 October 2026](reports/ATLAS_ASTRA_PRO_3D_VISION_LAB.md)
- [Astra calibration and point-cloud validation — 21 October 2026](reports/ATLAS_ASTRA_PRO_CALIBRATION_AND_POINTCLOUD_VALIDATION.md)
- [Astra standalone vision audit and integration candidate](reports/ATLAS_ASTRA_VISION_INTEGRATION_20261030.md)
- [Astra Depth + RGB startup: evidence and bounded offline correction](reports/ATLAS_DEPTH_RGB_STARTUP_FAILURE_20261021.md)
- [Object Detection / read-only Target Tracking installation — FAIL, rolled back](reports/ATLAS_OBJECT_TARGET_INSTALL_20261030.md)
- [Vision Lab installation diagnosis and corrected offline package](reports/ATLAS_OBJECT_TARGET_INSTALL_DIAGNOSIS_20261030.md)
- [First Object Detection / read-only Target Tracking — repository preparation](reports/ATLAS_OBJECT_TARGET_PREPARATION_20261030.md)
- [Safe backend staging — PASS; activation remains blocked](reports/ATLAS_OBJECT_TARGET_SAFE_STAGING_20261030.md)
- [Existing Vision Lab: six-feature integration candidate](reports/ATLAS_SIX_FEATURE_LAB_20261030.md)
- [Six-feature UI-only deployment preparation](reports/ATLAS_SIX_FEATURE_UI_DEPLOYMENT_20261030.md)
- [Stage 29 — offboard ARM64 preparation, 21 October 2026](reports/ATLAS_STAGE29_ASTRA_OFFBOARD_ARM64_BUILD.md)
- [Stage30 — Astra resource-block recovery, 21 October 2026](reports/ATLAS_STAGE30_ASTRA_RESOURCE_RECOVERY.md)
- [ATLAS Stage 32: Astra Pro Infrared, Calibration and XYZ Point Cloud](reports/ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md)
- [One Depth-only verification after direct-worker deployment](reports/ATLAS_STAGE32_DIRECT_DEPTH_VERIFICATION.md)

</details>

## Hardware and commissioning (29)

<details><summary>Show documents</summary>

- [Stationary calibration measurement sheet](ATLAS_CALIBRATION_MEASUREMENT_SHEET.md)
- [ATLAS software commissioning — 2026-08-10](ATLAS_SOFTWARE_COMMISSIONING_2026-08-10.md)
- [ATLAS closed-loop wheel speed and yaw control](CLOSED_LOOP_DRIVE_PID.md)
- [Phase 2 — evidence-first reliability, increment 1](COMMISSIONING_PHASE2_2026-09-20.md)
- [Project ATLAS commissioning status - 2026-08-06](COMMISSIONING_STATUS_2026-08-06.md)
- [CrowPanel wireless controller plan](CROWPANEL_WIRELESS_CONTROLLER.md)
- [Project ATLAS commissioned hardware](CURRENT_HARDWARE.md)
- [ATLAS automatic network fallback — 2026-09-15](NETWORK_FALLBACK_2026-09-15.md)
- [Three-encoder commissioning — 2026-09-17](THREE_ENCODER_COMMISSIONING_2026-09-17.md)
- [Three-encoder manual ground observation — 2026-09-17](THREE_ENCODER_GROUND_OBSERVATION_2026-09-17.md)
- [Track A: Astra calibration source (2026-11-06)](TRACK_A_FACTORY_CALIBRATION.md)
- [Ultrasonic sample-validity increment — 2026-09-20](ULTRASONIC_VALIDITY_2026-09-20.md)
- [USB role discovery — 2026-09-19](USB_AUTO_DISCOVERY_2026-09-19.md)
- [ATLAS web commissioning audit and staged implementation](WEB_COMMISSIONING_PLAN.md)
- [Commissioning increment 1 — validation and deployment](WEB_COMMISSIONING_VALIDATION_2026-09-20.md)
- [Yahboom diagnostic publication cadence — 2026-10-04](YAHBOOM_DIAGNOSTIC_CADENCE_2026-10-04.md)
- [Encoder distance against LiDAR, by speed (offline), 2026-10-11 20:40 IST](audits/ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11.md)
- [UNO I2C / USB recovery and clock-safe silence watchdog](audits/ATLAS_I2C_USB_RECOVERY_2026-10-20.md)
- [Stage 32: depth admission failure, 21 October 2026](audits/ATLAS_STAGE32_USB_ACCESS_20261021.md)
- [Daly BMS freshness repair — 2026-10-09](audits/BMS_FRESHNESS_REPAIR_2026-10-09.md)
- [Orin Nano CV temperature policy and fresh safety check](reports/ATLAS_ORIN_NANO_CV_THERMAL_POLICY_FIX.md)
- [Corrected temperature probe: one Jetson check](reports/ATLAS_PC_BRIDGE_TEMPERATURE_JETSON_CHECK.md)
- [Temperature admission probe — offline correction](reports/ATLAS_PC_BRIDGE_TEMPERATURE_OFFLINE_FIX.md)
- [ATLAS permanent USB access and reboot recovery](reports/ATLAS_PERMANENT_USB_ACCESS_AND_REBOOT_RECOVERY.md)
- [Stage 17B — single-person front steering measurement](reports/ATLAS_STAGE17B_SINGLE_PERSON_STEERING_TEST.md)
- [Stage 20 — minimum safe public capture option](reports/ATLAS_STAGE20_MINIMUM_SAFE_DEPLOYMENT.md)
- [Stage 25b — encoder fault recovery and Dashboard Motion Chip deployment](reports/ATLAS_STAGE25_ENCODER_FAULT_RECOVERY_AND_DASHBOARD_DEPLOYMENT.md)
- [ATLAS Stage 26 — Motor & Encoder Test Lab (Dashboard V2)](reports/ATLAS_STAGE26_MOTOR_ENCODER_TEST_LAB.md)
- [Wi-Fi / SIM / optional cloud — read-only findings](reports/ATLAS_WIFI_CELLULAR_AUDIT_20261030.md)

</details>

## Performance and CPU (23)

<details><summary>Show documents</summary>

- [Recovery startup CPU burst: attribution from existing evidence (2026-11-04)](ATLAS_RECOVERY_STARTUP_CPU_ATTRIBUTION_20261104.md)
- [Stage 32: thread-profile access checkpoint — 2026-10-21](ATLAS_STAGE32_THREAD_PROFILE_ACCESS_CHECK.md)
- [Sensor-recovery idle CPU optimization — 2026-10-04](SENSOR_RECOVERY_IDLE_CPU_2026-10-04.md)
- [Status-web idle camera CPU containment — 2026-10-04](STATUS_WEB_IDLE_CPU_2026-10-04.md)
- [rover-status-web performance audit (read-only), 2026-10-11](audits/ATLAS_DASHBOARD_SERVER_PERF_AUDIT_2026-10-11.md)
- [Background-search CPU pacing — 15 October 2026](reports/ATLAS_BACKGROUND_SEARCH_CPU_20261015.md)
- [CPU sampler timing correction — offline PASS](reports/ATLAS_CPU_SAMPLER_TIMING_FIX_20261030.md)
- [Observer startup CPU investigation — NO-GO](reports/ATLAS_OBSERVER_STARTUP_CPU_INVESTIGATION_20261030.md)
- [Parked CPU repair and manual-only verification — 15 October 2026](reports/ATLAS_PARKED_CPU_MANUAL_ONLY_20261015.md)
- [Recovery startup attribution preparation — 2026-10-31](reports/ATLAS_RECOVERY_CPU_ATTRIBUTION_PREPARATION_20261031.md)
- [Recovery collector correction and CPU audit — 2026-10-31](reports/ATLAS_RECOVERY_PARTIAL_EVIDENCE_FIX_AND_CPU_AUDIT_20261031.md)
- [Isolated snapshot benchmark safety wrapper — 2026-10-31](reports/ATLAS_SNAPSHOT_BENCHMARK_WRAPPER_20261031.md)
- [One isolated Jetson snapshot benchmark — PASS — 2026-10-31](reports/ATLAS_SNAPSHOT_JETSON_BENCHMARK_RESULT_20261031.md)
- [Stage20 CPU headroom and installation fix — 14 October 2026](reports/ATLAS_STAGE20_CPU_HEADROOM_AND_INSTALLATION_FIX.md)
- [Stage20 CPU optimization — bounded dashboard candidate, 14 October 2026](reports/ATLAS_STAGE20_CPU_OPTIMIZATION_REPORT.md)
- [Stage 20 dashboard executor CPU decision — 2026-10-14](reports/ATLAS_STAGE20_DASHBOARD_EXECUTOR_CPU_FIX.md)
- [Stage 20 recorder startup CPU investigation](reports/ATLAS_STAGE20_RECORDER_CPU_SPIKE_ROOT_CAUSE.md)
- [ATLAS Stage 26: CPU A/B findings (rover-status-web)](reports/ATLAS_STAGE26_CPU_AB_FINDINGS.md)
- [Stage 32: all-process CPU accounting after 56346db](reports/ATLAS_STAGE32_AGGREGATE_CPU_ACCOUNTING.md)
- [Offline depth-preview CPU optimization](reports/ATLAS_STAGE32_PREVIEW_CPU_OPTIMIZATION.md)
- [Remaining CPU: dominant cost unresolved; exact-live JSON candidate prepared](reports/ATLAS_STAGE32_REMAINING_CPU_AND_JSON_CANDIDATE.md)
- [Web shutdown CPU — cause UNKNOWN; activation NO-GO](reports/ATLAS_WEB_SHUTDOWN_CPU_ASSESSMENT_20261030.md)
- [Timestamp-corrected controlled attempt — FAIL, CPU admission rejected](reports/ATLAS_WEB_TIMING_RETRY_RESULT_20261030.md)

</details>

## Recovery, startup and deployment (68)

<details><summary>Show documents</summary>

- [Source provenance — offline implementation, 2026-11-02](ATLAS_SOURCE_PROVENANCE_20261102.md)
- [Bound Object/Target installation transaction — PREPARATION ONLY](ATLAS_WEB_BINDING_READY_20261102.md)
- [Live Jetson snapshot — 2026-11-06](JETSON_LIVE_SNAPSHOT_20261106.md)
- [Isolated Jetson recorder validation — 2026-10-11](MOTION_RECORDER_HUMBLE_VALIDATION_2026-10-11.md)
- [Motion-triggered diagnostic recorder — offline implementation](MOTION_TRIGGERED_RECORDER_2026-10-11.md)
- [ATLAS web diagnostics deployment — 15 September 2026](WEB_DIAGNOSTICS_2026-09-15.md)
- [Developer branch review — 2026-10-10](audits/ATLAS_DEVELOPER_BRANCH_REVIEW_2026-10-10.md)
- [ATLAS deployment record and consolidated status, 2026-10-11 (13:10 IST)](deploy/ATLAS_DEPLOYMENT_RECORD_2026-10-11.md)
- [Stage 1 / 1b: isolated test results (2026-10-11)](deploy/ATLAS_STAGE1_ISOLATED_TEST_RESULTS_2026-10-11.md)
- [Stage 1 (and 1b): supervised on-device procedure](deploy/ATLAS_STAGE1_ONDEVICE_PROCEDURE_2026-10-11.md)
- [ATLAS staged deployment plan: four independent stages (2026-10-11)](deploy/ATLAS_STAGED_DEPLOYMENT_2026-10-11.md)
- [ATLAS Dashboard V2 redesign: Home and 3D Vision Lab (Stage 31)](reports/ATLAS_DASHBOARD_V2_UI_REDESIGN.md)
- [ATLAS offboard PC recording feasibility — 2026-10-14](reports/ATLAS_OFFBOARD_PC_RECORDING_FEASIBILITY.md)
- [Original recovery restoration attempt — preflight FAIL — 2026-10-31](reports/ATLAS_ORIGINAL_RECOVERY_PREFLIGHT_FAILURE_20261031.md)
- [Original recovery restoration preparation — 2026-10-31](reports/ATLAS_ORIGINAL_RECOVERY_RESTORE_PREPARATION_20261031.md)
- [Owner-authorized restoration retry after Xbox B — FAIL — 2026-10-31](reports/ATLAS_ORIGINAL_RECOVERY_RETRY_RESULT_20261031.md)
- [Approved stationary bridge attempt — blocked at preflight](reports/ATLAS_PC_BRIDGE_STATIONARY_ATTEMPT_20261015.md)
- [ATLAS PC offboard recorder readiness — 15 October 2026](reports/ATLAS_PC_OFFBOARD_RECORDER_READINESS.md)
- [Exact-live production snapshot integration preparation — 2026-10-31](reports/ATLAS_PRODUCTION_SNAPSHOT_PREPARATION_20261031.md)
- [Passive Jetson attribution benchmark — 2026-10-31](reports/ATLAS_RECOVERY_ATTRIBUTION_JETSON_RESULT_20261031.md)
- [Corrected Recovery restoration result — 2026-10-31](reports/ATLAS_RECOVERY_CORRECTED_ATTEMPT_RESULT_20261031.md)
- [Corrected Recovery restoration package — 2026-10-31](reports/ATLAS_RECOVERY_CORRECTED_RESTORATION_PACKAGE_20261031.md)
- [One diagnostic Recovery restoration — 2026-10-31 result](reports/ATLAS_RECOVERY_DIAGNOSTIC_ATTEMPT_RESULT_20261031.md)
- [Recovery overload: saved kernel-time evidence — 2026-10-31](reports/ATLAS_RECOVERY_KERNEL_TIME_FINDING_20261031.md)
- [Recovery snapshot runtime-validation preparation — 2026-10-31](reports/ATLAS_RECOVERY_SNAPSHOT_RUNTIME_PREPARATION_20261031.md)
- [Original Recovery startup diagnostic — final offline preparation, 2026-10-31](reports/ATLAS_RECOVERY_STARTUP_DIAGNOSTIC_PACKAGE_20261031.md)
- [Priority incident: original recovery startup CPU overload — 2026-10-31](reports/ATLAS_RECOVERY_STARTUP_ROOT_CAUSE_REVIEW_20261031.md)
- [Recovery startup type-loading correction — 2026-10-31](reports/ATLAS_RECOVERY_TYPE_PRELOAD_CORRECTION_20261031.md)
- [Snapshot producer installation-only — PASS — 2026-10-31](reports/ATLAS_SNAPSHOT_INSTALL_RESULT_20261031.md)
- [One recovery-only snapshot runtime validation — FAIL — 2026-10-31](reports/ATLAS_SNAPSHOT_RUNTIME_RESULT_20261031.md)
- [Existing-observation supervisor integration — offline PASS](reports/ATLAS_SNAPSHOT_SUPERVISOR_INTEGRATION_20261030.md)
- [Snapshot verification preparation — 2026-10-31](reports/ATLAS_SNAPSHOT_VERIFICATION_PREPARATION_20261031.md)
- [Stage20 30-second upgrade readiness — 14 October 2026](reports/ATLAS_STAGE20_30S_UPGRADE_READINESS.md)
- [Stage 20 deployment-readiness assessment — 14 October 2026](reports/ATLAS_STAGE20_DEPLOYMENT_READINESS_REPORT.md)
- [First live30s capture — preflight only](reports/ATLAS_STAGE20_FIRST_LIVE_30S_CAPTURE.md)
- [First live30s attempt — NOT SUCCESSFUL](reports/ATLAS_STAGE20_FIRST_SUCCESSFUL_LIVE_CAPTURE.md)
- [Stage20 installation-only result — 14 October 2026](reports/ATLAS_STAGE20_INSTALLATION_ONLY_RESULT.md)
- [Stage20 installation failure investigation — 14 October 2026](reports/ATLAS_STAGE20_INSTALL_FAILURE_ROOT_CAUSE.md)
- [Stage 20 live recorder validation preparation — 2026-10-14](reports/ATLAS_STAGE20_LIVE_RECORDER_VALIDATION_PLAN.md)
- [Stage20 activation evidence correction — 14 October 2026](reports/ATLAS_STAGE20_RECORDING_ACTIVATION_FAILURE_FIX.md)
- [Stage20 single supervised installation retry — 14 October 2026](reports/ATLAS_STAGE20_SUPERVISED_RETRY_RESULT.md)
- [Stage 21: driver stop anchor deployment, 2026-10-15](reports/ATLAS_STAGE21_DRIVER_STOP_ANCHOR_DEPLOYMENT.md)
- [Motion validation readiness (Stage 21 follow-up), 2026-10-15 13:45 IST](reports/ATLAS_STAGE21_MOTION_VALIDATION_READINESS.md)
- [Stage 22: steering-validation recorder profile, 2026-10-15](reports/ATLAS_STAGE22_RECORDER_DEPLOYMENT.md)
- [Stage 24 post-deployment location recovery, 2026-10-15 20:22–20:40 IST](reports/ATLAS_STAGE24_POST_DEPLOYMENT_LOCATION_RECOVERY.md)
- [Stage 25 — round-trip root cause, targeted fix and deployment readiness](reports/ATLAS_STAGE25_ROUNDTRIP_ROOT_CAUSE_AND_FIX.md)
- [ATLAS Stage 26b: Home Dashboard shortcut to the Test Lab (deployed)](reports/ATLAS_STAGE26B_HOME_SHORTCUT_DEPLOYMENT.md)
- [ATLAS Stage 26: Test Lab live deployment (read-only)](reports/ATLAS_STAGE26_TESTLAB_LIVE_DEPLOYMENT.md)
- [Stage 31B live deployment and Depth-only test (21 Oct 2026, 15:07–15:13 IST)](reports/ATLAS_STAGE31B_LIVE_DEPLOYMENT.md)
- [Stage 31 live deployment: Home UI, Astra private domain, one Depth test (21 Oct 2026)](reports/ATLAS_STAGE31_LIVE_DEPLOYMENT.md)
- [Stage 32 cleanup deployment and one combined verification](reports/ATLAS_STAGE32_CLEANUP_LIVE_RESULT_20261021.md)
- [Stage 32: offline dashboard snapshot optimization](reports/ATLAS_STAGE32_DASHBOARD_SNAPSHOT_OPTIMIZATION.md)
- [Stage 32 direct-worker launch deployment](reports/ATLAS_STAGE32_DIRECT_LAUNCH_DEPLOYMENT.md)
- [Stage 32: remove repeated shell/ROS setup before worker admission](reports/ATLAS_STAGE32_DIRECT_WORKER_LAUNCH.md)
- [Stage32 exact-live snapshot optimization — installed and verified](reports/ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_DEPLOYMENT.md)
- [Stage32 exact-live dashboard patch — prepared, NOT deployed](reports/ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_PACKAGE.md)
- [Depth preview core deployment — verified](reports/ATLAS_STAGE32_PREVIEW_CORE_DEPLOYMENT.md)
- [One guarded Depth-only attempt after97735e9](reports/ATLAS_STAGE32_PREVIEW_CORE_LIVE_RESULT.md)
- [Stage32 dashboard snapshot deployment: aborted before modification](reports/ATLAS_STAGE32_SNAPSHOT_DEPLOYMENT_BLOCKED.md)
- [Stage 32 startup coverage and bounded integrity candidate](reports/ATLAS_STAGE32_STARTUP_COVERAGE_CANDIDATE.md)
- [Approved single UI attempt — FAIL, rollback VERIFIED](reports/ATLAS_UI_DEPLOYMENT_ATTEMPT_20261030.md)
- [Corrected six-panel UI deployment — PASS](reports/ATLAS_UI_DEPLOYMENT_PASS_20261030.md)
- [UI verification correction only — GO, execution not approved](reports/ATLAS_UI_VERIFIER_CORRECTION_20261030.md)
- [One approved activation attempt — FAIL before production mutation](reports/ATLAS_WEB_ACTIVATION_ATTEMPT_20261030.md)
- [One web-only activation procedure — execution NO-GO](reports/ATLAS_WEB_RESTART_PROCEDURE_20261030.md)
- [ATLAS dashboard: prioritised security and safety fix proposal (2026-10-11)](security/ATLAS_DASHBOARD_SECURITY_FIX_PROPOSAL_2026-10-11.md)
- [ATLAS Glass UI V2 — architecture audit and decision (2026-10-11)](ui/ATLAS_GLASS_UI_V2_ARCHITECTURE.md)
- [ATLAS Glass UI V2: prototype and feature-preservation report (2026-10-11)](ui/ATLAS_GLASS_UI_V2_PROTOTYPE_REPORT_2026-10-11.md)

</details>

## Other (20)

<details><summary>Show documents</summary>

- [ATLAS Human-Aware Navigation — Design (2026-11-16)](ATLAS_HUMAN_AWARE_NAVIGATION_DESIGN_2026-11-16.md)
- [Issue #12, M0: baseline and source of truth (26 Oct 2026)](ATLAS_ISSUE12_M0_BASELINE.md)
- [/api/status non-blocking diagnostic cache — independent review (2026-11-04, offline)](ATLAS_STATUS_CACHE_FIX_REVIEW_20261104.md)
- [ATLAS audit repairs and local-LLM decision — 2026-09-17](AUDIT_REPAIRS_2026-09-17.md)
- [Capability-aware fallback: work plan and increment 1](CAPABILITY_FALLBACK_WORK_PLAN_2026-09-20.md)
- [Lifted commissioning failure audit — 2026-10-08](LIFTED_TEST_FAILURE_AUDIT_2026-10-08.md)
- [Navigation foundation audit - 2026-08-04](NAVIGATION_FOUNDATION_AUDIT_2026-08-04.md)
- [Track A gate G2: Astra mount measurements, recovered from existing records (2026-11-06)](TRACK_A_G2_MEASUREMENTS.md)
- [Track A test report — 2026-11-06 (software only)](TRACK_A_TEST_REPORT_20261106.md)
- [UNO bridge polling reduction (offline change)](UNO_BRIDGE_POLLING_2026-10-04.md)
- [CHECK MY LOCATION — Stage A implementation and live validation](audits/ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md)
- [ATLAS complete failure timeline](audits/ATLAS_COMPLETE_FAILURE_TIMELINE.md)
- [Core reliability — new evidence checkpoint](audits/ATLAS_CORE_RELIABILITY_CHECKPOINT_2026-10-11.md)
- [ATLAS core reliability: read-only diagnostics, 2026-10-11 (13:15–13:35 IST)](audits/ATLAS_CORE_RELIABILITY_READONLY_2026-10-11.md)
- [ATLAS master failure analysis](audits/ATLAS_MASTER_FAILURE_ANALYSIS.md)
- [ATLAS navigation gate — stopped check, 2026-10-09](audits/ATLAS_NAVIGATION_GATE_2026-10-09.md)
- [Outbound 1636: AMCL started 0.55 m ahead of the confirmed home spot](audits/ATLAS_OUTBOUND_1636_START_OFFSET_2026-10-10.md)
- [ATLAS reliability review package — 2026-10-10 (evening)](audits/ATLAS_RELIABILITY_REVIEW_2026-10-10.md)
- [Sensor-based stationary position validation](audits/ATLAS_SENSOR_STABILITY_EVIDENCE_2026-10-09.md)
- [ATLAS stage 5: Glass UI V2 as the only dashboard, 2026-10-11](deploy/ATLAS_V2_DEFAULT_2026-10-11.md)

</details>
