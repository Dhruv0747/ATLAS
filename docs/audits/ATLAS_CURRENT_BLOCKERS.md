# ATLAS current blockers

2026-10-10 Hall cold start localized as Dhruv Room (confirmed): every
localization start seeds AMCL at the saved Dhruv Room pose without checking
the LiDAR. No recovery particles are injected, and 1 Hz parked updates
collapsed the cloud to one pose duplicated 2,000 times. The covariance is
round-off (±1e−14) that the map page can show as CONFIDENT and the mux and
mission control clamp to "perfect". A no-prior LiDAR search finds the Hall
uniquely (fit 0.976, margin 0.187) and was correct in 11/11 parked windows.
Replays: saved seed 0/24 correct, Nav2 global 12/24, search seed 24/24.
A verify-before-seed mode (UNKNOWN instead of guessing) is implemented and
dry-run on the Jetson: 3 correct VERIFIED, 4 UNKNOWN, 0 wrong. Installed and
switched on 17:25–17:30 IST with backups (operator approved). AMCL was
reseeded at the Hall (fit 0.991). Controlled reboot validation is pending. The delayed start was 25
LiDAR start failures over 11.5 min. See
[Hall cold-start report](ATLAS_HALL_COLDSTART_LOCALIZATION_2026-10-10.md).

2026-10-10 localization during motion: wheel odometry reports only ~0.6×
the distance LiDAR scan matching measures (M1/M2/M4 raw counts 0.60–0.62;
EKF 0.36–0.54 above 0.3 m/s), matching tape results of Sep 16 and Sep 25.
That drives UNCERTAIN while moving, forward map→odom corrections and the
"falls behind" symptom. A validated AMCL motion replay shows corrected
distance raises held-out fit from 0.69–0.74 to 0.84–0.94 on 3 of 4 drives.
Lowering alphas alone looks confident but is less accurate: rejected.
CONFIDENT-after-stop is the 1 Hz forced resampling. Wi-Fi roams caused no
Jetson-side ROS gaps. The dashboard mislabelled link stalls as POSE DELAYED:
fixed and deployed (display only). Four unclean reboots today followed NVMe
PCIe error storms. The next gate is a supervised tape-measured distance
calibration; no calibration, EKF or AMCL change was made. See
[motion investigation](ATLAS_LOCALIZATION_MOTION_INVESTIGATION_2026-10-10.md).

2026-10-10 operator confirms ATLAS was moved by hand on Oct 9. Manual
relocation (AMCL cannot see it) is the confirmed cause class for the
outbound 1636 start offset; exact move times were not recorded.

2026-10-10 operator: it is possible ATLAS was moved by hand on Oct 9. Manual
relocation without AMCL following is now the leading (not confirmed)
explanation for the outbound 1636 start offset. Mitigation needs no AMCL
tuning: reseed after any manual move, and gate mission start on a fresh
held-out scan-fit check.

2026-10-10 outbound 1636 start offset: AMCL began the recording already
converged 0.55 m ahead of the scan-best pose along the rover's heading (no
sideways error). AMCL's own likelihood peaks there (6.38–7.32 vs 4.08–4.92;
held-out fit 1.00 vs 0.60), and that pose is 7.5–8.5 cm from the morning's
operator-confirmed Dhruv Room reseed. The cloud was 1–2.5 cm wide with zero
odometry, so parked updates could not correct it. How AMCL got there predates
the bag (evidence gap: check Oct 9 16:00–16:37 Jetson journals). Offline only.
See [start-offset diagnosis](ATLAS_OUTBOUND_1636_START_OFFSET_2026-10-10.md).

