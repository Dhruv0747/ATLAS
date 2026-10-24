# Project ATLAS - Autonomous Service Rover

[Lifecycle cache follow-up](docs/ATLAS_LIFECYCLE_CACHE_TEST_20261024.md): explicit
cache rebuild fixes removal but fails recreated delivery; group-detach variant
fails ownership validation. Both rejected, no deployable CPU change or live work.

[Real ROS entity/bond validation](docs/ATLAS_NATIVE_ROS_ENTITY_BOND_TEST_20261024.md):
standard executor passed dynamic entities and0.387s heartbeat-loss detection.
Static candidate retained a removed subscription and is rejected;no deployment.

[Native wait-set experiment](docs/ATLAS_NATIVE_WAITSET_BENCHMARK_20261024.md):
18million fixture waits pass;condition retention reduces microbenchmark CPU.
Not an RMW/Jetson fix:dynamic ROS lifetime and bond regression gates remain.

[Nav2 native capture analyzed](docs/ATLAS_NAV2_NATIVE_PROFILE_RESULT_20261024.md):
15 on-CPU samples identify wait-set/bond work,not a proven runtime defect.
Six offline analysis tests pass;no new CPU-saving patch or deployment claimed.

[Saved CPU service ranking](docs/ATLAS_SAVED_CPU_SERVICE_RANKING_20261024.md):
historical Nav2/AMCL group51.345% of one core exceeds Dashboard44.842%; distinct
from localization monitor.10 accounting tests pass. No new runtime fix or CPU
savings claimed; native child-process attribution is missing. Nothing deployed.

[Isolated ARM64 comparison completed](docs/ATLAS_LOCALIZATION_ARM64_CPU_REPORT_TEST_20261024.md):
owner one-test CPU reporting exception;1716 callbacks and TF passed. Median
benchmark CPU saving3.55% (two pairs),not whole-Jetson headroom. Peak CPU87.04%;
RAM/temp/safety passed,services unchanged. Candidate not installed.

[Isolated Jetson comparison blocked](docs/ATLAS_LOCALIZATION_ARM64_ADMISSION_20261024.md):
CPU79.66% failed75% admission before benchmark launch. Hashes passed;protected
services unchanged,follow-up safety healthy. No ARM64 savings measured or retry.

[Paced localization CPU comparison](docs/ATLAS_LOCALIZATION_PACED_TRAFFIC_20261024.md):
saved sensor/TF timing and captured callbacks passed6896 deliveries/64 tests.
Candidate median PC CPU savings3.84% and10.03%,8/8 pairs positive. Not installed;
Jetson savings,full localization replay and Astra headroom remain unverified.

[Localization CPU capture analyzed](docs/ATLAS_LOCALIZATION_PROFILE_AND_EXECUTOR_TRIAL_20261024.md):
199 samples; main thread11.56% of one core. Wait-boundary samples are not CPU
attribution. Offline executor trial delivered378000 messages;60 tests pass,
but small workload-dependent savings do not justify deployment. Production unchanged.

[Localization thread profiler prepared](docs/ATLAS_LOCALIZATION_THREAD_PROFILE_PREP_20261024.md):
27tests pass,10second nonblocking all-Python-thread capture staged;owner sudo
required. Latest attempt aborted before profiling at75.21% CPU; evidence hashes
verified, no call stacks captured. Strict guards and production unchanged.
Owner-approved diagnostic-only CPU reporting option is now staged and hash
verified;29 tests pass. Other safeguards and production limits remain unchanged.

[Next CPU candidate rejected offline](docs/ATLAS_LOCALIZATION_CPU_CANDIDATE_REJECTED_20261024.md):
localization fit allocation preserved216 score cases/10 existing tests, but
paired savings2.40% then-0.51% were not repeatable. No production change.

[Safety scan retry deployed](docs/ATLAS_SAFETY_SCAN_DEPLOYMENT_RETRY_20261024.md):
single-file/safety-status-only restart verified under owner installation CPU
report-only. Reporter13.57 to13.10%onecore;wholeCPU70.72 to71.36%,no system saving.
Production guards,voice/UI preserved;Astra remains OFF.

[Safety scan deployment rolled back](docs/ATLAS_SAFETY_SCAN_DEPLOYMENT_ROLLBACK_20261024.md):
restart CPU85.69% exceeded75%;original restored and recovery verified. Only
safety-status restarted;no candidate retained or valid live savings comparison.

[Isolated Jetson scan test](docs/ATLAS_SAFETY_SCAN_JETSON_ISOLATED_20261024.md):
actual ARM64 callback4.57 to2.64ms,41.26% median paired saving;10/10 equal outputs.
No install/restart; whole-system savings not demonstrated,guards preserved.

[Offline scan CPU candidate](docs/ATLAS_SAFETY_SCAN_CPU_CANDIDATE_20261024.md):
335 equivalent cases,3 tests;47.18% synthetic callback CPU saving, not a
whole-Jetson saving. No installation or service change; Astra headroom unresolved.

[Voice candidate deployed](docs/ATLAS_VOICE_EXECUTOR_DEPLOYMENT_20261024.md):
voice-only restart and health/hash checks passed. Voice CPU25.16 to24.02% of one
core; whole-Jetson71.40 to71.47%,peak78.58%. No whole-system savings proven.
Owner installation-only CPU reporting exception; production guards unchanged.

