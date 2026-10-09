# Project ATLAS - Autonomous Service Rover

Localization release gate (2026-10-09): the recorded Hall → Dhruv Room return
had five large AMCL corrections after stopping. A new
[cross-bag and isolated AMCL audit](docs/audits/ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md)
found recurrent wheel-model/gyro heading disagreement; the velocity-only EKF
candidate improved some replay measures but worsened final-window position
stability. It is **not deployed**. Autonomous room-to-room navigation is not
qualified until moving and stopped localization pass repeatable validation.
The [replay-fidelity follow-up](docs/audits/ATLAS_AMCL_REPLAY_FIDELITY_2026-10-09.md)
found that live mission control requested AMCL no-motion updates once per
second. An isolated replay including those requests reproduced stationary
pose jumps (two versus five live), but no localization fix is validated.

Project-wide evidence baseline: [master failure analysis](docs/audits/ATLAS_MASTER_FAILURE_ANALYSIS.md),
[historical timeline](docs/audits/ATLAS_COMPLETE_FAILURE_TIMELINE.md),
[root-cause registry](docs/audits/ATLAS_ROOT_CAUSE_REGISTRY.json), and
[current blockers](docs/audits/ATLAS_CURRENT_BLOCKERS.md). Initial audit covers
all available Git refs with selected deep investigations; missing history and
remaining transcript/log review are explicitly documented. Not an autonomy pass.

2026-10-09 diagnostic follow-up: BMS errors now identify the failing Bluetooth
transaction stage. Live intermittent `connect` timeouts remain unresolved.
Twelve Daly regression tests pass; this does not qualify powered motor tests.

Latest [lifted-test failure audit](docs/LIFTED_TEST_FAILURE_AUDIT_2026-10-08.md):
six logged attempts requested no motor pulse. Readiness/discovery/timing faults
remain distinct from M3 hardware validation; live commissioning is not passed.

### Continuous lifted-test readiness gate (2026-10-08)

The test client now requires five continuously healthy seconds reported by the
owner before entering a session. Battery, feedback, policy, stationary and stop
checks must pass; a callback gap over 0.35 s resets the window. Missing fields
from older owners fail closed. The default client status wait is 15 s; hardware
freshness, heartbeat and pulse deadlines are unchanged.

64 offline tests passed. A live no-motion test reached the five-second gate,
then entered LOCKED, but subsequently aborted on `heartbeat_expired`. Therefore
this prevents premature startup entry; it does **not** qualify test-mode timing
or M3. All outputs remained zero. Driver and diagnostic client deployed; raw
testing disabled again afterward. Next investigation is end-to-end request and
callback scheduling under load, not another uninstrumented motor pulse.


### Lifted-test timing investigation (2026-10-08)

M3 powered validation is still pending. Stationary tests found delayed cached
encoder/safety-policy processing while the serial receiver remained fresh.
`/atlas/drive_pid/lifted/status` now reports `encoder_cached_age_s`,
`encoder_receiver_age_s` and `encoder_packet_fresh` for diagnosis, without
changing safety decisions. A trial workload-coalescing change failed its
no-motion heartbeat check and was reverted. Do not interpret the generic
`motor_controller_link_lost` reason alone as proof of a USB disconnection.
All test outputs stayed zero; no firmware, steering or PID settings changed.


### Response-driven BMS polling (2026-10-08)

Replaced fixed Bluetooth sleeps with bounded response waits (8-second
transaction deadline, up to 1 second process cleanup). Complete checksummed
pack/cell/extrema responses are still required; timeouts remain unhealthy.
Four live probes completed in 0.4–2.2 s. Ten decoder/transport tests passed.
Deployed reader/helper with a BMS-only restart. Initial service polls were
approximately 4.6–4.7 s apart, and the motor owner received fresh complete cells.
Dashboard briefly retained the prior sample during discovery, then updated.
This short observation is not an endurance qualification or an M3 motor pass.
Safety limits, steering, PID and motor outputs were unchanged; B remains latched.
Rollback: restore `/home/jetson/project_atlas/data/diagnostics/daly_bms_node.before_timing.py`
to `scripts/daly_bms_node.py` and restart `rover-daly-bms.service` while stopped.

Lifted client discovery follow-up (2026-10-08): wait up to 10 seconds for a
matched request subscriber before sending the one-shot entry request. Receiving
status alone does not establish the reverse ROS connection. The next live
attempt reached LOCKED but aborted on `bms_telemetry_stale` before a pulse.
M3 is front-left; its validation remains pending. Do not repeat attempts until
the battery polling interval is fixed. Normal disabled test mode restored.

### Daly Bluetooth packet repair (2026-10-08)

Stationary follow-up: 71 targeted software tests passed (54 lifted client/owner,
7 Daly decoder, 1 policy heartbeat, 9 mux). Dashboard battery subscriptions
were stale and recovered after a dashboard-only restart; sampled battery
timestamps then advanced with complete charging readings. Root cause of the
earlier dashboard subscription stall is not yet established. B stayed latched,
raw test mode disabled, motor outputs zero. A remaining gate is polling latency:
the reconnect-per-poll reader takes about 11.3 s, exceeding the lifted owner's
10 s battery freshness limit. Do not relax the limit or claim M3 validation;
improve and validate reader timing before retrying.

Raw probes showed a 26-byte cell response cut to 20 bytes at default MTU.
Negotiating MTU 64 returned both full frames in three probe polls. The reader
now requests this MTU; the decoder reassembles notification bytes within one
poll and accepts only complete 13-byte frames with valid length/checksum.
Payload `A5` bytes no longer split frames. Partial frames cannot certify cells.
Seven decoder tests passed. Deployed with only the BMS service restarted;
long-duration reliability remains unverified. No motor pulse was issued.
Backup: `/home/jetson/project_atlas/data/diagnostics/daly_bms_node.before_mtu.py`;
rollback by restoring it to `scripts/daly_bms_node.py` and restarting
`rover-daly-bms.service` (restores known parser defects).

### Lifted-test startup battery preflight (2026-10-08)

The operator client waits for an IDLE owner, latched stop, released B button,
and fresh complete healthy BMS data before requesting entry. Restarting the
base clears its battery cache: the previous attempt was rejected as
`bms_unhealthy`, not a missing operator reset. Rejections now surface directly
instead of being obscured by a LOCKED timeout and no-session heartbeats.
54 offline client/owner tests passed. The diagnostic client was updated on
Jetson without service restart or motor commands. This is not an M3 pass.
Rollback client backup: `/home/jetson/project_atlas/data/diagnostics/atlas_drive_pid_lifted_client.before_preflight.py`.

### Control-policy heartbeat (2026-10-08)

The mux now publishes mode/policy every 100 ms, instead of 500 ms. The
lifted owner's 500 ms stale-policy deadline remains unchanged. Previously
observed 493–507 ms delivery intervals could trip that deadline without a
communication outage. This change does not alter steering or stop priority.
47 targeted offline tests passed; deployed to Jetson with the mux restarted
and stop latched. A short stationary check showed approximately 10 Hz,
with no motor pulse issued. M3 encoder validation remains pending.
Rollback: restore `/home/jetson/project_atlas/data/diagnostics/atlas_cmd_vel_mux.before_heartbeat_20261008.py`
to `/home/jetson/project_atlas/scripts/atlas_cmd_vel_mux.py` and restart
`atlas-cmd-vel-mux.service` while stopped. This restores the known timing defect.

### USB discovery and incomplete BMS messages

USB ownership checks retry one `fuser` timeout with a six-second budget after
the initial two-second attempt. Repeated timeouts still fail closed; no port
is treated as free without a clean ownership check and passive protocol match.
This mitigates startup timeout failure, not the underlying system load.

Daly snapshots now expose `cells_complete` and `missing_cell_indices`.
Incomplete polls omit `cells_v` and report `ok:false` instead of filling missing
cells with zero. Previous polls are never merged to fake a complete reading.
The motor test remains blocked until a fresh complete snapshot passes its
existing voltage/spread checks. Bluetooth delivery itself is not fixed by this.
Both source files were deployed on 2026-10-08; only BMS was restarted. Existing
motor/GPS/IMU processes load the USB helper at their next start. Rollback copies
are under `data/diagnostics/usb_bms_guard_20261008/*.before` on Jetson.

### Encoder calculation diagnostics

`atlas_encoder_snapshot_review.py BAG` reads the synchronized snapshots,
groups nonzero command receipt times into motion windows, and compares integrated
wheel yaw with candidate gyro and gyro-seeded scan ICP. Scan ICP is diagnostic,
not independent ground truth. It never starts a ROS node or commands hardware.