2026-10-10 multi-drive parked-diversity check (12 parked windows, 6
recordings, 1,800 AMCL core runs): nudge 0.05 m / 2.5° never lowered held-out
scan fit in 11/12 windows (2 seeds in the already-failed window) and improved
it in 5. The parked-update gate lowered fit in 5 windows on every seed and
never improved it: rejected as a standalone repair. Nudge 0.10 m rejected.
New: outbound 1636 sat ~0.5 m from a far better-fitting pose (0.62 vs 1.00).
The 0.05 m nudge added jumps (up to 9) in correcting windows. Offline only.
See [multi-drive results](ATLAS_AMCL_PARKED_DIVERSITY_MULTIDRIVE_2026-10-10.md).

2026-10-10 parked-diversity experiment (AMCL 1.1.20 core, 450 runs, seeds
1–30): bounded jitter of 0.05 m / 2.5° after each parked resample moved the
failed return window onto the refined Dhruv Room pose in 22/30 seeds
(held-out fit 1.000) and kept the correct room and Hall windows correct in
30/30 each. 8/30 failure-window runs stayed wrong, some wandering up to 3 m:
not deployable. The parked-update gate never recovered and froze the Hall
window wrong in 30/30, where recorded updates had corrected it; do not
deploy it as a standalone repair. Unchanged existing harness reproduced
published Jetson numbers exactly. Offline, one drive; production unchanged.
See [parked-diversity experiment](ATLAS_AMCL_PARKED_DIVERSITY_EXPERIMENT_2026-10-10.md).

2026-10-10 weak-hypothesis trace: the 15 room-near particles were lost
while parked (+351.997 to +362.854 s, 11 forced no-motion updates, 0.23 mm
odometry). Scans did not reject them: the exact room pose outscored every
particle on every update, but none sat on that peak. Multinomial resampling
as KLD shrank 2,000 to 1,098 particles removes them in 9.6–14.2% of trials;
zero motion noise and zero recovery alphas meant no new particle could
reach the peak. Offline, one recording; no candidate fix or runtime change.
Next: replay the parked-update gate plus bounded diversity on saved drives.
See [weak-hypothesis trace](ATLAS_AMCL_WEAK_HYPOTHESIS_TRACE_2026-10-10.md).

2026-10-09 competing-pose comparison: equal bounded fitting plus later unused
beams favours the Dhruv region (99–100% endpoint fit, 0.214° corrected-gyro
residual) over the refined false region (78.9–85.6%, 98.229°). A recorded
cloud contains 15 particles near the better room pose; blanket missing-support
claims are not justified. Ten helper tests passed. Offline only, not a fix
or independent multi-drive validation. Next trace weak-hypothesis survival.
See [competing-pose evidence](ATLAS_COMPETING_POSE_EVIDENCE_2026-10-09.md).

2026-10-09 sensor evidence: six recorded stopped windows confirm that physical
stillness is not global localization correctness. Early return AMCL spans
1.148 m/76.478° against repeatable scans and +0.064° integrated gyro. Late
return is steady but wrong; its 77.4–82.7% endpoint fit overlaps late Hall.
No threshold or runtime change was deployed. Six helper tests passed.
See [sensor stability evidence](ATLAS_SENSOR_STABILITY_EVIDENCE_2026-10-09.md).

2026-10-09 follow-up: mission-start incompatibility is CONFIRMED, not merely
suspected. Saved isolated replay has two poses; actual mission code requires
four over at least 5.6 seconds in an 8-second window. One extra startup
refresh still cannot pass. Seven new offline contract tests passed, including
jump/heading/uncertainty rejection. Candidate remains disabled; no production
change or driving. Next: design and offline-validate an independent stationary
estimate-stability criterion before replacing the publication-count requirement.

2026-10-09: added an opt-in, bounded AMCL measurement-refresh handshake.
Healthy processing never overrides stale pose, jump or covariance checks.
The request tick stays blocked; only a subsequent real pose can satisfy the
existing guard. All new authority switches default OFF; production unchanged.
45 focused regression tests passed. Mission startup's multi-pose stability
window and moving/stop localization accuracy remain deployment blockers.
See [isolated experiment details](ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md).