[Voice-specific offline candidate](docs/ATLAS_VOICE_EXECUTOR_OFFLINE_20261024.md):
41-subscription workload,820000 messages,7 tests pass; median PC CPU saving3.086%,
8/10 pairs positive. Two-line exact-live patch prepared only; no deployment or
whole-Jetson/Astra readiness claim.

[Voice capture verified](docs/ATLAS_VOICE_CPU_CAPTURE_RESULT_20261023.md):
65 samples/zero errors; main ROS executor dominates sampled GIL stacks.
Command succeeded; no repeat needed. Voice-specific offline optimization pending.

[Voice CPU profiling prepared](docs/ATLAS_VOICE_CPU_PROFILE_20261023.md):
29 tests pass; bounded owner-run command staged. Explicit diagnostic-only CPU
reporting authorized; production safeguards unchanged. Awaiting administrator run.

[Remaining CPU investigation](docs/ATLAS_REMAINING_CPU_ACCUMULATOR_20261023.md):
distributed process load confirmed; next executor allocation candidate rejected
after median0.024% saving in10 pairs.10 tests and2.14M messages pass; no deployment.
Next discriminating evidence: voice-process thread/function CPU attribution.

[Executor retry deployed](docs/ATLAS_EXECUTOR_DEPLOYMENT_RETRY_20261023.md):
owner-authorized installation CPU-report-only retry installed three files;
only web restarted. White glass/safety/protected services unchanged. Parked CPU
71.218% to71.100%; no substantial whole-Jetson savings or Astra readiness proven.
Earlier entries below describe historical attempts, not current deployment state.

[Executor deployment rolled back](docs/ATLAS_EXECUTOR_DEPLOYMENT_ROLLBACK_20261023.md):
approved attempt exceeded75% CPU during postflight (77.234%). Original web/UI
restored and protected services unchanged. No Jetson CPU saving demonstrated.

[Dashboard-only executor package](docs/ATLAS_DASHBOARD_EXECUTOR_DEPLOYMENT_CANDIDATE_20261023.md):
QoS/concurrent shutdown tests and copy rollback pass;66 tests total. Three-file
exact-live package prepared, not installed. Separate web-only deployment approval required.

[Loaded executor comparison](docs/ATLAS_EXECUTOR_LOADED_INTERLEAVED_20261023.md):
2.14million messages delivered; median paired PC process CPU saving6.25%,9/10
pairs positive. Worst latency slightly worse; no Jetson/deployment claim.54 tests pass.

[Offline cancellation fix](docs/ATLAS_EXECUTOR_CANCELLATION_FIX_20261023.md):
terminal ready tasks now skipped before lookup;48 tests passed. Full-executor
CPU retest is variable, not proven Jetson savings. Nothing installed.

[Offline executor candidate](docs/ATLAS_EXECUTOR_COUNT_BENCHMARK_20261023.md):
direct count-field addition reduces PC idle-spin CPU5.45–8.06%;39 unit tests pass.
Existing cancelled-task KeyError reproduced in both variants; not deployment-ready.
No live changes or claimed Jetson-wide savings.

[Partial Python CPU evidence](docs/ATLAS_PYTHON_GIL_RESULT_20261023.md):45 usable
samples despite75.249% guard stop; executor bookkeeping is the focused next
offline target. No runtime fix or CPU savings claimed; white-glass unchanged.

[Targeted Python profiling prepared](docs/ATLAS_NATIVE_CPU_ADMIN_COMMAND_20261023.md):
10-second GIL-filtered diagnostic, 22 offline tests passed, staged hash verified.
Default 75/80/70 resource guards retained; no camera, restart or runtime fix yet.

[Native CPU result](docs/ATLAS_NATIVE_CPU_RESULT_20261023.md):75 samples/zero
reported losses; Python execution dominates selected threads. Exact Python
function cost unresolved; no safe runtime fix or CPU savings claimed. UI preserved.

[One-command native CPU profiling](docs/ATLAS_NATIVE_CPU_ADMIN_COMMAND_20261023.md):
user-bus fix passed; second run aborted77.14% with zero CPU stack samples.
Narrow two-thread profiler prepared,19 tests pass. Owner-authorized diagnostic
CPU report-only option does not change production guards. No camera/runtime change.

[New CPU evidence](docs/ATLAS_TAGGED_CPU_FINDINGS_20261023.md): recovered completed
admin capture; two hot threads confirmed, native cause still unresolved. Eight
offline analyzer tests pass. No runtime changes; white-glass UI preserved.

[White-glass UI deployed](docs/ATLAS_MATERIAL_GLASS_UI.md): all ten active V2 pages,
ATLAS watermark and header-only blur; controls unchanged. No restart or camera
start. Parked CPU70.47% before/70.45% after: no demonstrated CPU saving.
Runtime safety limits unchanged; verified backup and rollback retained.

[Astra stable-port guardian installed](docs/ATLAS_ASTRA_STABLE_GUARD_20261023.md):
56 focused tests pass; USB numbers resolved from verified topology. No camera
start/restart/reboot. Permanent rule installed; persistence test still pending.

[Permanent Astra permission installer](docs/ATLAS_ASTRA_PERMANENT_INSTALL_COMMAND_20261023.md):
one guarded owner command prepared; installation and reboot validation pending.

[Astra access/admin profiling](docs/ATLAS_ASTRA_ACCESS_AND_ADMIN_PROFILE_20261023.md):
lost temporary ACLs confirmed; guarded one-command helper staged, not executed.

