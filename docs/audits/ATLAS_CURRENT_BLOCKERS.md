# ATLAS current blockers

2026-11-12 16:16 remap REJECTED (closure passed 0.06 m/2 deg; SLAM map->odom jump 0.92 m/12 deg at ~16:06:18 and
"observation did not cover session start" gate). Old map preserved; localization restored and VERIFIED. Named places
restored to old-map x/y with RECONSTRUCTED headings; home pose moved aside and MUST BE RE-SAVED before return-home.
Next: analyse side recording for the jump cause (suspected odometry distance scale, ATLAS-001) and the start-coverage gate.

2026-11-12 EKF heading root cause CONFIRMED + scoped fix DEPLOYED: wheel odometry heading and Yahboom gyro are
sign-inverted vs an independent LiDAR keyframe heading; IM10A correct. EKF now fuses wheel vx only + IM10A yaw
(previously rejected velocity-only trial re-adopted on new discriminating evidence: replay median heading error 68 -> 1.3
deg; live turn and drive agree). A wrong IM10A sign change was applied then reverted. Hall localization on the existing
map still FAILS (fit 0.20, AMCL jumped while parked); candidate 2D map rejected. Full-drive position NOT verified.
See docs/LOCALIZATION_HEADING_DIAGNOSIS_20261112.md; registry ATLAS-011/ATLAS-010 events.

2026-10-21 remaining CPU: two-thread lifetime pattern persists; existing untagged
executor samples cannot identify a safe dominant-cost fix. Exact-live compact
JSON candidate prepared,6+60tests pass; historical expected saving only~0.06
whole-machine points/client set, NOT sufficient for headroom. No deployment.
See ATLAS_STAGE32_REMAINING_CPU_AND_JSON_CANDIDATE.md.

2026-10-21 exact-live snapshot DEPLOYED/HEALTH VERIFIED:98f3c269, web-only restart.
CPU69.270->71.215% mean; no demonstrated whole-Jetson saving. No camera Start.
Headroom remains unresolved. ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_DEPLOYMENT.md.

2026-10-21 superseding snapshot package: exact-live fa62787f baseline reverified;
candidate98f3c269 changes only2bookkeeping sites.9 package+60 dashboard tests
pass, byte-perfect rollback rehearsal. NOT deployed. Whole-Jetson CPU/Preview
unverified; approval required. ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_PACKAGE.md.

2026-10-21 snapshot deployment ABORTED before modification: live web hash
fa62787f differs substantively from reviewed baseline73094079. Repository file
would introduce unrelated steering/HTTP/JSON changes. No restart/Start or CPU
comparison. Prepare exact-live-baseline candidate; see
ATLAS_STAGE32_SNAPSHOT_DEPLOYMENT_BLOCKED.md.

2026-10-21 offline snapshot profiling: redundant timestamp scans confirmed;
single-file candidate reduces Linux synthetic snapshot CPU82.81%,60 dashboard
tests pass. NOT deployed, no live CPU savings/camera admission claim. Needs
separate installation/web-only restart approval; no Start. See
ATLAS_STAGE32_DASHBOARD_SNAPSHOT_OPTIMIZATION.md. Aggregate headroom unresolved.

2026-10-21 superseding CPU investigation: all-process parked trace averages
71.3972%, peaks75.6469% with Astra OFF; top10 omits31.1638 CPU percentage points
of other PID work. Observer itself ~1.0734 points. Exact historical76.61% cause
still unverified; no justified new runtime optimization or80% policy. Seven
offline accounting tests pass; no production changes/camera attempt. See
ATLAS_STAGE32_AGGREGATE_CPU_ACCOUNTING.md. Next: targeted offline web profiling.

Current21 October: preview-core deployed97735e9. One approved test rejected
76.6102% before driver launch;zero frames, optimized conversion not exercised.
Per-process top10 evidence does not explain full aggregate load. No retry;
ATLAS_STAGE32_PREVIEW_CORE_LIVE_RESULT.md supersedes earlier candidate status.

Superseding21 October status: direct launch deployed08ad26f; approved test06ed75f
received17depth frames then CPU76.0757% stopped it. Preview not verified.
New OFFLINE core-preview candidate removes19,200 redundant per-pixel validations:
WSL54.8% conversion CPU reduction,94 tests pass. Whole-Jetson contention remains
unresolved; no deployment/Start authorized. ATLAS_STAGE32_PREVIEW_CPU_OPTIMIZATION.md.
Older entries below retained as historical evidence, not current deployment state.

Latest Depth-only attempt072a22c rejected76.0726% before hashing/snapshot/driver.
Offline direct-Python launch candidate removes redundant shell/ROS setup: PC CPU
0.162734->0.055208s,79 tests pass. No deployment. Jetson aggregate contention and
live Preview remain unresolved. See ATLAS_STAGE32_DIRECT_WORKER_LAUNCH.md.

Latest: startup guard74ff38f installed and hash-verified with approved web-only
restart; transient99.83% settled under75% by27s. Sensors/protected PIDs unchanged;
camera/recorder OFF. No live guard or preview test authorized/performed. Calibration
preparation independent; see ATLAS_STAGE32_STARTUP_GUARD_DEPLOYMENT.md.

Offline startup-coverage candidate now captures pre-spawn baseline and checks
resources during bounded hashing;77 tests pass. PC peak allocation down97%, CPU
time increased; actual combined CPU contention unresolved. NOT deployed. Needs
single-file plus web-restart approval, then separate one-session approval. See
ATLAS_STAGE32_STARTUP_COVERAGE_CANDIDATE.md. Calibration preparation is independent.

Latest approved follow-up: cleanup from abc6837 deployed; ONE combined attempt
stopped at CPU77.104377%. Six depth frames, zero RGB at Dashboard receiver;
browser rendering not verified. No restart or retry. An earlier observer-only
78.8889% initialization sample exposed missing worker startup guard coverage.
Fix that offline before another test. Performance optimization design remains
separately reviewed/uninstalled. See ATLAS_STAGE32_CLEANUP_LIVE_RESULT_20261021.md.

Historical 21 October Depth+RGB: CPU78.4615% guard stops startup; signal log precedes
invalid-context error26.874ms. USB opening succeeded. Diagnostic/cleanup candidate
offline,66 tests pass; actual resource-heavy cause and combined reliability NOT
resolved. No live session/deployment. See ATLAS_DEPTH_RGB_STARTUP_FAILURE_20261021.md.
USB native sandbox follow-up preserved separately; no rules installed.

21 October permanent USB audit: owner restored both temporary Astra ACLs; direct
access passes. Subsequent preflight CPU75.2902% blocked before installation/Start;
no retry. New owner task is offline persistence preparation. Eight static tests
pass; proposed exact two-interface atlas-astra0660 rule NOT installed. Guardian
still uses numbered nodes; group/session transition and native rule validation
must precede any persistence claim. Existing serial access works; radar is UNO
topic-fed. See ATLAS_PERMANENT_USB_ACCESS_AND_REBOOT_RECOVERY.md.

21 October20:44 approved Astra recovery: three safety/resource samples PASS;
administrator ACL access unavailable (sudo password required). Stopped before
installation/ACL mutation, camera test NOT started. Original ACLs unchanged.
Read ATLAS_STAGE32_USB_ACCESS_20261021.md for measurements and uninstalled
persistent-permission proposal. Next prerequisite: operator administrator access.

21 October post-reboot USB follow-up (new owner task supersedes pause): depth
admission failed at1.2004s before streaming. Expected Astra VID/PIDs/nodes present,
both lack jetson RW ACL; direct open denied errno13. No evidence of current address
change. Minimal diagnostic candidate offline; targeted ACL restoration plus one
Depth-preview test awaiting approval. No calibration/rendering changes required.
See ATLAS_STAGE32_USB_ACCESS_20261021.md; no live restoration claimed.

21 October 19:25 PAUSED 3 DAYS by owner (see ATLAS_3_DAY_PAUSE_HANDOVER.md).
U2+P DEPLOYED 19:17 (monitored restart, all post-checks passed). Live Depth-only
3D preview test NOT started (camera never started); needs owner re-confirmation.
Calibration still needs owner measurements; metric cloud still gated.

21 October 19:30 UNCALIBRATED 3D preview (diagnostic only) built and tested offline;
packaged with U2 as U2+P (one monitored rover-status-web restart), rehearsed on a
copy, NOT deployed, camera not started. A4 / 25 mm target and tools ready; they
need the owner's measured square size and target distances. Waiting on owner:
U2+P approval, then a Depth-only session approval. Metric cloud still gated.

21 October 18:38 U1 Vision Lab status UI DEPLOYED (static, no restart, backup verified).
P0 route to a live XYZ cloud: U2 (monitored web restart; manifest serial for the
gate) -> one IR+Depth session (IR-to-depth offset) -> A5 IR checkerboard + depth
targets -> offline validation review -> A6 install + one Depth+3D cloud session.
Waiting on owner: U2 confirmation, IR+Depth approval, printed-target and distance
measurements. Calibration gate active; no metric cloud.

21 October 18:35 Stage32 continuation (offline): UI status fix READY (no-restart U1;
label/serial U2 needs a web restart), not deployed. Combined modes NOT tested
(driver has no IR/depth exclusion; both Astra devices on USB 2.0 behind shared hubs).
Calibration tooling ready: IR despeckle (synthetic 1/24 -> 24/24 detection),
front-face depth model, corners-only capture and depth-target tools. Calibration,
XYZ cloud, XYZRGB still blocked. See Stage32 report section 26.

21 October 18:02 IR RESOLVED (single acceptance): Vision Lab IR now requests
640x480@30 GRAY8 (runtime fc807489, retained). A 60-s IR-only session on the
production driver completed normally: 1624 frames, 29.7 fps, 640x480 mono8 rendered,
raw probe OK, guard 63.7-70.5%, no restart, lease heartbeat max gap 1.40 s. Still
blocked or unapproved: IR+Depth/other combinations, Depth+RGB regression,
calibration, XYZ cloud, XYZRGB, IR-no-frames banner.

21 October 17:45-17:49 permanent IR 640x480 attempt (approved): on the PRODUCTION
driver, real IR 640x480 mono8 ~29.7 fps was delivered and rendered for ~31 s, then
the 4-s viewer lease watchdog stopped the camera at ~42 s (guard 64.5-68.0%, not
resource). Clock comparison indicates the PC test client paused ~3 s. Acceptance
incomplete, so the runtime was restored to 320x240 (454dd25f). No restart; library
and manifest untouched. Next: a re-run from a non-pausing viewer needs approval.

21 October 17:37-17:40 D2 (approved): IR-only at 640x480@30 GRAY8 with the
instrumented driver, no restart. REAL IR FRAMES ON THE DASHBOARD: 1656 frames
read/published (29.70 fps hardware), 1569 received, canvas rendered, 60 s session
completed, guard 65.0-71.3%. Zero-frame cause on this unit: advertised 320x240@30
IR mode not served. All temporary files restored (runtime 454dd25f, lib 6ae87601,
manifest c1a6d1c0; integrity PASS). Production IR still 320x240 = no frames until a
separately approved permanent 640x480 change.

21 October 17:28-17:30 D1 (approved): instrumented driver installed WITHOUT any
restart, one IR-only session, rolled back (integrity PASS, identities unchanged).
Earliest failed boundary = 1: OpenNI started IR 320x240@30 (all rc 0) but
waitForAnyStream timed out (102) 11/11; no frame ever ready, no publish. Receiver
matched (subscribers=1), so the ROS/web path is not at fault. IR NOT verified. Next:
separately approved single 640x480@30 GRAY8 instrumented session.

21 October 17:20 Stage32 takeover from c68ba48 (offline/read-only; nothing installed,
no restart, no camera). The 95.64% sample measured the rover-status-web restart
transient itself: the same restart with a different payload (A1) averaged 93.6% with
about 51 runnable tasks; the candidate does not touch domain 0. Separately found that
the rolled-back candidate would have failed the worker's 458-file runtime integrity
check on every Start. New no-restart diagnostic package (driver library plus runtime
manifest only) rehearsed with byte-identical rollback. IR NOT verified; approval D1
needed. See ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md section 21.

Final documentation-only handover: `ATLAS_STAGE32_DEVELOPER_HANDOVER.md` and
`ATLAS_STAGE32_DEPLOYMENT_REGISTRY.json` index exact versions/evidence/approvals.
No new live checks. Next developer: passive read-only restart-CPU investigation
first; no unchanged install or IR retry. Last safe state is historical section19.

21 October Stage32 conditional installation ROLLED BACK: package/hash/safety
preflight and ARM64 dependency load passed; after web restart CPU95.64% failed75%
guard. Original three files restored; only web restarted (install+rollback).
No IR Start, no retry. Final stopped state, Pi Camera and protected identities
verified, full evidence retained. Next: diagnose restart CPU spike read-only;
new deployment/test approval required. IR failure boundary still unknown. Section19.

21 October Stage32 driver counters: ARM64 candidate built offline, three-file
package/rollback rehearsed. Counters discriminate OpenNI readiness/read, callback,
conversion, ROS publication/subscriber presence, receiver/API/browser. 94+3 tests
passed, one dependency skip; real hardware failure not reproduced offline. Live
hashes unchanged, no activation/deployment. Need owner approval for installation,
web-owner restart and ONE guarded IR test. No motion. Report section18.

21 October Stage32 offline follow-up: pinned vendor source silently discards
OpenNI wait timeouts; saved logs have no frame-read/publish counters or live graph
snapshot. Cannot isolate sensor readiness from ROS publication/discovery. PC
Domain77 real receiver passed 180 synthetic callbacks; this is NOT a hardware
pass. Diagnostic/banner/count-retention candidate prepared, not deployed; no
camera retry. Next evidence must include OpenNI wait/read/publish counters plus
receiver discovery in one separately approved instrumented IR session. Section17.

21 October Stage32 instrumented revalidation: one approved IR-only attempt FAILED
delivery. Eleven ACTIVE samples captured zero IR callbacks before Stop; monitor
ended it after >10s without frames. Peak guard CPU69.78%, RAM70.09%,59.47C, so
not resource blocked. No retry/A3. Driver started but publication/receiver cause
unresolved; offline path review next, not hardware-failure assumption. Postflight
safe, hashes and protected identities unchanged. Stage32 report section16.

21 October Stage32 handover: A1 already deployed, ten hashes and rollback verified.
A2 already attempted, but IR Dashboard delivery acceptance evidence missing:
stop clears counters, so saved zero counts do not prove absent frames. Driver
started IR; session stopped `viewer paused or closed`, not a CPU trip. A3 held.
A4 recovered firmware5.8.22/identity, not validated calibration. No repeat tests,
movement or restarts during reconciliation. See Stage32 report section15.

21 October 15:13 Stage31B: 1-s guard window and stale-summary fix DEPLOYED (no
restart). One 60 s Depth-only session ran to completion: 607 real frames on the
Dashboard, click-to-measure 2.721 m (uncalibrated), guard 63.7-71.1%, limits
unchanged. Astra live viewing now WORKS uncalibrated; calibration/XYZ/cloud still
blocked; single session is not a reliability qualification.

21 October 14:44 second Depth test BLOCKED at start-up: guard sample 76.0% (~0.5 s
window) = Astra start-up burst + kswapd0/kcompactd0 + network-fallback curl probe;
no 1-s sample in 191 s exceeded 75%. No frames, no retry. Owner decision needed on
guard window / background load. See ATLAS_STAGE31_LIVE_DEPLOYMENT.md second test.

21 October 14:35 Stage31 live: UI and Astra domain-77 fix DEPLOYED (web restart only,
protected identities unchanged). One Depth start delivered real frames for ~11 s
(guard 63.5-69.4% after launch, vs first-sample failures before), then a 77.8%
sample stopped it safely; cause unproven (own mid-session SSH observer likely).
Sustained viewing and click-to-measure still UNVERIFIED. Thresholds unchanged.
See ATLAS_STAGE31_LIVE_DEPLOYMENT.md.

21 October Stage31 takeover: Astra startup block traced to ROS/DDS discovery fan-out.
Camera-free, passive /proc sampling: one participant joining production domain 0
raised whole-machine CPU 65%->92% for ~3 s (34 existing nodes woke); the same
join in private domain 77 affected no other process. Parked baseline 65.4% is
spread over ~70 processes (20 points are nice-10/15 background). Fix IMPLEMENTED
(Astra driver + Vision Lab receiver in private domain 77; receiver verified on
Jetson at 30.01 Hz synthetic, no fan-out) but NOT DEPLOYED; projected guard peak
~73% vs 75% limit, so a pass is likely but not certain. Live viewing still
BLOCKED pending approval. Home/Vision Lab redesign built, tested offline and
package-rehearsed on Jetson; not deployed. Thresholds unchanged. See
ATLAS_NEW_DEVELOPER_HANDOVER_AND_RECOVERY.md and ATLAS_DASHBOARD_V2_UI_REDESIGN.md.

21 October Stage30 approved deployment follow-up: three-file ac34cd3 cleanup
installed and hash-verified, no restarts. One real Dashboard Depth attempt
stopped at80.7786% CPU; zero frames, no retry. Independent RAM69.916%,61.187C.
Cleanup is deployed; stable viewing remains BLOCKED. Pi camera and all protected
identities preserved. See final section of ATLAS_STAGE30_ASTRA_RESOURCE_RECOVERY.md.

21 October Stage30: parked CPU65.24% mean/66.78% peak; normal Astra startup
guard75.94%. Startup-only pacing failed to recover stable viewing and was
removed from proposal. Camera-free ROS join also tripped81.68%, implicating
native/graph startup but exact hot path unresolved.119 focused tests pass for
three-file observer-overhead/early-CPU-rejection cleanup; NOT deployed and NOT
a stable-camera pass. No threshold/production-service changes. See
ATLAS_STAGE30_ASTRA_RESOURCE_RECOVERY.md for failures, measurements and approval.

21 October read-only Vision Lab DEPLOYED (`/v2/vision3d`); only web restart,
12 hashes verified, desktop/mobile/Home links pass. One Depth-only attempt
RESOURCE BLOCKED CPU77.9097% >75%; camera stopped before frames, no retry/bypass.
No live pixel/accuracy pass. CPU headroom remains blocker; calibration/XYZ/cloud
still blocked.108 targeted tests pass; Pi camera/six protected owner identities
unchanged. See ATLAS_3D_VISION_LAB_LIVE_DEPLOYMENT.md for backup/hashes/evidence.

21 October calibration continuation:120-byte ctypes layout matches pinned SDK;
vendor validates only part of returned calibration. This does not explain NaNs
or prove camera damage. Alternative supported read paths still untested.
458 live hashes match; stationary admission passed, no stream activation.
94 targeted offline tests pass. Valid intrinsics, measured depth accuracy and
cloud remain blocked. See ATLAS_ASTRA_PRO_CALIBRATION_AND_POINTCLOUD_VALIDATION.md.

21 October Stage29 continuation supersedes the incomplete-build status below:
isolated PC-built ARM64 runtime installed and loader verified; concurrent RGB
15.095 Hz/depth10.527 Hz passed while Pi camera stayed active. 88 targeted tests
pass. Factory parameter query returns NaNs: metric cloud/registration remain
blocked pending valid calibration. CPU-report-only owner exception allowed test
CPU peak99.86%; no normal headroom/endurance pass. Runtime now OFF, production
identities unchanged, no autostart/dashboard deployment. See Stage29 report.

21 October Stage29: PC ARM64 compiler installed and real ELF64/AArch64 probe
passed (two offline tests). Compatible sysroot incomplete: read-only compressed
target copy stopped at CPU75.7983%. Custom target OpenCV4.8 must not be replaced
with host x86/stock4.5 libraries. No driver package or ROS stream verified.
Existing safety/production identities unchanged. See [Stage29](../../ATLAS_STAGE29_ASTRA_OFFBOARD_ARM64_BUILD.md).

21 October Stage28: fresh admission passed, but one incremental isolated build
with own-process duty pacing aborted on aggregate CPU80.8782% >75%; RAM68%,
thermal61.218 C. No automatic retry, ROS driver launch or production change.
Owned processes gone; essential service identities unchanged, recorder OFF.
Next: offboard ARM64 build feasibility, not another unchanged Jetson attempt.
Four new supervisor failure-path tests pass. See Astra report for separate status gates.