Updated 2026-10-09. Read alongside the [registry](ATLAS_ROOT_CAUSE_REGISTRY.json) and [master analysis](ATLAS_MASTER_FAILURE_ANALYSIS.md).

Processing/pose separation is now implemented and tested in an isolated AMCL
build. Diagnostic processing evidence survives stationary pose silence and
expires on data loss, including frozen ROS time after a discovered timer fix.
It never authorizes navigation. Production mux and AMCL are unchanged;
accurate pose validation and safe permission integration remain release gates.

Deployment validation of 4a4ea9a: **REJECTED**. Actual mux guard tests confirm
the candidate blocks after 2.5 s stationary or sufficiently slow movement.
Five contract tests preserve this counterexample; no deployment or driving.
Separate AMCL scan-processing health from pose publication before integrating
the update gate. Do not extend the timeout or republish stale poses as fresh.

Latest follow-up: [stationary-policy experiment](ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md)
reproduced the stationary-switching failure class, not the original exact five
events. Reduced resampling and frozen priors were rejected as complete fixes.
A source-only fresh-odometry request gate eliminated parked forced requests
in five recorded timelines; AMCL/mux continuity and accurate localization are
still deployment gates. User reboot explicitly seeded saved home at 21:39:42,
so the improved post-reboot marker does not demonstrate autonomous recovery.
No production changes or new driving tests were made.

Latest stationary capture: AMCL stayed at the previously wrong return pose
with 2,000 particles but only one effective geometric support point. The
saved drive also had collapsed support at +104.009 s. Unconditional 1 Hz
no-motion updates plus resampling every update provide a concrete mechanism
for stationary particle impoverishment; the original wrong-mode selection
is still unverified. Keep the current configuration preserved and test the
update/resampling policy offline before deployment. See
[particle-collapse evidence](ATLAS_AMCL_PARTICLE_COLLAPSE_2026-10-09.md).

Later stopped/charging checks found a concrete saved-map blocker: the taught
route is bound to an older map and the **previous** saved Hall goal failed
exact footprint clearance. After a manual Hall arrival, the operator confirmed
the live pose, and a new map-bound Hall point at (6.279, -2.199) passed exact
known-free 0.18 m clearance and grid connectivity to home. This is not a
recorded or repeated autonomous return-home pass. See
[the navigation gate](ATLAS_NAVIGATION_GATE_2026-10-09.md).