The 2026-10-08 short manual forward/left/right recording
`encoder_turn_snapshot-20261008-144037` captured 665 snapshots without sequence
gaps or stale flags. In the 70-snapshot motion window, all four wheels were
accepted 47 times and M1/M2/M4 alone 23 times. Raw count changes were
`[3560, -3687, 874, -3569]`; M3 is discrepant but the cause is not proven.
Net wheel yaw was +3.47 degrees, candidate gyro -8.26 degrees and scan ICP
-2.11 degrees (48/48 adjacent pairs, median residual 7.24 mm). These are net
changes across both turns, not separate left/right accuracy measurements.
This recording verifies diagnostic capture, not navigation accuracy. No steering
or calibration change was made; keep this bag for further per-turn investigation.

Per-turn review splits by commanded curvature sign (threshold 0.15/m), not by
observed gyro direction. Runs under 0.25 seconds are omitted from the per-run
table; whole-motion results retain them. Positive-curvature windows at
27.057–28.556 s and 28.661–29.964 s gave wheel/gyro yaw respectively
18.90/3.75 and 7.66/6.01 degrees. The negative window at 30.259–32.257 s
gave -23.09/-18.01 degrees. Signs are model labels, not physical steering
calibration. Gyro-seeded ICP gave 7.17, 6.25, -15.63 degrees; zero-seeded ICP
gave 3.47, 2.24, -10.25 degrees, demonstrating seed sensitivity. These short
scan windows are not ground truth. M3 counts were small in both directions.
Next investigation is the recorded count/steering timing and geometry model;
do not alter working steering or apply a global scale from this single trial.

Calculation replay of this bag reproduced every recorded accepted delta and
channel selection exactly after initialization (664 comparisons, maximum delta
error 0 m, zero selection mismatches). Median calculation interval was 100.2 ms,
maximum 498.6 ms; maximum reported packet age was 84.8 ms. Thus no missing
snapshot or estimator-replay mismatch was found. This does not prove physical
encoder accuracy, board acquisition timing, or correct steering geometry:
the model uses commanded servo offset as wheel angle, without measured wheel
angle feedback. Scheduling intervals and servo response need separate analysis;
the observed maximum interval alone does not establish the cause of turn error.

A steering-delay sensitivity sweep on 39 moving samples kept recorded distance
fixed and compared predicted yaw rate with interval-averaged candidate gyro.
Delays 0/0.1/0.2/0.3/0.5/0.75/1.0 s gave weighted RMSE
10.76/8.23/6.65/5.56/4.49/6.34/8.82 degrees/s. The 0.5-second hypothesis
fits this recording better, but is not a measured servo delay: count latency,
gyro timing, slip and geometry errors are confounded. No wheel normalization
was recomputed and no held-out trial was used. Do not deploy a 0.5-second
control delay from this result. Production steering remains unchanged.

Repeat trial `left_right_retry-20261008-150806` captured 431 snapshots with
zero sequence gaps/stale flags and exact post-initialization estimator replay.
Two separated command windows gave wheel/gyro yaw +32.87/+24.44 degrees and
-46.10/-41.24 degrees. Gyro-seeded scan ICP gave +25.10/-39.81 degrees, but
zero-seeded results +11.40/-30.70 remain materially different; do not treat ICP
as independent ground truth. During the right-turn moving subwindow, raw
M1/M2/M3/M4 count changes were [1601,-2330,1,-1477]; M3 was rejected in 19 of
22 updates. This is stronger evidence of M3 feedback inconsistency, not proof
of its electrical/mechanical cause. The 0.5-second hypothetical delay changed
yaw-rate RMSE only from 6.38 to 6.27 degrees/s (52 samples), so the prior delay
hypothesis is not established as a general fix. No production tuning changed.

Camera review: `atlas_turn_camera_extract.py BAG NEW_DIRECTORY` extracts original
compressed frames and nearest commanded steering values without modifying images.
Seven frames spanning offsets 26.5–32.5 s were extracted from this trial;
visual inspection at 26.5, 28.5 and 31.5 s showed a hazy close door view, no wheels
or linkages. The footage cannot validate physical steering angle or servo lag.
Sample header-to-bag receipt ages were 14–41 ms, not measurements of full camera
pipeline latency. A fixed external view of the steering linkage would be needed
for direct visual verification; no additional drive or steering command was issued.

`/atlas/encoder_update` is diagnostic JSON in `std_msgs/String`, schema version 1.
When subscribed, each wheel-odometry update reports its sequence, matching ROS
stamp, monotonic time, counts/calibration, commanded steering, path scales,
eligible/accepted/rejected channels, integrated delta, and resulting odometry.
Arrays use M1–M4 order; channel numbers are one-based. Steering is commanded,
not measured. The timestamp identifies the calculation, not a guaranteed atomic
hardware acquisition. Demonstration recordings include this topic. Diagnostic
publication does not grant motion authority or change the odometry calculation.

Activated on the Jetson on 2026-10-08 from commit `1771b1d` after operator
confirmation of stopped rover, remote emergency stop and clear steering linkages.
Four snapshot tests passed on the Jetson. Stationary messages showed all four
channels eligible, fresh packets, zero integrated movement and zero twist;
this does not validate moving encoder accuracy. No driving command was issued.
Rollback copies of both deployed scripts are in
`data/diagnostics/encoder_update_deploy_1771b1d/*.before` on the Jetson.
Restore those copies to their original script paths and restart
`rover-base-telemetry.service` only with the same physical safety checks.

### Isolated SLAM comparison

`atlas_encoder_geometry_audit.py BAG CONFIG_DIRECTORY NEW_JSON` reconstructs
complete four-topic encoder batches and compares commanded-angle, half-angle
and no-normalization cases. It is approximate: separate topic receipt times
do not recover atomic board packets or historical private fault state. Reports
include exclusions and configuration hashes; do not deploy a case simply
because it accepts more samples. The script never commands hardware.

`atlas_pose_correction_trace.py BAG NEW_JSON` traces same-time robot-pose
corrections through a recording and correlates their preceding five-second
odometry/gyro windows with encoder-health reports. Windows overlap; correlations
are not independent trials or proof of hardware failure. No ROS node is created.

`atlas_scan_map_jump_audit.py BAG NEW_JSON` projects event scans into a frozen
prior map under the before/after correction hypotheses. It also reports
same-time robot-position correction, which differs from the origin-dependent
translation of `map -> odom`. This reads recorded data only, not SLAM's internal
correspondence trace; endpoint fit alone cannot certify map accuracy.

`atlas_scan_rotation_sensitivity.py BAG --event UNIX_TIME --output NEW_JSON`
compares unchanged scans with two hypothetical uniform ray-time orders using
recorded gyro Z. It is a read-only sensitivity experiment, not validated deskew;
it creates no ROS node and does not modify scans used by ATLAS. The installed
driver's reported duration is not a verified per-ray acquisition clock.

`atlas_scan_tf_timing_audit.py BAG_DIRECTORY` checks raw/filtered scan stamps,
acquisition duration, recorded TF/odometry yaw alignment and IMU rotation during
scan acquisition. It is read-only. Receipt differences include recorder scheduling;
they are not direct sensor latency measurements. `atlas_fusion_replay.py` also
accepts `--comparison tf_offset` to compare the current offset against zero in
isolation, keeping wheel fusion and every other setting unchanged.

`atlas_fusion_replay.py SOURCE_BAG EKF_YAML NEW_OUTPUT_DIRECTORY --rate 0.5`
compares current wheel-pose-plus-velocity fusion with velocity-only wheel fusion.
Run from a sourced ROS Humble shell after verifying localhost domain 178 is
unused. It snapshots the supplied configuration, strips recorded map/odom TF,
and replays only scans, sensor-frame TF, wheel odometry and candidate IMU data.
It starts isolated EKF/SLAM processes, never actuator nodes. Output bags,
configuration hashes and logs remain diagnostic artifacts, not live deployment.
Use `atlas_summarize_slam_comparison.py` on the two closed result bags; inspect
logs, diagnostic health and scan completeness before interpreting differences.

`project_atlas/scripts/atlas_turn_sensor_audit.py BAG_DIRECTORY` compares scan-fit,
wheel/fused yaw and IMU integration around the largest recorded map correction.
Run with ROS Humble, numpy and scipy installed. It is read-only, starts no ROS
node, and provides diagnostic estimates rather than navigation approval.

`project_atlas/scripts/atlas_prepare_slam_comparison.py` creates a diagnostic
bag containing only `/scan`, `/tf`, and `/tf_static`, removing map transforms.
`atlas_slam_loop_ab.sh` compares loop closure on/off with separate SLAM processes
in localhost ROS domain 177. It never launches a motor driver or replays command
topics. Use a new output directory and confirm this domain is unused before
running. `atlas_summarize_slam_comparison.py` reports corrections and approximate
endpoint differences after both bags close. These are diagnostic results, not
map-promotion or autonomous-driving approval.