[23 October optimization checkpoint](docs/ATLAS_RELIABILITY_OPTIMIZATION_20261023.md):
bounded reporting-cache candidate tested offline; no deployment or meaningful
whole-Jetson savings claimed. Dashboard profiling access and Astra access remain blockers.

[Remaining CPU assessment](ATLAS_STAGE32_REMAINING_CPU_AND_JSON_CANDIDATE.md):
dominant executor cost unresolved; minor exact-live JSON candidate tested but
NOT deployed. No camera or safety-policy changes.

[Exact-live snapshot deployment](ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_DEPLOYMENT.md):
installed/health-verified, web-only restart; Astra OFF. Whole-Jetson CPU69.27%
before vs71.21% after: no demonstrated aggregate saving. Headroom still unresolved.

[Exact-live snapshot package](ATLAS_STAGE32_EXACT_LIVE_SNAPSHOT_PACKAGE.md):
two-site patch preserves deployed steering/HTTP behavior;9 package tests and60
dashboard tests pass. NOT installed; approval required for web-only restart.

[Snapshot deployment blocked](ATLAS_STAGE32_SNAPSHOT_DEPLOYMENT_BLOCKED.md):
live source differs from reviewed baseline; no installation/restart performed.

[Offline dashboard snapshot candidate](ATLAS_STAGE32_DASHBOARD_SNAPSHOT_OPTIMIZATION.md):
Linux fixture CPU0.475->0.082 ms per snapshot;60 dashboard tests pass. Single-file
candidate NOT deployed; whole-Jetson savings and camera admission unproven.

[All-process CPU audit](ATLAS_STAGE32_AGGREGATE_CPU_ACCOUNTING.md): measured
parked load71.40%, no Astra test or production changes. Seven accounting tests
pass; new CPU optimization and80% safety qualification remain unproven.

[Latest approved preview test](ATLAS_STAGE32_PREVIEW_CORE_LIVE_RESULT.md):
CPU76.61% blocked before driver launch; zero frames/points, no retry.
Conversion optimization not exercised; full-session3D Preview still unverified.

[Offline depth conversion optimization](ATLAS_STAGE32_PREVIEW_CPU_OPTIMIZATION.md):
54.8% less PC conversion CPU, identical PNG output,94 tests pass.
[Deployed and verified](ATLAS_STAGE32_PREVIEW_CORE_DEPLOYMENT.md), Astra OFF;
this is not a whole-Jetson CPU or live3D Preview success claim.

Latest [single Depth verification](ATLAS_STAGE32_DIRECT_DEPTH_VERIFICATION.md):
17 real depth frames received, then CPU76.0757% stopped the session. No retry;
3D preview/interaction NOT verified. Protected services unchanged.

21 October offline launch optimization: [direct worker candidate](ATLAS_STAGE32_DIRECT_WORKER_LAUNCH.md).
Repeated login-shell/ROS setup removed; PC launch CPU work down66.1%,79 tests pass.
[Now deployed and verified](ATLAS_STAGE32_DIRECT_LAUNCH_DEPLOYMENT.md) with web-only
restart. Jetson launch savings and real Preview success remain unverified;
Astra and recorder OFF. Separate camera-test approval required.

21 October: [startup guard deployment verified](ATLAS_STAGE32_STARTUP_GUARD_DEPLOYMENT.md).
One runtime file and approved web-only restart; CPU peaked99.83%, settled below75%
by27s. Protected sensor services unchanged. Astra/recorder OFF; no camera test.

21 October offline follow-up: [startup coverage and bounded hashing candidate](ATLAS_STAGE32_STARTUP_COVERAGE_CANDIDATE.md).
77 tests pass; memory allocation reduced in PC fixture, aggregate CPU improvement
NOT proven. No deployment/session. Installation requires approval including one
web restart; calibration preparation need not wait for RGB startup.

21 October combined-camera follow-up: [cleanup deployed and one guarded test](ATLAS_STAGE32_CLEANUP_LIVE_RESULT_20261021.md).
CPU77.10% stopped the single attempt; Dashboard receiver got 6 depth/0 RGB frames.
No retry or service restart. Combined viewing remains unverified. Startup resource
coverage gap and separately reviewed optimization plan documented; no performance fix claimed.

21 October permanent USB access audit: [inventory, exact offline Astra rules,
tests and approval gates](ATLAS_PERMANENT_USB_ACCESS_AND_REBOOT_RECOVERY.md).
Serial access already works; only Astra needs the proposed persistent raw-USB
grant. Rules NOT installed; no reboot/reconnect or preview test performed.

Approved USB recovery currently blocked on administrator access; preflight passed,
but no installation, ACL change or live preview test has occurred. See the USB
access audit below. Persistent permissions are a proposal only.

21 October USB access follow-up: Depth admission is blocked by missing temporary
jetson USB ACLs after reboot, not calibration. Diagnostic-only candidate is offline;
no permission restoration or camera retry yet. See [evidence and approval/rollback plan](docs/audits/ATLAS_STAGE32_USB_ACCESS_20261021.md).
This new owner-requested investigation supersedes the pause note below; historical deployment notes remain preserved.

**Deployed 21 October 19:17 (U2+P): an UNCALIBRATED — DIAGNOSTIC ONLY 3D preview** of the Astra's real depth
(orbit/zoom/pan in the browser; nominal field of view; no metric output, no ROS, no navigation). It has not yet been
viewed live: the live Depth session awaits owner re-confirmation. **Development is paused for 3 days**; see
[ATLAS_3_DAY_PAUSE_HANDOVER.md](ATLAS_3_DAY_PAUSE_HANDOVER.md) and
[Stage32 report section 29](ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md).