The subsequent recorded **manual** Hall → Dhruv Room return exposed a new
localization reliability blocker: AMCL made five >0.5 m position steps after
remote commands stopped, the largest 2.206 m/130°, while wheel odometry was
stationary. The wheel-odometry path was about 6.77 m, so its 4.236 m endpoint
displacement versus 6.053 m between map-frame endpoints must **not** be used
as proof of wheel-distance under-reporting. The drive bag also recorded 32
traction samples with critical encoder consensus (about 3.2 s total) and
about 49 degrees of wheel-versus-IM10A integrated yaw-rate disagreement.
LiDAR/AMCL message delivery was fresh, so the operator's roughly 20-second
map-position lag cannot be dismissed as browser delay alone.
The web map now flags stale displayed poses, but that does not repair AMCL or
motion-estimate disagreement. Keep autonomy gated pending same-time heading,
TF, encoder and localization validation; do not retune wheel scale from this
manual route alone.
The subsequent [cross-bag audit](ATLAS_LOCALIZATION_CROSS_BAG_2026-10-09.md)
confirmed recurrent but variable wheel/gyro heading disagreement, including
an Oct9 short interval where wheel-model yaw had the opposite sign to gyro
and scan ICP despite four selected encoders. An isolated saved-map AMCL A/B
did **not** reproduce the five live jumps in either configuration; velocity-only
improved some correction metrics but worsened final-window position stability.
The experimental EKF change is rejected for deployment; localization remains
unresolved, and the exact physical steering/traction/geometry contribution
is not proven.
The subsequent steering-interface review confirmed that the live driver sends
front/rear commands to Yahboom PWM channels 2/1; the vendor's readable UART
bus-servo API is a different interface. There is no current external steering
position feedback. The wheel-odometry curvature assumes commanded servo
offset equals physical road-wheel angle, including during encoder path
normalization. This is an unverified model assumption, not a proven failed
servo. No steering/EKF parameter was changed. See the cross-bag audit.
Operator photos confirm visible left/right wheel response and the operator
wants the existing steering behavior preserved; they do not measure physical
wheel angles. A read-only per-jump correlation of the Hall-return bag found
all five AMCL steps 2.856–13.063 s after the last remote command with zero
nearby wheel XY motion, zero corrected-gyro turn and 6–8 LiDAR scans between
poses. AMCL XY uncertainty was already >1 m at each event. These are
stationary localization-hypothesis changes, not a physical motion pulse at
the jump instants. Why the filter became uncertain remains unresolved; do
not retune steering or deploy the velocity-only EKF candidate on this basis.
The particle-cloud and same-scan follow-up confirms a diffuse, multimodal
AMCL estimate switching while stationary: fresh scans and particles were
present, odometry did not move, and one reverse switch worsened scan/map
endpoint agreement. A replay-only beam laser model made position stability
worse; velocity-only EKF also remains mixed. None of the isolated replays
reproduced the five live jumps, so neither candidate is a verified fix.
Production localization is unchanged and autonomy remains gated; see the
cross-bag audit for per-event and replay measurements.
The next [replay-fidelity audit](ATLAS_AMCL_REPLAY_FIDELITY_2026-10-09.md)
confirmed that the saved map matches the recorded map cell-for-cell, but the
earlier replay omitted source scans and rebuilt odometry. A closer replay with
all original scans and EKF odometry in its input still emitted only 120 AMCL
poses versus 168 live and reproduced none of the five jumps in two runs.
Its particle spread also differed. The recorded bag lacks AMCL's internal
particle/RNG checkpoint and pre-clip update history, so these zero-jump
outputs are not evidence of a localization repair.
The full-bag replay also stopped emitting AMCL poses before the original
post-stop jump window. A replay-only zero-motion-threshold experiment kept
updates flowing and produced one repeatable 1.827 m correction, but at 512
poses versus 168 live; it does not reproduce the original five-event failure
or justify deploying an AMCL parameter change.
Follow-up found the missing replay trigger: mission control requested AMCL
no-motion updates about once per second during the original jump window.
Post-stop odom/TF drift was only 0.01221 m/0.504°, below the replay update
gates. A full-bag, isolated replay with that request cadence matched the
original 384 total and 80 post-stop AMCL poses and reproduced two stationary
>0.5 m jumps (max 3.470 m), versus five (max 2.206 m) originally. This
explains the earlier replay's missing updates and reproduces the failure
class, **not** the exact event sequence or a validated repair. Production
localization remains unchanged and autonomy remains gated; see the replay-
fidelity audit for measurements and remaining particle/likelihood work.
A matched one-second scan-window/particle follow-up found broad clouds in
both runs, but original jumps 1 and 4 moved to poses with *worse* map-endpoint
fit across all seven preceding scans each, while both replay jumps moved to
better-fitting poses across every selected scan. Published cloud weights are
uniform and omit AMCL's pre-resampling likelihood/cluster decision. The replay
cannot validate a localization fix; the original hypothesis-selection cause
remains unverified. No further repeats of the same replay output can restore
those unrecorded internals.
A separate, bounded AMCL 1.1.20 shadow binary now captures pre-resampling
weights and cluster selection without replacing production AMCL or
broadcasting TF. A properly paced 10-second stationary run verified the
capture topics and showed one stable cluster. This does not reproduce the
historic five jumps or clear the autonomy gate. The shadow is off by default;
see the [trace audit](ATLAS_AMCL_SHADOW_TRACE_2026-10-09.md).
An isolated A/B replay on the same Hall return found velocity-only wheel
fusion materially closer to saved-map LiDAR endpoints than current wheel
pose+velocity fusion (median 50.2% versus 23.1% within 15 cm), but the
candidate still underfit and a prior Oct 8 comparison was mixed. It has
**not** been deployed. The map page now reveals AMCL uncertainty and pose
jumps instead of treating a fresh TF as a precise fix; it does not solve the
localization instability. See the navigation gate for test scope and data.
Per operator priority, continue non-motion navigation evidence first and leave
the intermittent BLE transport repair until later; **do not bypass fresh BMS
telemetry or any movement safety gate**.