### Demand-driven camera publication and lightweight safety heartbeat — 2026-10-04

The IMX708 driver still captures and processes the commissioned 1280×720,
10 FPS stream continuously, but it no longer constructs a 2.76 MB raw ROS
image when no raw subscriber exists and it skips JPEG encoding only when no
compressed subscriber exists. The safety-status node now uses the matching
`/camera/detections/json` detector heartbeat instead of deserializing the
annotated JPEG merely to update freshness. Topics, camera quality, inference,
the 2.5-second camera-freshness boundary, collision logic, and control
authority are unchanged. Both changes are deployed; a post-deployment camera
request returned a fresh 23,737-byte JPEG in 89 ms while safety remained
`READY: STOPPED`, command stayed zero, and the relevant services had zero
automatic restarts. See
[the camera-path deployment note](docs/CAMERA_PATH_CPU_2026-10-04.md).

### Adaptive Visual Cloud collection — 2026-10-04

The read-only Visual Cloud agent now lowers redundant work while ATLAS is
stationary: snapshots change from 1 Hz to 0.2 Hz, ROS graph discovery from
every 5 seconds to every 30 seconds, and non-activity sensor messages stay
serialized until their compact value is due at 1 Hz. Receive timestamps are
still captured for every monitored message, so topic Hz, age, and health
remain evidence-based. A nonzero motion
command or active mapping/navigation/recovery status immediately restores the
original real-time cadence and holds it for 30 seconds. The agent still has no
publisher or control path. It is deployed; idle CPU fell from about 22.3% to
11.1% of one core with zero service restarts. The configured remote endpoint
is still a placeholder, so this validates the local collector rather than a
production cloud deployment. See
[the stationary result](docs/VISUAL_CLOUD_IDLE_CPU_2026-10-04.md).

### Lower-cost voice sensor liveness — 2026-10-04

The voice companion now receives LiDAR and IM10A liveness-only streams as
serialized messages, avoiding construction of unused scan and IMU objects.
Wake, USB/audio, privacy, freshness, cloud fallback, and motion restrictions
are unchanged. The reconciled stopped-only local-LLM hook remains opt-in and
is not enabled by the live environment. The deployed voice service returned
USB online and `IDLE`; its first stationary CPU sample fell from about 26.8%
to 19.2% of one core. See [the deployment note](docs/VOICE_IDLE_CPU_2026-10-04.md).

### Lower-cost sensor-recovery freshness monitoring — 2026-10-04

The bounded recovery node now receives large/high-rate freshness-only streams
as serialized ROS messages rather than constructing unused Python camera,
LiDAR, IMU, odometry, encoder, and map objects. Every arrival still refreshes
the same monotonic timestamp. Fault-bearing status and GNSS payloads remain
decoded, and no topic, QoS, threshold, recovery budget, stop guard, or actuator
authority changed. It is deployed with all monitored streams fresh, zero
service restarts, and process CPU reduced from about 20.0% to 15.3% of one
core. See [the stationary result](docs/SENSOR_RECOVERY_IDLE_CPU_2026-10-04.md).

### Lower-cost UNO sensor-hub polling — 2026-10-04

The Jetson-side UNO bridge now polls at 25 Hz instead of 100 Hz while retaining
the same bounded same-callback serial drain, backlog invalidation, reconnect,
camera-command, and stale-sensor rules. It is deployed; radar, ultrasonic,
thermal, ambient, I2C, and camera-servo telemetry remained live with zero
service restarts, and process CPU fell from about 23.6% to 8.7% of one core.
See [the polling result](docs/UNO_BRIDGE_POLLING_2026-10-04.md).

### Lower-cost Yahboom dashboard telemetry — 2026-10-04

The Yahboom motor owner keeps its 10 Hz motor keepalive, raw encoder, IMU,
wheel-odometry, encoder-health, and safety processing unchanged. Only 22
legacy dashboard wheel/motor summary topics are now cadence-limited to 2 Hz,
removing up to 176 redundant ROS publications per second without changing an
interface. It is deployed: authority streams remained about 10 Hz,
dashboard-only diagnostics about 2 Hz, encoder state `READY`, and process CPU
fell from about 30.1% to 23.4% of one core. See
[the stationary result](docs/YAHBOOM_DIAGNOSTIC_CADENCE_2026-10-04.md).

### Demand-driven status-web camera cache — 2026-10-04

The local status web server now releases its raw and annotated compressed-image
ROS subscriptions two seconds after the last camera HTTP request. A 1 Hz ROS
graph check keeps idle camera availability visible without JPEG deserialization;
the existing subscription and latest-frame cache return automatically when a
dashboard reconnects. Annotated frames are requested only for a live client in
Object mode, and stale frames are never presented as live. It is deployed; a
fresh camera request woke in about 279 ms and returned to idle without a
restart. Remaining status-web CPU is caused by roughly 270 non-camera ROS
callbacks/s across its broad telemetry fan-in, so it was not blindly
throttled. See [the idle CPU note](docs/STATUS_WEB_IDLE_CPU_2026-10-04.md).

### Latched remote-stop publication throttling — 2026-10-04

The command mux still sends an immediate zero command and flushes every queued
source when the software remote stop latches or releases. While the same stop
remains latched, duplicate `/cmd_vel` zeros are limited to a 5 Hz keepalive,
which stays safely inside the Yahboom base driver's 0.45-second command
deadman. Repeated `/atlas/motion_safety` messages are limited to 1 Hz, while
`/atlas/drive_mode` and `/atlas/control_policy` retain their existing 2 Hz
freshness timer. A changed stop reason or latch state is published immediately.
It is deployed; unchanged stop output fell from roughly 33–41 Hz to about
4.7 Hz while immediate stop behavior, zero command, and the latched remote
stop remained intact.

### Fail-closed candidate-map acceptance — 2026-10-04

Mission control now promotes a mapping candidate only after fresh,
same-session TF-jump, settled closure, commissioned-footprint, and
bidirectional plan-only evidence passes. It also checks connectivity directly
in the exact sanitized candidate YAML/PGM bytes with unknown space blocked and
0.18 m obstacle inflation. These checks dispatch no motion. Missing, sparse,
or failed evidence leaves `atlas_latest` and all map-bound locations untouched.
Map YAML/image plus Home, seed, and named places now share rollback handling,
with the authoritative YAML committed last. The gate is deployed and mission
control is `READY`; accepted map ID `d12a1f183177212a3cc8` was preserved. See
[the acceptance-gate procedure](docs/MAP_ACCEPTANCE_GATE.md).

Before dispatching a saved-map named-place or return-home goal, mission control
also checks that the current map-frame pose has known free space and 0.18 m
clearance in those exact accepted map bytes. A pose in unknown or occupied
space fails closed with an explicit status; active SLAM mapping is not judged
against an older saved map. This does not prove localization matches physical
reality, so a conflicting pose still needs stationary verification.

The deployed TF evidence tracker now makes Slam Toolbox's configured
1.5-second `transform_timeout` explicit. Source age and future-skew checks use
the normalized acquisition time, while acceptance reports retain the raw
stamps and separately identify invalid stamps, true publication-order
regressions, and excess normalized future skew. Replaying the rejected
2026-10-04 mapping bag removed its false timestamp error while preserving the
real 1.221502 m / 20.596114 degree discontinuity failures. The allowed offset
is capped at 1.5 seconds; TF geometry, coverage-gap, freshness, 0.15 m
translation, and 5-degree yaw gates are unchanged.

Manual map teaching does not require the operator to reproduce an exact path
or feather the joystick precisely. While `/atlas/mode` is `MAPPING`, the
physical remote is capped to 0.30 m/s linear speed while retaining the
commissioned 1.20 rad/s steering authority; outside mapping, its commissioned
response is unchanged. The mapping envelope and limits are reported on
`/atlas/control_policy`. Emergency-stop handling remains upstream of this
conditioning and retains absolute priority.

Starting manual mapping now has an explicit two-stage readiness contract. The
durable session first reports `state=starting`, `drive_ready=false`, and
`MANUAL MAPPING PREPARING`; ATLAS must stay stopped. Only after fresh SLAM and
Nav2 are ready does it report `state=active`, `drive_ready=true`, save the new
session Home and begin map-quality observation. This prevents a manually
driven route from starting before its map evidence exists. Demonstration bags
also include raw/filtered LiDAR, encoder health, control policy, all bounded
command paths, and the IM10A shadow candidate for complete failure forensics.