**Latest (21 October 18:02): real Astra infrared is live in the 3D Vision Lab.** Infrared mode now requests
640x480@30 GRAY8. This camera never serves the advertised 320x240 IR mode. A 60-second IR-only acceptance
session on the production driver completed normally at 29.7 fps with no restart. IR + Depth and the other
combinations, calibration and the point cloud are still not enabled. See
[Stage32 report section 25](ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md).

**Next developer:** start with [Stage32 final handover](ATLAS_STAGE32_DEVELOPER_HANDOVER.md).
Documentation-only checkpoint; no new operational authorization. Diagnose the
web-restart CPU spike read-only before requesting another deployment/test.

**Latest Stage32 deployment outcome:** approved instrumentation install was rolled
back after post-web-restart CPU95.64% exceeded75%. Original hashes restored;
IR test NOT started, no retry. Protected services unchanged except approved web
restarts; E-STOP latched, recorder/Astra OFF. See Stage32 report section19.

**Stage32 instrumented driver candidate:** ARM64 build and offline tests pass;
three-file package prepared, NOT installed. OpenNI read/conversion/publication
counters now cover the missing boundary; API/browser counters separate downstream
delivery. Real IR root cause still unresolved. See Stage32 report section18.

**Stage32 offline IR follow-up:** diagnostic/status fix candidate ready, NOT deployed.
Native PC ROS Domain77 test delivered 180 synthetic frames; real Astra delivery
remains unresolved. No new camera start. See Stage32 report section17 for the
missing OpenNI/publisher evidence and approval boundaries.