The operator later confirmed ATLAS is at the exact saved Dhruv Room/home
spot and heading while stopped and charging. The earlier live AMCL pose was
about 3.8 m away in unknown map space; fresh LiDAR endpoints strongly favored
the saved spot. A backup was made and the existing AMCL seeder applied the
map-bound Dhruv Room pose once. The subsequent live pose was in known free
space within about 9 cm of the saved point, with 99% of scan endpoints within
15 cm of mapped walls. This resolves the observed stopped-pose mismatch, not
reboot or moving localization repeatability. The named places and accepted
map are bound to `d12a1f183177212a3cc8`. On the Oct 9 boot,
`atlas-localization.service` had six restarts. Its start-preflight exited
124 (timeout) while LiDAR repeatedly logged hardware operation timeouts;
missing scans are a strong explanation for the preflight failures, not proof
that the seed caused them. Once running, Nav2 logged several out-of-map robot
poses before settling. These observations make localization
verification a current autonomy gate. The later physical confirmation and
scan-map check isolated the prior AMCL pose as wrong. Do not start an
autonomous route solely because the stationary reseed worked. See
[the navigation gate](ATLAS_NAVIGATION_GATE_2026-10-09.md).
An exact saved-map lookup subsequently found the reported rover position in
unknown cells (205), while the saved Dhruv Room point was known free (254).
The 15-second stopped scan was fresh and wheel/EKF odometry did not move. This
is a concrete route-start blocker even if AMCL's short-window variance looks
small. A fail-closed start-cell check was deployed in mission control with
25 offline map-acceptance tests passing; physical localization still needs
validation under motion and across reboot, and no autonomous movement was
attempted.

## Current verified boundary

Latest observed motor owner: IDLE, stop latched, raw test interface disabled, all outputs zero; PID 3120, NRestarts=0. At 10:07 IST live encoder health reported fresh packets and selected encoders M1–M4, no exclusions, but this is **not** dynamic encoder qualification or proof M3 is physically reliable. At that time autonomy separately reported `FAULT: STOP: SLAM MAP DATA LOST`; see the later stopped diagnostic recovery below. No autonomous readiness can be inferred from the encoder flag alone.
At about 10:14 IST, a ROS CLI snapshot showed `/atlas/mode` publishing `LOCALIZATION` but `/map` with zero publishers. A later snapshot found the map publisher, and a new transient-local subscriber successfully received the saved map. The dashboard had received it at startup but the safety reporter still marked it `LOST`. Graph discovery therefore fluctuated; the zero-publisher snapshot was **not** proof of a dead map server. An earlier CLI check without the matching transport was also misleading about `/atlas/mode`.
With explicit operator approval while ATLAS was stopped, the safety reporter alone received a diagnostic-only update and restarted at 10:22 IST. It then reported `operating_mode=LOCALIZATION`, `received=true`, `slam_map=ONLINE`, and stayed online at map age 27.68 s, as expected for a latched saved map. The motor service kept PID 3120 and zero restarts. The prior false map-loss state cleared, but whether its cause was a missed mode callback, discovery lapse, or another stale in-process state is **unproven**. This does not validate physical localization or a navigation mission.
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

