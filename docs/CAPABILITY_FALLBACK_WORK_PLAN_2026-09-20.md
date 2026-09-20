# Capability-aware fallback: work plan and increment 1

## Scope and baseline

Requested: sensor failures should trigger goal/capability evaluation, use only
prevalidated alternatives, preserve goals where safe, and never bypass local
safety. Baseline read/fetched: `212e4dd`. This is NOT a completed fallback system.

Increment 1 adds a **read-only capability registry/assessment** to the existing
commissioning endpoint and page. No driver, Nav2, EKF, mux, remote-stop, camera
home, calibration, motor-selection or service autostart policy is changed.
It does not publish ROS messages or control motion, and has no profile-activation
or mission-resumption endpoint. Loss of this web view cannot change local safety.

## Audit: already / partial / missing / correction

| Area | Status and reuse |
|---|---|
| Health/freshness | Existing driver diagnostics, web cache, sensor recovery and mux. Reuse; freshness is not calibration. |
| Encoder handling | Existing selection/exclusion, shared packet timeout, command-aware frozen-channel detection and incremental estimator. Reuse unchanged. |
| Evidence/history | Existing bounded SQLite ledger, per-gate configuration signatures, explicit invalidation and restart persistence. Reuse unchanged. |
| Next gate | Existing ordered evidence workflow. Continue opens a page; never starts motion. |
| Emergency stop | Existing remote B latch, deliberate reset, watchdogs, mux priorities and commissioning lock. No new bypass. |
| Recovery | Existing bounded peripheral recovery; motor-link restart requires stationary/fresh latched stop. Not a fusion-profile selector. |
| Capability registry | Added in this increment; source-backed configuration and live cached health, deliberately advisory. |
| Fallback profiles | Only disabled candidate definitions; no approved alternative. A two-encoder or VIO fallback is NOT commissioned. |
| Goal retention/resume | Missing verified failure checkpoint/resume state machine. Existing mission owner remains untouched. |
| Ultrasonic authority | Existing Float32 directional veto, but full validity/provenance and physical qualification need correction/testing. |
| AI supervision | Existing agent diagnostics may say READY/ACTIVE while deterministic gates prohibit autonomy. Never treat those labels as motion permission. |

## Ordered work list

1. **DONE in source:** registry, goal-requirements assessment, sensor-authority
   view and offline failure tests, reusing cache/evidence. Deployment evidence below.
2. **INSTALLED / STATIONARY FOLLOW-UP OPEN:** atomic UNO `UVALID1` sample age/sequence,
   bridge `/ultrasonic/validity`, directional mux checks and offline tests.
   Legacy/default ranges cannot grant clearance; missing front/rear proof
   blocks the corresponding autonomous direction. Firmware and paired runtime
   installation plus operator power-cycle autostart are observed. Passive checks
   found intermittent serial backlog; trailing-fragment handling and bounded
   same-tick receive draining are now installed after renewed power-OFF
   confirmation (112/112 offline tests). Fault/stability and physical qualification remain open;
   no degraded continuation is approved.
   See [increment 2 validation/deployment boundary](ULTRASONIC_VALIDITY_2026-09-20.md).
3. **PENDING:** deterministic profile selector and mission-owner checkpoint.
   Profiles need exact configuration-bound evidence, healthy source requirements,
   bounded speeds, entry/exit criteria, hysteresis and localization verification.
   Resume needs a new owner-issued goal generation, not a replayed stale Twist.
   Operator stop/cancel and reboot must prevent automatic resume. Preserve goal
   metadata/map identity for explicit review; do not persist motor commands.
4. **PENDING:** offline fault-injection campaign for that selector: stale shared
   link, individual/multiple encoder faults, partial recovery, invalid TF/pose,
   control-policy loss, stop during transition, reboot and wrong-map goals.
5. **PENDING operator gate:** verify/save the front steering range, then only the
   next unresolved ledger gate. Do not erase/repeat retained direction observations.
6. **PENDING physical validation:** independent measured odometry, stopping and
   relevant near-field/localization/remote-stop tests, in ledger order. Dynamic
   IMU qualification is required before IMU fusion, not to view its telemetry.
7. **PENDING:** controlled low-speed room missions, fault/recovery validation,
   repeatable return-home and longer mapping/map-save testing. Approve a profile
   only on its measured evidence; retain the goal without moving if none qualifies.