### Acquisition-time LiDAR filtering — 2026-10-04

The repository LiDAR self-filter now preserves the `/scan_raw` header on
filtered `/scan` messages. A `LaserScan` timestamp represents first-ray
acquisition time, so replacing it with filter publication time selected a
later rover pose during turns. The rejected-remap bag measured a 131.59 ms
median timestamp shift even though filtering itself took only 5.02 ms median;
at the captured 1.2 rad/s turn rate that is about 9° of possible pose mismatch.
Scan geometry, self-return removal, topics, QoS, TF frames, services, and motion
authority are unchanged. The correction is deployed and passed an 82-pair
stationary capture with exact raw/filtered headers, monotonic stamps, about
4.98 ms median pipeline latency, and a valid acquisition-time TF lookup. See
[the timing note](docs/LIDAR_SCAN_TIMING_FIX_2026-10-04.md) before the next slow
mapping run.

### Live mapping dashboard — 2026-10-02

The command center links to `/mapping`, a read-only live mapping page. It
renders the current ROS occupancy grid from `/map` and overlays the fresh
`map -> base_link` rover pose, `/plan`, `/goal_pose`, mission status, and
source-labelled map locations. Missing or stale streams are shown as
unavailable rather than replaced by cached example data. This page does not
publish motion commands. It deliberately does not substitute raw wheel
odometry when the authoritative `map -> base_link` TF is absent, because those
coordinates can diverge after a driver or EKF restart.
The map page also reports fresh AMCL position/heading uncertainty and flags
recent large pose corrections. A fresh but uncertain map pose is drawn as an
amber **estimate**, not a confidently located rover. These are display-only
diagnostics; the existing Jetson-local motion safety gates remain authoritative.

### AI/robotics adaptation Phase 0 — 2026-09-30

The book-inspired improvement roadmap is governed by the corrected
[Phase 0 baseline and execution gate](docs/AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md).
The book repository is treated as conceptual reference only: no Albert driver,
ROS 1 control loop, CNN-direct `cmd_vel`, old chatbot or educational planner may
replace ATLAS's ROS 2/Nav2/safety architecture. The proposed degraded motion
feedback set is M1/M2/M4 with weak M3 diagnostic-only, but its navigation
validation was revoked on 2026-09-30 after M4 failed to change during a bounded
ground command and the mux correctly stopped on fewer-than-three consensus.
Closed-loop PID and IM10A navigation fusion remain disabled pending evidence. New
AI/VO/PID work is blocked until the bounded straight, turn and supervised
room-round-trip gates pass.

### Encoder diagnostics — transport and wheel consensus separated (2026-09-25)

The motor-board health report now distinguishes a shared Yahboom serial-link
loss from physical wheel-feedback disagreement. It exposes link state, packet
age, packet/checksum/write counters, explicit hardware faults, and separately
lists channels rejected by the dynamic three-of-four distance consensus. Any
real link loss still stops motion immediately and now requires three continuous
seconds of fresh packets before feedback can qualify again. A two-versus-two
wheel split remains fail-closed; LiDAR is not used to hide missing close-range
wheel feedback. Ground commissioning remains locked until at least three wheel
channels agree reliably under traction and the measured distance/turn tests
pass.

### LiDAR odometry fusion candidate — installed, shadow-only (2026-09-25)

ATLAS now runs RF2O scan-matching odometry through a fail-closed validation
gate and a separate shadow EKF. The candidate combines gated, signed LiDAR
body-forward speed, dynamic-consensus wheel velocity and configured IMU yaw-rate on
`/odom/lidar_fused_candidate`. It deliberately publishes no TF and does not
replace the authoritative `/odom` used by Nav2 yet. Stationary drift protection
held gated/fused output at zero for 20 seconds. An isolated replay measured
27.93 cm for the operator-measured 30 cm run; RF2O's false heading and pose
direction are excluded, leaving heading authority with the IMU. Promotion requires a fresh
supervised straight/turn/return validation; autonomy remains locked. The bounded
straight-distance tool now stops from gated LiDAR displacement and reports
wheel odometry separately; the 2026-09-25 20 cm request travelled about 50 cm
while wheel odometry reported 29.4 cm, so the corrected controller still
requires a fresh supervised ground validation before use or promotion. Its
motion path is a 20-second, speed-clamped commissioning lease inside the mux;
manual-only remains enabled and the physical remote stop retains priority.
The dependency and services can be reproduced with
`project_atlas/scripts/install_lidar_odometry.sh`; RF2O is pinned to the tested
upstream Humble commit.

### Live diagnostics refresh — 2026-09-25

The Web dashboard now separates a fresh offline I2C report from a genuinely
live BME680/AMG8833 measurement, derives radar approach/retreat direction from
the target's live range history, and labels each encoder as moving, stopped,
excluded, faulty or stale. The Yahboom service discovers its verified protocol
instead of assuming a CH340 USB index that can change after reconnects. A
supervised lifted check produced changing raw counts from M1–M4; this is useful
hardware evidence but is not metric ground validation. The later measured
ground evidence superseded this snapshot: M3 is now excluded and M1/M2/M4 are
the selected degraded-speed set. Closed-loop PID remains separately disabled and
closed-loop/autonomous gates remain unchanged.
Physical channel identity, forward encoder sign and retained CPR now have one
validated source, `project_atlas/config/encoder_calibration.yaml`, consumed by
both live Yahboom telemetry and the optional PID. Its numeric CPR values are
unchanged and explicitly remain provisional after motor replacement.

### Closed-loop drive PID — implemented, safely disabled (2026-09-23)

ATLAS now has a hardware-independent four-wheel-speed PID core, bounded yaw-rate
steering correction, fail-closed state machine, live per-wheel diagnostics and a
staged evidence recorder. It is integrated into the existing sole motor owner;
there is no second `/cmd_vel` or motor-control path. Repository defaults retain
open-loop operation: PID disabled, hardware/navigation uncommissioned, track
width/gains uncommissioned and encoder requirements locked independently of the
active three-channel navigation-feedback policy. This is implementation and
simulation coverage, not physical authorization. See the
[architecture, tests, commissioning gates and rollback](docs/CLOSED_LOOP_DRIVE_PID.md).

A new sole-owner lifted harness can request one bounded raw motor-channel pulse
and record post-zero encoder evidence, but it is also default off and never
authorizes PID. It requires independent physical-cutoff confirmation, fresh
STOPPED/zero/link/stationary state, Jetson temperature below 80 C, and healthy
fresh 4S BMS cells within 3.00–3.65 V and 0.10 V spread. The presently observed
88 C Jetson and roughly 0.356 V cell spread are explicit blockers. See the same
document for the dry-run client, exact stage gates, evidence, and safe release.

### Ultrasonic validity increment — installed; stationary follow-up open (2026-09-20)

The installed UNO firmware adds atomic sample sequence/age reports; bridge, mux
and the read-only capability view consume `/ultrasonic/validity`. Legacy ONLINE,
no echo, stale/default ranges cannot grant directional safety validity. Existing
LiDAR, manual remote, B-stop/reset, encoder exclusion and autonomy locks remain.
Firmware upload and the paired Jetson deployment succeeded after the operator
entered the bootloader. A subsequent operator power cycle verified autostart and
fresh front/rear ultrasound, BME680, AMG8833, PCA9685 and decoded radar telemetry.
Manual-only, latched stop, zero velocity and M4 exclusion remain unchanged.

Stationary observation exposed intermittent serial-backlog rejection. After
renewed motor/servo-power-OFF confirmation, two narrow bridge corrections were
installed: distinguish a partial next line from complete backlog, and drain
newly arrived bytes within the existing bounded processing cycle. Jetson staging
passes **112/112 offline checks**. No further firmware flash or safety-limit
change was needed. Physical sensor/stopping qualification remains pending; fresh
telemetry is not autonomous permission. See [live results, limitations and
remaining tests](docs/ULTRASONIC_VALIDITY_2026-09-20.md).

Final passive 120-second window: **421 valid front/rear reports, 3 fail-closed
backlog events, zero parse errors/reconnects**. This is improved communication,
not fault-free certification. No motor/servo movement test was run.

Follow-up stationary check: a software communication pause correctly expired
front/rear readings and the commissioning view marked them stale; data returned
after resume. The earlier 50 cm reference was a communication misunderstanding,
not verified ground truth. The operator subsequently confirmed the observed
ultrasonic clearances of approximately **1.35 m front / 0.24 m rear** as plausible.
A simultaneous 20-second comparison measured LiDAR clearance near **2.45 m front /
0.31 m rear** after applying the existing footprint. Different origins, heights
and beam geometry prevent treating those values as interchangeable.

