# ATLAS current blockers

Updated 2026-10-09. Read alongside the [registry](ATLAS_ROOT_CAUSE_REGISTRY.json) and [master analysis](ATLAS_MASTER_FAILURE_ANALYSIS.md).

## Current verified boundary

Latest observed motor owner: IDLE, stop latched, raw test interface disabled, all outputs zero; PID 3120, NRestarts=0. At 10:07 IST live encoder health reported fresh packets and selected encoders M1–M4, no exclusions, but this is **not** dynamic encoder qualification or proof M3 is physically reliable. Live autonomy separately reported `FAULT: STOP: SLAM MAP DATA LOST`; no autonomous readiness can be inferred from the encoder flag alone.
At about 10:14 IST, read-only ROS CLI checks using the localization service's `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` setting showed `/atlas/mode` publishing `LOCALIZATION` but `/map` with zero publishers and an AMCL subscriber. The localization process and map-server PID existed, and startup logs showed the saved map loaded and lifecycle nodes activated earlier. Thus a running process and successful startup do not establish a **current** map stream. The missing publisher/freshness cause remains under investigation; an earlier CLI check without the matching transport was misleading about `/atlas/mode` and is superseded by this corrected observation.
BMS reported healthy samples around 94–96% between BLE connection timeouts; percentage is a dated observation, not a present guarantee. Source review later found JSON invalidation was correct but scalar SOC/voltage/current were republished stale on failures; the repair was deployed to the stopped Jetson and passed a short healthy-runtime check, but live invalid-path and BLE endurance validation remain. See [BMS freshness repair](BMS_FRESHNESS_REPAIR_2026-10-09.md).
LiDAR service recovered to running/device-health OK after startup retries; stream freshness and navigation readiness still need direct checks.
No movement is authorized by these reports. Keep manual emergency stop authoritative.

## Ordered work / release gates

| Priority | IDs | Next bounded action | Acceptance / what remains |
| --- | --- | --- | --- |
| 1 | 007,006 | Diagnose single-owner BLE connection failures; distinguish phone/radio/stack/reconnect behavior without resetting all Bluetooth | Proposed 10-minute stopped observation with complete fresh four-cell snapshots, no unexplained connection loss; deliberate unavailable BMS stays invalid and inhibits testing. Current result FAIL/unresolved |
| 2 | 004,005 | Add isolated no-motion common-clock timing instrumentation; distinguish client send, DDS arrival, owner execution, receive thread and cache | Three 60-second zero-output trials; current deadlines unchanged; missed-heartbeat injection aborts; cleanup verified even on timeout. Ground rover must not falsely assert lifted mode |
| 3 | 002,003,015 | Audit bounded discovery fairness and startup/ROS environment | Motor-power-off controlled reboot/reconnect/absent-device tests with one verified serial owner, no restart storm or ambiguous binding. Operator approval for disruptive tests |
| 4 | 001 | Fresh operator readiness, short M3-only lifted response test | Correct physical wheel/direction and coherent encoder sign/delta; reliable stop. Does not require every old air test again |
| 5 | 010,013 | Verify exact deployed IMU/EKF authority and wheel model against saved data; keep approved steering unchanged | Stable stationary bias and signed turns, no stale TF; measured wheel/IMU/scan agreement on independent data. No magnetometer authority assumed |
| 6 | 011 | Reuse saved mapping bags; validate composed robot-pose correction and frame-bound places | Accepted geometry, closure, full footprint/connectivity and collision-free plan. Small endpoint closure alone insufficient |
| 7 | 001,011,012 | Only after prerequisites, supervised low-speed ground distance/turn and Dhruv Room→Hall→Dhruv Room | Predeclare measured pose/stopping tolerances and route clearance; no contact/unexplained abort; record recovery and map reload. Then a repeatability campaign, not a one-off success |

Proposed test counts/windows above are future acceptance criteria, not tests already passed. Do not run motor tests while charging or override battery freshness simply because SOC looks high.

## Evidence still needed before changing control

- Exact serial packet and ROS callback timing in the **test mode** that fails.
- BLE connection-stage evidence with competing phone connection ruled in/out; do not presume it.
- Current selected encoder mask and calibration hashes after hardware replacement.
- Why the live selector includes M3 despite earlier exclusion/uncertainty, and whether its loaded-motion counts/sign are coherent.
- Current SLAM map freshness and exact fault origin; do not treat the saved map's presence as an active SLAM stream.
- Physical steering angle versus commanded servo angle if model discrepancy persists; no steering recalibration without explicit scope.
- Source/deployed IMU authority identity and valid retained bias calibration.
- Same-time robot pose, not just transform-origin translation, for map quality.
- Current LiDAR scan age and geometry after the observed startup recovery.

## Work explicitly deferred

No new PID authority, LLM control authority, perception redesign, additional hardware purchase, firmware flashing, automatic motion or safety relaxation is justified by this audit. Existing working features remain intact.

Local Whisper/faster-whisper is a later **voice evaluation**, not a current reliability repair. The active voice path still sends microphone clips to cloud transcription and checks the wake phrase afterward; local Piper speech and optional local text reasoning do not make recognition offline. Preserve that working path and its privacy/motion gates while benchmarking any offline candidate. See [voice ASR evaluation](ATLAS_VOICE_ASR_EVALUATION_PLAN.md).

## What the user needs to do now

No route driving or air lift for this documentation/read-only phase. If a phone is connected to the BMS, report it and disconnect that app before a controlled BLE comparison. A fresh confirmation will be requested only when a specific physical test is ready—not repeatedly while its software prerequisites fail.

## Publication and follow-up

The audit is an initial baseline; full developer transcript review, older unavailable journals, all raw ROS logs, all commit diffs and an independent replay of every historical test remain incomplete. Continue the registry in future sessions; no background automation was installed.