No completion percentage or physical PASS is inferred from software tests.

## Sensor usage and authority

The machine-readable inventory is `project_atlas/config/capability_registry.json`.
It records driver, topic chain, consumer, capability, role and required evidence.
Runtime fields describe **observed data**, not proof that every downstream
consumer is running or correctly configured. Full ROS graph/TF commissioning
remains necessary. Unsupported runtime policy changes are reported, not adapted to.

| Source | Existing use / authority | Remaining limitation |
|---|---|---|
| M1 rear-left, M2 rear-right, M3 front-left | Selected wheel-feedback components -> `/yahboom/odom` -> wheel-only EKF `/odom` -> Nav2 | Metric/stopping/turn reliability still unqualified |
| M4 front-right | Excluded feedback; raw diagnostics | Drive motor remains separate; no claim of repaired encoder |
| RPLIDAR | `/scan` to costmaps, AMCL/SLAM and existing obstacle guards; primary geometry | Live scan is not proof of trustworthy localization/TF or all-around clearance |
| IM10A | `/im10a/imu/unvalidated` and dashboard observer | No `imu0` in current EKF; gyro/mounting/dynamic test pending; no magnetic-heading fusion |
| Yahboom IMU | Board IMU diagnostics | Not a validated alternate EKF source |
| Camera | Video/perception/visual observation | No validated VO/VIO; never substitute camera-online for odometry |
| PCA9685 PTZ | Existing UNO camera owner | Commands are not measured angles; physical limits need evidence |
| Front/rear ultrasonic | Existing directional mux veto | Qualification and provenance pending; not LiDAR/SLAM replacement |
| Left/right ultrasonic | MCU reports disabled in audit | Not available protection; no automatic enable |
| RD-03D | Target diagnostics/tracker and optional forward Nav2 speed guard | Cannot claim live guard enabled from decoder data; no localization replacement |
| Hiwonder GNSS USB | Diagnostics and position reporting | Current indoor data has no fix; not an input to current indoor EKF |
| BME680, AMG8833 | Environmental/thermal display and logging | No collision/navigation authority |
| Main BMS | Battery diagnostics and existing battery policy | Do not bypass battery limits |
| INA3221 | Jetson onboard rail/power diagnostics | Not traction battery SOC |

## Current encoder policy (preserved)

Configured selected set is M1/M2/M3; M4 is excluded. `navigation_validated=false`.
The existing estimator requires at least three valid channels in both samples;
it cannot safely manufacture distance from one/two channels. Additional selected
faults or stale shared packets therefore block autonomous output under the
existing owner/mux policy. Frozen feedback is checked under commanded traction,
not by declaring a stationary count faulty. A fault is evidence, not proof of
a particular electrical/mechanical cause. No new encoder-count threshold is added.

## Proposed architecture and profiles

Existing sensor health -> capability registry -> goal requirements -> validated
source authority -> deterministic approved-profile selector -> continue/degrade/stop.

This increment ends at **advisory assessment**. All `validated_providers` lists
are empty until end-to-end authority is explicitly commissioned. A ledger PASS
remains a PASS for its recorded scope, not a general navigation permission.

- `SELECTED_WHEEL_LIDAR`: disabled candidate documenting the current selected
  wheel/scan architecture; allowed speed from this report **0 m/s**.
- `FUTURE_VIO_IMU_LIDAR`: **NOT AVAILABLE**, no VO/VIO implementation/qualification.
- Safe stop remains the existing deterministic mux/base behavior, not a new
  web-issued velocity profile. Approved alternates: **none**.

Goal scenarios distinguish room navigation/mapping from stationary image
observation. A missing encoder is not an image-observation requirement. No
scenario dispatches an action. Agent goal text is display-only, and stale agent
data is shown UNKNOWN. Goal preservation/resumption is explicitly not claimed.

## Failure display rules

- Reject missing, negative or nonfinite ages/values; use existing cache receive age.
- Encoder health must have fresh shared packet age, known selected/excluded set,
  recognized owner state and valid fault structure. Stale transport is distinguished
  from a selected-channel fault. Constant stopped counts are not a failure.
- LiDAR summary needs finite positive usable returns; it does not certify
  scan timestamp/TF latency, pose covariance or lack of occlusion.