A further 120.15-second passive run produced **418 valid front/rear reports,
6 fail-closed backlog events and zero parse errors**. Ultrasound remains a
secondary close-range source; LiDAR remains primary. Controlled stopping is the
remaining ultrasonic safety test.
The front sensor has now passed stationary close-range screening: all 15 fresh
samples at an operator-set 30–35 cm target measured 31.7–33.2 cm (median 32.8 cm).
It is qualified only for the intended secondary close-range role; the variable
long-range response is advisory. No scale factor or safety limit was changed.

The rear sensor also passes the intended secondary close-obstacle role, with an
accuracy limitation. At an operator-confirmed 30–35 cm target, the first window
measured 28.6–30.7 cm (median 30.6 cm) and the repeated window measured
27.2–28.2 cm (median 28.1 cm). The conservative short bias can trigger warning
earlier. After target repositioning, a confirmation window placed all 15 samples
inside 30–35 cm, measuring 30.1–31.1 cm (median 31.1 cm). Rear close-obstacle
detection passes; this is still not full-range precision. LiDAR remains authoritative.

Physical rear disconnect/reconnect now passes fail-closed behavior. Disconnect
changed rear from valid 31.6 cm to fresh `NO_ECHO` with no retained range while
front stayed valid and motion remained zero. Reconnect created a new sensor-stream
identity and automatically restored fresh rear readings. A subsequent 30.14-second
direct ROS check recorded 102 valid front/rear reports, one fail-closed backlog
report and zero parse errors; rear remained 31.0–33.7 cm. One dashboard request
timed out during recovery, but the direct sensor stream was healthy.

The isolated directional-veto suite also passes **38/38** on Windows and Jetson
staging. Close, missing, stale and no-echo directional data block the applicable
autonomous command. This is logic validation only; the physical stopping-distance
test remains blocked by the existing encoder/autonomy ground-validation gate.

### Capability-aware fallback — read-only first increment, 2026-09-20

Open `/commissioning` → **Sensor authority & fallback readiness** for configured
sensor roles, live cached data age, evidence status and blocked capabilities.
This reuses the existing cache/ledger: no new driver, fusion or control path.
Camera VO is NOT AVAILABLE; IM10A corrected gyro Z is configured as the EKF
yaw-rate source but its authority is currently revoked pending revalidation
after a stationary drift regression; magnetic heading remains excluded; M4
feedback remains excluded.
No alternate profile or automatic goal resumption is approved. See the
[ordered remaining-work list, audit and safety boundary](docs/CAPABILITY_FALLBACK_WORK_PLAN_2026-09-20.md).

### Phase 2: evidence and next-step commissioning — 2026-09-20

On `/commissioning`, use **CONTINUE ATLAS COMMISSIONING** to open the next
unresolved gate. It never starts motion. The same SQLite database now retains
scoped test evidence, explains retests after relevant changes, and preserves
valid results across restart. Old telemetry checks do not become physical PASS.
Steering has explicit **RECORD VERIFIED FRONT/REAR SAVED RANGE** controls after
the operator physically verifies and saves through the existing motor owner.
No navigation, encoder-selection, camera-home or IMU-fusion setting is changed.
This is the first bounded Phase 2 increment, not completion of all physical or
fallback work. See [audit, remaining gates and validation](docs/COMMISSIONING_PHASE2_2026-09-20.md).

Camera startup home selected by user on 2026-09-20: pan **1725 µs**, tilt
**1500 µs**. UNO reconnect/startup, web Home, tracker and mission defaults match.

Commissioning Camera page now includes manual left/right/up/down one-tap controls,
25/50/100 µs steps and return to configured home. It reuses the existing camera
owner, stale-controller gate and pulse bounds; it does not set a new boot home.

Steering Master Reset discards unsaved marks only: it preserves saved
calibration, target positions and traction inhibition. The diagram uses live
owner-saved centres; it cannot measure hand-moved wheel positions. PWM servo
torque release is not verified and no UART torque-off command is used.

Steering diagram correction (2026-09-20): top-view wheel rotation now uses
counterclockwise SVG rotation for increasing/left servo commands. This is a
display-only correction, not a change to motor direction or physical feedback.

### Manual steering commissioning — deployed 2026-09-20

Front-left calibration travel is now bounded at 126° (previously 121°).
The normal operating endpoint remains unchanged until the operator marks and
saves a verified limit. Rear and right-side bounds are unchanged.

The commissioning **Steering** page now has independent front/rear 1°/5°
command jogs, mark centre/left/right, explicit permanent save, and exit to saved
centres. It requires the new motor owner online, a fresh latched drive stop and
operator confirmation that wheels are lifted. Browser loss freezes adjustments
after 1.5 seconds and keeps traction inhibited. Re-enter then explicitly exit;
the page never resets the drive stop. Existing endpoint envelopes cannot be
expanded here. Servo command degrees are not physical tyre-angle feedback.
Calibration lives in `project_atlas/config/steering_calibration.json` and is
loaded by the motor owner at startup. Do not edit it while the owner is running.
Web controls and motor owner deployed after lifted-wheel confirmation. Live
enter/timeout/re-enter/exit verified with centres unchanged and stop latched.
Physical jog directions/ranges and operator calibration remain to be checked.

### Commissioning console — 2026-09-20 (first increment)

Open `/commissioning` on the existing dashboard server, or use its
**COMMISSIONING / HARDWARE CHECK** link. Live subsystem pages distinguish
commanded, reported and calculated values. Non-motion hardware checks and
bounded IMU/GNSS/distance observations have persistent result history.
Actuator commissioning and calibration writes remain locked: an exclusive
owner-side control lease and physical verification are still required.
See [plan](docs/WEB_COMMISSIONING_PLAN.md) and
[validation report](docs/WEB_COMMISSIONING_VALIDATION_2026-09-20.md).

### Front ultrasonic — 2026-09-19

UNO R4 front TRIG D2 / ECHO D3 is enabled by the sensor-hub
`front-ultrasonic.conf` drop-in and reapplied after USB reconnect. This enables
telemetry only; navigation qualification and safety policy are unchanged.

### Steering neutral — 2026-09-18

User-requested servo neutral is now front **90°**, rear **90°** (previously
91°/89°). Existing endpoint limits are unchanged. Commanded neutral is not proof
of physical wheel alignment; straight-ground driving needs revalidation.

### On-demand local companion — 2026-09-18

Added a stopped-only, read-only local conversation backend with automatic model
unloading and explicit resource limits. Existing deterministic telemetry replies,
remote emergency stop, navigation gates and cloud fallback are preserved. The
local model has no action tools or motor-command path. Voice recognition still
needs internet; this is **not a fully offline voice assistant**.
See [installation, current deployment evidence and limitations](docs/LOCAL_LLM_2026-09-18.md).

### Audit-driven reliability repairs — 2026-09-17

The recovery monitor now parses complete encoder-health JSON instead of treating
truncated messages as faults. Motor-link recovery additionally requires fresh,
sustained zero commands and a fresh latched stop. A fresh, explicitly degraded
three-encoder report is not a serial failure or permission for autonomous driving.
The agent role board now distinguishes communication from autonomous readiness.

“Hey ATLAS” alone now gets a cached local English/Hindi acknowledgement after
recognition. Cloud speech recognition is **still required**; that September 17
repair did not install a local LLM or offline wake-word recognizer. Empty/ignored recordings clear the
transcription stage, and microphone privacy is rechecked before playback.

Visual Cloud now receives retained maps/static-TF after late startup and labels
these snapshots `CACHED`, not live traffic. Its map overlay remains a preview:
map/odom/scan frame alignment and a complete buffered TF tree are still pending.
No navigation tuning, wheel motion, IMU fusion or encoder qualification changed.
See [deployment evidence, limits and local-LLM decision](docs/AUDIT_REPAIRS_2026-09-17.md).

### Dynamic encoder commissioning — updated 2026-09-25

M1 rear-left, M2 rear-right, M3 front-left and M4 front-right remain dynamic
odometry candidates. Recorded ground tests showed that weak feedback can move
between M3 and M4, so ATLAS no longer permanently trusts or excludes either
front channel. Each interval uses the median of the largest coherent group of
at least three wheels. A single outlier is rejected; fewer than three agreeing
channels produces zero odometry and keeps autonomy fail-closed. **All four
motors still operate.** Provisional measured CPR values replay the 20 cm and
~70 cm evidence within about 1.3% and 0.1%, respectively, but a fresh distance,
turn and stopping validation is still required before `navigation_validated`
may be enabled. Manual-only restrictions and the remote stop remain in place.
IM10A live EKF fusion has not been enabled by this change.