21 October latest: isolated Astra RGB/depth each returned 15 real frames within
resource limits; depth warning/parser correction verified offline from preserved
output. No recording or existing-service restart. User cgroup CPU quotas are NOT
enforceable; global CPU stability remains unresolved. Full ROS driver, simultaneous
streams, TF/accuracy/endurance and viewer deployment pending. Earlier blocked
attempts below are historical. See [measurements](../../ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

21 October2026 approved Astra stationary setup follow-up: vendor source and seven
private dependency packages staged, no global install. Build aborted by unchanged
CPU75% admission (75.884% measured); no auto retry. Depth/RGB USB permissions remain
ungranted; SSH has no suitable passwordless sudo. No streams, movement, recordings
or existing-service restart.86 targeted offline tests pass, not a vendor-build or
live-camera pass. See [follow-up](../../ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

21 October 2026 Astra Vision Lab: read-only USB confirms Astra Pro0403/RGB0501,
but no vendor ROS driver/publications and no user write access to depth USB.
Offline viewer tested; NOT deployed and NOT a navigation/localization fix.
72 targeted tests pass including native message serialization; all camera modes,
real depth accuracy, TF/extrinsics and streaming resource impact remain unverified.
Separate stationary driver/permission approval is next; no motion/recording or
production dashboard/service change authorized. See
[Vision Lab report](../../ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

20 October2026 UNO incident: full operator power cycle restored native USB and
all3 I2C devices. Initial I2C-offline/LOW reports and later USB enumeration failure
are separate observations; common root cause not proven. A reproducible wall-clock
serial-watchdog defect was fixed with monotonic elapsed time (same8-second limit),
67 tests pass, scoped bridge deployment verified with essential owners/calibration
unchanged and stop/recording safeguards preserved. Original electrical/firmware
lockup remains UNRESOLVED, not a permanent stability certification. See
[evidence, deployment and rollback](ATLAS_I2C_USB_RECOVERY_2026-10-20.md).

16 October 2026 09:30 UPDATE: Dashboard Motion Chip correction DEPLOYED and verified (static files, no restart). OPEN and
now the main blocker: physical check of the M2 (rear-right) and M3 (front-left) encoder channels; evidence shows
direction-dependent count loss that has moved M4 -> M3 -> M2 since 2 Oct (connector/harness/supply suspected, unproven).
Jetson was power-cycled overnight; an AMCL/Nav2 launch started outside systemd at ~08:56 by an unknown actor (mux
manual-only, E-STOP latched, no goal). No drive, Candidate B or fallback deployment until the hand test is done.
See [report](../../ATLAS_STAGE25_ENCODER_FAULT_RECOVERY_AND_DASHBOARD_DEPLOYMENT.md).

15 October 2026 22:30 UPDATE (Stage 25): the slow return failed because encoders M3 (front-left, near-dead) and M2
(rear-right, froze 21:40:24 then reversed) removed the 3-of-4 consensus; the base failed closed (37% of travel
discarded). Physical encoder check on M2/M3 is the blocker before any further drive. Final AMCL pose unverified
(owner says back in Dhruv Room; AMCL/LiDAR say ~4.3 m east). E-STOP was not latched during the loop. Dashboard chip
fix is offline and undeployed. Candidate B, Foxglove hardening, Stage 17B and physical E-STOP tests unchanged/open.
See [report](../../ATLAS_STAGE25_ROUNDTRIP_ROOT_CAUSE_AND_FIX.md).

15 October 2026 21:06 UPDATE: owner confirmed the 19:46/20:19 position changes were deliberate tests. AMCL seeded once
(20:52:54) at (0.235,-1.435,78); parked 10 minutes stable (max step 0.015 m, 21 checks VERIFIED fit0.981-0.985,
commands zero). OPEN: moving validation (needs separate approval); odometry response to hand moves unexplained
(/odom ~0 during ~1.7 m of owner moves); Dashboard rendered page not visually confirmed by agent; global
ambiguity unproven for other placements; one unexplained MOVING blip at 21:03:43. E-STOP latched, manual-only.
See [seed validation](../../ATLAS_STAGE24_AMCL_SEED_VALIDATION.md).

15 October 2026 20:40 UPDATE (supersedes the 20:12 stationary reading below): ATLAS was physically moved at
~19:46 and ~20:19 (scan range images change 0.19 m and 0.34 m median between periods, identical within them;
monitor MOVING bursts at those times); /odom did not register the moves. Five read-only samples: global and Dhruv
Room agree on (0.235,-1.435,75), fit1.0, margin0.105-0.125 (4 of4 completed global; 1 global run failed on the
seeder's 3 s /odom discovery under load). AMCL still NOT seeded; one seed awaits owner approval; tape check
requested. Boot success depends on placement (4 of8 boots UNKNOWN). See
[recovery report](../../ATLAS_STAGE24_POST_DEPLOYMENT_LOCATION_RECOVERY.md).

15 October 2026 20:12 Stage 24 deployed; AMCL seed BLOCKED. Live dry runs on a stationary ATLAS
(/odom static) returned (0.115,-2.155,71.5) at 19:44 and (0.335,-0.935,72.0, fit1.0, margin0.116) at 20:08
as front LiDAR arcs reappeared (cause unknown). Poses disagree by1.2 m, so no seed; AMCL
NOT_INITIALIZED, Dashboard unknown. Global ambiguity not proven fixed. E-STOP latched,
manual-only, commands zero. See [Stage 24 deployment](../../ATLAS_STAGE24_LOCALIZATION_DEPLOYMENT.md).

15 October2026 CPU continuation: diagnostic search paced without changing its
math, inputs or30-second deadline. Monitor burst74.27%→23.24% of one core;
56 focused tests pass, exact geometry results preserved. Final90-second system
CPU mean70.747%, peak78.696% (3 excursions>75): sustained headroom still NOT
resolved. Largest peak coincides with polkitd32.29%; requester unknown, unprivileged
headers-only trace denied. Need bounded privileged attribution before further
changes. E-STOP latched, manual-only true, commands zero, recordingOFF; essential
services/steering unchanged. See [CPU continuation](../../ATLAS_BACKGROUND_SEARCH_CPU_20261015.md).

15 October 2026 parked CPU/manual-only update supersedes the earlier false
manual-only state below: live manual-only now true, E-STOP latched, commands zero,
recorder OFF. Unused AI preview rendering fixed and deployed; 19 tests pass.
Final short resource check passes, but sustained CPU still peaks above 75%.
Rejected diagnostic CPU-quota trial restored to 60%; localization still ambiguous.
See [measurement and rollback report](../../ATLAS_PARKED_CPU_MANUAL_ONLY_20261015.md).

15 October2026 Nano thermal policy corrected: NVIDIA documents CV0/1/2 absence
on Nano; fresh device-tree identity verified and exact CV EAGAIN is now N/A.
26 offline tests pass. Fresh Jetson check: thermal reads pass, E-STOP latched,
commands zero, commissioning false, Stage20 inactive/PID0. Admission remains
BLOCKED: CPU sample77.89%>75%, manual_only=false. No recording/movement/change
to production settings. See [verified policy/check](../../ATLAS_ORIN_NANO_CV_THERMAL_POLICY_FIX.md).

15 October2026 authorized fixed-probe check: six thermal readings59.625–60.656C,
CPU peak71.43%, RAM66.46%; CV0/1/2 return EAGAIN, precise paths/traces preserved.
Full admission blocks. Separate safety status could not be fetched: SSH timeouts
over Tailscale and Wi-Fi. Fresh E-STOP/recorder state unverified; no activation.
See [Jetson check](../../ATLAS_PC_BRIDGE_TEMPERATURE_JETSON_CHECK.md).

15 October2026 offline correction: bounded binary thermal reads replace the
UTF-8 read path; exact None-read exception reproduced offline. Per-file paths and
tracebacks now preserved, unavailable data still blocks.17 focused tests pass
on Ubuntu22.04. Original live failing attribute/cause remains unproven without
its traceback. No Jetson probe/deployment or recording retry. See
[offline fix](../../ATLAS_PC_BRIDGE_TEMPERATURE_OFFLINE_FIX.md).

15 October2026 approved10s bridge attempt: BLOCKED before connection. Five fresh
CPU intervals69.19–73.46%, RAM65.05%; temperature measurement path raised
`TypeError: can't concat NoneType to bytes`. Exact cause unverified; thermal map
empty and safety/sensor admission incomplete. No subscription, bag or retry.
See [attempt evidence](../../ATLAS_PC_BRIDGE_STATIONARY_ATTEMPT_20261015.md).

15 October2026 follow-up: publisher-presence blocker cleared by3/10/20s graph
snapshots; AMCL/raw scan/particle publishers now visible. Earlier snapshot below
is historical, not a device-fault diagnosis. WSL10s graph-only DDS probe found
no Jetson nodes; existing bridge TCP reachable. Clock bounds still unstable;
Windows Time stopped and WSL initial sync observed, causation not yet established.
Next requires approval for10s stationary receive-only qualification; no movement.
See [connectivity report](../../ATLAS_PC_JETSON_CONNECTIVITY_AND_LOCALIZATION_NEXT.md).

15 October2026 PC offboard update: native21-topic synthetic capture verified,
22,779/22,779. Live recording remains NO-GO: direct DDS over WSL NAT unqualified;
clock-offset bounds varied by~944ms; bounded graph snapshot had no AMCL/scan_raw
publishers and no particle_cloud topic. These are observations, not new root-cause
claims. Jetson unchanged, recorder OFF. See
[readiness report](../../ATLAS_PC_OFFBOARD_RECORDER_READINESS.md).

Latest startup audit: exact post-start refusal76.2295% is confirmed, process attribution
UNKNOWN. Isolated setup profile0.6521 CPU-seconds does not reproduce or attribute it.
No justified correction, deployment or retry;75% preserved. See
[CPU root-cause report](../../ATLAS_STAGE20_RECORDER_CPU_SPIKE_ROOT_CAUSE.md).
Prior supervisor evidence-loss fix is deployed; older source-only status below is history.

Latest: activation supervisor evidence-loss defect fixed in source;18 PC/native
isolated tests pass. Original rejecting measurement UNKNOWN. Installed recorder
unchanged/OFF, no grant or retry. Separate supervisor deployment/activation approval
required; see recording activation failure fix report. Resource headroom unresolved.

Latest17:11UTC: owner approved installation-only CPU exception. Five-file30s upgrade
DEPLOYED/OFF; exact hashes match,328 protected files/production identities unchanged.
Recording grant absent, static/inactive PID0. Runtime75% gate remains unchanged.
Activation and localization validation still pending; earlier rollback preserved below.

14 October17:10UTC approved30s installation passed preflight, failed postflight
CPU77.35%>75%, rolled back all five exact originals. Recorder never started;
production identities and328 protected hashes unchanged. No retry. See readiness
report installation addendum and preserved transaction evidence.

14 October upgrade readiness: exact five-file30s diagnostic patch prepared, six
native install/rollback scenarios passed. Live nine hashes unchanged and unit OFF.
Current parked dashboard~70% does not negate historical CPU refusal; six-core
synthetic recorder estimate adds~8 percentage points. No higher admission justified.
Installation-only approval requested; activation still NO-GO. See
[readiness](../../ATLAS_STAGE20_30S_UPGRADE_READINESS.md). No repeated localization replay.

14 October latest milestone: installed legacy Stage20 remains OFF, nine payloads
and83 protected files unchanged. New30s source passed isolated native capture and
failure checks; not deployed. Required static TF loss found/fixed in candidate.
CPU79.496% admission refusal preserved,75% limit unchanged. Minimal fusion candidate
contract-tested only; missing EKF initialization prevents faithful A/B and five AMCL
jumps remain unresolved. No new drive requested. See
[milestone](../../ATLAS_NEXT_LOCALIZATION_MILESTONE.md) for current status, superseding
older installation-absent status below without erasing historical attempts.

14 October CPU optimization: compact dashboard JSON is verified faster in isolated
native response tests, but its absolute budget cannot establish Stage20 headroom.
Live dashboard stack profiling refused OS access; noninteractive sudo requires a
password. No permissions/services changed. Live/repository dashboard drift includes
undeployed steering diagnostics: future rollout must be JSON-only, not whole-file
repository replacement. See [optimization report](../../ATLAS_STAGE20_CPU_OPTIMIZATION_REPORT.md).

14 October CPU admission follow-up: read-only baseline demonstrates actual CPU
excursions above75% with collector absent and no installation running. Historical
postflight exact sample remains unavailable; causality is not retrospectively proved.
Exact resource evidence and transactional postflight rollback are corrected in
`bb8ec665ed5474d7b2b0db22e9b5624ddd137b06`; nine runtime payloads unchanged.
No third production attempt, recording activation, motion or service restart.
See [CPU investigation](../../ATLAS_STAGE20_CPU_HEADROOM_AND_INSTALLATION_FIX.md).

14 October supervised retry: installer and unit registration succeeded, but immediate
postflight resource guard refused acceptance. Exact threshold sample was not retained;
subsequent CPU79.7% exceeds75%. Rolled back only new diagnostics; collector never ran.
All production service identities/protected hashes unchanged, stop latched/zero commands.
No automatic retry. See [retry result](../../ATLAS_STAGE20_SUPERVISED_RETRY_RESULT.md).

14 October Stage20 installation update: initial install aborted before writes;
original child error UNKNOWN because wrapper discarded captured stderr. Durable
installer failure evidence fixed in source; 83 PC tests pass (one POSIX skip),
19 native targeted tests and fake-root install/rollback pass. Unit parser/offline
static state verified; manager reload simulated. Nine runtime payloads unchanged.
No production retry authorized or performed; collector absent/OFF, stop latched,
production identities unchanged. See [installation investigation](../../ATLAS_STAGE20_INSTALL_FAILURE_ROOT_CAUSE.md).

Stage20: **PUBLIC-ONLY alternative qualified, approval pending; private checkpoint
NOT ready**. Native120s rate/2000-particle test captures all97,901 source messages;
raw CDR fixes a demonstrated diagnostic receive bottleneck. Actual530-unit graph,
adapter/grant, resource bounds and scratch rollback pass;65 offline checks pass.
CPUQuota/device filesystem sandbox unavailable; actual total-CPU75s/memory192MiB/
tasks48/runtime bounds distinguished. No overlays/hooks shipped or live changes.
Private initialization/covariance/reference/consumption/RNG unavailable in partial
scope; localization unresolved, B–E blocked, Stage17B HOLD. See
[minimum-safe scope](../../ATLAS_STAGE20_MINIMUM_SAFE_DEPLOYMENT.md).

Stage20 continuation: controlled native startup/consumer audit passes (2734
consumptions), static matched EKF comparison passes (609 samples; max full-covariance
difference0.0895%). Earlier wall-time covariance3.223%/discovery losses retained;
not a moving/historical repair. Gaussian allocation reseeds static pf_pdf_seed,
correcting wall-seed-only explanation. 46 current checks and native crash/quota
tests pass; package/systemd/reset/timing/full-rate qualification still pending.
DEPLOYMENT READY NO; live unchanged, EStop latched, Stage17B HOLD and B–E blocked.
See [readiness report](../../ATLAS_STAGE20_DEPLOYMENT_READINESS_REPORT.md).

14 October Stage 20 partial milestone: sandbox-only collector and upstream-library
EKF observer capture actual relative reference/full covariance; opt-in service-call
hooks default OFF. Native synthetic smoke and 28 offline checks pass. NOT production
ready: complete startup/consumer order, AMCL internal events, total overhead and
failure/rollback qualification remain missing. Fidelity and B–E still BLOCKED;
no live installation, motion, seed or calibration. See [Stage20](../../ATLAS_STAGE20_EKF_AMCL_CHECKPOINT_CAPTURE.md).

14 October Stage 19: full native Humble EKF/AMCL Hall-return baseline completed in
private network/PID/device namespaces, without actuator access. Five original parked
jumps NOT REPRODUCED; eight native pre-stop corrections instead. Cold EKF starts
at zero while original starts (18.392,-3.654 m,-128.476 deg), with unrecorded prior
relative wheel reference/full estimator state. Even after initial rigid alignment,
native differs up to 1.343 m/18.401 deg. Candidate comparisons FIDELITY BLOCKED;
B native launch refused by strengthened gate. No live configuration/service changed,
E-STOP remained latched, Stage17B HOLD. Next evidence is initialization/checkpoint
capture, not another repeated route. See [Stage19](../../ATLAS_STAGE19_NATIVE_EKF_AMCL_REPLAY.md).

14 October Stage 18 supersedes the next-step approval request: Stage 17B is on
HOLD, not authorized for deployment or motion. Offline general 4WS math and
neutral-seeded ICP/gyro screening are tested. Final roundtrip also contains exact
encoder updates (4,591), correcting the earlier incomplete inventory. General
lateral correction using the same commands does not fix wrong yaw; gyro-heading
shadow improves yaw but not translation consistently. Five original AMCL jumps
remain unresolved. No calibration, fusion, map, policy or live service changed.
See [Stage 18 report](../../ATLAS_STAGE18_ODOMETRY_SENSOR_FUSION_REPORT.md).

14 October Stage 17: exact encoder/raw-gyro/particle/steering instrumentation
is prepared and an isolated parked Humble capture passed (7,032 messages,
zero application or DDS-reported losses, all required topics available).
E-STOP stayed latched; no physical steering/movement or production deployment.
Current PWM owner is front channel 2/rear 1, centres 90/90, with no physical
angle readback. Visual perspective/sync tools are tested; actual road-wheel
angles and loaded linkage behavior remain missing. The unused direct-serial
utility's opposite channel mapping is disabled in source, not implicated in
the recorded yaw failure. Recorder ~85 MiB/40.5% one-core CPU, whole-system
sampled peak 99.4%; fresh timing/resource and functional remote checks remain
physical-test prerequisites. Battery was charging. Next approval is stationary
lifted front/rear measurement; ground movement remains separate. See
[Stage 17 preparation](../../ATLAS_STAGE17_STEERING_YAW_VALIDATION.md).

14 October read-only resumption: Stage 16 has four retained startup verdicts.
Alternate-position checks failed for two distinct measured reasons: one best
fit 0.923 below 0.93, another best fit 0.950 but ambiguity margin 0.028
below 0.06. Both had 21–24 scans and ≥58 valid rays per quadrant on the same
accepted map; neither seeded AMCL. Two Home checks scored 1.000 and seeded via
the startup service. The second alternate check reused an Oct 11 Jetson boot
ID, so was not a new Jetson boot. Exact physical cause of poor/ambiguous fit
is unverified; motion localization remains unvalidated. Oct 9 bag receipts
show ≈10 Hz encoder publication and no diagnostic sequence gaps in the main
Hall→Dhruv recording, while measured encoder distance remains low. No live
settings changed. The repository's `atlas_latest` map differs from the
accepted Jetson map: any offline replay must use the archived accepted pair.
See [resumption report](../../ATLAS_CORE_LOCALIZATION_RESUMPTION_REPORT.md).

11 October 20:15 IST: AMCL localized again, through the existing startup verifier, after the owner's
19:52 dashboard restart (fit 0.989, margin 0.111). No manual seed was applied. Live CHECK MY
LOCATION is VERIFIED 3/3: AMCL (0.178, −1.473, 78°) versus LiDAR (0.235, −1.435, 72–75°),
0.069 m / 3–6°. The heading spread is the 3° search grid.

New finding: the board IMU on `/imu/data` read −1.71°/s parked this boot (+0.006°/s on the
previous boot). It is not used by the EKF, but it held the location check in ROVER_MOVING; stage 15
moved that gate to the EKF's IM10A gyro.

Voice latch/release fix deployed (stage 14); a spoken release is not physically tested.

The 0.90 startup score on the 19:06 boot remains unexplained: its verdict and journal were lost,
and web driving 19:13–19:32 means its pose is uncertain. Per-boot replayable verdict capture is
prepared (`b81d7ac`), not deployed. See the
[evening record](../deploy/ATLAS_LOCALIZATION_RECOVERY_2026-10-11_EVENING.md).

11 October 19:47 IST: CHECK MY LOCATION "UNAVAILABLE" after the 19:06 restart. **Root cause:**
the startup verifier refused to seed (best 0.90 < 0.93), so AMCL was active with no pose. The
check required an AMCL pose before even starting its independent LiDAR search and reported a
merged "SCAN UNAVAILABLE or AMCL reference unavailable"; scan, scan-time TF and map were all
fresh. **Fix (stage 13, deployed latched):** precise blocking codes and a stage table; AMCL
reported separately; without AMCL the search runs and the best answer is LIDAR_ONLY_MATCH, never
VERIFIED. Live result in Dhruv Room: (0.235, −1.435, 72–78°), fit 0.994–1.000, margin
0.079–0.107; runner-up is the known alias near (3.9, −0.6). The isolated replay of the Oct 10 bag
reproduces the 3.95 m AMCL alias MISMATCH. AMCL is still un-seeded; no reseed was performed. Only
the location monitor was restarted. Evidence gap: why the boot-time fit was 0.90.
The voice stop announcement (latch spoken, release silent) is fixed in source (27ccfcd), not
deployed. See [stage 13 record](../deploy/ATLAS_LOCATION_CHECK_NO_AMCL_2026-10-11.md).

11 October 18:55 IST: CHECK MY LOCATION Stage A is now deployed on both
dashboard pages with fresh scan/IMU/odometry/TF/map/AMCL validation. 73 scoped
Python tests, 6 UI assertions, isolated ROS smoke tests and both live buttons
passed. Live checks report roughly 1.6–1.7 m AMCL/LiDAR disagreement; candidate
ambiguity remains. This is diagnostic evidence, NOT localization repair or
autonomy clearance. E-STOP remained latched; no movement or pose correction.
Stage B correction is not enabled. Details, resources and rollback:
[implementation report](ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md).
The foundation-only statement below is superseded by this deployment.

11 October follow-up: 26 saved plus 18 fresh paired scans locate all missing
returns in raw +inf, not self-filter removal. Physical cause remains unknown;
guard permissions unchanged. Settled CPU 70.35%, RAM 5442.83 MiB; no basis to
attribute the earlier entire increase to the guard. CHECK MY LOCATION has an
isolated-tested lifecycle foundation only; adapter/UI/replay/deployment remain.
See [checkpoint](ATLAS_CORE_RELIABILITY_CHECKPOINT_2026-10-11.md) and
[location feature status](ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md).

11 October 18:10 IST: approved recovery freshness + stop-only NAV2/recovery
LiDAR guard deployed; RPP conversion 3 -> 15 deployed in both config copies
and running controller, without AMCL restart. 15 full-controller/mux checks,
11 native checks and 38 regressions pass. Direct ROS verifies latched stop,
zero commands and fresh sensors. Historical entries below are preserved.
Remaining: 68/68 fresh real scans have missing observation bins and conservatively
veto hypothetical autonomy in every direction; this is NOT proof of occupied
space. Swept-path observation qualification, physical stopping, and unresolved
moving localization/encoder qualification still block autonomous acceptance.
Two startup verification attempts rolled back on dashboard timing; direct ROS
and systemd verification succeeded. See
[deployment evidence and rollback](ATLAS_NAVIGATION_GUARD_DEPLOYMENT_2026-10-11.md).

11 October decision-path audit: STOP remains latched; no movement or live
control changes. Confirmed recovery defect: all-invalid sectors were infinite
clearance, permitting forward/reverse choices. Source-only correction passes
six regressions. Local costmap does not track unknown space; expected scan
update rate is zero. Neither proves observed free space or a scan-loss stop.
Live RPP inflation-cost conversion is 3 versus costmap scaling 15: confirmed
configuration mismatch. Both need bounded approval-backed commissioning, not
arbitrary range suppression. Full controller action replay remains unfinished.

Latest 11 October 17:15 IST: LiDAR provenance stage 10 is now installed from
`1a9f077`; new markers and raw-ray details verified in the browser. All 60
parked API samples LIVE. Only dashboard restarted. The physical object behind
the front-right minimum is still unknown; no timed before/after hand-test
capture exists. Combined map/scan overlay and arbitrary-point raw provenance
remain unfinished (quadrant minima have raw provenance). BMS still times out;
passive HCI monitoring is blocked by OS permissions. No autonomy enabled.
See the appended stage-10 section of `ATLAS_LIDAR_PROVENANCE_2026-10-11.md`.

Latest 11 October 16:33 IST: owner-approved BMS ownership fix deployed; no
competing restart, but connect still times out (one/120 s, zero healthy samples).
Read-only LiDAR/camera/Home views deployed. All 62 sampled HTTP JPEGs exactly
match original ROS JPEGs: current blur is upstream of V2, precise cause unknown.
See `../ATLAS_MASTER_DEPLOYMENT_2026-10-11.md`; older rollback notes below retained.

2026-10-11 staged rollout update: bounded motion recorder installed and parked
capture verified (3,203 messages; one DDS-reported loss; zero application drops).
No continuous service, no movement. BMS link reuse/backoff stage rolled back
after confirmed competing recovery-supervisor restarts. Offline ownership fix
awaits approval to restart the supervisor; no motor-related restart performed.
connection root cause still unresolved. Owner confirms phone BMS app disconnected.
Current Wi-Fi baseline had no losses/disconnects over 120 s; this does not erase
historical roaming/DHCP faults. No network settings changed. See
`../ATLAS_ROLLOUT_2026-10-11.md` for deployment identities, rollback and measurements.

2026-10-11 13:35 read-only reliability pass (no changes, no motion; see
[core reliability report](ATLAS_CORE_RELIABILITY_READONLY_2026-10-11.md)).
- **Wi-Fi.** Roams to AP B or the extender X failed DHCP 4 of 16 times (plus 1
  unresolved when the journal ends); the
  main router succeeded 26 of 26. The longest outage (73 s on cellular) was a
  DHCP failure, not radio loss. The fallback agent also saw 5 Wi-Fi Internet
  failures (17–109 s), one today at 09:39 with no roam. Six 1 s cellular
  default-route flips with no Wi-Fi event have unknown cause. Power save is on
  at two levels, the regulatory domain is 00, and BT coexistence runs against
  1,164 BMS bonding failures this boot.
- **Correction:** the Oct 10 "46 roams 14:00–15:00" cannot be reproduced from
  the retained journal (6 found); treat it as unverified.
- **LiDAR.** Start-only failures: 0–21 per boot, first scan at 20–257 s, never
  a runtime failure once scanning. No USB re-enumeration. ModemManager,
  vc02 voice and other port users are ruled out. The deferral fix works. The
  5 V supply remains suspected; it needs a measurement.
- **IMU.** The EKF's IM10A gyro outputs exactly 0 when parked (587 of 587
  samples; 54% zeros on the Oct 2 drive). The Oct 2 "zero drift"
  qualification therefore did not observe the bias. This does not explain the
  0.46× fast turn.
- **Localization.** It failed again live. The operator's web drive at
  13:23–13:24 took a VERIFIED pose to LOST, 1.05 m / 24°. The monitor caught
  it 4 s after the stop. There was no recording, so a bounded drive recorder
  is proposed. ATLAS is currently LOST, with the latch released by the
  operator. Not reseeded.
- **Boot −1** ended uncleanly at 00:55:16. Boot 0 began 07:36:51 real time
  with the clock at 01:16 until NTP.

2026-10-11 00:00 local map validation. Candidate v1 is REJECTED: it opened
new passages and deleted real surfaces. The safe v3 gives no benefit. The
corridor needs a supervised slow re-map at ≤ 0.15 m/s and ≤ 15°/s, driven
by the operator. Fresh scans at the corridor midpoint and the Hall are still
pending.

2026-10-10 23:30 local map audit, Dhruv Room → Hall (read-only). About 17%
of the mapped walls in this section are contradicted by 6 independent drives,
mostly shifted copies drawn by the mapping run's return leg. A candidate map
(not promoted) improves offline AMCL replays but leaves the corridor weak. A
slow local re-map is recommended. See
[local map repair](ATLAS_LOCAL_MAP_REPAIR_DHRUV_HALL_2026-10-10.md).

2026-10-10 21:29: steps 1 and 2 of the reliability review were deployed with
approval. The step 3 LiDAR restart limit is on HOLD. On the Jetson:
- Dhruv Room was verified by the monitor and by an independent dry run;
- monitor CPU fell from 0.28 to 0.10 core;
- in a replay, all states and all stale-input rejections behaved correctly.

Still open: stop latency on a real drive, and LiDAR start failures at boot.
Autonomy is still disabled.

2026-10-10 21:30 reliability review (offline fixes, **nothing deployed**).
The monitor took 30–40 s to verify after a stop because the search took
17–20 s on the Jetson. The monitor also had no stopped/verifying state, could
apply a result from before a move, and had no input freshness checks. Fixed
offline:
- search 2.2–2.6 s on the Jetson with identical hypotheses;
- expected about 5 s from odometry stop to result.

LiDAR start failures are chronic: 6 of the last 10 boots had 10–21 failed
starts. The restart loop is unbounded, and two restarters compete. The cause
of the start failure is unconfirmed; suspected supply at boot, which needs a
measurement. Mission's 0.85 scan-fit gate is below the alias peak (0.872);
the autonomy-gate integration is proposed separately. `CPUQuota` is not
enforced on user services, which corrects an earlier claim. The crash boot
left no journal. Awaiting approval for the deployment steps. See [reliability review](ATLAS_RELIABILITY_REVIEW_2026-10-10.md).

2026-10-10 19:16–19:27: localization monitor deployed in suggest-only mode,
with backups and the operator's approval. It marked the live 4 m error LOST
(fit 0.785), and the page showed red LOST. ATLAS was reseeded while parked
by the verify-mode seeder (fit 1.00) and independently re-checked VERIFIED
(monitor fit 0.962, 0.09 m; separate dry run fit 1.00). Autonomy remains
blocked (`navigation_validated: false`). Next: startup LiDAR stability, then
supervised recorded slow/fast drives.

2026-10-10 18:30 moving failure after a verified start. A fast remote drive
from a verified start (3.72, −0.70) to Dhruv Room left AMCL at (4.13, −0.77,
160°), 4.0 m wrong, while the page said START VERIFIED. Confirmed:
- the wrong pose is a recurring Dhruv Room alias (fit 0.87), found in 4
  recordings;
- EKF odometry reported 0.77 of the distance and **0.46 of the −97.5° turn**,
  and wheel yaw had the wrong sign;
- the encoder consensus went CRITICAL at the stop;
- the cloud collapsed to one particle.

The cause of the heading shortfall is unproven (no drive bag). A
continuous parked LiDAR check, built and tested offline, flags all 12
known-wrong AMCL states as LOST and confirmed 14 correct ones on 29 parked
checks. It is not deployed. "START VERIFIED" no longer turns the page green.
A recorded repeat drive is needed. See
[moving failure report](ATLAS_MOVING_LOCALIZATION_FAILURE_2026-10-10.md).

2026-10-10 household movement vs start-pose verifier. Quiet Hall scans fit
0.97–1.00. With people moving (operator confirmed 17:05–17:15) the dry runs
fit 0.86–0.95; that is a time correlation, because those scans were not
saved. Stress test: simulated people in real scans from 11 windows, 484
runs: **0 wrong-place verdicts**. With people, 111 of 176 were verified
correctly and the rest were UNKNOWN. A wrong place out-scored the truth in 10
runs (up to 0.919), and both guards rejected them. Percentile aggregation and
lower thresholds were rejected on this evidence; deployed settings unchanged.
A people recording is needed to confirm on real data.

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

## Latest LiDAR priority on 11 October 2026

The owner reprioritized sensing provenance before further BMS/network work.
The reproduced 0.509 m FRONT minimum is raw ray 318 at -44.7 degrees in
base_link, not a fabricated dashboard range or forward-wall estimate.
64 paired raw/filtered samples preserved all finite measurements; scan-density
variation was already present upstream. A second 26-sample capture retained
raw payloads and replayed identically on Jetson. Physical obstacle/reflection
identity remains unknown; do not remove the close point. Candidate provenance
markers and cluster diagnostics are tested but not deployed. No motion,
localization, map, network or calibration change. See
[the consolidated sensing report](ATLAS_LIDAR_PROVENANCE_2026-10-11.md).
Next physical action, after authorized diagnostic deployment, is a parked
measured target check, not another manual room loop. Earlier observations below
remain dated evidence rather than current readiness guarantees.

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


## 2026-10-11 20:45 update: encoder distance by speed (ATLAS-001, offline)

**Data:** Oct 9 bags, 898 near-straight LiDAR-ICP scan pairs, binned two ways (by ICP speed and by
encoder speed) to expose binning bias.

**Findings:**
- **0.10–0.45 m/s:** both binnings agree. Raw M1/M4 read 0.64–0.72× and M2 0.51–0.64× of the true
  distance.
- **Slow end:** not interpretable; the two binnings disagree in opposite directions.
- **Consensus estimator:** removes only 1–3%.

**Still open:** constant CPR/scale error versus constant slip is not separated. M2 differs from
M1/M4.

**Retracted:** a same-day claim of "speed-dependent count loss".

**Evidence gap:** tape-measured straight runs at two speeds. **No calibration change is proposed.**
See [encoder scale by speed](ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11.md).

## 2026-10-14 Stage 17B preparation — ATLAS-013

Disabled-by-default single-person front steering measurement sequence is prepared
and mock-tested. Tilt-only phone orientation is not physical steering feedback.
No live deployment, motion, calibration or localization repair is claimed.
Physical wheel-angle evidence and expanded-profile Jetson resource validation
remain pending. See [Stage 17B](../../ATLAS_STAGE17B_SINGLE_PERSON_STEERING_TEST.md).
# 2026-10-14 executor-profile clarification

Owner-provided live py-spy evidence is now available, superseding the earlier profiler-access gap. Focused audit found measurable dashboard CPU, but no demonstrated avoidable executor defect or duplicate constant-topic subscriptions. Eleven offline checks passed; no runtime patch/deployment or CPU savings claimed. Stage 20 headroom remains blocked. See `ATLAS_STAGE20_DASHBOARD_EXECUTOR_CPU_FIX.md` for sample-attribution limits and the bounded thread measurement. Suppressing QoS, adding sleeps and replacing executors are rejected without further discriminating evidence.


## 2026-10-15 update: EKF translation/heading contamination, Candidate B-safe (offline; ATLAS-011, ATLAS-001)

**Confirmed (offline):**
- The production EKF's X/Y follows the wheel-integrated, commanded-steering trajectory while its
  yaw follows the gyro. Its travel direction against its own heading has a 90th percentile of 22°;
  LiDAR gives 9°.
- Native replay reproduces the recorded EKF's relative motion, so a relative A/B is valid.
  Stage 19's absolute/AMCL fidelity block still stands.
- Removing wheel X/Y pose (Candidate B) cuts heading drift per about 1.4 m from 4.8 / 7.4 / 23.6°
  to 0.5 / 2.3 / 3.4°.

**New hazard, closed in source:** B coasts 2 m during a parked stop when encoder consensus is lost.
The fresh-zero-count twist anchor in `yahboom_base.py` closes it in source (0.003 m in the
synthetic test). **Not deployed.**

**Separate open issue:** a constant +5.5° LiDAR travel-direction offset, either a LiDAR mount yaw
error or a steering crab. B's sideways benefit depends on resolving it.

**Unchanged:**
- the wheel distance under-read (about 0.65×);
- the five unexplained parked AMCL jumps.

**Deployment gates:** see the [recovery handoff](../../ATLAS_SINGLE_DEVELOPER_RECOVERY_HANDOFF.md).

## 2026-10-15 13:30 update: Humble transfer, stop-anchor revision, bridge exposure

**Candidate B on native Humble (robot_localization 3.5.4):** it reproduces the Jazzy A/B. B's
heading benefit transfers.

**Stop anchor revised:**
- The `3eff519` one-tick rule was too weak: all four counts stay unchanged for up to 0.79 s while
  moving.
- Replaced by a 1.0 s stillness detector.
- The stage 21 package is prepared and rehearsed against byte-identical live files.

**Foxglove bridge (production):**
- Any tailnet/LAN client can publish `/goal_pose` (relayed to Nav2), write any node's parameters
  and call services. Demonstrated in isolation.
- Read-only config prepared.
- Bridge 3.x requires subprotocol `foxglove.sdk.v1`.

**Pre-existing test failures, not caused by this work:**
- `test_status_web_estop_reset` wrong-PIN lockout (409 ≠ 403);
- `test_atlas_safety_status_camera_heartbeat`.

**Not deployed.** See the [deployment plan](../../ATLAS_CORE_LOCALIZATION_FIX_DEPLOYMENT_PLAN.md).

## 2026-10-15 13:10 update: Stage 21 deployed and parked-verified

**Deployed** (12:53:45, owner-approved): the driver stop anchor. Only `rover-base-telemetry` was
restarted.

**600 s parked check:**
- `/odom` drift 0.0 cm;
- encoders fresh, 4/4 accepted;
- safety state unchanged;
- protected services untouched.

**Not yet shown:**
- **NOT LIVE EXERCISED:** the new fewer-than-3 branch.
- **MOVING VALIDATION PENDING.**

**Not deployed:** Candidate B and the Foxglove hardening. See the
[Stage 21 report](../../ATLAS_STAGE21_DRIVER_STOP_ANCHOR_DEPLOYMENT.md).

## 2026-10-15 13:30 update: Stage 22 recorder profile deployed (recording OFF)

**Deployed:** the steering-validation recorder profile. Recording is OFF.

**New finding:** the live `atlas_steering_calibrate.py` is the August direct-serial tool, which can
command the steering servos. The repository version is retired. The repository tests execute it.
- In the Stage 22 rehearsal it was run against a scratch copy and failed safely, because
  `/dev/yahboom` is absent.
- **Replacing it needs owner approval.**

**Still blocking the baseline drive:** AMCL is unseeded on this boot.

See the [Stage 22 report](../../ATLAS_STAGE22_RECORDER_DEPLOYMENT.md).

## 2026-10-30 Vision Lab backend installation

Rolled back; Type=simple HTTP readiness race corrected offline. CPU79.15% was
measured during OLD web shutdown, not candidate startup. Attribution remains
unknown; NO-GO for retry. See [diagnosis](../../ATLAS_OBJECT_TARGET_INSTALL_DIAGNOSIS_20261030.md).

2026-10-30 shutdown follow-up:39/39 historical scrapes failed; CPU attribution and
duration remain UNKNOWN. Staging avoids restarts; functional API activation does
not. See [assessment](../../ATLAS_WEB_SHUTDOWN_CPU_ASSESSMENT_20261030.md).

2026-10-30 restart safety follow-up: independent ROS observer and bounded restart/
policy/file recovery implemented offline.8 focused tests including native WSL
SIGKILL fake-unit recovery pass. Actual Jetson admission/performance remains gated;
79.15% cause remains UNKNOWN. [Package](../../ATLAS_WEB_RESTART_SAFETY_PACKAGE_20261030.md).

2026-10-31 PRIORITY INCIDENT: original recovery STOPPED after93.624% startup rejection. Original bytes restored; snapshot producer disabled. Saved stack is within ROS Node initialization before custom work. Exact process attribution missing;19 historical Prometheus scrapes failed. Offline rejection evidence retention fixed/tested, not a runtime optimization. Incident OPEN; see ATLAS_RECOVERY_STARTUP_ROOT_CAUSE_REVIEW_20261031.md.

2026-10-31 CPU attribution preparation: stdlib all-PID/selected-cgroup collector;11focused PC tests PASS,12s native PC run0.045941CPU-s/14.80MiB. No live execution. Root cause still UNKNOWN; Recovery restart NO-GO pending guarded collector integration and Jetson overhead validation. See ATLAS_RECOVERY_CPU_ATTRIBUTION_PREPARATION_20261031.md.

2026-10-31 attribution follow-up: guarded passive wrapper complete,13 new focused tests PASS. Native PC observer0.05061CPU-s first sample,0.09019CPU-s over12s,20.64MiB. GO for separately approved isolated overhead test only. Recovery start remains NO-GO; cause UNKNOWN. See ATLAS_RECOVERY_ATTRIBUTION_GUARDED_TEST_20261031.md.

2026-10-31 passive attribution test PASS on Jetson: observer0.68516CPU-s through final sample/20.42MiB, peak aggregate63.12%;42units unchanged, child absent after cleanup. Recovery remains stopped; original93.624%cause unknown. Future startup needs separate actor/cgroup integration and approval. See ATLAS_RECOVERY_ATTRIBUTION_JETSON_RESULT_20261031.md.

2026-10-31 final startup preparation: verified collector integrated with one-start original-Recovery actor;8focused offline tests PASS including native fake-unit SIGKILL/timeout and rejected first-interval evidence. GO to request ONE separately approved diagnostic restoration, not proof startup will pass75%. No live execution. See ATLAS_RECOVERY_STARTUP_DIAGNOSTIC_PACKAGE_20261031.md.

2026-10-31 approved diagnostic restoration FAILED: RecoveryPID364817 started once; first startup sample68.729% retained with PID/cgroup. Next collector scan exceeded150ms and discarded partial counters. No CPU>75rejection proven. Recovery stopped, Restart=always restored;41unrelated units unchanged. Incident OPEN; no retry. See ATLAS_RECOVERY_DIAGNOSTIC_ATTEMPT_RESULT_20261031.md.

2026-10-31 confirmed tooling defect corrected OFFLINE:150ms scan exhaustion returns explicit partial evidence rather than discarding acquired counters; safety measurements still validated and true CPU rejection retained.8focused tests PASS. Runtime CPU root cause remains UNKNOWN; no startup performed. See ATLAS_RECOVERY_PARTIAL_EVIDENCE_FIX_AND_CPU_AUDIT_20261031.md.

2026-10-31 corrected restoration package prepared: eight focused built-package tests PASS; nine hashes verified. GO for separate execution approval with fresh admission, not a live safety PASS. Recovery remains last verified STOPPED; startup CPU cause UNKNOWN. See ATLAS_RECOVERY_CORRECTED_RESTORATION_PACKAGE_20261031.md.

2026-10-31 corrected attempt: FAIL at actual 86.934673% CPU; complete 42.96ms scan retained. Recovery PID374161 reached READY but failed safety, now STOPPED. Recovery cgroup54.71% and localization48.22% of one core; causal hot functions UNKNOWN. Original policy/config restored, 41 unrelated services unchanged. See ATLAS_RECOVERY_CORRECTED_ATTEMPT_RESULT_20261031.md.

2026-10-31 offline candidate: required Recovery message types preloaded before rclpy.init, methods/QoS/safety unchanged. Four tests and native no-node check PASS; PC import16ms only, no measured Jetson saving. Not sufficient evidence to declare86.93% issue resolved. Recovery remains STOPPED. See ATLAS_RECOVERY_TYPE_PRELOAD_CORRECTION_20261031.md.

2026-10-31 saved-counter review: approx96% of66.28->86.93% CPU increase is system/IRQ/softIRQ time, not user time. Existing user-only Nav2 stacks cannot identify kernel hot path. No substantial safe runtime fix established; no new tools/tests/live actions. See ATLAS_RECOVERY_KERNEL_TIME_FINDING_20261031.md.

2026-10-31 OWNER STOP: CPU investigation stopped at evidence limit; root cause UNKNOWN. Recovery incident OPEN, service STOPPED; its fault reporting/automatic recovery unavailable. CPU optimization and restoration NOT COMPLETE. AMCL initial-pose/missing-map-transform warnings tracked separately, not a confirmed CPU cause. Evidence retained; no further tools/retries authorized. Handover: ATLAS_RECOVERY_INCIDENT_HANDOVER_20261031.md.

2026-10-31 separate localization finding: map loaded; verify-mode seeder deliberately withheld initial pose after ambiguous matches (margin0.004). AMCL/map-TF readiness blocked, physical disambiguation unresolved. No pose published or runtime changed. One ambiguity test PASS; old source-text seeder test ERROR due renamed observer call. See ATLAS_AMCL_INITIAL_POSE_FINDINGS_20261031.md.

2026-10-31 AMCL follow-up: saved two candidates match230/246 and229/246 held-out beams,213 common; current room independently confirmed DHRUV ROOM. Heading/movement history pending, no current pose verified. Existing verify-place dry-run needs separate live approval; five focused tests PASS, test-only API fix. Recovery remains STOPPED/open. See ATLAS_AMCL_PLACE_VERIFICATION_PLAN_20261031.md.


2026-10-31: Named-place localization dry-run safety path corrected offline: one
attempt, bounded processing, independent existing safety utilities and continuous
sensor/TF freshness checks. 14 focused tests passed. Not deployed or executed;
localization remains unverified and Recovery remains STOPPED/open. See
[guard report](ATLAS_LOCALIZATION_DRY_RUN_GUARD_20261031.md).

2026-11-02 superseding state: bounded snapshot validation failed CPU77.4461%; no same-window process attribution, causeUNKNOWN. Exact original Recovery script andRestartalways restored; RecoverySTOPPED, snapshotdisabled, incidentOPEN. Original-only restoration prepared/offline8tests, not executed. No restart authorization in overnight sprint. See ATLAS_WEB_BINDING_READY_20261102.md superseding section. AMCL edd6563 mission-start offline15tests PASS; no live localization acceptance.

2026-11-02: Original-only restoration failed watcher freshness before start; noCPUviolation (acceptedpeak62.79%). RecoverySTOPPED/PID0, originalpolicy/source intact. Timing cadence/publication ordering corrected offline in existing package,8focusedtests/reviewPASS; newattempt requiresapproval. HardwaretimingPENDING; earlier77.45%CPUcause remainsUNKNOWN. See ATLAS_WEB_BINDING_READY_20261102.md.

2026-11-02: Cadence-corrected restoration aborted on watcher systemctlPID query during daemonreload beforestart; noCPUviolation. Direct cgroup/proc identity replacement offline12tests/reviewPASS, notdeployed. RecoverySTOPPED; incidentOPEN; separateoriginal-only executionapproval required. See ATLAS_WEB_BINDING_READY_20261102.md.

2026-11-04: Neural PARTIAL LIVE (owner-accepted 3-second PC scrape trial; two paths verified). Continuous coverage remains blocked by the unchanged 15-second exporter cache; separate follow-up only. PRIMARY task is independent Object Detection/read-only Tracking host. Existing RGB HTTP route can start viewer transport through touch(), so it is not yet a guaranteed passive boundary. Deployment remains NO-GO pending cache-only transport/API implementation and reviewed access/rollback. No service changes. See ../ATLAS_VISION_HOST_PREPARATION_20261104.md.

2026-11-04: Vision independent host/cache boundary implemented offline; 15 focused checks and independent review PASS. SSH-authenticated private Unix-socket design, disabled inactive archive and exact-live rollback prepared. No deployment. Runtime BLOCKED: running Web lacks passive endpoint; no verified no-restart module loading path. CPU/model resource compatibility UNKNOWN. See ../ATLAS_VISION_HOST_OFFLINE_RESULT_20261104.md. Neural remains PARTIAL LIVE; no monitoring changes.

2026-11-12 remap-jump follow-up (offline replay, no live changes): EKF process-noise candidate q_vx 0.025->0.5 replayed on remap_20261112-160012_bag. Room->hall straight-line: live EKF 2.31 m, replay current 2.31 m, candidate 3.34 m, vs truth ~6.1-6.4 m (SLAM 6.39 m, old map places 6.07 m). Heading identical in all variants (-187.3 deg). Raw wheel |speed| integrated room->hall is only 5.12 m path, i.e. below the 6.39 m straight-line distance, so the wheel odometry itself under-reports distance (>=20%) in addition to the EKF lag. Candidate q_vx=0.5 is NOT sufficient alone and was NOT applied; atlas_ekf.yaml unchanged (vx-only + IM10A yaw). Next discriminating test: offline wheel-speed vs LiDAR keyframe-ICP translation scale on the same bag (no motion needed). Remap attempt 2 stays blocked until odometry distance is fixed.

2026-11-12 wheel vs LiDAR scale (offline, read-only; tool project_atlas/tools/localization/wheel_vs_lidar_scale.py, same method as ATLAS_ENCODER_SCALE_BY_SPEED_2026-10-11): clean straight scan pairs from today's three drive bags. /yahboom/odom over LiDAR ICP distance: remap_20261112-160012 0.64x (278 pairs, 17.29 m), m3_session_151321 0.66x (104 pairs), m3_session_153118 0.65x (87 pairs). Binned by ICP speed and by wheel speed: 0.58-0.71 in all bins, no consistent speed trend in both binnings. Same ~0.6-0.7x as ATLAS-001 on Oct 9 bags, so it is persistent, not new. The EKF (vx-only, q_vx 0.025) further reduces it to 0.34-0.43x on short pairs (lag). Root cause of the remap jump: wheel distance about 0.65x true plus EKF lag. Constant CPR/wheel-size error vs constant slip is still not separated; needs a wheels-off-ground hand-rotation test by the owner. No calibration or config changed.

2026-11-12 ~16:55-17:02 hand-turn test (owner; wheels lifted, E-STOP latched (software latch), board/motor power ON, each wheel turned forward ~5 turns by hand): read-only recorder (project_atlas/tools/localization/wheel_hand_turn_recorder.py) got ~4,400 fresh packets per wheel (/atlas/encoder_update packet_fresh true, sequence advancing) but raw counts did not change by even 1 count on any wheel (152190, -168149, -26078, -145047 before and after). INCONCLUSIVE for CPR vs slip. Either the board does not report count changes while traction PWM is 0, or the hand rotation did not reach the encoders. A powered lifted-wheel test (owner drives slowly with the remote, counting tape-marked turns) is the next discriminating step. Nothing changed.

2026-11-12 17:08-17:21 hand-turn test, second attempt (owner, wheels lifted, E-STOP latched, power on, each wheel turned forward 2 full turns by hand, one at a time; read-only recorder, logs /tmp/hand_turn_log_frontleft.csv and /tmp/hand_turn_log_3wheels.csv on the Jetson). Counts per wheel in turn order:
- front left: M3 +149 counts (0.07 turn of 2), jittering -128..+149. Consistent with the known M3 forward-count loss.
- front right: M4 -2980 counts = 1.34 configured turns, i.e. ~1490 counts/turn vs configured 2230.5 (0.67x).
- "rear left": counted on M2 (configured rear_right), -2992 counts, ~1496/turn vs 2215.0 (0.68x); M1 unchanged.
- "rear right": counted on M1 (configured rear_left), +3170 counts, ~1585/turn vs 2238.4 (0.71x). M2 also moved back +1477 during this step (unexplained: coupling, contact or a counting artefact).
Conclusion (provisional, hand-counted turns are about ±5 %): the configured counts_per_revolution values are ~1.4-1.5x too high, which explains most of the 0.65x wheel distance seen against the LiDAR. It is a calibration/config error, not mainly floor slip. Rear M1/M2 position mapping may be swapped; the owner's left/right perspective still needs confirming. No calibration or config changed; a CPR change needs owner approval and a LiDAR-verified drive.

2026-11-12 17:24 APPLIED (owner approved): encoder_calibration.yaml counts_per_revolution M1 2238.4->1585, M2 2215.0->1496, M3 2199.1->1500 (estimate, faulty channel), M4 2230.5->1490. Backup on the Jetson: config/encoder_calibration.yaml.before-cpr-20261112 (md5 ea558981...). rover-base-telemetry restarted while parked with E-STOP latched; loader validation OK; encoder_health READY 4/4. The rear M1/M2 position swap was approved too but NOT applied: atlas_encoder_calibration.py enforces fixed labels (m1 rear_left, m2 rear_right), so the swap needs a code change.
Verification drive 17:39-17:41 (owner; back ~1.1 m then forward, recorded /tmp/cpr_check_bag3): 47 clean straight LiDAR ICP pairs, wheel/LiDAR 0.97x (2.72 / 2.80 m; bins 0.86-1.09), was 0.64-0.66x. Wheel distance FIXED. The EKF /odom is still 0.58x on short pairs (lag: wheel twist cov 0.1 vs q_vx 0.025); the q_vx candidate is still open. Rollback: copy the backup back and restart rover-base-telemetry while parked.

2026-11-12 ~17:50 EKF q_vx replay on the verification drive (cpr_check_bag3; no IM10A topic in this bag, straight drive): whole-drive path wheel 2.69 m (~0.97x LiDAR), live EKF 2.53 m (0.94x wheel), replay current 2.43 m, replay candidate q_vx=0.5 2.55 m (+5 % vs current replay). After the CPR fix, the EKF loses only ~6 % over a full drive; the 0.58x on short scan pairs is timing lag that catches up, not lost distance. q_vx change NOT applied (small gain). Re-evaluate after remap attempt 2 if the SLAM jump is still over the gate.

2026-11-12 18:30 Astra colour ENABLED (owner OK "Yes, use Astra"): new astra.color block in astra_obstacles.yaml (UVC 2bc5:0501, 640x480 MJPEG at 15 fps, extrinsic publishing on). Depth parameters are unchanged and depth_registration stays false, so the obstacle scan keeps the factory depth CameraInfo. Backups on the Jetson: *.before-20261112-colour. After the restart (parked, E-STOP latched): /astra/color/image_raw 15 Hz, depth 17.6 Hz, obstacle_scan_status OK, astra camera_node ~39 % of one core. The atlas-astra-bridge (domain 0) did NOT restart: its parked check refused because cmd_vel telemetry is stale while the E-STOP is latched (fails closed as designed; not bypassed). The bridge needs a fresh cmd_vel (owner releases the E-STOP with sticks untouched) before it is started again. Rollback: color.enable false, restart atlas-astra-obstacles.
2026-11-12 18:33: the owner released the E-STOP with the sticks untouched; the bridge parked check passed and atlas-astra-bridge is active. /astra/obstacle_scan is 8.1 Hz in domain 77 and 6.7 Hz in domain 0, the same as the Nov 6 baseline (6.4-6.9 Hz), so colour did not slow the obstacle scan.

2026-11-12 ~18:50 map-acceptance start-coverage fix (owner OK "Yes, fix it"). Root cause: manual teaching deliberately begins the map->odom observation at ready_unix (after ensure_mapping_stack, about 79 s in attempt 1), but evaluate_acceptance_evidence required it within 5 s of started_unix, so manual teaching could never pass. Fix: for mode manual_teaching, the coverage reference is ready_unix, and a NEW fail-closed gate requires /yahboom/odom stillness between the start request and drive-ready (displacement <= 0.02 m, yaw <= 2 deg, odom age <= 2 s at both ends; missing evidence = reject). Exploration sessions are unchanged; all other limits are unchanged. Tests: scripts/test_map_acceptance_startup.py, 8/8 PASS on the Jetson, including a replay of the attempt-1 evidence: old reference reproduces the coverage failure; new reference leaves only the real 0.916 m / 12.0 deg jump; missing stillness rejects. Deployed; atlas-mission-control restarted while parked (READY). Backups: scripts/*.before-startup-gate-20261112. Pre-remap state backup: ~/.config/project_atlas/manual_session_backups/pre-remap2-20261112. Colour side recorder: tools/m3/color_side_record.sh (tested, ~13 MB/s).

2026-11-12 remap attempt 2 (sessions):
- 18:45-19:04, session 6c954325: ABORTED with no drive. The owner did not drive, and "hall" was saved at the start spot by mistake. The session file was moved aside before stop_exploration, so no candidate map was saved and the accepted map was preserved. Saved places were restored from pre-remap2-20261112 and the session's home pose was set aside.
- 19:43-19:58, session 348c4a79 (owner drove room -> hall -> room; colour side recording maps3d/remap3_colour_20261112-194252): REJECTED, accepted map preserved (atlas_latest.pgm md5 3b049b9e unchanged).
  - startup stillness 0.000 m; ready 1.5 s after start;
  - the start-coverage failure is GONE (the fix works);
  - closure PASSED (0.092 m / 7.0 deg);
  - failures: map->odom translation jump 1.392 m at 19:50:21 and yaw jump 20.7 deg at 19:51:52 (around the hall / start of the return).
  - Report: maps/.atlas_candidate_348c4a79....acceptance.json.
  - Hall saved at map (-8.40, 2.57), 6.8 m from start.
  - Place, home and seed files from the session are kept in ~/.config/project_atlas/rejected_session_348c4a79; named_places restored; home NOT set.
  - Normal localization restored: atlas-localization started (slam-fast/nav2 stopped by its Conflicts), seeded; verify-place "dhruv room" VERIFIED, fit 0.996, margin 0.217.
  - Open: why EKF /odom moved only 3.3 m vs SLAM 6.8 m room->hall despite wheel 0.97x on a straight drive. Turns / heading are suspected; needs analysis of the base bag.

2026-11-12 ~20:30 remap attempt 2 jump analysis (offline, maps3d/remap3_colour_20261112-194252/base):
- Sensors are fine. Wheel vs LiDAR ICP 0.93x (315 straight pairs). Heading: EKF follows IM10A, and both stay within about 3-10 deg of LiDAR keyframe ICP through 350 deg of net turning.
- Room->hall straight-line distance by estimate:
  - LiDAR keyframe ICP 6.88 m;
  - wheel speed x IM10A heading dead reckoning 6.05 m, ending 0.13 m from start;
  - live EKF 3.32 m, ending 1.38 m from start;
  - SLAM hall 6.8 m.
- EKF vx is 0.38x wheel vx while moving (best correlation at 0.2 s lag). The EKF itself throws away distance: wheel twist variance 0.1 vs process noise q_vx 0.025 makes it heavily low-pass vx. Timestamps are fine (lag <10 ms) and the IMU has no acceleration inputs.
- Replays of this bag (offline, domain 92):
  - current: 3.32 m / end 1.38 m (reproduces live);
  - +vy fusion: no change;
  - q_vx 0.5: 5.00 m / 0.49 m;
  - q_vx 2.0: 5.69 m / 0.16 m, path 21.71 m vs wheel 21.67 m.
- Candidate: process_noise_covariance[vx] 0.025 -> 2.0. NOT applied; needs owner OK.
2026-11-12 ~20:45 APPLIED (owner OK "Yes, apply it"): atlas_ekf.yaml process_noise_covariance vx 0.025 -> 2.0 (all else unchanged). Backup on the Jetson: config/atlas_ekf.yaml.before-qvx2-20261112. atlas-ekf restarted while parked with the E-STOP latched; /odom 9 Hz, at rest 0.0. AMCL re-seeded with verify-place "dhruv room": VERIFIED (fit 1.0, margin 0.229); AMCL (0.215, -1.891). Live drive validation is pending (owner drive with LiDAR comparison), then remap attempt 3. Rollback: copy the backup back, restart atlas-ekf while parked, re-seed with verify-place.
2026-11-12 21:09-21:12 live check of q_vx 2.0 (owner short drive, about 1 m; /tmp/ekf_check_bag): EKF vx / wheel vx 0.78 mean while moving (before: 0.38). Straight pairs EKF/LiDAR 0.78x (before: 0.40-0.54x). End displacement LiDAR ICP 0.88 m, wheel+IM10A 0.77 m, EKF 0.65 m; path EKF 0.74 vs wheel 0.83 (0.89x). Clearly improved; the drive was too short for a full validation. Next: remap attempt 3 (room->hall->room) as the real test.

2026-11-12 remap attempt 3 (session b852bf94, 21:11-21:35, with EKF q_vx 2.0): REJECTED, accepted map preserved (md5 3b049b9e unchanged).
- startup stillness 0.000 m; start coverage OK;
- closure PASSED (0.033 m / 0.96 deg; the owner moved forward 45 cm onto the true start spot, which was 45 cm ahead of the old tape after the test drive);
- room->hall: SLAM 6.6 m vs EKF about 5.4 m (attempt 2: 3.3 m), so improved but still ~0.8x;
- failures: map->odom single-step jump 1.112 m at 21:31:06 and yaw 14.8 deg at 21:32:20. Both came early in the return drive, after a 20-min parked wait in the hall. They look like slam_toolbox snapping the accumulated odometry error (~1 m) in one step when it re-recognised the corridor/room.
- Colour data: maps3d/remap4_colour_20261112-211052 (outbound) and remap4b_colour_return_20261112-213018 (return).
- Restored as before: rejected_session_b852bf94 kept; named_places from pre-remap2 backup; home not set; atlas-localization restarted; verify-place "dhruv room" VERIFIED (fit 1.0, margin 0.117).
- Next candidate (not done): wheel+EKF alone remains ~10-20 % short. The existing shadow EKF with rf2o LiDAR odometry (atlas-ekf-lidar-candidate) should be evaluated offline on these bags before any change. The 0.15 m single-step gate is unchanged.

2026-11-12 ~22:00 offline odometry comparison on the remap attempt 3 outbound bag (remap4_colour_20261112-211052/base; 12.3 m SLAM path, 416 s). Each track is aligned to the SLAM pose (map->odom ∘ odom) at motion start; error vs SLAM at the end:
- live /odom (q_vx 2.0) 1.35 m (replay "current" reproduces it exactly: 1.35 m);
- existing LiDAR shadow EKF (rf2o -> lidar_odom_gate -> atlas_ekf_lidar_candidate, replayed in domain 93) 2.28 m, i.e. WORSE; NOT a candidate;
- wheel speed x IM10A dead reckoning 1.09 m;
- keyframe scan-to-scan ICP alone 0.47 m (max 0.62), but heading error up to 18 deg. Its translation must be rotated by 180 deg: the laser frame points backwards relative to base_link;
- ICP translation x IM10A heading: 0.20 m final, 0.28 m max (0.17 m per 10 m), about 5x better than the live EKF.
Conclusion: wheel-based odometry cannot meet the 0.15 m single-step map gate over a room->hall->room loop. A LiDAR scan-matching translation source with IM10A heading is the promising fix; it needs a new real-time node plus EKF fusion, an offline replay first, then owner approval. Tools: project_atlas/tools/localization/{replay_lidar_ekf.sh, compare_odom_to_slam.py, icp_wheelimu_export.py}. Nothing changed live.

2026-11-12 ~22:40 NEW (offline-validated, NOT deployed): LiDAR keyframe-ICP odometry node.
- Files: scripts/atlas_icp_odometry.py + atlas_icp_odometry_core.py, publishing /lidar/icp_odom with body vx/vy; the laser mount comes from TF (yaw 180 deg).
- Tests: test_icp_odometry_core.py 5/5 PASS (synthetic room, backwards laser, still/forward/turn+drive/rejection).
- Replays (tools/localization/replay_icp_ekf.sh, domain 94) against the SLAM pose:
  - outbound 12.3 m: live EKF 1.35 m; ICP node alone 0.03 m final (0.19 max); EKF + ICP vx/vy (variance 0.002) 0.30 m final (0.32 max);
  - return drive (includes the SLAM 1.1 m snap in its reference): live 1.18 m; EKF + ICP 0.46 m.
- Live CPU test (read-only, 60 s, new topic only): 23 ms/scan, ~14 % of one core, 0 rejected, inliers 0.995. Initially 179 ms/scan; fixed with an early-convergence stop.
- Proposed live change (needs owner OK): run the node as a user service and add odom1 /lidar/icp_odom (vx, vy) to atlas_ekf.yaml. Restart the EKF while parked with the E-STOP latched, then verify-place.
2026-11-12 ~22:30 APPLIED (owner OK "Yes, switch it on"):
- New user unit atlas-icp-odometry.service (enabled at boot) runs scripts/atlas_icp_odometry.py with velocity variance 0.002 and a stationary lock: velocity is zero while fresh wheel odometry is still (|vx| < 3 mm/s, |wz| < 0.01 rad/s, age < 1.5 s).
- atlas_ekf.yaml gains odom1 /lidar/icp_odom (vx, vy). Backup: config/atlas_ekf.yaml.before-icp-20261112.
- atlas-ekf restarted while parked with the E-STOP latched.
- Parked drift: 1.0 cm per 40 s without the lock, 0.0 with it.
- Node: 16-52 ms/scan under live load (scan period 128 ms), 0 rejected, inliers ~0.99.
- AMCL re-seeded from a LiDAR-verified pose (0.315, -1.135) in Dhruv Room.
- Pending: live drive validation, then remap attempt 4.
- Rollback: copy the EKF backup back, disable --now atlas-icp-odometry, restart atlas-ekf while parked, verify-place.

2026-11-12 ~23:10 colour 3D map v1 (offline, from remap attempt 3 recordings):
- Built with tools/m3/build_colour_map.py:
  - Astra depth 160x120 + colour 640x480;
  - SLAM poses (map->odom ∘ odom), refined by scan-to-map ICP against the session's 2D map (.atlas_candidate_b852bf94);
  - frames skipped above 8 deg/s turn rate;
  - 2 cm voxels seen >= 2 times.
- Result: 327,802 points (maps3d/colour_room_hall_20261112.ply); dashboard copy 52,199 points at 5 cm.
- Checks (sharpness = 5 cm cells occupied):
  - depth time offset sweep -0.3..+0.35 s: 0 is best;
  - camera yaw sweep -6..+6 deg: 0 is best;
  - map refinement: 6 % sharper.
- Known limits: some walls in Dhruv Room still show 2-3 copies; the hall is dark (lighting); no depth->colour offset (extrinsic message not recorded); refinement failed for 154 of 267 frames outside the room.
- Dashboard: web/v2/home-cards.js draws real colours when the feed has "rgb" (far-to-near order) and redraws once the full-screen overlay is sized. map3d_live.txt now holds the stored colour map. Backups: *.before-colour3d-20261112.
- Next for better quality: a new drive with the ICP odometry live and the lights on.

2026-11-13 remap attempt 4 (session 00c9e957, 10:24-10:48, first drive with the ICP odometry live). REJECTED; accepted map preserved (md5 3b049b9e).
- First start attempt (10:21) failed: "mapping stack did not become ready within 90 s" (CPU ~8 % idle after boot). Retry with the stack up: ready in 1 s.
- Startup stillness 0.000 m; closure PASSED (0.036 m / 1.3 deg, after the owner backed up 20 cm).
- Room->hall: map->odom correction only 0.29 m / 1.4 deg on reaching the hall (attempt 3: ~1.2 m), so the ICP odometry helped.
- Failures:
  - map->odom jump 1.456 m at 10:32:39 and yaw 11.0 deg at 10:32:49, at the start of the return drive;
  - max SLAM TF source age 2.1 s;
  - candidate map not connected room<->hall (no inflated path, footprint path or Nav2 plans).
- Context: the Jetson was overloaded during the return. Load average reached 40-47 with ~2 % CPU idle (two bag recorders, mapping stack, IMX708 camera node, Nav2). The dashboard (rover-status-web) stopped answering; it was restarted at 10:42 after the colour recorder stopped.
- Suspected: CPU starvation delayed slam_toolbox (2.1 s source age), then a large correction. Not yet proven.
- Restored: rejected_session_00c9e957 kept; named_places from pre-remap5-20261113; home not set. atlas-localization failed its first start ("AMCL is not subscribed to /initialpose"; lifecycle timeouts under load) and came up on retry; seeded from a LiDAR-verified pose (0.235, -1.535).
- Colour data: maps3d/remap5b_colour_20261113-102354 (outbound and return until ~10:40).

2026-11-13 ~11:10 attempt 4 jump analysis (tools/localization/slam_jump_timeline.py on remap5b_colour_20261113-102354/base):
- The big corrections (1.95 m / 14.6 deg at 10:32:52, 1.30 m at 10:32:50, 1.32 m / 18.9 deg at 10:33:24, plus 0.8-0.9 m steps to 10:33:25) all fall in the first ~45 s of the return.
- During that window the wheels report the rover driven fast: up to 0.78-1.02 m/s and 82-148 deg/s turn rate. Over the whole return, speed 95th percentile was 0.65 m/s (outbound 0.52), turn rate max 148 deg/s (outbound 86).
- LiDAR rate stayed normal (6.5-6.8 Hz every minute, scan delay <= 0.54 s). The SLAM TF delay was ~3.8 s all session, also when calm, so it is not specific to the jump. CPU overload is therefore NOT the primary cause.
- Main cause: aggressive driving/spinning at the start of the return smeared LiDAR scans (148 deg/s = ~22 deg per scan at 6.7 Hz) beyond what scan matching tracks, and SLAM corrected in large steps. The room<->hall connectivity failure follows from the resulting smeared map.
- Fix to try: a mapping-mode speed limit (e.g. <= 0.3 m/s, <= 30 deg/s) or strict slow driving. Any limit is a config change needing owner OK.

2026-11-13 ~11:40 CORRECTION to the 11:10 entry (new discriminating evidence from independent sensors, same window 10:32:19-10:33:25):
- Turn rate: IM10A max 53 deg/s (95 % 34 deg/s). The 148 deg/s figure was WHEEL-reported and wrong: wheel yaw is unreliable (swapped rear labels, faulty M3). The existing mux mapping limits (mapping_remote_max_linear 0.30 m/s, mapping_remote_max_angular 1.20 rad/s, active in operating mode MAPPING) held for turning.
- Linear speed (LiDAR ICP): 0.61 m/s 95 %, 0.77 max, about 2x the commanded 0.30 m/s cap. The open-loop PWM drive (drive PID disabled) moves ~2x faster than the commanded value since the CPR fix.
- ICP odometry: 0 rejected scans in the window; EKF /odom stayed smooth.
- SLAM (map->odom) oscillated within ~40 s: (-0.22,0.19,1.4 deg) -> (-0.51,0.29,3.8) -> (+0.64,-0.24,-7.8) -> (-1.51,0.30,9.4) -> (-1.15,0.18,5.2) -> (-1.52,0.38,10.4) -> (-0.90,0.36,4.3) -> (-0.55,0.20,0.4) -> (-1.08,0.26,8.4).
- So the jumps come from slam_toolbox scan matching bouncing, not from odometry. SLAM TF stamps lag receipt by ~3.8 s all session (scan_queue_size 20, minimum_travel_distance 0.05 m, minimum_time_interval 0.1 s): SLAM is running ~4 s behind.
- Revised suspects: (1) the SLAM processing backlog and its default correlative search accepting wrong matches during faster motion; (2) real speed ~0.6 m/s.
- Candidate fixes (not applied): lower mapping_remote_max_linear to ~0.15 (real ~0.3 m/s); offline replay of slam_toolbox parameter variants (larger minimum travel, smaller scan queue, stronger odometry trust) on this bag before any live change.

2026-11-13 ~12:00 APPLIED (owner OK "Yes, do both"): atlas_cmd_vel_mux.py default mapping_remote_max_linear 0.30 -> 0.15. It applies only in operating mode MAPPING and can only reduce speed. Live parameter read back as 0.15. Backup: scripts/atlas_cmd_vel_mux.py.before-mapcap-20261113. The mux restarted while parked; RemoteStop starts latched by design. The angular cap stays 1.20 rad/s (the real turn rate stayed below it).
Started: offline slam_toolbox replays (tools/localization/replay_slam.sh, domain 95) of the attempt 4 bag with three variants: live params; lighter processing (0.2 m / 0.17 rad / 0.5 s, queue 1); lighter + stronger odometry trust (variance penalties 1.0/2.0, search 0.3 m).

2026-11-13 ~13:00 offline slam_toolbox replays of the attempt 4 bag (tools/localization/replay_slam.sh; odom->base_link TF rebuilt from /odom because the recorded /tf odom->base_link arrived ~11 s late, 1.6 Hz, which made the first replay attempt invalid):
- live params: max single step 0.757 m at 10:32:55 (reproduces live); 63 steps > 0.15 m; 6 > 5 deg; total correction 28.7 m.
- lighter (min travel 0.2 m / 0.17 rad, interval 0.5 s, queue 1, map update 3 s): max 1.019 m at 10:33:20; 32 steps > 0.15 m; total 14.9 m.
- lighter + variance penalties 1.0/2.0 + search 0.3 m: same as lighter (no effect).
- lighter + loop closing off: same max 1.019 m at 10:33:20, so the big jump is scan matching, NOT loop closure.
At 10:33:15-29 the rover moved up to 0.87 m/s (0.19 m and 11.5 deg between consecutive odom samples) in a narrow spot: 170/360 valid beams, median range 0.58 m. Conclusion: lighter processing halves the bouncing; the remaining large jump comes from fast motion through a tight, feature-poor place. The new 0.15 mapping cap (real ~0.3 m/s) targets it directly; slower driving cannot be proven by replay.
Proposal (not applied; needs owner OK): lighter SLAM settings in atlas-slam-fast.service.
2026-11-13 ~13:10 APPLIED (owner OK "Yes, switch on"): atlas-slam-fast.service lighter settings.
- minimum_time_interval 0.10 -> 0.5; minimum_travel_distance 0.05 -> 0.2; minimum_travel_heading 0.10 -> 0.17; map_update_interval 1.5 -> 3.0; scan_queue_size 20 -> 1.
- Only ExecStart changed. Backup: ~/.config/systemd/user/atlas-slam-fast.service.before-lighter-20261113. daemon-reload done; the unit was inactive (localization mode), so it takes effect at the next mapping session.
- Together with the mapping speed cap 0.15, ready for remap attempt 5.

2026-11-13 ~13:40 owner-approved fixes ("Yes, deploy all"):
- Dashboard deadlock: rover-status-web was found hung (27 threads in futex wait, ~2 % CPU, CLOSE-WAIT sockets with unread requests), so CPU was not the cause.
  - atlas_status_web.py now registers faulthandler on SIGUSR1, which dumps all thread stacks to the journal.
  - New atlas-status-web-watchdog.timer (every 20 s, enabled at boot) curls /v2/; after 2 failed checks it sends SIGUSR1 and restarts rover-status-web only.
  - The root-cause lock is still unknown; the next hang will produce the stack dump.
- Mapping CPU: manual teaching paused nothing (only exploration called pause_mapping_background). start_manual_mapping now pauses MAPPING_BACKGROUND_UNITS, extended with ai-annotator, agent-team and person-sensor-fusion (~25 % of a core), and restores them on start failure and at stop (existing finally). The Pi camera is kept: atlas_sensor_recovery restarts atlas-camera when its stream is stale.
- Backups: scripts/*.before-20261113-cpu-dash.
- CORRECTION to the 13:10 SLAM change: scan_queue_size 1 broke live SLAM. The tf message filter discarded every scan ("queue is full"), so no map frame was produced; that is why the 13:08 mapping start failed after 90 s. The offline replay did not show this. Set scan_queue_size 5 (other lighter settings unchanged); after the restart the map frame appeared within 10 s with 0 drops. Dashboard /api/map now returns the live SLAM map and the rover pose (map->base_link).

2026-11-13 remap attempt 5 (session 57941c0d, 13:41-13:52; speed cap 0.15, lighter SLAM with queue 5, ICP odometry). REJECTED; accepted map preserved.
- Passed: startup stillness 0.000 m; closure 0.051 m / 8.6 deg; room<->hall connectivity and Nav2 plans (they failed in attempt 4).
- Failed: map->odom single-step jumps 1.120 m (13:49:34, return) and yaw 12.0 deg (13:45:43, room lap).
- Other large steps, often paired back-and-forth: 0.89 m at 13:46:31/33 and 0.80-0.89 m at 13:49:02/08.
- The SLAM TF is now timely (stamp ahead of receipt; it was ~3.8 s behind in attempt 4).
- At every jump window: real speed median 0.04-0.14 m/s (scan-pair max 0.52-0.66), IM10A turn <= 38 deg/s, ICP odometry 0 rejections. Only 130-173 of 360 beams were valid, median range 1.0-1.5 m.
- Conclusion: the bouncing persists at walking speed with good odometry. slam_toolbox scan matching accepts wrong matches with this sparse RPLIDAR data.
- Bug found and fixed: pause_mapping_background stopped the voice companion, but "Job for atlas-ai-annotator.service canceled" raised before the record was written, so voice was not restored. Voice restarted manually; ai-annotator removed from the list; units are now stopped one by one with a per-unit record. Deployed (mission control restarted, no session).
- Localization restored (seeded from a LiDAR-verified pose (0.115, -1.995)); named_places from pre-remap6-20261113; rejected_session_57941c0d kept.
- Next candidates (offline replay on this bag first): stricter scan-match acceptance (link_match_minimum_response_fine, smaller search window); odometry-led mapping (scan matching off) with closure checked against ICP drift.

2026-11-13 ~14:30 offline replays on the attempt 5 bag (remap6_colour_20261113-134122/base):
- current lighter params: max step 0.525 m at 13:49:35 (live had 1.12 m at 13:49:34); 14 steps > 0.15 m; total correction 7.33 m.
- strict matching (link response 0.3, loop response 0.6, search 0.3 m, loop distance 2 m): 0.515 m at the same moment, 14 steps, i.e. no effect (like the penalty/search variants earlier).
- odometry-only (scan matching off) checked directly from /odom: start vs parked end 0.610 m / 5.2 deg over a 27.1 m path. Fails the 0.15 m closure, so it is ruled out.
LiDAR data: while parked, only 207/360 bins are valid; the 153 empty bins are spread evenly over all directions, so it is not an obstruction. Driver: rplidar_ros scan_mode Standard (2 kHz sample rate) at ~7-8 Hz with angle_compensate into 360 bins (fw 1.29, hw rev 7). Leading hypothesis: sparse scans give ambiguous matches in the corridor. Candidate (needs owner OK, parked restart): a denser RPLIDAR scan mode (Express/Boost, if supported), then measure valid bins and replay.
2026-11-13 ~14:30 APPLIED (owner OK "Yes, test LiDAR mode", kept after test): atlas-lidar.service scan_mode Standard -> Boost.
- RPLIDAR A1 fw 1.29 hw rev 7 accepts Boost: 8 kHz sample rate.
- Backup: atlas-lidar.service.before-scanmode-20261113. Restarted while parked with the E-STOP latched.
- /scan now 1080 beams at 0.33 deg, 1040 valid (96 %), 7.2 Hz. Standard mode gave 207/360 valid (57 %).
- Downstream: atlas_scan_self_filter uses angle_increment (no fixed 360).
- ICP odometry: scan_to_points now subsamples to max_points 400. 92 ms/scan -> 20 ms/scan; core tests 5/5 pass.
- Localization on the old map with Boost scans: verify-place "dhruv room" VERIFIED, fit 0.987, margin 0.205.
- CPU: atlas-localization (AMCL + Nav2) ~53 % of a core during the check.
- Next: remap attempt 6 with denser scans.

2026-11-13 ~14:35-14:50 remap attempt 6 ABORTED, Boost REVERTED:
- Session 1e570a39 started only after a manual atlas-slam-fast restart. Cold switches from localization to mapping have failed three times today (10:21, 13:08, 14:29: no map frame within 90 s); a restart always fixes it. Cause not yet found.
- The remote stop latched ("REMOTE STOP: joystick unavailable"). The owner reset it.
- With LiDAR Boost (1080 beams) + mapping + recorders, load average reached 50-59. TF odom->base_link stopped arriving (map and base_link not connected) and the EKF missed its update rate.
- Session aborted without a map: the session file was moved aside before stop_exploration. Accepted map preserved; background profile restored.
- LiDAR restored to Standard from atlas-lidar.service.before-scanmode-20261113. Named places from pre-remap7.
- Localization restarted; seeded at the hall (6.475, -2.375) before the owner drove back. Load fell to ~14 by 14:49.
- Remote input priority: atlas-remote.service (joy_node + teleop) had default CPU weight while the base and mux have CPUWeight=1000. joy gaps under load latch the remote stop. Applied `systemctl --user set-property atlas-remote.service CPUWeight=1000` (live, persistent in ~/.config/systemd/user.control, no restart).
- Boost needs scan thinning first: one decimating node (1080 -> ~360 bins) for all consumers, keeping full density only where needed.

2026-11-13 ~15:05 CPU reduction (owner chose "Pause AI extras" and "Lighten the dashboard"):
- Baseline per service (% of one core, localization mode): atlas-localization 55, rover-status-web 40, atlas-camera 34, rover-base-telemetry 30, voice 22, astra 22, sensor-recovery 16, mux 16, mission-control 15, localization-monitor 14, safety-status 13, icp-odometry 13, rf2o 10, ai-annotator 10, agent-team 9. Total ~430 % of 600 %.
- Dashboard: stack sampling (SIGUSR1) showed the time going into executor wait-set rebuilds (wait_for_ready_callbacks), one per message, ~190 msg/s on the hot node.
  - atlas_dashboard_executor.create_executor/spin gained batch_s: sleep before each wait-set rebuild so pending messages are dispatched in one pass.
  - Hot node (web drive/E-STOP path) 30 ms; status node 100 ms. The integrity-hashed impl file is unchanged.
  - Result: rover-status-web 40 % -> 17 %; /v2/ answers in 0.01 s; /api/map OK.
  - Tests on the Jetson are identical before and after: idle_camera 11 pass, smart_panels 7 pass, executor_split 4 pass/1 fail/1 skip. estop_reset, estop_safety, no_reboot and executor_profile ERROR at collection (missing module calibration_validation, pre-existing); snapshot_cost 5 fail (pre-existing). So the web E-STOP path is NOT covered by a passing test.
  - Backups: scripts/*.before-batching-20261113.
- AI extras: stopped, but atlas-feature-on-demand restarted them within ~1 min. The design is fail-open: mission_status != READY counts as autonomy demand, and after the abort the status stayed "MAPPING NOT ACTIVE; ACCEPTED MAP PRESERVED". Mission control restarted (no session), status READY, so the manager stops them after idle_s 300. They were already "disabled" at boot; boot state recorded in ~/.config/project_atlas/ai_extras_paused_20261113.txt.
- Follow-up: mission control should publish READY after a stop/abort finishes.
2026-11-13 ~15:15 parked in Dhruv Room: verify-place VERIFIED (fit 0.996, margin 0.22), AMCL (0.20, -1.80). Normal localization healthy after today's changes.

2026-11-13 ~16:00 APPLIED (owner OK "Thin dense scans"): LiDAR Boost + thinning in atlas_scan_self_filter.
- Filter rewritten with numpy; self-box logic unchanged. When the raw scan has >= 1.5x TARGET_BINS (360) beams, each output bin is the NEAREST valid return of its consecutive raw beams (conservative for obstacles). angle_min is the group centre, angle_increment and time_increment are x factor, and the header stamp is unchanged. Standard-mode scans pass through unthinned.
- tests/test_atlas_scan_self_filter.py: 3 new tests (nearest-per-bin with empty and below-min bins; self-returns removed before thinning; Standard not thinned). 6/6 pass on the Jetson.
- Recorded Boost scans: 1080 -> 360, valid 88 % -> 90 %, 0.4 ms/scan.
- Live after deploy (parked; atlas-scan-filter restarted, then atlas-lidar.service scan_mode Boost again):
  - /scan 7.2 Hz, 360 bins, 98 % valid (Standard was 57 %);
  - load average ~15-17 (Standard ~12-13; Boost without thinning 50-59);
  - ICP node 15 % CPU, 0 rejected;
  - verify-place "dhruv room" VERIFIED fit 0.99 margin 0.236.
- Backups: scripts/atlas_scan_self_filter.py.before-thinning-20261113; atlas-lidar.service.before-scanmode-20261113 (Standard).

2026-11-13 ~16:20-16:35 remap attempt 7 ABORTED (Boost + thinning live):
- The cold start failed again (no map frame in 90 s); the automatic retry after restarting atlas-slam-fast reached ACTIVE (session d8a4d0ff).
- Load average then rose to 50-57: run queue 67-120, 0 % idle, ~50 % system time, ~70k context switches/s.
- Cause: mission control paused the AI extras at session start, but atlas_feature_on_demand restarted them within one tick. "Autonomy" demand comes from mission_status != READY, and its MAPPING_PAUSED only listed the camera tracker and follow-person. Startups (heavy imports) on top of SLAM + Nav2 + session bag + camera overloaded the Jetson.
- Session aborted without a map (session file moved; accepted map preserved; named places from pre-remap8).
- Fix:
  - MAPPING_PAUSED now also lists vision-lidar-fusion, person-sensor-fusion, ai-annotator and agent-team.
  - Mission control pauses the same units, dependents before ai-annotator.
  - tests/test_feature_on_demand_mapping.py 3/3 pass on the Jetson (not started while mapping; started when not mapping; lists match). Deployed.
  - Backups: *.before-mappause-20261113.
- Side effect noted: restarting atlas-feature-on-demand runs restore-all (ExecStopPost), which starts every managed unit (incl. follow-person, camera-tracker, active-vision) until idle. Those three were stopped manually; the rest stop after boot grace + idle.
- Also: after an aborted/stopped session the mapping stack stays up; atlas-localization must be started explicitly. Done: seeded in Dhruv Room (0.135, -1.835); run queue 18, 24 % idle, system time 12 %.

2026-11-13 remap attempt 8 (session c7c28ee9, 16:37-17:31; Boost + thinning, mapping speed cap, feature-manager pause fix). REJECTED; accepted map preserved.
- The cold start failed again; the retry after restarting atlas-slam-fast reached ACTIVE.
- Load stayed 29-54 throughout (run queue 24-37, 2-4 % idle, 37-39 % system time) with the AI extras off. The mapping stack itself (slam_toolbox + full Nav2 + session bag + EKF at ~29 %) plus the camera, Astra, rf2o, base and Python monitors oversubscribe the 6 cores.
- The remote stop latched ("joystick unavailable") under this load, so the owner's first drive attempt did not move the rover. The owner then reset it and drove.
- Hall saved (0.60, -6.64), 6.6 m from start. Closure PASSED 0.082 m / 0.3 deg.
- Failures: map->odom jump 1.710 m (17:28:40, start of return); yaw jump 16.4 deg; footprint not connected between places; reverse Nav2 plan failed.
- Restored as before (rejected_session_c7c28ee9; named places from pre-remap9; localization seeded (0.175, -1.675)).
- Conclusion: on this Jetson, manual-teaching mapping with the full stack is CPU-bound. Next design step before any further drive: a lighter mapping mode (e.g. Nav2 started only for the acceptance plan checks, no session bag or a lighter one, and the Astra/rf2o paused), measured parked first.

2026-11-13 evening (21:20-22:40), owner away, rover parked in Dhruv Room, E-STOP latched. Read-only measurements and offline replays only; no motion, no service restarts. All code changes are STAGED (repo + ~/atlas_staging_20261113), NOT deployed.
1. CPU profile (tools/profiling/atlas_cpu_profile.py; 30 s, localization mode, idle; data/diagnostics/cpu_profile/localization_idle_20261113.json):
   - Services total 396 % of 600 %, load 13-18, system time 12 %.
   - Largest units: atlas-localization (Nav2 + AMCL) 51 %, camera 30 %, rover-base-telemetry 30 %, voice companion 20 %, Astra 20 %, cmd-vel-mux 17 %, localization-monitor 17 %, dashboard 16 %, sensor-recovery 16 %, rf2o 15 %, mission-control 14 %, safety-status 13 %, ICP odometry 13 %.
   - Topic rates are low (/scan 7.5 Hz, /odom 10 Hz, camera 11 Hz). The small Python nodes' cost is rclpy's executor rebuilding its wait set per message, not their callbacks (sensor recovery already reads raw bytes and still uses 16 %).
2. SLAM's own cost (offline replay of session c7c28ee9, 54 min at 1x, live parameters): slam_toolbox mean 3.9 % / max 31 % of one core, RSS 39 MB. SLAM is NOT the CPU hog; the load during mapping comes from everything around it.
   - The same replay still had map->odom steps: max 0.645 m (live 1.710 m), 29 steps > 0.15 m, max yaw step 8.6 deg.
   - So overload made the jumps ~2.6x worse, but odometry drift that SLAM corrects in steps remains. See 4.
3. LiDAR validation (tools/lidar/lidar_scan_validation.py; data/diagnostics/lidar_validation/), first 600 s of each bag, Standard (00c9e957) vs Boost + thinning (c7c28ee9):
   - Timing: Boost scan period p95 0.154 s vs 0.261 s; gaps > 0.3 s 0 vs 3; time_increment x beams / scan_time = 1.001 (consistent per-point timing); latency median 0.14 s for both.
   - Geometry: /scan 360 beams for both; valid 98.0 % vs 47.2 %.
   - Range resolution: Boost 1-4 mm steps vs 0.25 mm Standard (56 % of beams repeat the previous value). Negligible against 5 cm map cells.
   - Accuracy proxy (scan-to-scan ICP residual RMS on /scan): 3.5 mm median (p90 8.0 mm) Boost vs 15.5 mm (p90 22.8 mm) Standard, with 353 vs 181 points/scan. Boost + thinning gives more consistent geometry. A map-level check still needs an accepted Boost map.
4. EKF tuning offline (tools/localization/ekf_variants.sh; isolated domain 92):
   - Method: ICP node + EKF variants replayed on two drives that ended on the start mark (SLAM closure 3.6 cm / 5.1 cm). Score = start->end closure. Repeatability ±0.02 m.
   - Results (57941c0d / 00c9e957):
     - live 0.45-0.47 / 0.50-0.51 m;
     - wheel + IMU only 0.40 / 0.49;
     - ICP without wheel 0.32 / 0.56;
     - q_vx 0.5: 0.45 / 0.49; q_vx 8: 0.48 / 0.49;
     - + ICP yaw rate 0.49 / 0.48;
     - ICP yaw rate instead of IMU 1.06 / 0.68 (yaw -18 / -11 deg);
     - ICP pose differential, no IMU 1.28 / 1.33;
     - raw wheel 2.26 / 8.11.
   - The ICP node's own integrated pose: 0.31 / 0.09-0.10 m.
   - Decision: NO EKF change (live is the best EKF variant; IM10A heading confirmed; q_vx insensitive).
   - Open lead: raw ICP translation closes 2-4x better than any EKF output. Next offline test: SLAM replay with odom->base_link built from the ICP pose, to see whether the map->odom steps in 2 shrink.
5. Dashboard: no restart since 16:35, watchdog never fired, HTTP 2-140 ms, 114 MB. Staged: listen backlog 5 -> 64 (several tabs/phones polling could get connections refused).
6. Light manual-mapping mode (staged; mission control parameter mapping_profile, default "light"; "full" = previous behaviour):
   - Also pauses Astra obstacles, the rf2o gate, the candidate EKF, tight recovery, rf2o and the experience store. Consumers checked: Nav2 astra_layer / autonomy only; the live EKF uses /lidar/icp_odom. The experience store is added to the feature manager's MAPPING_PAUSED.
   - Starts SLAM only. Nav2 starts when the session is stopped, before the goal cancel, plan checks and footprint evidence (ensure_nav2_for_acceptance, 120 s).
   - Records a lighter bag: ATLAS_RECORD_PROFILE=mapping_light drops camera JPEGs, AMCL topics and /map; /lidar/icp_odom is now recorded too.
   - Expected saving vs the idle profile: ~54 % (paused units) + ~35 % (Nav2 deferred) + the bag's camera stream, on top of the AI extras already paused (~47 %).
7. Mapping safeguard (scripts/atlas_mapping_guard_core.py + mission control + mux; 6 unit tests):
   - Armed only during a drive-ready manual session; trips on any of:
     - /scan age > 1.5 s;
     - /yahboom/odom age > 1.5 s;
     - map->odom TF gap > 4 s;
     - CPU idle < 4 % with load/core > 4 sustained for 20 s.
   - A trip publishes /atlas/mapping_guard/stop. A new latch-only mux input latches the existing remote stop ("REMOTE STOP: mapping guard"); the normal LB 3 s release applies.
   - The trip is recorded in the session (guard_trips), and accept_saved_map rejects that session's map. Suspended while the session is being stopped.
8. Executor batching for monitoring nodes (scripts/atlas_batched_spin.py; opt-in through ATLAS_EXECUTOR_BATCH_S drop-ins):
   - 100 ms: localization monitor, sensor recovery. 50 ms: mission control, safety status, rf2o gate.
   - Not used for the base, mux, remote or any stop path. Revert = delete the drop-in.
9. Regression suite (tools/regression/atlas_regression.py):
   - quick: unit tests minus the known-failure list; old map (map id = places, room->hall connected); gate history (all 11 stored rejected candidates still rejected).
   - --full adds the return-to-start replay (limit 0.60 m).
   - Quick run on staging: ALL PASS.
   - The 11 mux test failures are pre-existing (same set on unmodified HEAD; fixtures lack controller_accepts / flysky_reset_observe), listed in tests/regression_known_failures.txt.
Deploy (needs the owner's OK; rover parked + E-STOP latched): copy the changed scripts + drop-ins; daemon-reload; restart mission-control, cmd-vel-mux, feature-on-demand, sensor-recovery, safety-status, localization-monitor, lidar-odom-gate and rover-status-web. Then profile again (localization idle), then a parked light-mode CPU measurement before any drive.

2026-11-13 22:47 DEPLOYED the evening changes (owner: "ok deeploy"), with the remote stop latched, wheels at 0 and no mapping session.
- Ran ~/atlas_staging_20261113/deploy_20261113_evening.sh: backups *.before-evening-20261113, rollback with --rollback. All 8 restarted units are active.
- Remote stop stayed latched. The guard topic /atlas/mapping_guard/stop has 1 publisher (mission control) and 1 subscriber (mux).
- Batched executor confirmed in the logs: 100 ms for localization monitor and sensor recovery; 50 ms for mission control, safety status and the rf2o gate.
- The feature-manager restart started follow-person, camera-tracker and active-vision again (known restore-all side effect); stopped them.
- CPU, localization idle, 30 s profiles:
  - total 396.9 % -> 379.1 %; idle 29 % -> 32 %;
  - mission control 14.6 -> 7.4 %; sensor recovery 16.4 -> 4.4 %; safety status 13.3 -> 6.9 %; localization monitor 16.8 -> 11.2 %; rf2o gate 4.8 -> 3.9 %.
- Quick regression on live: ALL PASS (unit, old map, gate history). Mission status READY.
- Not yet measured: light mapping mode live (parked).

2026-11-13 23:00-23:45 live-system audit (owner request "audit running ATLAS, find problems and fix"). Rover parked, remote stop latched the whole time (verified before and after).
Healthy:
- No crash loops.
- Sensors: /scan 7.3 Hz, /odom 10, wheel odom 10, IM10A 10, IMU 10.6, ICP 7.3, rf2o 5.3, camera 8.8, radar 20, ultrasonic 7.3, joy 16, BMS every 5 s (14.6 V, 100 %).
- Recovery monitor: all HEALTHY.
- TF map->base_link (0.195, -1.762, 72.8 deg) agrees with the LiDAR-verified seed.
- Disk 35 %; RAM 2.4 GB available; swap 26 MB; temperatures 67-68 C (trip 99 C); fan PWM 138.
FIXED (deployed; backups *.before-shutdownfix-20261113 / *.before-grace-20261113):
1. Services ended "failed" on every normal systemctl stop (2 days: voice 11, visual-cloud 11, camera-joystick 11, person-fusion 8, localization-monitor 8, rf2o gate 8, follow-person 2).
   - Causes: ExternalShutdownException not caught; the voice overlay raises its own exception class; rclpy.shutdown() called twice; follow-person publishing a final zero on an invalid context.
   - A race I introduced at 22:47: a stop during the batch sleep made the wait-set rebuild raise RCLError. atlas_batched_spin and atlas_dashboard_executor now turn it into the normal shutdown signal; new unit test, 4/4 pass.
   - Verified with two stop/start cycles each: localization-monitor, rf2o gate, safety-status, sensor-recovery, mission-control, dashboard, camera-joystick, visual-cloud and follow-person all stop with Result=success.
   - Voice companion fixed in the file but not restarted (night); the fix applies on its next start.
2. Dashboard watchdog killed the dashboard during deliberate restarts (22:48:45, 23:37:05, 23:37:45): no startup grace, so SIGUSR1 arrived before faulthandler was registered.
   - Added a 60 s grace after the unit starts (a first version overflowed in awk and effectively disabled the watchdog; replaced with integer seconds).
   - Tested: healthy -> no action; simulated hang -> USR1 + restart on the 2nd miss.
3. reset-failed for update-notifier-crash (crash-report notifier). Crash reports in /var/crash: rplidar_composition 13 Nov 14:25 (during the Boost overload, not recurred), ros2 CLI, nmcli, rtabmap (old).
NEEDS THE OWNER (sudo or hardware):
A. Power mode is "25W" (nvpmodel ID 1): CPU capped at 1.344 GHz, lower than 15W mode (1.498 GHz). MAXN_SUPER (ID 2) runs at 1.728 GHz, +29 % CPU, with the CPU-bound mapping problem in mind. No earlier decision about the power mode is recorded. Suggested: sudo nvpmodel -m 2, watch the temperature (now 68 C at 1.344 GHz).
B. atlas-ptz-home.service (system unit, /home/jetson/home.py) fails every boot: PCA9685 at 0x40 is no longer on Jetson I2C bus 7 (the pan/tilt now goes through the UNO R4 hub, PCA=1). Obsolete. Suggested: sudo systemctl disable atlas-ptz-home && sudo systemctl reset-failed atlas-ptz-home.
C. GPS: the hub reports GPS_BYTES=0 since boot (UART at 9600 baud receives nothing). Wiring/power/module check; indoors alone would still give NMEA bytes.
D. AMCL particle collapse persists (covariance ~1e-15, perfect confidence). Already registered (issues 33/36: 1 Hz forced no-motion updates + resample_interval 1 + zero recovery alphas). No new tuning without the reviewed change. LiDAR start verification and the scan-fit gate remain the real checks.
Watch: cellular modem USB re-enumerated 6x between 14:34 and 14:47 (overload window), none since. rover-base-telemetry "USB discovery busy" at startup 3x in 2 days (auto-retried).

2026-11-13 23:53 power mode changed by the owner: sudo nvpmodel -m 2 (MAXN_SUPER), no reboot needed. Was ID 1 "25W" (CPU cap 1.344 GHz).
- Now: all 6 cores max 1.728 GHz; temperatures unchanged at cpu 68 C / tj 67-68 C (trip 99 C); fan PWM 132; remote stop latched; no failed units; dashboard 200.
- Localization idle (30 s profiles):
  - process total 396.9 % (before the evening deploy) -> 379.1 % (batching) -> 359.0 % (MAXN_SUPER);
  - idle 29 % -> 32 % -> 35 %;
  - load average 14-18 -> ~10.
- /var/lib/nvpmodel/status records the mode for boot (/etc/nvpmodel.conf DEFAULT is still 1; the status file takes precedence).
- Watch the temperature during the next mapping drive.

2026-11-13 23:59 - 2026-11-14 00:30 PARKED light-mapping-mode test (owner request), session d29d7b23. Remote stop latched throughout; nothing moved; MAXN_SUPER.
Worked:
- Cold start reached MANUAL MAPPING ACTIVE in 22 s on the first try. Before, cold starts often missed the 90 s check; Nav2 is no longer started.
- Startup stillness 0.0 m / 0.0 deg. Paused: voice, Astra, rf2o gate, candidate EKF, tight recovery, rf2o. Nav2 inactive.
- Light bag (no camera) recorded.
- Mapping guard armed ~20 min with 0 trips (no false positives, including the high-load period).
- Stop: QUEUED -> "MANUAL MAPPING FINISHING: starting Nav2" -> acceptance evaluated 40 s later -> REJECTED as expected (no hall / no drive). Accepted map unchanged (pgm sha 4beb26d5a999).
- Restore: session files moved to rejected_session_d29d7b23 / *.rejected-session-d29d7b23.json; atlas-localization started; seeded LiDAR-verified "dhruv room" (0.215, -1.795); Nav2 active; mission control restarted -> READY (known: status stays ERROR after a rejection). Regression ALL PASS (12 rejected candidates still rejected).
FIXED during the test:
- The feature manager restarted ai-annotator, agent-team and experience-store in the ~20 s while SLAM was "activating" (mapping was detected only as slam-fast == active). They then stayed on for the whole session; this probably also contributed to earlier remap overloads.
  - Now mapping = a session file in "starting"/"active" OR slam-fast active/activating (once per tick).
  - Running MAPPING_PAUSED units are stopped while mapping.
  - 3 new tests (6/6). Deployed mid-session: 7 units stopped within 12 s.
  - Backup atlas_feature_on_demand.py.before-mapenforce-20261114.
- Still open: atlas-active-vision is not in MAPPING_PAUSED (it was only started by restore-all).
CPU in light mapping (60 s, parked): 386 % total, but 27 % system time + 8 % irq. Biggest: mission-control cgroup 72 % (incl. session ros2 bag record 45 %), EKF 48 % (2.7 % in localization; main thread 37 % sys, "Failed to meet update rate, took 0.11-0.23 s"), slam_toolbox 44 % (4 % offline), dashboard 39 %, mode manager 17 %.
LEAD (strong, not yet reproduced): stopping ONLY the session's recorder dropped EKF 46 -> 3.4 %, SLAM 44 -> 2.2 %, dashboard 40 -> 25 %, mode manager 17 -> 6.6 % within 15 s.
- Fresh recorders started from a shell did NOT reproduce it: /tf alone (reliable or best-effort), scans + odom, and the exact light-profile script for 4.5 min all left EKF/SLAM at 2-4 %; the recorder itself uses ~35 %.
- Difference to test next: the session recorder starts while localization is being stopped and SLAM started (publishers churn during its discovery).
- Next discriminating test, parked: start a session and compare EKF/SLAM sys time with the recorder started (a) at session start (now) vs (b) after MANUAL MAPPING ACTIVE.

2026-11-14 00:26-01:00 recorder-timing test (owner: "Yes, test it"), parked, stop latched throughout; session cadee163, restored after (localization seeded (0.175, -1.855), READY, map unchanged).
- Localization baseline: EKF 2.9 %.
- A, session recorder: EKF 21-23 % (sys 14-16 %), SLAM 28-30 % (sys 21-22 %). Mapping-mode overhead reproduced (smaller than last night's 45 %).
- B0, session recorder killed: EKF 18 %, SLAM 29 %. Unchanged.
- B1/B2, same recorder script started after ACTIVE: unchanged.
- => The recorder is NOT the cause. Last night's drop after killing it is now treated as coincidental or as an indirect reset. The 2026-11-14 00:30 "recorder lead" above is WITHDRAWN.
- C, SLAM SIGSTOP 20 s then SIGCONT: costs fell (EKF 3 %, SLAM 2 %). INVALID as a fix: after the resume, mission control never received SLAM's map->odom again (guard: "SLAM map->odom stale 180.4s"; stop failed with "localization seed requires a live map-frame pose"); restored manually. Do not use SIGSTOP on DDS nodes.
- Reproduced WITHOUT mapping: in localization, adding one dummy /tf publisher (unrelated frames, rclpy, UDPv4 or default transports, 10 or 50 Hz) raised EKF sys 1 % -> 23-30 % and every /tf subscriber by ~4-6 % sys. The cost does not depend on the rate.
- The state PERSISTS after the extra publisher exits and survives an EKF restart (a fresh EKF picks it up at once). /tf traffic itself is normal (odom->base_link 6.9/s, map->odom 6.0/s).
- /tf has a publisher "_NODE_NAME_UNKNOWN_" (GID 01.0f.9f.1f.07.d8.3a.02...) with no matching live PID, a stale or unidentified participant.
- Working hypothesis: churn of /tf participants (SLAM appearing at mapping start, killed or paused processes) leaves the Fast DDS (Humble default RMW) graph in a state where every /tf reader and writer burns kernel time. This would explain the mapping-mode overload behind the rejected remaps.
- Not confirmed at syscall level: no strace or perf on the Jetson (installing them needs sudo).
- Side effect: my probes left the system in that state: 481 % CPU, 10 % idle, 29 % system time, load 48, atlas-localization 122 %. Rover parked, stop latched, READY. A reboot is recommended to clear it.
- Next: (1) reboot; (2) the owner installs strace and linux-tools; (3) parked, start mapping and catch the syscall mix in EKF and SLAM; (4) candidate fixes for a reviewed change: SLAM transform_publish_period, discovery / lease settings, or the participant churn at mapping start. No change made yet.
- Also: use `ros2 topic pub --once -w 1` (the first stop without -w was lost).

2026-11-14 01:05 Jetson rebooted (owner ran sudo reboot) to clear the sticky /tf state left by the probes.
- After boot: pmode 0002 (MAXN_SUPER, 1.728 GHz) kept; all core units active; remote stop latched; mission READY. Only atlas-ptz-home failed (obsolete unit, audit item B).
- Localization: AMCL (0.211, -1.850); LiDAR verify-place "dhruv room" unique match (0.175, -1.855, 69 deg), margin 0.22. No reseed needed.
- CPU (30 s): 354.5 % total, idle 36 %, system 13 %; atlas-localization 54 %; EKF ~2 % (was 37 % in the stuck state, 481 % total).
- Confirms that the expensive state is cleared by a full restart of the DDS graph.

2026-11-14 ~01:20 diagnostic tools installed by the owner: sudo apt-get install strace linux-tools-generic.
- strace 5.16.
- perf 5.15.223 at /usr/lib/linux-tools/5.15.0-203-generic/perf. There is no linux-tools package for the 5.15.148-tegra kernel; the generic 5.15 binary works. Call it by full path (the /usr/bin/perf wrapper rejects the tegra kernel name). No kernel was installed.
- Both work on processes they start themselves.
- Attaching to running ATLAS services is blocked by the stock security settings ptrace_scope=1 and perf_event_paranoid=2, which were NOT changed. For the parked syscall capture, either the owner runs the capture with sudo, or the owner temporarily relaxes them until the next reboot (sudo sysctl kernel.yama.ptrace_scope=0 kernel.perf_event_paranoid=1). This is the owner's decision.

2026-11-14 ~08:20, owner via sudo:
- kernel.yama.ptrace_scope=0 and kernel.perf_event_paranoid=1 until the next reboot (not persistent). strace and perf now attach to running ATLAS services (checked on the EKF).
- atlas-ptz-home.service disabled + reset-failed (audit item B closed). No failed system units remain.

2026-11-14 08:20 parked capture attempt (owner: "capture now"); stop latched throughout. Uptime 7 h since the 01:05 reboot, few restarts since.
- Localization baseline: EKF 1 % user / 1 % sys.
- The manual-mapping start FAILED at set_home: "SLAM pose is not settled (shift=0.20m)". The new SLAM pose moved 20 cm while starting.
  - Mission control cleaned up correctly (no session file, places unchanged, extras restored) but left atlas-slam-fast running without localization (known "stack stays up").
  - Restored: SLAM stopped; localization started; seeded LiDAR-verified (0.195, -1.675); mission control restarted -> READY.
- NO overload with SLAM running ~3 min (no session or recorder): EKF 1/1 %, SLAM 1/0 %, total 326 %, idle 42 %.
- Every overloaded session on 13-14 Nov started after many service restarts (deploys, tests). This fits the sticky-state hypothesis (participant churn builds it up; a reboot clears it). Practical mitigation to test: reboot before a mapping drive.
- The capture needs the bad state. It can be triggered deliberately (the dummy /tf publisher reproduced it at 00:5x) but then needs a reboot to clear.
- Also: my wait loop matched "MANUAL MAPPING ACTIVE" inside the PREPARING text again; scripts must match '^data: .?MANUAL MAPPING ACTIVE'.
- Open: set_home's settle check vs a cold SLAM start (0.20 m shift); a retry after a few seconds may pass.

2026-11-14 08:44-08:48 deliberate trigger + capture (owner: "trigger it"); localization mode, stop latched.
- The dummy /tf publisher (UDPv4, 10 Hz, 40 s) did NOT trigger the state this time: EKF 1 % user / 1 % sys before, after and 10 s later.
- The trigger only worked after the 13 Nov's many restarts/kills, so the cause ACCUMULATES with participant churn and a reboot clears it. No reboot needed now.
- Healthy EKF strace (15 s; data/diagnostics/dds_capture_20261114/strace_ekf_healthy.txt): recvfrom 48 % / futex 46 % of syscall time; 5670 sendto, each preceded by a FAILING setsockopt.
  - Detail: setsockopt(SOL_SOCKET, SO_SNDTIMEO_OLD, timeval with tv_usec out of range) = -1 EDOM on every send, so Fast DDS's UDP send timeout is NEVER applied and a send can block without limit.
  - Defect in the Humble Fast DDS / aarch64 stack (not ATLAS code). It may explain the 0.11-0.23 s EKF "Failed to meet update rate" stalls seen while stuck. Not proven.
- /dev/shm: 36 Fast DDS segments, 34 mapped by live processes, 3 stale from boot. Not the accumulating factor.
- Kernel counters since the 01:05 reboot: 318,187 ICMP destination-unreachable sent and received (UDP sends to ports nobody listens on). The healthy rate now is 0/s, so these came in bursts, most likely around restarts, the failed session start and the probes.
- Hypothesis (unproven): after churn, writers keep sending to UDP locators of dead participants (e.g. the "_NODE_NAME_UNKNOWN_" /tf publisher seen at 00:5x), and every send costs kernel + ICMP work in all /tf processes.
- tools/profiling/atlas_cpu_profile.py now prints "dds/udp per s" (udp_noports, icmp_out_unreach; healthy 0). The next time overload appears, one profile confirms or rejects this.
- Practical plan for remap 9:
  - reboot shortly before the drive;
  - profile once at MANUAL MAPPING ACTIVE (CPU + dds/udp);
  - avoid killing ROS processes;
  - if overload appears anyway, capture strace/perf at once (attach allowed until the next reboot only).

2026-11-14 08:52-09:01 parked start check (owner: "do it"), session eece59aa; stop latched; uptime 7.8 h after the 01:05 reboot.
- Start: ACTIVE on the FIRST attempt in 15 s (QUEUED 08:52:17 -> ACTIVE 08:52:37). The 08:20 "SLAM pose is not settled (0.20 m)" refusal did not recur. set_home's settle check (5 samples / 1.6 s / 5 cm) remains as is. A retry is the documented response if it happens again.
- Light mapping CPU (30 s at ACTIVE and +2 min): total 302 % / 292 %, idle 45-47 %, system 10 %; EKF 3 %, SLAM 2 %, session recorder 33 %, mission-control cgroup 41 %; dds/udp noports 0, icmp unreachable 0.
  - AI extras, Astra and Nav2 all inactive. Guard armed, 0 trips, startup wheel displacement 0.0 m.
  - FIRST clean measurement of the light profile. The overload did not appear on this clean system.
- Stop: Nav2 started at the end -> rejected after 57 s (expected: parked, no hall). Accepted map unchanged (4beb26d5a999). Restored: seeded (0.215, -1.795); READY.
- NEW GATE ISSUE (would also reject a real remap): "map->odom source timestamps predate the mapping session".
  - first normalized SLAM map->odom source stamp = started_unix + 17.41 s = ready_unix - 1.51 s.
  - Since 2026-11-13 mission control passes session_started_unix = ready_unix for manual teaching (to keep startup jumps out of the evidence). The core then also checks source_started >= ready_unix - 1.0.
  - SLAM's first transform carries the stamp of the last scan it processed. Parked, that predates ready by 0.25-0.9 s in earlier sessions (pass) and by 1.51 s here (fail). The lighter SLAM settings make the margin smaller.
  - PROPOSED (needs the owner's OK): keep the observation/jump window referenced to ready_unix, but check "source predates the session" against started_unix (the real session start, when SLAM was not yet running). Jump and closure gates unchanged.

2026-11-14 ~09:15 FIX DEPLOYED (owner: "Yes, fix it"): map-acceptance source-stamp floor. Stop latched, no session open.
- atlas_map_acceptance_core.evaluate_acceptance_evidence gains source_floor_unix (default = session_started_unix, so other callers keep their behaviour). The "map->odom source timestamps predate the mapping session" check uses it.
- Mission control passes source_floor_unix = session["started_unix"]. Coverage, observation start and the jump window keep the drive-ready reference.
- Not weakened: TF jump (0.15 m / 5 deg), closure (0.15 m / 10 deg), connectivity, plans, startup stillness, observation-start coverage. A source stamp from before the session started still fails (new test).
- Tests:
  - tests/test_atlas_map_acceptance_core.py +3 (between start and ready passes; before start fails; default unchanged).
  - The transform-timeout test now falls back to ~/.config/systemd/user on the Jetson's installed layout.
  - Staging 33 passed / 3 skipped (incl. scripts/test_map_acceptance_startup.py); live regression ALL PASS (40 unit, old map, 13 rejected candidates still rejected).
- Re-evaluation of stored sessions with the new floor:
  - eece59aa loses only the predate failure (7 -> 6; still rejected);
  - d29d7b23, c7c28ee9 and 57941c0d unchanged (6 / 5 / 2; still rejected).
- Backups: *.before-sourcefloor-20261114. Mission control restarted -> READY, stop latched, no errors.

2026-11-14 ~10:00-10:25 small code jobs (owner: "do the small code jobs first"); rover parked, stop latched.
DEPLOYED (backups *.before-smalljobs-20261114; mission control + feature manager restarted; follow/camera-tracker/active-vision stopped after the restore-all; READY, latched):
1. atlas_feature_on_demand MAPPING_PAUSED += atlas-active-vision (it moves the camera; not needed while mapping). +1 test.
2. Mission status returns to READY when idle. A FINISHED or FAILED status (allow-list: ERROR, PLACE/HOME SAVED, GOAL FINISHED/REJECTED, RETURN HOME FINISHED/VERIFIED/INACCURATE/REJECTED/RETRY BLOCKED, NAVIGATION CANCELED, MAPPING NOT ACTIVE, MAP ACCEPTED, SCAN CHECK OK, BUSY) stays visible for 120 s (errors) or 60 s (others), then reverts to READY.
   - Only if no operation holds the lock, no mapping session is open and exploration is inactive.
   - In-progress or unknown statuses (QUEUED, *DISPATCHED, *ACCEPTED, MANUAL MAPPING *, EXPLORATION ACTIVE, RETURN HOME RETRY, TAUGHT ROUTE DISPATCHED) never revert. Navigation is asynchronous, so the lock alone is not enough.
   - Why: the feature manager reads mission != READY as autonomy demand and restarted every AI extra after rejected maps; the camera settings page refused changes; both needed a mission-control restart.
   - tests/test_mission_status_idle_revert.py: 6 tests.
   - Live test: "MAPPING NOT ACTIVE" 10:23:34 -> READY 10:24:34.
TESTS FIXED (test files only):
3. 11 remote-stop mux tests (stop_hold, mapping_limit): the fixtures now extract flysky_reset_observe / controller_accepts (Stage 29 additions) and set manual_controller=XBOX. 11/11 pass. tests/regression_known_failures.txt emptied.
4. Dashboard E-STOP tests: the "missing module calibration_validation" collection error was an incomplete test tree (tools/vision3d and tools/diagnostics absent on the Jetson's live and staging trees), not a missing module. With the full tree:
   - estop_safety needed the same Stage 29 fixture addition;
   - executor_split expected rclpy.spin(self.node), which the 13 Nov batched dashboard executor replaced (my change);
   - now 41 passed, 1 skipped (estop_reset, estop_safety, no_reboot, executor_profile, executor_split).
NOT DONE (not small, or not allowed):
- Automatic localization restore after a session. After a rejection the session stays active by design; automating needs decisions (archive the session, set aside session-bound home/seed, reseed without a known place). Proposed separately.
- Rear encoder label swap: this is the motor/encoder driver mapping (hardware driver / calibration), outside this workflow without an explicit, separate owner decision.

2026-11-14 ~10:40 survey of existing colour recordings for 3D map v2 (read-only; /tmp/colour_survey.py). maps3d/ holds 8 colour recordings. Each has an Astra bag (/astra/color 640x480 rgb8 ~27 Hz, /astra/depth 160x120, camera_info, depth_to_color extrinsic) and a base bag (/scan /odom /yahboom/odom /tf /tf_static IM10A /amcl_pose /map).
- Full room->hall->room drives (wheel/EKF path, end-start gap):
  - remap6_colour_20261113-134122: 629 s, 27.1 m, 0.61 m (session 57941c0d drive). BEST.
  - remap5b_colour_20261113-102354: 1037 s, 26.5 m, 0.93 m.
  - remap3_colour_20261112-194252: 756 s, 19.7 m, 1.37 m.
  - remap4 + remap4b (outbound 7.1 m + return 17.1 m).
  - remap7: 9.5 m, one way.
- Still-rover only (no use for 3D): remap2_colour_20261112-184531 (14 GB, 0.8 m) and remap5_colour_20261113-102057 (1.3 GB, 0.0 m). Deletion candidates, 15.3 GB, owner's decision.
- Sampled frames: colour exposure normal (mean 76-134); depth 36-70 % valid, median ~1.8-2.1 m.
- Conclusion: a 3D v2 can very likely be built WITHOUT a new colour drive: localize each recording's /scan against the accepted 2D map (scan-to-map, as build_colour_map.py already refines), then project colour+depth.
  - Not proven yet: needs an accepted map, or a dry run against the current accepted map (d12a1f).
  - Risk: furniture or layout changes since 13 Nov.

2026-11-14 ~11:00 3D v2 DRY RUN from an old recording, no drive (owner: "Yes, dry run"). Offline at nice 15; nothing restarted.
- tools/m3/build_colour_map.py gains ALIGN_INIT="x,y,yaw_deg" (used with REFINE_MAP). It places a recording made in another map frame (a rejected session's SLAM) onto REFINE_MAP: the first scan is matched at the start-mark guess (±20 deg search), and every later successful scan-to-map refinement re-anchors the frame offset.
- FIXED a refinement bug: icp() returns yaw in (-pi, pi] while the trajectory yaw is unwrapped, so after a full turn every good match failed the 8 deg check (180 of 202 failures). This affected the first colour map (12 Nov) too.
- Failure reasons are now counted.
- Run: remap6_colour_20261113-134122 onto the current accepted map atlas_latest (d12a1f), ALIGN_INIT=0.2,-1.8,70:
  - start match (0.170, -1.956, 78.9 deg), 85 % inliers;
  - 340/341 keyframes refined (27 without a scan within 80 ms use the anchored prediction);
  - inliers median 0.955, p10 0.902; correction mean 2.8 cm, max 23 cm;
  - path covers room -> hall (x 6.45 m; hall place at 6.28) -> back, ending 5 cm from the start;
  - 344,576 points (2 cm), 53,664 occupied 5 cm cells.
  - Output maps3d/colour_v2_dryrun_remap6_20261114.{ply,json}; render docs/colour_3d_20261114/colour_v2_dryrun_render.png.
- Conclusion: once remap 9 is accepted, 3D v2 can be built from the existing recordings (remap6, optionally + remap5b / remap3) without a colour drive.
- Visual limits: depth is 160x120; colour/depth centres are assumed equal (v1 limitation); some doubled walls near the hall (x 6-7.5 m). Not yet investigated.

2026-11-14 ~10:40-11:10 3D v2 doubled walls investigated (owner: "look into the doubled walls"). Offline only, recording remap6 on the accepted map.
- New tool tools/m3/wall_check.py: distance from 3D points (z 0.15-1.2 m, or the LiDAR band 0.15-0.35 m) to the nearest occupied cell of the 2D map; reports median, p75, p90, % within 5 cm and % at 10-30 cm (the doubled-wall signature).
- Baseline (dry run): median 6.7 cm, 41 % within 5 cm.
- Outbound vs return passes (KEEP_FROM/KEEP_TO; the pose chain runs through all frames):
  - outbound 3.8 cm / 57 %; return 9.6 cm / 29 %.
  - Both lock onto the 2D map equally (inliers 0.955), so the error is in placing the depth points and depends on direction: the doubled walls.
  - The room area is worse in both passes partly because of furniture above the LiDAR plane; that is not doubling.
- Sweep (median / within 5 cm):
  - DEPTH_DT -0.2: 6.0 / 44; -0.1: 6.4 / 44; 0: 6.7 / 41; +0.1: 7.4 / 38; +0.2: 7.5 / 37.
  - MOUNT_YAW_DEG -4: 9.6 / 33; -2: 8.3 / 37; +2: 6.5 / 42; +4: 7.0 / 39.
  - Combined DEPTH_DT=-0.2 + MOUNT_YAW_DEG=+2: all 5.5 / 48; outbound 3.5 / 65; return 7.6 / 35.
  - Hall at the LiDAR band: outbound 3.5 cm vs return 5.7 cm. A residual error remains in some return frames (after the hall turnaround).
- FIX: frame gate DEPTH_GATE_CM. A frame is skipped when its depth points in the LiDAR band (0.15-0.35 m) are a median of more than N cm from the 2D map walls.
  - Gate 6 cm: 146/375 frames gated; all 3.8 cm / 57 %; hall 2.9 cm / 74 %, 10-30 cm 7 % (return was 26 %).
  - Gate 4 cm: 238/375 gated; all 2.9 / 69; hall 2.9 / 79; sparser.
  - Render docs/colour_3d_20261114/colour_v2_gate6_render.png: the hall wall is single.
- Recommended for 3D v2: DEPTH_DT=-0.2 MOUNT_YAW_DEG=2 DEPTH_GATE_CM=6, merging remap6 + remap5b + remap3 to refill the gated coverage.
- The build-tool values (-0.2 s, +2 deg) are offline estimates for the 3D tool only; config/astra_obstacles.yaml (live Astra mount) is NOT changed. A +2 deg mount yaw is a calibration question for the owner.

2026-11-14 ~11:20-12:00 dashboard warnings, M3 encoder, IM10A, Astra mount (owner request). Rover parked, stop latched.
DASHBOARD "13 OK / 4 WARN / 1 FAULT" -> now "15 OK / 1 OFF / 1 WARN / 1 FAULT" (verified in the browser).
- Edits in web/v2/command.js and the identical V1 source in scripts/atlas_status_web.py (tools/ui_v2/build_command_js.py builds command.js from it); glass.css adds .healthitem.off. Backups *.before-tiles-20261114; rover-status-web restarted.
- IMU / COMPASS was WARN "navigation fusion not validated" (hard-coded whenever live). Now OK when the IM10A's own dashboard_json says qualified_for_navigation=true and navigation_fusion "ENABLED: corrected gyro Z only" (live: LIVE_FUSED_GYRO_Z). Text: "gyro Z fused in EKF (heading) • compass diagnostics-only".
- DRIVE PID was WARN for DISABLED/controller_disabled; config/drive_pid.yaml ships enabled:false by design. Now OFF (grey, counted separately, never colours the summary). FAULT_STOP is still a FAULT.
- ULTRASONIC was WARN because it required all four sides. The UNO hub reports USTAT,F=ONLINE,L=DISABLED,R=DISABLED,B=ONLINE (left/right not installed) and the topic alternates HEARTBEAT/USTAT. Now only hub-enabled sides count (last USTAT remembered): OK "front 633 mm • rear 749 mm • left/right not installed".
- Still WARN (real): DRIVE FEEDBACK. Autonomy is not qualified (encoder_selection.yaml navigation_validated:false because of M3).
- Still FAULT (real): GNSS, no NMEA (GPS hardware).
M3 ENCODER: cannot be corrected in software.
- Replay of sessions 57941c0d and c7c28ee9, 1 s windows while moving:
  - net M3 count -659 / -1452 vs about ±50k for M1/M2/M4; |sum| about 28k vs about 85k;
  - per-window M3/others 0.08-0.97 (median 0.19); corr(|M3|,|M4|) 0.38-0.44 vs corr(|M1|,|M4|) 0.92-0.99; sign agrees with M4 in 1 % of windows.
  - M3 counts back and forth (direction lost): the signature of a quadrature channel (A or B wire, connector or encoder disk) failing while the motor works. No scale or CPR value can fix it.
- Offline replay through the live EncoderDeltaEstimator (dynamic 3-of-4 consensus, median):
  - all 4: path 22.12 / 21.84 m, consensus failed in 2.1 % / 3.7 % of moving intervals, M3 accepted 39 % / 35 %;
  - M3 statically excluded: 22.26 / 21.93 m (+0.6 / +0.4 %), failures 3.7 % / 6.0 %.
  - DECISION: keep the dynamic consensus (M3 rarely biases distance; excluding it nearly doubles fail-closed intervals). encoder_selection.yaml unchanged.
  - Hardware follow-up: check the M3 encoder channel A/B wire and connector.
IM10A: fully integrated for a 2D indoor rover.
- Bias-corrected gyro Z is the EKF's yaw-rate input (imu0 /im10a/imu/bias_corrected_candidate in base_link, navigation_qualified per config/im10a_gyro_bias.json).
- Magnetic heading deliberately excluded (indoor magnetic distortion from motors and steel); accelerometer not needed in 2D.
- Offline 2026-11-13: IM10A heading beat ICP heading (ICP yaw instead of IMU 0.68-1.06 m closure vs live 0.45-0.51 m).
- The "candidate" topic name is legacy; renaming it would change the EKF interface for no functional gain, so it is kept.
ASTRA MOUNT: the recorded owner tape values stay authoritative (config/astra_obstacles.yaml: x 0.21, y 0.0, z 0.23, pitch 0.0 re-levelled, yaw 0.0). The +2 deg from the offline 3D fit stays a 3D-build parameter only; not applied to the live mount.

2026-11-14 11:25-14:15 REMAP 9 and REMAP 10 (owner at the rover, driving with the remote; stop latched at every start and end).
ROOT CAUSE FOUND AND FIXED - DDS packet storm. After a fresh reboot, parked manual mapping showed udp_in 107,726/s (healthy 3-7k), RcvbufErrors 1,627/s, EKF 44 % (35 % sys), SLAM 38 % (28 % sys).
- Per-socket /proc/net/udp drops: recorder 6,917/5 s, dashboard 3,550, localization monitor 573, SLAM 534 (rx queue 149,760 B against the 212,992 B default limit), EKF 169.
- Reliable DDS repairs every dropped fragment and the repairs are dropped again -> storm. This is the mapping-mode "sticky overload" of 13-14 Nov.
- FIX (owner sudo; persistent /etc/sysctl.d/60-atlas-dds-buffers.conf): net.core.rmem_default=4194304, rmem_max=8388608, wmem_max=8388608, net.ipv4.ipfrag_high_thresh=33554432, ipfrag_time=3; reboot.
- After the fix, light mapping parked: udp_in 3,159/s, drops 0, EKF 3 %, SLAM 2 %, idle 46 %.
- During both drives: idle 37-47 %, no guard trips. Short drop bursts (150-1,550/s for ~15 s) about every 90 s, attributed to the dashboard's socket (3,698 drops in one 45 s window). Not yet fixed; cosmetic for mapping.
REMAP 9 (session 2f57dfa7). REJECTED.
- Passed: connectivity, footprint, Nav2 plans both ways (8.34 m).
- Failed: map->odom jump 1.344 m / 12.8 deg at 12:26:28 (start of return from the hall); closure 0.197 m; source predates session. The last one was caused by my start script retrying while the first start was still preparing (two sessions 8dec1c9a -> 2f57dfa7; the second overwrote the paused-services list with []; services restored by hand).
REMAP 10 (session de55c1d3; owner stop-and-go: short moves, wait for LiDAR GO; slow stepwise hall turnaround). REJECTED.
- Passed: connectivity, plans both ways, source timestamps (source_floor fix verified live).
- Failed: jump 1.460 m / 14.2 deg at 13:50:40 (hall turnaround); closure 0.230 m / 4.4 deg.
- A live map->odom watcher showed SLAM FLIP-FLOPPING at the hall turnaround: 0.36, 0.63, 1.30, 1.46, 1.31, 0.44 m within 13 s (13:50:26-13:50:39); more 0.5-1.1 m steps while leaving the hall; smaller ones (0.1-0.45 m) on re-entering Dhruv Room.
- Three attempts now jump at the same place (1.71 m 13 Nov, 1.34 m, 1.46 m) with the CPU healthy => the hall is AMBIGUOUS to SLAM (scan matching or loop closure alternating between two hypotheses). NEXT: offline replay of manual_mapping_de55c1d35092-20261114-134350 around 13:50:20-13:50:45: compare the scan matcher's candidate poses, loop-closure events and the hall geometry (glass, mirror, open space).
- By eye the new map is cleaner than the accepted one: straighter walls, hall fully covered, free area 26.6 vs 23.9 m² (docs/colour_3d_20261114/map_compare_remap10.png). The candidate stays rejected: the jump rule is not changed without a reviewed analysis of the final-map accuracy.
OTHER FIXES / TOOLS TODAY:
- tools/drive/stop_and_go_coach.py (read-only), per second MOVING/WAIT/GO.
  - Localization: GO = stopped >= 1.5 s, pose steady, scan-fit >= 85 % (the mission-control gate), plus the dashboard strict check (VERIFIED / LOCAL only).
  - Mapping: SLAM adds scans only after ~0.2 m, so GO = settled + fit >= 60 % on the growing map.
- Dashboard /api/map hides a nav plan older than 30 s. The map-acceptance plan-only check in a candidate frame had been drawn over the live map ("blue line wrong orientation"). Owner: "path line is correct" now.
- Live LiDAR checks in localization: corridor fit 90-95 % (local OK) but strict unique-place 90-92 % < 0.93, because the accepted map is stale there (moved furniture; an object ~1 m in front of the room spot; an opening behind-right). Dhruv Room start spot VERIFIED (fit 0.983). The 0.93 bar is NOT lowered: a true pose on the stale map now scores like the best wrong place of Oct (0.897).
- Corrected a claim made in passing: a "+2 deg LiDAR mount" fit gain is indistinguishable from a 2 deg heading error (the global search already optimizes yaw). No mount change.
OPEN BUGS (to fix):
(1) The light mapping profile does not start atlas-map-footprint-filter, so there is no /map for the dashboard (started by hand in both remaps).
(2) Mission control accepts start_manual_mapping while a session is preparing or active; it should refuse.
(3) The mapping page draws the SLAM pose as a faded "ATLAS ESTIMATE" and shows old-map place labels while mapping.
(4) Periodic dashboard socket drop bursts.
(5) `ros2 topic pub --once -w 1` lost the stop request once (re-sent; it was received).

2026-11-14 14:15-15:30 HALL TURNAROUND ANALYSIS (offline; recording manual_mapping_de55c1d35092-20261114-134350; isolated domain 95; rover parked).
- Odometry is NOT the cause.
  - During the multi-point turn (13:50:26-13:50:42) IMU, ICP and EKF yaw rates agree (-0.12 to -0.37 rad/s).
  - map->odom alternated between about (1.46,-0.25,-17) and (0.18,-0.01,-4) (1.3 m / 13 deg apart), ending at (0.72,-0.17,-9).
  - SIDE FINDING: wheel-odometry yaw rate has the WRONG SIGN during this 4WS multi-point turn (+0.3..+0.5 vs IMU -0.2). Not fused (EKF uses IMU yaw rate). To fix later.
- Scan at 13:50:36 against the candidate map: solution B fit 96 %, A 79 %, where SLAM settled 88 % (docs/colour_3d_20261114/hall_overlay_remap10.png). The hall view is dominated by one long straight wall with large openings, so matching is under-constrained along the wall.
- Offline replays (live parameters reproduce it: max step 0.68 m at 13:48:17/13:48:33 entering the hall and 13:50:27-40 at the turnaround). First 9 min unless noted:
  - loop closure OFF (full bag): 0.68 m, 19 steps > 0.15 in the hall window (live: 20). Loop closure is NOT the cause.
  - distance/angle variance penalty x2: 0.72 m, 21 steps. No help.
  - more frequent scans (0.1 m / 5 deg / 0.2 s): 0.66 m, 30 steps. No help.
  - correlation_search_space_dimension 0.25 and 0.35: slam_toolbox CRASHES ("Mapper FATAL ERROR - unable to get pointer in probability search"). Not usable without further parameter work.
- Conclusion: the jumps come from local scan matching in the hall geometry, not from CPU, odometry, loop closure or scan rate.
- Next options:
  (a) Physical: place 1-2 distinctive static objects in the hall (e.g. a box or chair near the long wall, off the path) to break the sliding ambiguity, then remap.
  (b) Driving: avoid the multi-point turnaround inside the hall (turn where geometry is rich, or reverse out along the same path).
  (c) Build the map offline from the recording with heavier processing, plus a reviewed acceptance route.
  (d) Reviewed change of the jump gate to judge final-map accuracy.
- Tooling: replay_slam.sh gains RATE and T_END (filtered copy until a time). Lesson: never edit a running bash script, and kill leftover sim-time SLAM nodes by PID (pattern kills matched the ssh command itself).

2026-11-14 15:27-15:45 REMAP 11 (session 2902fe9a). Owner placed objects in the hall, used no turnaround inside the hall, stop-and-go with the coach. Start: one request, ACTIVE first try (start_once.sh now matches "]: MANUAL MAPPING ACTIVE" only). REJECTED.
- Jump 1.511 m / 17.1 deg at 15:37:07 (leaving the hall); closure 0.389 m; exact candidate connectivity FAILED ("no inflated path"; the hall objects probably narrowed the passage); Nav2 plans both ways passed.
- Live corrections: 0.44-0.66 m already in the corridor/hall entry (15:33:54, 15:34:54), 0.6-1.05 m inside the hall (15:35:16-15:35:32), then 0.9-1.5 m while leaving (15:36:53-15:37:08).
- So the objects and the no-turnaround route did NOT help; the hall itself triggers it.
- NEW EVIDENCE (remap-10 bag, 235 hall scans 13:48:00-13:50:45 against the remap-10 candidate):
  - 8.7 % of returns land BEHIND mapped walls, up to 115/294 (39 %) at the turnaround spot (-0.22, -6.35);
  - concentrated at world bearings 90-120 deg (0.7-2.5 m) and 150-180 deg (up to 6.2 m).
  - Hypothesis: see-through or reflective surfaces in the hall (glass, mirror, shiny surfaces, open space under furniture at LiDAR height), so phantom geometry moves with the rover. Owner asked to inspect.
- Restored: localization seeded (0.235, -1.775), READY, latched, accepted map unchanged (4beb26d5a999), places from pre-remap11.
- Dashboard: web/v2/mapping.html in mapping mode (live /map, no AMCL) now hides saved-map places and draws the SLAM pose as a green "ATLAS (SLAM)" arrow. Static file, no restart; verified in the browser.

2026-11-14 ~16:05 OFFLINE range-limit tests (remap-10 recording, start -> hall turnaround, isolated domain).
- max_laser_range 8 m (live): max step 0.68 m, 19 steps > 0.15 m.
- 5.0 m: 0.70 m / 19. 4.0 m: 0.75 m / 19. 3.5 m: 0.75 m / 19.
- No help, so the confusing returns are near the rover (owner confirmed glass door/window, mirror or shiny surface, and open space under furniture in the hall; they must stay).
- RPLIDAR Boost intensities are binary (0/47): no intensity filtering possible.
- Owner's hall context: cannot be covered. Proposed next:
  (1) offline accuracy check of the remap-10 final map (all scans vs the final map, plus tape-measured room sizes);
  (2) if accurate, a reviewed acceptance change that judges final-map consistency instead of mid-drive map->odom corrections (owner decision);
  (3) the 3D v2 map;
  (4) M3 wire -> Drive PID -> supervised autonomy.
- Also shown to the owner: remap-10 drive path image (docs/colour_3d_20261114/drive_path_remap10.png). Plan-only Nav2 route dhruv room -> hall on the accepted map: 7.31 m, 89 poses (docs/colour_3d_20261114/planned_path_room_to_hall.png), republished plan-only for 10 min for the dashboard. No goal sent, rover latched.
- Owner asked ATLAS to drive itself. Declined: autonomy gate (navigation_validated false / M3), no Drive PID, stale corridor/hall map. Not bypassed.

2026-11-14 ~16:20 OFFLINE ACCURACY CHECK of the remap-10 candidate map (de55c1d3); /tmp/map_accuracy.py, owner: "Yes, check it".
- Method: each recorded scan after drive-ready (every 3rd, 3,603 scans) ICP-matched to the FINAL candidate map, seeded with SLAM's live pose.
- Results:
  - all 3,603 matched;
  - fit within 15 cm: median 100 %, p10 99 %, 100 % of scans >= 85 %;
  - within 5 cm: median 99 %;
  - by area (room 2,243, corridor 764, hall 596 scans): median 100 %, p10 98-100 %; worst scan 92 % (13:48:32 hall entry; 14:05:33 room);
  - best fit vs SLAM live pose: median 3 cm, p90 14 cm, max 24 cm.
- Interpretation: the final map is internally consistent along the whole drive, including the hall (no bends or doubled walls). The 1.3-1.5 m map->odom "jumps" were frame corrections (map vs odom); the robot pose itself was never more than about 24 cm from the final-map best fit.
- Caveats: self-consistency is not absolute scale, so the owner will tape-measure Dhruv Room width (map 3.05 m) and hall depth (map 2.20 m) (docs/colour_3d_20261114/map_sizes_remap10.png). Repeatable glass/mirror reflections may appear as phantom features.
- Proposal (for the owner's review; NOT implemented): add a final-map consistency evidence path to map acceptance:
  - >= 95 % of session scans fit the final map >= 85 % within 15 cm;
  - live-pose vs best-fit <= 0.30 m;
  - plus the unchanged closure <= 0.15 m / 10 deg, connectivity and Nav2 plans.
  - Remap 10 would still fail closure (0.230 m).

## 2026-11-14 — Final-map acceptance check written for review (STAGED, OFF BY DEFAULT, NOT DEPLOYED)

Owner asked to write the change proposed after the remap-10 accuracy check. Nothing on the running rover changed.

What it does when enabled (`map_acceptance_final_map_mode: true`, default `false`):
- Mission control keeps ~2 LiDAR scans/s during a manual mapping session with SLAM's live map->base_link pose at the
  scan stamp (cap 1200 samples, halved density when full so the whole drive stays covered; read-only).
- At acceptance it ICP-matches every sample to the exact candidate map bytes (`scripts/atlas_final_map_consistency.py`).
- If the map->odom translation/yaw JUMP limits fail, passing final-map evidence may replace those two checks only:
  >= 100 samples, every sample matched, >= 95 % of samples with >= 85 % of returns within 0.15 m of a final-map wall,
  live pose never > 0.30 m / 10 deg from the best fit. `atlas_map_acceptance_core.final_map_consistency_failures`
  re-checks the numbers and thresholds; the evidence's own `passed` flag is not trusted alone.
- Unchanged: closure (0.15 m / 10 deg), exact-candidate connectivity, full-footprint connectivity, both Nav2 plans,
  startup stillness, guard trips, and every tf_jump integrity/timestamp check.

Tests (Jetson staging ~/atlas_staging_20261113): test_final_map_consistency (10), test_mission_final_map_sampling (5),
test_atlas_map_acceptance_core, test_mission_status_idle_revert: 49 passed.

Replay of remap 10 (de55c1d3) through the staged path (`tools/localization/replay_final_map.py`):
- 903 samples (thinned 3x), 903 matched, fit median 100 %, p10 100 %, fraction good 100 %, pose offset median 3 cm /
  max 17 cm, heading offset max 9.97 deg (limit 10), evaluation 10.5 s.
- switch OFF: REJECT (jump 1.46 m, yaw 14.2 deg, closure 0.23 m) — identical to the stored decision.
- switch ON: REJECT, only "round-trip translation closure 0.230 exceeds 0.150". The closure gate still decides.
- Heading note (do not loosen to fit this data): 49/903 samples had the live heading > 5 deg off the best fit, max
  10.0 deg at 13:50:31 in the hall and ~9 deg at 13:46:20-24 while PARKED in Dhruv Room. So SLAM's live heading really
  was ~9 deg wrong early in the drive and was corrected later (that correction is the 14 deg yaw jump). Remap 10 passes
  the 10 deg limit by 0.03 deg; a similar remap may fail it. Mapping is owner-driven (no Nav2 while mapping), so
  this measures how wrong the live pose was, not a risk to the accepted map.

Open review points: sample cap (1200, about 4.8 MB, ~10 s evaluation) vs a 30-min drive; whether 10 deg is the right
live-heading limit; closure 0.23 m on remap 10 is still a real reject (owner tape measures pending).
Enabling needs the owner's OK plus a deploy with the rover parked and the E-STOP latched.

## 2026-11-14 16:37 — Final-map acceptance check DEPLOYED and ON (owner: "depay kar do")

- Pre-checks: no mapping session file, wheel odom twist 0, motion blocked ("REMOTE STOP: joystick unavailable"),
  live mission control / acceptance core identical to commit 2e21270 (md5) before replacing.
- `tools/deploy/deploy_20261114_final_map.sh`: backed up as *.before-finalmap-20261114, copied the 3 scripts + tests,
  added drop-in ~/.config/systemd/user/atlas-mission-control.service.d/final-map-mode.conf
  (`-p map_acceptance_final_map_mode:=true`), restarted ONLY atlas-mission-control. Rollback: `bash <script> --rollback`.
- Verified: service active, READY, `ros2 param get ... map_acceptance_final_map_mode` = True; 49 focused tests pass in
  ~/project_atlas; atlas_regression ALL PASS (55 unit, old map connected, 17 rejected candidates re-checked: none
  accepted now — the stored ones lack scan samples, so the new path cannot accept them).
- Limits unchanged (strict version that passed the tests). Next remap is the first real use; watch the heading-offset
  margin (remap 10 was 9.97 / 10 deg) and the closure (must be <= 0.15 m).

## 2026-11-14 16:44-17:00 — Remap 12 (session 22776983): REJECTED; final-map sampler collected 0 scans (my bug)

- Owner drove Dhruv Room -> hall -> back to the tape mark, stop-and-go. Closure 0.100 m / 0.1 deg: PASSES (first remap
  under 0.15 m). Jump 1.274 m / 15.6 deg (same corridor/hall SLAM corrections as before).
- Rejected also because named places "dhruv room"/"hall" were not saved in this session (in remap 10 I saved them on
  the owner's call-outs; this time I did not remind/save — process miss, mine).
- final_map_consistency: scans 0. Cause: under the batched executor (ATLAS_EXECUTOR_BATCH_S=0.05, deployed 11-13)
  rclpy takes at most ONE message per subscription per wait cycle (~20 msg/s per topic). /tf arrives at ~30 Hz, so
  mission control's TF buffer lags by seconds and an immediate lookup at the scan stamp always failed
  (reproduced: 0/80 ok with batching). tf_jump sample_count 7429 over ~380 s (= 19.5/s) confirms the cap.
  Also: parked, slam_toolbox's map->odom stamp stops advancing, so exact-stamp map->base_link lookups fail too.
  Unit test missed it because the fake TF answered immediately.
- Offline replay of this bag through the staged evaluation (latest-TF method): 799/799 scans matched, fit median 100 %,
  p10 97.8 %, pose offset max 0.23 m, heading max 13.6 deg -> would FAIL the 10 deg limit. Both > 10 deg samples were
  during fast turns (24 and 11 deg/s, where replay TF latency inflates heading); while still (< 3 deg/s, n=648) max 9.4.
- WIDER FINDING (needs review): every batched node subscribed to /tf (mission control, localization monitor, ...)
  sees TF capped at ~20 msg/s and seconds late. Mission control's current_pose / scan-fit gate / named-place saves
  read that lagged TF (only refuses or saves while stopped, but it is wrong). Candidate fix: TransformListener
  spin_thread=True or excluding /tf-heavy nodes from batching. Not changed yet.
- Rover parked at the mark, session still open, SLAM running. Nothing else changed.
- 17:05 owner latched E-STOP; session 22776983 ended with end_restore (files in rejected_session_22776983, bag kept,
  81 MB). AMCL active, accepted map unchanged (atlas_latest.pgm 4beb26d5a999), dashboard localization check VERIFIED.
  The deferred-lookup sampler edit in the working tree is NOT committed/deployed (does not solve the TF lag).

## 2026-11-14 17:10-17:20 — Mission-control TF lag FIXED and final-map sampler verified live (DEPLOYED, owner: "Yes, fix it")

- Probe (batched main node + a SEPARATE tf node on its own SingleThreadedExecutor thread): 95/100 exact-stamp
  map->base_link lookups ok (5 = startup), wait p50 0.05 s / max 2 s. (Same-node spin_thread=True variant did not help.)
- atlas_mission_control.py: TransformListener now on node `atlas_mission_control_tf` with its own executor thread
  (all mission-control TF lookups see current transforms, not the ~20 msg/s capped /tf). Sampler queues ~2 scans/s and
  resolves the exact scan-stamp pose on a 0.25 s timer (give up after 3 s, counted as lookup_failures, first error
  kept in the evidence). Logs "FINAL-MAP SAMPLES n=.. lookup_failures=.." every 30 s while sampling.
- Tests: 51 focused pass (new: late-TF and never-TF cases, own-executor check); atlas_regression ALL PASS.
- Deployed 17:11 (backups *.before-tffix-20261114), E-STOP latched by owner, mission control restart only.
- Live parked test session 2a84f36b (no drive, 60 s): 228 samples, 228 matched, fit median 100 %, pose offset max
  0.035 m / 0.2 deg, lookup_failures 2 (SLAM startup), evaluation 1.6 s -> final_map_consistency PASSED. Rejected only
  for named places (expected). Session ended with end_restore; its 60 s parked test bag deleted (throwaway, no drive).
  AMCL active, localization check VERIFIED, accepted map unchanged (4beb26d5a999).
- Still open: other batched nodes that read /tf (localization monitor, lidar odom gate, safety status, sensor recovery)
  have the same ~20 msg/s per-topic cap; not changed. Remap 13 must save "dhruv room" at start and "hall" in the hall.

## 2026-11-14 17:21-17:30 — Remap 13 (session 21ed0671): REJECTED, but map quality and closure pass

- Places saved in-session: "dhruv room" (-0.77, 0.17) at the start mark, "hall" (1.47, -5.91). Sampler worked:
  946 samples, 0 lookup failures.
- PASS: closure 0.135 m / 1.3 deg; final map 946/946 matched, fit median 100 %, p10 98.4 %, 100 % of scans good,
  live position offset max 0.256 m (limit 0.30).
- FAIL 1: live heading offset 13.84 deg (limit 10). Offline (latest-TF, inflates in turns): 2/972 samples > 10 deg,
  all > 8 deg samples in the corridor end / hall (y < -3); while still (< 3 deg/s, n=858) max 8.2. 17:27:22 at
  (1.89, -4.64) +13.1 deg at only 6 deg/s -> a real transient SLAM live-heading error in the hall, not a timing effect.
- FAIL 2: "candidate start is not clear for the inflated rover": nearest final-map wall 0.24 m from the "dhruv room"
  place (rover half-width 0.175 + 0.18 inflation). The start mark is too close to furniture for Nav2 — needs an open
  start/place spot (>= ~0.5 m from walls). This is a real gate, not changed.
- map->odom jump 1.274 m / 13.6 deg (remap 12: 1.274 / 15.6) — the same corridor/hall corrections.
- Decision needed from owner: keep the 10 deg live-heading limit (hall remaps keep failing) or raise it (e.g. 15 deg;
  position limit 0.30 m stays). Not changed. Note: a re-stop of the same session cannot re-use samples (buffer is
  released at the first evaluation), so this session cannot be salvaged.

## 2026-11-14 17:35-17:45 — Live-heading limit 10 -> 15 deg DEPLOYED (owner: "15 digera kar do"); places finding

- Owner decision after remap 13. FinalMapConsistencyPolicy.max_pose_offset_deg and
  MapAcceptancePolicy.final_map_max_pose_offset_deg = 15.0; position limit 0.30 m and every other gate unchanged.
  Re-evaluating remap 13's stored evidence with 15 deg leaves ONLY the start-clearance / plan failures.
- Owner asked to approve remap 13 instead: NOT done. The "dhruv room" place is 0.24 m from a wall in that map; Nav2
  cannot plan from it (real safety gate). The session also cannot be re-validated (samples released at evaluation,
  lost on the restart needed for the new limit). Remap 14 needed: same route and start mark, but save "dhruv room" at an
  open spot (>= 0.5 m clear on every side).
- Session 21ed0671 ended with end_restore (E-STOP latched by owner); bag kept (97 MB); AMCL active, check VERIFIED.
- Deployed 17:40 (backups *.before-heading15-20261114), mission control restart only: active, READY, final-map mode
  True, 46 focused tests pass. atlas_regression: unit PASS, gate_history PASS, old_map FAIL
  ("candidate goal is not clear for the inflated rover").
- FINDING (pre-existing since remap 9, exposed now): saving "dhruv room"/"hall" during a mapping session OVERWRITES
  ~/.config/project_atlas/named_places.json, and a rejected session does not restore them. Saved places came from
  remaps 9, 10, 11 and 13 in their own SLAM frames; the accepted map d12a1f18 has had places from rejected sessions
  (the owner's earlier "map says Dhruv Room but it is the kitchen" fits this). old_map passed before only because
  remap 11's coordinates happened to be clear. No backup holds verified accepted-map places. Navigation to places is
  blocked anyway (navigation_validated false). An accepted remap 14 rewrites the places correctly. Code fix proposal:
  keep in-session places in the session (or back up and restore on rejection). Not changed.
