# Project ATLAS Offline Agent Team and Experience Plan

Date: 2026-08-10

## Mission objective

ATLAS must reliably accept a command such as "go to Dhruv's room", navigate there, recover from ordinary blocked-path and no-progress failures, verify arrival, and return home. Core motion, safety, localization, recovery, and known-place missions must work without internet access.

## Decisions already agreed

1. Use the existing Jetson Orin Nano Super 8GB. Do not add major hardware until evidence proves a sensing blind spot.
2. Use one shared mission-planning model with multiple lightweight specialist ROS roles. Do not run a separate large model for every role.
3. Keep deterministic safety outside the AI. The command mux, stale-command watchdog, collision checks, E-stop, speed limits, and Nav2 remain authoritative.
4. Keep BME680, AMG8833, power, temperature, and environmental telemetry active.
5. Keep the Mission AI supervisor active. Pause only heavy vision/tracking or duplicate video/dashboard processes when measured timing data proves they interfere with navigation.
6. Real-time navigation and recovery must be offline-first. Internet research is optional and may not sit in the motion-control loop.
7. Store successful and failed mission experience locally so verified recovery knowledge becomes reusable offline.
8. Internet-derived changes, downloaded software, firmware changes, safety-limit changes, and motor calibration changes require Dhruv's approval.

## Agent-team architecture

### Mission Director

Parses Dhruv's intent, creates a bounded allowlisted plan, assigns work, observes results, and never reports completion before verification.

### Safety Officer

Has veto authority over every physical action. It checks E-stop state, command freshness, battery, localization health, LiDAR freshness, collision clearance, current mode, and retry limits.

### Driver Agent

Dispatches named-place and return-home goals through Nav2. It never invents direct wheel PWM or bypasses the command mux.

### Localization Agent

Monitors encoders, IMU, EKF, `/odom`, `odom -> base_link`, `map -> odom`, AMCL/SLAM confidence, timestamp age, and transform continuity.

### Perception Agent

Summarizes LiDAR, ultrasonic, radar, and optional camera observations into obstacle geometry and sensor health. Object classification is not required for basic collision avoidance.

### Recovery Agent

Classifies blocked path, no progress, stale costmap, localization loss, traction failure, and controller failure. It may select only prevalidated bounded recovery behaviors.

### Systems Agent

Monitors systemd services, ROS topic rates, CPU, GPU, RAM, temperature, storage, power, network, and node restart counts. It may automatically restart only allowlisted non-motion services.

### Internet Research Agent

Runs only while ATLAS is safely stopped. It packages evidence, searches trusted documentation, proposes a fix, and stores a cited research note. It cannot directly install packages or modify safety-critical configuration.

### Mission Recorder

Records mission state transitions, commands, sensor-health summaries, recovery attempts, outcomes, maps, named places, benchmark results, and the last known-good software commit.

### Voice and Communication Agent

Reports concise status to Dhruv and converts authenticated voice requests into Mission Director requests. It must clearly say when ATLAS is stopped, recovering, degraded, waiting for confirmation, complete, or failed.

## Local experience store

Use a lightweight SQLite database plus bounded rosbag/MCAP evidence files. A database server or many AI models are not required.

Proposed paths:

```text
/home/jetson/project_atlas/data/experience/atlas_experience.sqlite3
/home/jetson/project_atlas/data/experience/episodes/<episode-id>/
/home/jetson/project_atlas/data/research/
/home/jetson/project_atlas/maps/
/home/jetson/project_atlas/config/named_places.json
```

Each experience episode stores:

- Timestamp, software commit, map ID, mission ID, start pose, goal pose, and operating mode.
- Failure class and human-readable reason.
- LiDAR clearance sectors, ultrasonic values, footprint, local/global costmap state, and localization quality.
- Commanded and measured motion, steering, encoder response, IMU motion, odometry, and TF age.
- Recovery behavior, parameters, bounded distance, retry count, and safety decisions.
- Outcome: success, failure, manual intervention, collision-free verification, and final pose error.
- Whether the case is `candidate`, `validated`, `rejected`, or `retired`.

Raw sensor recordings are useful evidence but must be rotated. Keep compact summaries and validated cases permanently; cap large raw recordings by age and total disk usage.

## Learning from Dhruv's manual recovery

When Dhruv manually rescues ATLAS, record remote commands together with LiDAR, costmaps, odometry, TF, steering, encoders, and the final outcome. Convert the recording into a candidate recovery case.

ATLAS must never blindly replay an old command sequence. Before reuse it must:

1. Match the current failure class and obstacle geometry.
2. Confirm localization and sensor freshness.
3. Recalculate clearance for the current map and footprint.
4. Collision-check the proposed maneuver.
5. Enforce current speed, distance, timeout, and retry limits.
6. Prefer a case only after controlled validation and repeated collision-free success.