On 2026-09-25, a fresh stationary bag measured a constant -0.00403 rad/s on
the corrected IM10A topic and about -6.6 degrees of false yaw in 29 seconds.
The saved bias is therefore disabled and no corrected candidate is published.
Raw IM10A monitoring remains live. A repeat test with IM10A authority removed
held EKF yaw at 0.0 degrees over 30 seconds; IM10A requires fresh stationary
bias plus controlled bidirectional turn validation before fusion is restored.

Fresh packet age is checked separately from unchanged counts at rest. M4 raw
counts remain diagnostic and are labelled excluded in the dashboard. A fault
in another selected channel or loss of shared feedback blocks autonomy.
Odometry uses per-wheel increments, avoiding cumulative-position jumps when
channels are rejected/reintroduced; rejected intervals do not catch up later.
Steering-based yaw and existing encoder scales remain provisional after motor
replacement. See [commissioning status](docs/THREE_ENCODER_COMMISSIONING_2026-09-17.md).

### Intercom audio and camera USB recovery — 2026-09-17

Intercom playback now sends only valid PCM samples, excluding PyAV plane padding.
The UNO native sensor-hub driver no longer mistakes its CMSIS-DAP debug interface
or another USB ACM device for the sensor application. Dashboard camera commands
require fresh online controller telemetry; an offline report is not a healthy
heartbeat. See [repair evidence and limitations](docs/INTERCOM_CAMERA_REPAIR_2026-09-17.md).

### Voice companion: useful, truthful status — 2026-09-17

- Say **“Hey ATLAS, battery status”**, **“Hey ATLAS, encoder status”**,
  **“Hey ATLAS, IMU status”**, **“Hey ATLAS, why are you stopped?”**, or
  **“Hey ATLAS, बैटरी कितनी है?”**. Answers use fresh local telemetry;
  recognition of the spoken question still requires cloud transcription.
- Local Piper English/Hindi speech provides startup and bounded automatic
  alerts without cloud TTS. Startup distinguishes voice-online from drive-ready;
  it greets Dhruv once per OS boot, not after every USB reconnect/intercom call.
- Announcements cover BMS low charge, high SOC with a charger-verification
  disclaimer, newly stale LiDAR/IM10A/encoder data, remote-stop latch, and
  allowlisted mission events. A ready encoder link at rest is **not** proof
  that every wheel encoder works. No imagined arrival or map completion.
- Dashboard **ATLAS COMPANION → MUTE AI MIC / ENABLE AI MIC** controls a
  persistent software capture mute. The live acknowledgement is shown below
  the LED legend; stale status is explicitly unknown. This is not a physical
  mic disconnect. TALK / LISTEN is a separate explicit intercom session.
- Blue = voice idle, green = capture, white = processing/buffering, pulsing
  blue = speech. Red also represents software mute or a live call, so read
  the dashboard state; colour alone is not a fault diagnosis.
- Wake phrases are checked **after** cloud transcription; active voiced clips
  can leave the device before a wake phrase is recognized. Mute discards new
  microphone audio on the Jetson; an already-sent request cannot be recalled.
  Speech is AI-generated. The current firmware has no physical privacy-mute
  button; Key2 long-press retains its existing shutdown function.
- Voice stop requests use stop-only `/atlas/voice/stop` and latch the existing
  command mux stop. **Remote B remains the immediate stop**; speech recognition
  is not a safety-rated emergency stop and may need Internet. Voice cannot
  reset the latch. Existing neutral/LB-hold/release remote reset is unchanged.
- Wheel-driving voice actions remain uncommissioned by default
  (`ATLAS_VOICE_MOTION_ENABLED=0`). Even if separately commissioned, fresh mux
  policy, no remote latch, autonomous readiness and encoder health are required;
  existing safety and manual-only restrictions cannot be bypassed.

Tests: `python3 -m unittest discover -s project_atlas/scripts -p test_voice_status.py`.
`verify_voice_stationary.py` synthesizes both languages with HTTP calls forbidden
and observes status/command topics; it publishes no goals or velocity commands.
This feature changes no navigation parameters, IMU authority, or camera firmware.

### IM10A isolated EKF comparison — 2026-09-17

`project_atlas/scripts/atlas_im10a_shadow_test.py` runs a bounded 60-second
wheel-only versus wheel-plus-gyro comparison in `/atlas_imu_shadow`.
Both filters disable TF publication; live `/odom` and its EKF configuration
are unchanged. Only gyro Z is selected; magnetic/Euler heading, acceleration
and the disabled historical bias correction are not used. Stale, invalid or
non-increasing IMU messages are rejected. The test stops its own filters on
exit and saves results outside Git. It is not an autostart service and does
not qualify ATLAS for autonomous operation with the faulty M4 encoder.

### Camera remote — 2026-09-17

D-pad left/right pans and up/down tilts the camera; Y returns it to saved
home (pan 2300 us, tilt 1500 us). LB is not required for camera operation.
Camera commands use a 40 ms minimum interval and only transmit changed axes;
actual responsiveness depends on joystick delivery, the hub and servo speed.
Held movement uses bounded 400-us/s increments, and delayed hub reports are
ignored during an active hold, including at the configured servo limits.
The hub uses bounded batch reads instead of one serial line per 50 ms.
`/arduino/serial_diagnostics` exposes unread USB/parser bytes and processed
line counts. Old pulse reports cannot overwrite a newer unacknowledged target,
even between button presses. Reported pulses are not physical servo feedback.
B is exclusively the rover stop and suppresses camera input in that packet.
Manual camera input pauses automatic camera tracking. Existing 700–2300 us
limits are preserved; no wheel commands are published by this node.
Only `atlas-camera-joystick.service` runs; duplicate `atlas-camera-remote.service`
is disabled. Five mapping tests passed; physical directions need user confirmation.

### Manual commissioning and remote software stop — 2026-09-17

Remote and motor services are enabled at boot. Mux startup is latched stopped:
Xbox B (verified button index 1) latches a zero-output stop for every mux source.
Missing joystick messages for 0.5 s also latch stopped. Releasing B does not
restart motion. Release all buttons and centre sticks, hold LB alone for
2 seconds, then release it to reset. Press LB again with deliberate stick
input to drive. All other buttons must remain released throughout; stick
movement, B, RB or a message gap cancels the gesture. LB is verified Xbox
joystick index 4 (`remote_reset_button`). The complete physical reset gesture
still requires operator verification; the earlier Start/Menu reset was replaced.
Alternatively, after one second fully neutral, deliberately call
`/atlas/remote_stop/reset` (`std_srvs/srv/Trigger`).
Hold LB to drive; release LB to stop manual drive. This software stop is NOT
a substitute for an independent physical motor-power emergency switch.

Live deployment uses `40-manual-commissioning.conf` with
`ATLAS_MANUAL_ONLY=1`: non-REMOTE sources are rejected while commissioning
continues. The passive encoder observer is disabled to avoid serial contention;
the normal base driver publishes feedback. The former commissioning condition
file was retained as `.conf.disabled` and backed up, not deleted. M4 encoder
and rear ultrasonic reliability remain unresolved; autonomy is not released.
Ten stop-state unit tests and live zero-output startup observation passed.
Physical button-to-wheel stopping and remote motion still require operator
validation. No powered movement test was issued as part of this deployment.

### Wheel mapping — 2026-09-17

Steering centres are front 91 and rear 89 (visually confirmed). Steering
limits are unchanged and require checking relative to the new centres.

Confirmed controller order: M1 rear-left, M2 rear-right, M3 front-left,
M4 front-right. Forward PWM signs are `[-,+,-,+]`; validated encoder forward
signs for M1–M3 are `[-,+,+]`. M4 encoder remains faulty/unvalidated. Updated
driver mapping does not authorize driving: commissioning inhibits remain,
and previous metric encoder scales require revalidation after replacements.

### IM10A commissioning — 2026-09-16

The initial stationary bias passed a holdout check, but failed a later recheck
and is now disabled. Magnetometer and sensor Euler heading are diagnostics-only,
excluded from navigation. Sensor internal fusion mode was not changed. Gyro
fusion remains disabled pending measured-turn validation. See
[bias recheck](docs/IM10A_BIAS_RECHECK_2026-09-16.md) and
[turn review](docs/IM10A_TURN_REVIEW_2026-09-17.md).

Hiwonder GPS is now the primary live GPS. IM10A and passive four-channel encoder
monitoring are deployed with autostart and dashboard data. **IMU/navigation
fusion and driving remain inhibited pending physical commissioning.** USB paths
are socket-specific; keep devices in their assigned sockets. See
[commissioning report](docs/IM10A_COMMISSIONING_2026-09-16.md).