**Latest Astra checkpoint (21 October):** [Stage32 handover reconciliation](ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md#15-recovered-live-handover-evidence--21-october-2026).
Stage32 is deployed and hash-verified. The separately approved instrumented IR
revalidation received zero frames and stopped safely (report section16); A3 combination tests are held.
Metadata recovered; calibration/cloud remain gated. Astra and recording OFF.
Earlier summaries below are historical, superseded where this checkpoint differs.

[Stage30 resource investigation](ATLAS_STAGE30_ASTRA_RESOURCE_RECOVERY.md):
camera-free ROS startup also exceeded75%; stable Astra viewing still blocked.
Three-file observer-overhead/early-rejection cleanup DEPLOYED from `ac34cd3`,
119 focused tests retained; no restart or threshold change. One approved real
Dashboard Depth test stopped at CPU80.7786%, zero frames delivered. Astra OFF;
Pi camera and production identities unchanged. Live depth viewing NOT fixed.

[Read-only Vision Lab deployed](ATLAS_3D_VISION_LAB_LIVE_DEPLOYMENT.md) at
`/v2/vision3d`, Home shortcut verified desktop/mobile. First bounded depth attempt
stopped safely at CPU77.91% >75%; live frames/pixel measurements NOT verified.
Explicit Start/Pause, no autostart, uncalibrated axial Z only; live XYZ/cloud OFF.
Only web service restarted; protected camera/control/localization owners unchanged.

[Astra calibration continuation](ATLAS_ASTRA_PRO_CALIBRATION_AND_POINTCLOUD_VALIDATION.md):
installed hashes reverified, ABI layout checked, offline provenance/depth-statistics
tools prepared; 94 targeted tests pass. No new camera activation or production
change. Calibration root cause and real metric geometry remain unresolved.

[Stage29 continuation](ATLAS_STAGE29_ASTRA_OFFBOARD_ARM64_BUILD.md): ARM64 driver
built on PC and installed in an isolated Jetson directory. Bounded concurrent ROS
RGB (~15.1 Hz) and depth (~10.5 Hz) passed; existing Pi camera remained active.
Factory calibration query returned NaNs: metric PointCloud2 stays blocked.
88 targeted tests passed. Test runtime OFF; no autostart/dashboard deployment.
Owner-approved CPU-report-only tests exceeded normal CPU admission; this is not
CPU-headroom or endurance certification. Production control services unchanged.

Stage28: isolated paced Astra build aborted safely at CPU80.88% (limit75%).
No ROS stream/concurrent/cloud milestone claimed; no production deployment.
[Exact status and offboard-build next step](ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

21 October: [Astra isolated RGB/depth smoke tests verified](ATLAS_ASTRA_PRO_3D_VISION_LAB.md).
15 real frames per test; CPU peaks 71.43%/69.19%; depth SDK warning retained.
No production driver/viewer deployment, movement or recording. Global CPU stability
and simultaneous-stream endurance remain unverified.

Latest: [Orin Nano CV readings correctly treated as not applicable](ATLAS_ORIN_NANO_CV_THERMAL_POLICY_FIX.md).
26 offline tests pass; fresh Jetson thermal/safety check confirms stop latched,
zero commands and Stage20 OFF. Admission still blocks on CPU77.89% and manual_only=false.

Latest: [fixed temperature probe checked once on Jetson](ATLAS_PC_BRIDGE_TEMPERATURE_JETSON_CHECK.md).
CPU/RAM and six thermal zones under limits;CV0/1/2 unavailable, so admission blocks.
Subsequent SSH checks timed out; fresh safety/recorder state unverified. No recording.

Latest: [temperature probe corrected offline](ATLAS_PC_BRIDGE_TEMPERATURE_OFFLINE_FIX.md).
Bounded thermal reads and per-file error traces;17 focused offline tests pass on
Ubuntu22.04. No Jetson deployment, live probe or recording retry.

Latest: [approved bridge attempt blocked before connecting](ATLAS_PC_BRIDGE_STATIONARY_ATTEMPT_20261015.md).
Outgoing operation tests passed; fresh temperature measurement raised a Python
exception. No production subscription, capture or retry. Safety admission incomplete.

Latest: [PC–Jetson connectivity next action](ATLAS_PC_JETSON_CONNECTIVITY_AND_LOCALIZATION_NEXT.md).
All three previously missing publishers now visible; direct WSL DDS discovery failed
its bounded graph-only probe. Existing bridge reachable; live subscription needs approval.
Clock uncertainty persists. No production change, recording or movement.

Latest checkpoint: [PC full-contract recorder readiness](ATLAS_PC_OFFBOARD_RECORDER_READINESS.md).
21-topic native synthetic capture passed22,779/22,779; live recording remains NO-GO.
Clock relationship unstable, DDS transport unqualified; publisher finding superseded above.
Jetson unchanged; no production subscribers, recording, movement or service restarts.

Latest saved checkpoint: [PC runtime installed; morning handoff](ATLAS_PC_RECORDER_MORNING_HANDOFF.md).
WSL2/Ubuntu22.04/Humble installed; isolated native30s test passed1454/1454.
Paused overnight. Live transport/recording not authorized; Jetson unchanged.

Latest: [offboard PC recording feasibility](ATLAS_OFFBOARD_PC_RECORDING_FEASIBILITY.md).
Historical pre-installation report; WSL/ROS are now installed as noted above.
Live transport and Jetson CPU benefit remain unverified. Jetson unchanged.

Latest: [recorder startup CPU investigation](ATLAS_STAGE20_RECORDER_CPU_SPIKE_ROOT_CAUSE.md).
Historical 76.23% attribution remains UNKNOWN. One isolated startup profile completed;
no evidence-backed optimization or live retry. Recorder remains OFF;75% retained.

Latest: [activation evidence fix](ATLAS_STAGE20_RECORDING_ACTIVATION_FAILURE_FIX.md).
Supervisor now preserves exact refusal samples and non-masking final reports;
18 PC/native isolated tests pass. Source only; recorder OFF, no live retry.

Latest17:11UTC: exact30s diagnostic upgrade installed with owner's installation-only
CPU exception; recording OFF, runtime75% gate unchanged. Five hashes verified,
production unchanged. See readiness report's latest deployment entry.

Latest: [Stage20 exact30s upgrade readiness](ATLAS_STAGE20_30S_UPGRADE_READINESS.md).
Five-file diagnostic patch and native partial-failure rollback rehearsed; installed
package remains unchanged/OFF. Installation-only approval requested; recording
NO-GO pending real resource headroom. No CPU-limit change or localization claim.

Latest 14 October: [30-second recorder and minimal fusion milestone](ATLAS_NEXT_LOCALIZATION_MILESTONE.md).
Installed Stage20 legacy package remains OFF; older installation-blocked notes below
are historical. New opt-in30s profile passed isolated native capture/failure tests,
but is NOT deployed. CPU admission remains blocked. Minimal wheel-pose removal
candidate is contract-tested, not a proven localization fix; missing initialization
history prevents trustworthy historical A/B. No production or steering changes.

14 October: [CPU optimization candidate](ATLAS_STAGE20_CPU_OPTIMIZATION_REPORT.md)
removes unnecessary JSON formatting without caching telemetry or reducing rates.
Native serialization savings verified, but too small to establish installation
headroom; dominant dashboard stack profiling is blocked by OS permissions.
Source only, not deployed; preserve live/repository steering-integration differences.

14 October: [Stage20 CPU admission investigation](ATLAS_STAGE20_CPU_HEADROOM_AND_INSTALLATION_FIX.md)
adds exact five-interval resource evidence and transactional postflight rollback.
All resource ceilings and the nine public runtime payloads remain unchanged.
This is diagnostic preparation only; no third production installation or recording
activation is authorized. Genuine production CPU excursions must not be bypassed.

14 October: [Single supervised Stage20 retry](ATLAS_STAGE20_SUPERVISED_RETRY_RESULT.md)
installed the exact files and inactive unit, then failed the postflight resource gate.
New diagnostic files were rolled back; production services remain unchanged and
recording never started. No further attempt is authorized.

14 October: [Stage20 aborted-install investigation](ATLAS_STAGE20_INSTALL_FAILURE_ROOT_CAUSE.md).
Original abort cause remains UNKNOWN; discarded child error evidence is a confirmed
wrapper defect. Durable, sanitized installer evidence and sandbox rollback checks
are prepared. The public payload is unchanged. Production retry requires renewed
owner approval; recording remains OFF and production installation has not occurred.

14 October: [Minimum safe Stage20 public capture option](ATLAS_STAGE20_MINIMUM_SAFE_DEPLOYMENT.md)
separates deployment safety from replay fidelity. A default-OFF finite public-only
capsule is qualified for separate owner approval (65 offline tests and native
rate/ledger/resource/adapter/rollback checks). No private EKF/AMCL overlay is shipped.
No production installation, service restart, motion or localization-fix claim.
Full checkpoint and moving replay remain unqualified; the partial capsule does not
unlock autonomous navigation or fidelity-blocked candidates.

Stage20 continuation: [readiness report](ATLAS_STAGE20_DEPLOYMENT_READINESS_REPORT.md)
records native startup/consumer ledger and controlled EKF comparator passes,
preserved failure evidence, crash/quota tests and Gaussian RNG reseeding findings.
Instrumentation is **not deployment-ready**; no production or navigation change.

14 October: [Stage 20 checkpoint capture milestone](ATLAS_STAGE20_EKF_AMCL_CHECKPOINT_CAPTURE.md)
adds sandbox-only startup evidence tooling and an isolated EKF observer for the
actual relative anchor/full covariance. Service-call hooks default OFF. Native
smoke passes; full startup/consumer-order/AMCL fidelity and deployment readiness
remain incomplete. No production change or localization success is claimed.

14 October: [Stage 17 steering/yaw preparation](ATLAS_STAGE17_STEERING_YAW_VALIDATION.md)
adds an opt-in bounded recorder profile with raw IM10A, exact encoder snapshots,
particles and stationary steering-change capture. The isolated parked Humble
test passed; perspective-corrected visual road-angle tools and a supervised
test sequence are prepared. Physical steering measurements and moving
localization remain unvalidated. Default recording and live drive settings
are preserved; no autonomous-navigation release is implied.

11 October follow-up: [CHECK MY LOCATION checkpoint](docs/audits/ATLAS_CHECK_MY_LOCATION_IMPLEMENTATION_REPORT.md)
now includes the deployed fresh-sensor adapter and shared Command Center/Mapping
button. Stage A is read-only; 73 scoped tests and live browser checks passed.
Fresh checks expose an AMCL/LiDAR mismatch, not a localization fix. See the report
for measured resources, exact hashes, rollback and remaining accuracy gates.
Correction and navigation authorization remain disabled.
[New guard/resource evidence](docs/audits/ATLAS_CORE_RELIABILITY_CHECKPOINT_2026-10-11.md)
traces missing rays to raw infinity, not self-filter removal. Existing safety and maps remain unchanged.

11 October approved follow-up: the isolated installed Nav2 controller + exact
live-based command-mux candidate passed 15 safety/behavior checks. The new
stop-only LiDAR availability veto applies to NAV2/recovery only; it is not a
path-clearance estimator and leaves manual steering unchanged. Deployment
status and limits: [navigation guard report](docs/audits/ATLAS_NAVIGATION_GUARD_DEPLOYMENT_2026-10-11.md).
The historical source-only entries below describe earlier stages.
Both fixes are now deployed with matching hashes; B was updated dynamically
without restarting AMCL. Autonomy remains inhibited. Real-scan observation
gaps, moving localization and physical stopping qualification remain open.

11 October follow-up: recovery now rejects stale acquisition timestamps as
well as stale arrival times, including before its first pulse. Thirteen
source regressions pass; this extension is NOT installed. Deployment remains
conditional on the full navigation safety gates and fresh operator-stop evidence.

11 October decision-path audit: native Nav2 footprint checks distinguish the
front-right return from a blocked straight path. A separate recovery defect
allowed unknown sectors to grant motion; a tested fail-closed source fix is
prepared, NOT deployed. See the decision-path appendix in
[LiDAR evidence](docs/audits/ATLAS_LIDAR_PROVENANCE_2026-10-11.md). This is not
autonomous-navigation acceptance; verify the current stop latch before installation.

A separate source-only RPP correction explicitly matches obstacle-cost
conversion factor 15 to the existing inflation layer (live controller was 3).
Inflation geometry and motion limits are unchanged; deployment requires approval.

2026-10-11 sensing audit: the reproduced 0.51 m FRONT minimum is a raw
front-right return near -44.7 degrees, not the wall straight ahead.
[Evidence, candidate diagnostics and remaining validation](docs/audits/ATLAS_LIDAR_PROVENANCE_2026-10-11.md).
Minimum-point markers/provenance were deployed as stage 10 at 17:11 IST;
60/60 parked live requests succeeded. No range was discarded and no
localization or physical-return correction is claimed.

Parked operator views: `/v2/camera` displays the original JPEG without
recompression; `/v2/lidar` projects actual scan returns using scan-time TF.
Missing/stale scans and missing TF never imply clear space. Home navigation is
injected consistently on V2 HTML pages. Map overlay remains unimplemented.
These are observation views, not navigation authority or physical acceptance.

Daly BMS transport source now supports persistent healthy connections and bounded
reconnect backoff while preserving five-second healthy polling and fail-closed
freshness. See `docs/ATLAS_ROLLOUT_2026-10-11.md` for staged deployment evidence;
this does not by itself establish BLE endurance or autonomous readiness. The
live BMS stage was rolled back after a competing supervisor restart was found.
The tested retry-ownership correction was subsequently approved and deployed
as stage 8; the underlying BLE connection timeout remains unresolved. See
`docs/ATLAS_MASTER_DEPLOYMENT_2026-10-11.md` for current evidence and rollback.

### Motion-triggered diagnostics

The bounded background writer removes SQLite I/O from ROS callbacks. Sixteen
offline recorder tests pass; Jetson transfer of 7,874 pre-roll samples measured
5–37 ms (previously 463–512 ms). No autostart service is added. The current
rollout and live-validation status is tracked in `docs/ATLAS_ROLLOUT_2026-10-11.md`.

Installed as an opt-in process (not an autostart service). Final Humble test:
47,887 messages read back exactly; parked live capture: 3,203 messages, SQLite
healthy, 29.29% of one core / 78.27 MiB RSS. One DDS-reported lost message, no
application drops. The finite trial stopped; it is not recording continuously.
See `docs/ATLAS_ROLLOUT_2026-10-11.md` for exact versions and rollback.

### Staged deployment packages — 2026-10-11

`project_atlas/tools/deploy/make_package.py` builds one patch-based package per approved stage:
- the install rehearses on a scratch copy, backs up, then applies;
- `ROLLBACK.sh` has its install root pinned;
- nothing is restarted.

`check_packages.py` rehearses every install order against the deployed baseline, and `verify.sh`
runs GET-only post-install checks. The current stages and their status are in the
[staged deployment plan](docs/deploy/ATLAS_STAGED_DEPLOYMENT_2026-10-11.md).

**Developer handoff (2026-10-11):** start with [docs/HANDOFF_2026-10-11.md](docs/HANDOFF_2026-10-11.md).

### Glass UI V2 — the only dashboard since 2026-10-11 14:21 IST

`project_atlas/web/v2/` is the phone-first dashboard, with the camera and drive pad together and a
sticky E-STOP on every screen size.
- It is served at `/` and at `/v2/` by the same `rover-status-web` process
  (`scripts/atlas_web_v2.py`).
- The old page paths `/mapping`, `/commissioning` and `/wifi` redirect (302) to their `/v2/`
  versions. Other unknown GET paths return 404.
- Every API, `POST /`, camera stream, JS asset, the manifest, E-STOP and the web reset are
  unchanged.

The classic V1 pages are disabled, not deleted:
- `command.js` and the V2 sub-pages are still generated from the V1 sources by
  `tools/ui_v2/build_*.py`, so those sources stay in place.
- Setting `Environment=ATLAS_CLASSIC_UI=1` in a `rover-status-web` drop-in, then restarting,
  restores the classic routing with no file change.
- The full rollback is the stage 5 backup's `ROLLBACK.sh`.

Tests:
- `python3 -m unittest test_v2_default_route test_atlas_web_v2` (from `project_atlas/tests`);
- `tools/ui_v2/test_ui_v2.py <snapshot_dir> <out_dir>`.

Deployment record: [V2 default](docs/deploy/ATLAS_V2_DEFAULT_2026-10-11.md).

### Mission-start LiDAR check — 2026-10-10

Before any saved-map goal (return home, named place, taught route), mission
control now scores a fresh LiDAR scan against the accepted map at the current
AMCL pose. It uses only the beams AMCL itself does not sample. If fewer than
85% of returns land within 15 cm of a mapped wall, the goal is refused with
"ATLAS may have been moved. Set the current named place, then retry".

It also refuses on a missing or stale scan (older than 1 s), a missing laser
transform, or no map-frame pose. Mapping sessions are exempt. It never
publishes, seeds or moves anything.

Why: on Oct 9, after ATLAS was moved by hand, AMCL sat still and confident
0.55 m from the true spot (fit 61%). The covariance and stillness checks
both passed. Replaying the recordings, the check refused every known-wrong
pose (61–82%) and passed every good one (96–100%).

Parameters: `scan_fit_gate_enabled` (default true) and
`scan_fit_min_fraction` (default 0.85). If a goal is refused, reseed with
`seed_atlas_localization.py --place <place>`; never lower the threshold to
get past it.

2026-10-09 competing-pose comparison: equal bounded fitting plus later unused
beams favours the Dhruv region (99–100% endpoint fit, 0.214° corrected-gyro
residual) over the refined false region (78.9–85.6%, 98.229°). A recorded
cloud contains 15 particles near the better room pose; blanket missing-support
claims are not justified. Ten helper tests passed. Offline only, not a fix
or independent multi-drive validation. Next trace weak-hypothesis survival.
See [competing-pose evidence](docs/audits/ATLAS_COMPETING_POSE_EVIDENCE_2026-10-09.md).

2026-10-09 sensor evidence: six recorded stopped windows confirm that physical
stillness is not global localization correctness. Early return AMCL spans
1.148 m/76.478° against repeatable scans and +0.064° integrated gyro. Late
return is steady but wrong; its 77.4–82.7% endpoint fit overlaps late Hall.
No threshold or runtime change was deployed. Six helper tests passed.
See [sensor stability evidence](docs/audits/ATLAS_SENSOR_STABILITY_EVIDENCE_2026-10-09.md).

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
See [isolated experiment details](docs/audits/ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md).

An isolated AMCL build now exposes **scan processing separately from pose
publication**, with stale/failed-input diagnostics. It has no navigation
authority and is not installed in production. See the
[health contract and tests](docs/audits/ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md).

**Do not deploy the 4a4ea9a update-policy candidate:** integration validation
found stationary/slow-motion freshness stops with the existing mux. Five
contract tests document the rejection. The live configuration is unchanged.

Latest [offline update-policy results](docs/audits/ATLAS_AMCL_STATIONARY_POLICY_EXPERIMENT_2026-10-09.md):
stationary AMCL switches reproduced in the core harness. A repository-only
mission request gate stops gratuitous parked updates; **not deployed or an
autonomy qualification**. Full pose correctness and mux integration remain
unresolved. Steering and live production settings are unchanged.

Latest [stationary AMCL audit](docs/audits/ATLAS_AMCL_PARTICLE_COLLAPSE_2026-10-09.md)
found geometric particle collapse despite 2,000 published particles and tiny
covariance. A new read-only diagnostic counts distinct support independently
of particle weights. This is evidence for the next isolated update-policy
test; localization remains unresolved and no production setting changed.

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
The follow-up scan-window comparison shows the replay does not duplicate
the original hypothesis choices; missing internal AMCL likelihood/particle
state still prevents an evidence-backed tuning decision.
An [isolated stationary AMCL shadow trace](docs/audits/ATLAS_AMCL_SHADOW_TRACE_2026-10-09.md)
now captures pre-resampling particle weights and cluster choices without
replacing production AMCL; it is bounded and off by default. The short
capture validates instrumentation, not a localization fix.

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
Since 2026-10-10 the status chip separates the link from the rover: if this
browser has not heard from ATLAS for 2.5 s it shows **CONNECTION DELAYED - NO
DATA FROM ATLAS (ROVER STATE UNKNOWN)**. **POSE DELAYED ON ATLAS** appears only
when a fresh response reports a stale Jetson-side pose. The pose panel lists
"Data age on ATLAS" and "Link to this screen" separately. Wi-Fi or Tailscale
drops therefore no longer look like localization failures.
A low AMCL covariance alone no longer turns the chip green. Green **LIVE / AMCL
CONFIDENT (START VERIFIED)** also needs this boot's LiDAR start check
(`seed_atlas_localization.py` in `verify` mode). Otherwise the page shows
**AMCL CONFIDENT - START POSE NOT VERIFIED** or **LOCALIZATION UNKNOWN**. To
opt in, run `echo verify > ~/.config/project_atlas/seed_mode`. To check
without seeding, run `seed_atlas_localization.py --dry-run`. Neither grants
navigation authority.
A start check is not continuous proof. Green **LIVE / LOCALIZATION VERIFIED BY
LIDAR** needs `atlas_localization_monitor.py`. That monitor checks the current
AMCL pose against the LiDAR whenever ATLAS has been parked for 2 s, and the
check must be under 60 s old. Otherwise the page shows **MOVING – LOCALIZATION
NOT VERIFIED**, **LOCALIZATION NOT CONFIRMED – PARK TO CHECK**, **LOCALIZATION
LOST** (with the LiDAR's pose), or **START VERIFIED ONLY, NOT RE-CHECKED**.
Recovery mode is set in `~/.config/project_atlas/relocalize_mode`: `suggest`
(the default) or `auto`. In `auto`, AMCL is reseeded only after two agreeing
parked checks. No mode grants autonomy.
After a stop, the monitor shows **STOPPED - CHECKING LOCALIZATION WITH LIDAR**
(PARKED_SETTLING, then VERIFYING) until the check finishes. If odometry, the
LiDAR or the AMCL pose stops arriving, it shows red **LOCALIZATION UNKNOWN**
(INPUT_STALE). A result is discarded if ATLAS moved, an input went stale or
AMCL changed during the check. Each transition and its timing is appended to
`~/.local/state/project_atlas/localization_check_history.jsonl`.

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

## Stage 17B commissioning (prepared, not deployed)

Opt-in single-person front steering sequence, paused Vernier observations and
bounded diagnostic capture are documented in
[Stage 17B](ATLAS_STAGE17B_SINGLE_PERSON_STEERING_TEST.md).
Disabled by default; no physical-angle feedback or autonomy qualification is claimed.
Stage 18 owner directive places Stage 17B on HOLD, without deployment authorization.

## Stage 18 motion reliability (offline only)

[Stage 18 report](ATLAS_STAGE18_ODOMETRY_SENSOR_FUSION_REPORT.md) covers the isolated
general 4WS model, independent motion screening and two-drive shadow comparison.
No live sensor-fusion or reduced-encoder authority change is deployed. AMCL jumps
remain unresolved; improved relative yaw alone is not a localization pass.

## Stage 19 native replay (fidelity blocked)

[Stage 19 report](ATLAS_STAGE19_NATIVE_EKF_AMCL_REPLAY.md) records the completed
native Humble baseline, sandbox isolation and newly identified EKF initial-reference
gap. Correction comparisons fail closed until baseline fidelity is established.
No live fusion, calibration, map or autonomy change is authorized by these results.

## Parked CPU/manual-only checkpoint

20 October2026: UNO USB/all3 I2C devices recovered after operator power cycle.
Clock-safe serial-silence watchdog deployed; initial lockup cause remains unproven.
See [scoped fix and evidence](docs/audits/ATLAS_I2C_USB_RECOVERY_2026-10-20.md).

Continuation: background diagnostic-search burst reduced about69%; whole-system
CPU still exceeds75% briefly. No recording/autonomy admission. See
[paced search measurements and remaining blocker](ATLAS_BACKGROUND_SEARCH_CPU_20261015.md).

15 October 2026: manual-only restored live; AI previews render only when viewed.
Recording stays off; sustained CPU headroom remains unresolved. See
[measurements and rollback](ATLAS_PARKED_CPU_MANUAL_ONLY_20261015.md).

# Astra Pro Vision Lab candidate — 21 October 2026

Read-only identification confirms Astra Pro depth `2bc5:0403` and RGB `2bc5:0501`.
The additive `/v2/vision3d` viewer and Home shortcut are offline-tested candidates,
**not deployed**; no Astra ROS driver is running or authorized by this change.
See [hardware evidence, tests and approval/rollback plan](ATLAS_ASTRA_PRO_3D_VISION_LAB.md).

Approved stationary setup follow-up: pinned vendor source/private dependencies
are staged only. Build stopped at CPU75.88% (unchanged75% guard); camera USB
permissions still require administrator execution. No live Astra stream,
production page installation, recording or existing-camera restart occurred.