- Increment 2 replaces the legacy `USTAT` projection with fresh atomic `UVALID1`
  sample proof. Legacy ONLINE is not echo validity. Physical transducer range,
  blind zones, mounting and stopping distance still require qualification.
- Fresh GNSS status cannot hide stale NMEA/GGA or NO FIX.
- A diagnostic registry failure does not hide the independent evidence ledger.
- Browser polling failure/expiry clears the capability view instead of leaving
  old health labels visible. This 5-second view is not a real-time safety loop.

## Current evidence / next action

On 2026-09-20 the fresh live read showed manual-only=true, stop_latched=true,
steering owner locked with expired lease, and navigation_validated=false. This is
not an automatic invitation to release the lock. M1–M3 historical direction is
retained as OBSERVED, M4 exclusion as EXCLUDED; metric and steering gates are not
recorded as physical PASS. The unsaved front draft is not a valid saved range.

**NEXT SINGLE OPERATOR ACTION:** while securely lifted, use the existing steering
commissioning owner to physically verify and explicitly save the front centre and
safe left/right endpoints, then record the verification. This establishes a saved,
configuration-bound range missing from the ledger; it does not request another
encoder-direction repeat. Fresh hands-clear confirmation is required before any
servo action. Do not put the rover on the ground for the current software work.

## Performance and validation

No additional ROS subscriptions, processes, drivers, camera streams, point-cloud
processing, AI models or databases. Pure stdlib assessment runs with the existing
5-second evidence fetch; registry contains a bounded configured sensor inventory.
CPU/RAM impact has not yet been measured under a full navigation workload. Do not
quote a whole-Jetson CPU improvement from this advisory change.

Offline tests exercise stationary counts, exclusions, individual/shared failures,
NaN/ages, unknown policies, camera-not-VO, goal-specific requirements, ultrasound
stub/disabled/no-echo, GNSS stale fix, evidence invalidation, stop restrictions,
registry escalation rejection, nonmutation and corrupt/missing-registry isolation.
Validation results:

- Windows: 57 commissioning tests run, 56 passed, 1 skipped (existing optional
  PyYAML import); all 16 steering-commission tests passed.
- Jetson staging: all **57 commissioning tests passed**. An initial staging run
  lacked the driver source fixture needed for a read-only AST test; copying that
  source fixture resolved the test setup error without importing/actuating it.
- JavaScript syntax, Python compilation and whitespace/diff checks passed.
- Live browser verification using the computer-use skill: the new expandable
  sensor-authority section renders actual cached state; stop/steering controls
  remained untouched. No image, motion or calibration test was invoked.
- Live API after web restart: 22 configured source entries; ADVISORY_ONLY,
  NO_APPROVED_PROFILE, motion_authorized=false, resume_authorized=false;
  retained encoder_direction=OBSERVED and m4_feedback=EXCLUDED.
- Local development-machine microbenchmark: about 0.17 ms per pure report over
  100 evaluations and about 18 kB JSON. This is NOT a Jetson CPU/RAM measurement
  or a normal-navigation-load endurance result.

## Deployment / rollback

Only verified web/commissioning assets and the new read-only registry/evaluator
are eligible for deployment. No base/mux/MCU/Nav2/IMU service restart is required.
Before restarting the web service confirm fresh stopped/latched telemetry and zero
command. Back up the previous web commissioning assets on Jetson. Roll back those
assets and restart only `rover-status-web.service`; new unused registry/evaluator
files may remain inert. Existing SQLite evidence is not rolled back or deleted.

The first rollout is not permission to launch a mission, alter a fusion source or
claim that goal retention and automatic fallback are complete.

Deployment completed on 2026-09-20: `atlas_capabilities.py`,
`atlas_commissioning.py`, `atlas_commissioning.html`, `atlas_evidence_ui.js`,
`capability_registry.json` and the new offline test file. Stopped/manual-only,
latched-stop and fresh zero command were checked before and after installation.
Only `rover-status-web.service` was restarted. Base, mux and UNO services remain
active; their software and calibration were not changed.

Backup: `/home/jetson/project-atlas-migration/capability-advisory-20260920/backup/`
with original commissioning Python/HTML/JS assets. Restore those three files to
their corresponding `project_atlas/scripts/` paths to revert this UI increment;
restart only the web service while stopped. Do not restore or delete the ledger.