### Automatic networking — 2026-09-15

`atlas-network-fallback.service` prefers home Wi-Fi Internet, selects SIM8230G
RNDIS Internet after repeated Wi-Fi failures, and activates **ATLAS-Rescue** if
both Internet checks fail repeatedly. The local-only rescue dashboard is
`http://10.42.0.1:8088/`. Its WPA2 password is provisioned on the Jetson only;
no password is stored in this repository. The normal dashboard NETWORK panel
shows the mode, per-interface Internet checks and hotspot state.
The AP's captive portal opens the dashboard through a supported phone's Wi-Fi
login prompt; tap **Sign in to network** if it does not open automatically.
Direct local links still work. No Internet or automatic motion is implied.

The single radio cannot be a Wi-Fi client and AP simultaneously. Rescue clients
are not disconnected for automatic Wi-Fi recovery; with no clients, home Wi-Fi
is retried every three minutes. See [network setup and test record](docs/NETWORK_FALLBACK_2026-09-15.md).

### Main operator diagnostics — 2026-09-15

Use `http://100.87.208.71:8088/` (Tailscale) or `http://192.168.1.14:8088/`
(current LAN address). **DIAGNOSTICS / LOGS** opens the read-only workbench:
current service state, restart counters, current-boot logs, searchable telemetry,
last-update age, observed callback rates, USB identities and JSON snapshot export.
Visual Cloud remains linked for the ROS graph and mission history. Service state
does not prove sensor validity; a stationary encoder heartbeat is not a motion test.

GNSS now separates communication, satellites in view and position fix. Zero-count
GSV sentences no longer create misleading "DETECTED" bars. `/gps/diagnostics`
identifies the current SIM8230G USB receiver, stale data and serial reconnects.
EOF, changed USB identity and sustained silence reopen only the NMEA reader;
they do not reset the modem, network, motor board or navigation stack.

The unused legacy HDMI dashboard has `Hidden=true`, autostart disabled, and its
generated user unit masked on Jetson. Source remains available as a manual fallback.
The web dashboard and GNSS service remain enabled at boot. Do not expose port 8088
to the public Internet; use the private LAN or Tailscale. See
[deployment and test notes](docs/WEB_DIAGNOSTICS_2026-09-15.md).

### Primary GPS — 2026-09-15

SIM8230G USB GNSS now supplies the existing `/gps/*` topics. The disconnected
L76K/J12 receiver is no longer selected by `atlas-gnss.service`. The NMEA port
uses its USB by-id identity (interface 03), and `atlas-sim8230-usb.service`
restores the option driver binding at boot. Dashboard labels follow this source.
Deployed and built on Jetson; live checksum-validated NMEA verified, but zero
satellites and no position fix at commissioning. Position accuracy remains unverified.

### Steering commissioning checkpoint — 2026-09-09

Physical front steering is Yahboom channel 2, with user-confirmed lifted center
81 degrees. Physical rear is channel 1, with user-confirmed lifted center
114 degrees. Both centers are saved in the boot-enabled base driver.
Front-right operating limit is 50 degrees, approved by the user after the
lifted 81 -> 50 -> 81 test; this is not a measured mechanical hard stop.
Front-left operating limit is 121 degrees, approved after the lifted
81 -> 121 -> 81 test. Rear-right operating limit is 64 degrees, approved after
the lifted 114 -> 64 -> 114 test. Rear-left operating limit is 134 degrees,
approved after the lifted 114 -> 134 -> 114 test. These are user-approved
servo command limits, not measured wheel angles or mechanical hard stops.
Front/rear software labels were corrected while
retaining the existing numeric endpoint envelope per channel. Do not infer that
turn directions, endpoints or ground drift are validated; keep commissioning
lifted until directional checks are complete. Older standalone
steering test scripts may contain obsolete channel/center constants; do not run
them without reviewing them against this checkpoint.

## Secure live-call intercom

ATLAS now has mutually exclusive AI Voice and on-demand WebRTC Live Call
modes. A live call requests browser echo cancellation/noise suppression, turns
the ESP32 speaker LED red, and automatically returns USB audio ownership to the
AI companion when the call ends. The server binds to loopback and must be
published only through authenticated Tailscale HTTPS—not the public Internet.

**Creator: Dhruv Kaushik**

Project ATLAS is an open robotics development project for a four-wheel autonomous service rover. It runs ROS 2 Humble on Ubuntu 22.04 with an NVIDIA Jetson Orin Nano Super 8GB and combines LiDAR SLAM, Nav2 autonomous navigation, wheel odometry, IMU sensor fusion, bounded recovery behaviours, AI vision, voice control, Foxglove, and wireless dashboards.

The Jetson web command center uses a 70%-transparent glass interface. Its live
camera automatically reconnects after a stalled frame request, and the hardware
panel performs a post-boot and continuous health evaluation of sensor feeds,
including individual M1 front-right, M2 front-left, M3 back-right, and M4
back-left encoder message age and count readings.

This repository is the searchable engineering record for ATLAS: ROS 2 source code, launch files, robot parameters, hardware integration, safety controls, autonomous mapping, recovery logic, diagnostics, operating documentation, and commissioning evidence.

The read-only [ATLAS Visual Cloud](docs/ATLAS_VISUAL_CLOUD.md) integration adds
an authenticated ROS graph/traffic agent, historical API and real-time browser
view. It has no cloud-to-velocity or cloud-to-motor interface; all safety and
control authority remains local on the Jetson.

**Search terms:** Project ATLAS rover, Dhruv Kaushik, autonomous rover, ROS 2 Humble, Jetson Orin Nano Super, Nav2, SLAM Toolbox, Explore Lite, LiDAR mapping, Ackermann steering, service robot, autonomous navigation, robot recovery, Foxglove, MCP robotics.

## Current autonomy maturity

- Core navigation foundation: operational with ROS 2, Nav2, LiDAR SLAM, encoder odometry and IMU/EKF fusion.
- Deterministic recovery: implemented for no-progress detection, LiDAR-validated bounded reverse, costmap clearing and replanning.
- Autonomous mapping: functional and under controlled endurance testing.
- Current engineering gate: repeatable TF/odometry reliability and 20/20 controlled dead-end recovery trials.
- Unattended operation is not yet approved; ground tests require a clear area and an operator at the physical emergency stop.

ATLAS uses its 360-degree LiDAR as the primary navigation and obstacle sensor. Ultrasonic sensors provide close-range secondary protection. AI may select high-level goals, but it cannot bypass the deterministic command mux, watchdog or emergency stop.

## Hardware

- Four-wheel rover with wheel encoders and Yahboom motor controller
- RPLIDAR A1, calibrated Yahboom motor-board IMU, ultrasonic sensors, and
  RD-03D radar
- Arduino UNO R4 WiFi sensor hub carries the I2C sensors, RD-03D radar,
  camera PCA9685, and four sequentially sampled ultrasonic channels.
  See [`firmware/atlas_uno_r4_i2c_hub/README.md`](firmware/atlas_uno_r4_i2c_hub/README.md).
- The L76K GNSS uses the Jetson J12 UART directly: L76K RX to header pin 8
  (TX), L76K TX to pin 10 (RX), and common ground; Linux exposes it as
  `/dev/ttyTHS1` at 9600 baud.
- IMX708 Camera Module 3 on a pan/tilt platform
- GNSS, BMS, BME680, AMG8833 8x8 thermal sensor, Wi-Fi, and cellular connectivity
- Jetson onboard INA3221 power telemetry; the removed external INA219 and Pi
  UPS HAT are not part of the commissioned system.

The commissioned sensor transport now uses an Arduino UNO R4 WiFi. It forwards
the PCA9685 (`0x40`) discovery state, BME680 (`0x76`/`0x77`), AMG8833
(`0x68`/`0x69`), RD-03D frames and four
ultrasonic ranges over a fixed Jetson USB physical path. The Jetson bridge
republishes the original ROS 2 topic names, so Nav2, EKF, dashboards and
Foxglove do not depend on the physical bus.

The local web dashboard also consumes a small atomic UNO snapshot as a
read-only fallback when DDS discovery is delayed during simultaneous service
restarts. Fresh ROS messages always take precedence; the fallback carries no
control commands and cannot affect motor or navigation safety.
- ESP32-S3 voice interface and 11-inch touchscreen dashboard

The web Command Center includes both a conventional 2D RD-03D radar scope and
a lightweight **3D PEOPLE** digital-twin view. The latter places up to three
avatars using live radar X/Y coordinates, distance and speed. It is an operator
visualization, not a depth-camera body scan, and it does not alter navigation or
motor commands.

## Mobile notifications