A strategy becomes automatically selectable only after at least three controlled successes, zero collisions, and explicit approval. The final acceptance benchmark remains stricter.

## Internet-assisted improvement

Internet access may help diagnose an unknown failure, but it must not be required to move or stop.

Workflow:

1. Stop and hold the rover.
2. Save the complete evidence bundle.
3. Search official or primary documentation.
4. Produce a proposed explanation and patch.
5. Test the proposal without ground motion, then wheels lifted, simulation/replay, or a controlled low-speed test as appropriate.
6. Ask Dhruv before persistent software, firmware, calibration, or safety changes.
7. Record the result locally so the same problem can be handled offline later.

## Permission classes

### Class A - automatic and non-motion

- Stop/cancel navigation.
- Save evidence and maps.
- Rotate logs.
- Restart allowlisted dashboard, camera-stream, or non-authoritative sensor-display services.
- Switch between already configured network links.

### Class B - automatic only while safely stopped

- Clear Nav2 costmaps.
- Restart an allowlisted localization or sensor service.
- Reload the last verified map.
- Perform one prevalidated, sensor-checked bounded recovery after deterministic preflight.

### Class C - Dhruv approval required

- Install or remove software.
- Apply internet-generated code.
- Change firmware, motor calibration, footprint, safety clearance, speed, power mode, or command priority.
- Disable a watchdog, E-stop, collision check, or required sensor gate.

## Required operating modes

Only one high-level mode may own autonomy at a time:

```text
BOOTING -> IDLE -> MAPPING -> STOP_AND_SAVE -> LOCALIZATION
                         \-> RECOVERING -> MAPPING

LOCALIZATION -> NAVIGATING -> VERIFYING -> COMPLETE
                            \-> RECOVERING -> NAVIGATING

Any mode -> FAILED_SAFE -> IDLE
```

The mode manager must start and stop SLAM, map server, AMCL, Nav2, Explore Lite, and recovery services in a deterministic order. Mapping and saved-map localization may not publish competing `map -> odom` transforms.

## First online implementation sequence

1. Confirm ATLAS is stationary, E-stop available, battery safe, and network stable.
2. Back up Jetson configuration and capture service enablement, ROS graph, topic publishers, and current Git commit.
3. Reconcile the Jetson with the local repository. Do not overwrite unrelated user changes.
4. Replace the temporary EKF with one persistent authoritative service. Eliminate duplicate odometry and TF publishers.
5. Deploy active Mission AI supervisor mode with confirmation and preflight gates enabled.
6. Inventory installed AI, MCP, model, ROS, and recovery components before installing anything new.
7. Keep environmental telemetry and one diagnostic interface active. Measure heavy vision and duplicate-interface load instead of disabling them blindly.
8. Verify LiDAR, encoders, IMU, EKF, `/odom`, TF, and safety status continuously while stationary.
9. Run a controlled lifted-wheel command-chain test.
10. Run a 30-minute state-estimation soak test with topic-rate, age, restart, CPU, RAM, thermal, and power evidence.
11. Implement and verify the mode manager.
12. Implement the SQLite experience store and Mission Recorder.
13. Implement persistent named places and `save_named_place` / `navigate_named_place` tools.
14. Connect voice requests to the allowlisted named-place tools.
15. Begin controlled ground benchmarks only after all preflight gates pass.

## Acceptance gates

- EKF, odometry, scan, and TF remain fresh for at least 30 minutes with zero unexplained publisher loss.
- Reboot/autostart produces exactly one authoritative odometry publisher and one map transform source for the selected mode.
- Dead-end recovery passes 20/20 controlled trials without manual extraction.
- Named-room navigation passes at least 10 controlled trials.
- Return-home passes at least 10 controlled trials with measured final pose error.
- Reboot-to-mission passes at least 5 trials without hidden manual preparation.
- Zero collisions in the acceptance set.
- Every failed mission stops safely and gives Dhruv a human-readable reason.
- CPU spikes do not correlate with stale scan, odometry, TF, or missed controller deadlines.
- The verified configuration, test evidence, and last-known-good commit are synchronized to GitHub.

## Resource policy

The Jetson is adequate for core navigation. Preserve control-loop headroom by sharing one planning model, using lightweight ROS roles, keeping large local models out of the real-time path, and pausing only workloads proven to cause timing failures. Environmental monitoring remains active. Heavy object detection, tracking, and duplicate video rendering are reintroduced one at a time after navigation acceptance.

## Definition of success

Dhruv can say "ATLAS, go to Dhruv's room". ATLAS verifies readiness, localizes on the saved map, navigates offline, performs bounded recovery when appropriate, verifies arrival, reports status, and returns home on request. If it cannot complete the mission safely, it stops, preserves evidence, explains the exact reason, and improves only through a controlled and recorded validation process.