ATLAS can notify Dhruv's Android or iOS phone through the ntfy app when the
rover boots, when the main DALY BMS reaches 20%, and when charging remains at
99% or higher for three consecutive BMS readings. Alert state includes
hysteresis to avoid repeated notifications near a threshold. Notification HTTP
work runs in a separate worker and cannot block ROS motion control.

On the Jetson, run:

```bash
bash /home/jetson/project_atlas/scripts/setup_mobile_notifications.sh
```

Install the ntfy app on the phone and subscribe to the private random topic
printed by the setup helper. The private topic is stored only in
`~/.config/project-atlas/notifications.env`; it must not be committed.

## Planned wireless controller upgrade

The broken 11-inch Jetson-connected display will be replaced by a removable 10.1-inch CrowPanel Advanced ESP32-P4 HMI with its optional camera. It will operate as ATLAS's wireless dashboard and manual controller while the Jetson remains responsible for motors, safety, ROS 2, navigation and AI. See `docs/CROWPANEL_WIRELESS_CONTROLLER.md` for the approved architecture and installation checklist.

## Repository layout

- `project_atlas_ws/src/`: ROS 2 packages and launch/configuration files
- `project_atlas/scripts/`: operational nodes, dashboard, diagnostics, voice, and recovery tools
- `project_atlas/config/`: robot configuration
- `project_atlas/maps/`: current mapping assets

## Citation and authorship

Project ATLAS was created by **Dhruv Kaushik**. Academic papers, articles and derived projects should cite the repository using the metadata in [`CITATION.cff`](CITATION.cff).

Suggested attribution:

> Dhruv Kaushik, Project ATLAS: ROS 2 Autonomous Service Rover, 2026.

## AI and MCP control

`project_atlas/scripts/atlas_mcp_server.py` exposes a small MCP interface for
status, sensors, camera snapshots, navigation stop, emergency stop, mapping and
return-home. It uses the commissioned Jetson gateway and ROS 2 mission/mux
interfaces; it never accesses the motor controller directly.

Motion-capable tools are locked by default. Commission status, sensor, camera
and stop behavior first. Only then set `ATLAS_MCP_ENABLE_MOTION=1` in the MCP
client environment while an operator has access to the physical emergency stop.
The MCP process uses stdio and must be launched by the trusted MCP client. It is
not a standalone systemd daemon or an unauthenticated network API.

Install its isolated dependency set with:

```bash
python3 -m venv /home/jetson/project_atlas/.venv-mcp
/home/jetson/project_atlas/.venv-mcp/bin/pip install \
  -r /home/jetson/project_atlas/requirements-mcp.txt
```

Generated ROS directories, local environments, models, logs, credentials, and historical backups are intentionally excluded.

## Engineering policy

Reliability and safety come before new capability. Implement one feature at a time, build and test it, update documentation, and commit it. Emergency stop must override manual, web, voice, and autonomous commands.

## Development baseline

1. Verify hardware diagnostics and TF.
2. Validate wheel odometry and IMU fusion.
3. Validate localization and Nav2.
4. Tune perception and human-aware behavior only after navigation is stable.

## Commissioned navigation baseline - 2026-08-06

The Jetson migration and primary navigation commissioning sequence are complete.

- Physical footprint: 0.50 x 0.36 m; Nav2 footprint is `[+/-0.25, +/-0.18]`.
- Costmap inflation radius: 0.28 m with cost scaling factor 15.0.
- Wheel order: M1 front-right, M2 front-left, M3 back-right, M4 back-left.
- Installed 125 mm wheels use independently calibrated encoder counts per revolution:
  M1 4048.7, M2 3300.6, M3 4080.1 and M4 2697.8.
- LiDAR centre is 0.30 m behind the front chassis edge, placing it 0.05 m behind
  `base_footprint`; the authoritative static transform is x=-0.05 m, z=0.18 m,
  yaw=pi.
- `/yahboom/odom` is encoder-distance-derived and is fused by the EKF onto `/odom`.
- The Yahboom motor-board IMU is the sole canonical system IMU and has a
  separately recorded stationary calibration.
  Raw controller measurements are available on
  `/yahboom/imu/data_uncalibrated`; software-zeroed attitude, gyro and
  accelerometer measurements are available on `/yahboom/imu/data_calibrated`.
  Its yaw is zeroed relative to each driver start because the controller's
  absolute magnetic origin is not yet trusted. The calibrated values also own
  the standard `/imu/*` dashboard, logging, and health topics. Gyro data is
  deliberately excluded from the EKF until a recorded
  clockwise/counter-clockwise yaw comparison against wheel odometry passes.
- Nav2 uses the one-shot fail-stop behavior tree. It does not accumulate recovery
  movement after a failed short goal.
- Explore Lite holds one frontier goal until completion, abort or genuine
  no-progress timeout. It no longer preempts goals as the frontier boundary moves.
- Exploration stop automatically saves `maps/atlas_latest.yaml` and
  `maps/atlas_latest.pgm`.
- Reboot/autostart verification passed for the base, sensors, SLAM, Nav2, command
  mux, remote, camera, AI, mission controls, Foxglove and dashboard. Autonomous
  exploration remains off after boot until explicitly requested.

Ground autonomous tests always require a clear area and an operator at the
physical emergency stop. The priority command chain remains REMOTE > WEB >
FOXGLOVE > NAV2, with stale-command stopping.

## Safety-constrained mission agent

`atlas_agent_supervisor.py` adds an observe-plan-act-verify layer above the
commissioned ROS 2 stack. It accepts natural mission requests on
`/atlas/agent/command`, creates a maximum four-step plan from a fixed tool
allowlist, publishes its operator-visible state, requires confirmation for
motion, rechecks live safety data, dispatches only high-level mission topics,
and verifies the resulting status. It never publishes velocity commands.

The service is commissioned in `MONITOR_ONLY` mode. In that mode cloud or
offline planning can be tested, but no physical action is dispatched. Runtime
execution can be enabled through `/atlas/agent/set_execution_enabled`; motion
plans still require `/atlas/agent/confirm_plan` and must pass the deterministic
LiDAR, odometry, SLAM, manual-control and battery preflight.

Useful interfaces:

- `/atlas/agent/state`, `/status`, `/plan`, `/decision`, `/response`: dashboard
  and Foxglove visibility
- `/atlas/agent/command` (`std_msgs/String`): natural mission request
- `/atlas/agent/confirm_plan`, `/cancel_plan`: explicit operator gate
- `/atlas/agent/set_execution_enabled`: monitor-only/active selection
- Persistent bounded event memory:
  `~/.config/project_atlas/agent_memory.json`

## Retired hardware

The Portenta H7, Mega 2560, BNO055/BNO08x, external INA219, Pi UPS HAT, and
old 11-inch wired display have been removed from the active source and Jetson.
Their history remains in `CHANGELOG.md`; they must not be reintroduced by an
installer or used as fallback sensor/control paths.
# Dashboard battery indicator

The web header now displays main DALY BMS percentage and net charging/discharging
state. The Power card also shows live net current (A) and power (W); tap either
the card or the header badge for four cell voltages, cell spread, SOC source,
and sample age. Negative current/power means the pack is discharging; positive
means it is charging. Near zero is labelled idle. These are whole-pack net
measurements, not a separate charger-current or Jetson-only measurement.
Missing, invalid, or older-than-10-second BMS data is explicitly marked;
the indicator does not substitute the motor-board voltage estimate.
On a failed Daly Bluetooth read, `/bms/json` reports `ok:false`; scalar BMS
topics must not republish the last successful measurements as if new. The
mission-agent battery preflight uses the coherent JSON status and rejects an
unhealthy or stale snapshot. Deployed Oct 9 with a short healthy-runtime check;
BLE connection endurance and the live invalid-read path remain unvalidated.

# Dashboard shutdown

Use **SHUT DOWN** beside Diagnostics / Logs and confirm to power off the Jetson.
Wait for shutdown before removing power. Physical motor/battery power is separate.
This does not reboot or automatically power ATLAS back on.
# Remote startup dependency

`atlas-remote.service` is enabled under `default.target` but must not be ordered
after that target. Camera joystick units may start after the remote. An explicit
service stop is not automatically reversed by `Restart=always`.
## Bounded active vision

`atlas-active-vision.service` provides stopped-only left/centre/right camera inspection.
Publish `inspect` on `/atlas/active_vision/request`; results appear on
`/atlas/active_vision/status`. Each view requires a new post-move YOLO inference and
live LiDAR clearance. The scan cancels if rover motion begins, returns the camera to
its saved home position, and never publishes velocity. Its recommendation is advisory:
LiDAR, the Nav2 costmaps, and local safety guards retain movement authority.
