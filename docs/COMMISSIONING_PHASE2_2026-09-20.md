# Phase 2 — evidence-first reliability, increment 1

Baseline fetched from origin/main: `8e4a2a11b395bf9d207e7b0336181f05cd0bf9fc`.
This continues, not replaces, the existing port-8088 console, serial owners,
camera stream, steering lease, calibration file and bounded SQLite history.
Earlier September 20 first-increment documents are historical deployment
snapshots, not statements that steering/camera controls are still absent.

## Current audit (read-only Jetson check)

- Web, base, mux and UNO hub active. Mux `ATLAS_MANUAL_ONLY=1`, stop latched.
- M1/M2/M3 selected, M4 feedback excluded, `navigation_validated=false`.
- Wheel-only EKF (`odom0=/yahboom/odom`); no `imu0`. IM10A monitoring remains
  unvalidated. Historical bias and turn disagreements do not justify enabling it.
- Steering lease expired with traction inhibited. Live saved defaults were
  90/90 centres; **no steering_calibration.json existed on disk**. An unsaved
  draft is not permanent commissioning. No lock was cleared and no servo moved.
- Camera home remains 1725/1500 microseconds; reported pulses are not angles.
- UNO USTAT showed front/rear ONLINE, left/right DISABLED. That is transport
  evidence, not ranging accuracy or safety qualification.
- Mux subscribes to all four range topics and can veto autonomous forward,
  reverse and turning commands from fresh positive ranges. Source defaults:
  rear stop 0.30 m, freshness 1 s, dynamic reaction-distance floor. This is NOT
  sufficient end-to-end validation: stale ranges lose veto authority, positive
  values lack source provenance/debounce in this callback, and runtime parameter
  overrides/driver fallback provenance still need qualification. Do not infer
  PATH CLEAR from USTAT ONLINE, synthetic or maximum-range values.

## Implemented in this bounded increment

- Same SQLite file: additive `evidence`, `evidence_current`, `evidence_meta`
  tables. Original `results` are preserved. Journal bounded to 500 events;
  last record per known gate pinned so repeated hardware checks cannot evict
  an old valid physical PASS. Latest 100 journal events available via history.
- Gate/test IDs, timestamps, status, measurements, confirmation, source,
  configuration hash/source hashes, hardware-revision disclosure, invalidation
  link and retest reason. Source hashes capture relevant owner/config files,
  not unrelated dashboard appearance. Steering geometry is hashed per axle,
  ignoring save timestamp. Runtime overrides are not silently certified.
- Legacy observations migrate idempotently as observations, never physical PASS.
  The September 17 direction report is retained as historical OBSERVED, with
  its document checksum and unknown historical config explicitly stated. The
  approximate 40 cm run is not promoted to a precision calibration.
- File/calibration changes project RETEST_REQUIRED with changed filenames.
  Operator-reported hardware changes append a retest record with a required
  reason. They do not alter calibration. Physical hardware cannot be auto-
  fingerprinted: operators must report wiring, motors, linkage or sensor changes.
- Existing non-motion checks record start/terminal evidence. Interrupted runs,
  corrupt storage, missing telemetry and failed writes cannot yield PASS.
- `CONTINUE ATLAS COMMISSIONING` selects the next unresolved gate, not Step 1
  on every visit. It only opens a page, never starts motion. Completed PASS is
  retained; historical direction OBSERVED advances to metric validation without
  pretending it qualified autonomous navigation.
- Explicit front/rear physical witness recording requires a saved file,
  matching fresh owner report, successful save, latched drive stop, unchanged
  hash and operator description. No arbitrary HTTP PASS endpoint. A configured
  default or software save alone cannot produce physical PASS.
- Read-only readiness view remains AUTONOMY BLOCKED. It cannot release the mux,
  set navigation_validated, enable an IMU, change excluded channels, or start
  fallback/resume. Active control authority remains in the existing safety stack.
- Evidence refresh is 5 seconds; existing fast telemetry and single cached JPEG
  remain unchanged. No sensor rates, navigation parameters or serial code changed.

## Remaining implementation and physical gates (not claimed complete)

1. Finish operator range verification/save using existing steering controls.
   Current missing saved file makes this the first unresolved gate; do not run
   wheel tests while the existing calibration lock still inhibits traction.
2. Owner-enforced camera safe-bound persistence/versioning/rollback, retaining
   1725/1500 home. Electrical 700–2300 is not a verified mechanical envelope.
3. Separate bounded motor-owner commissioning lease/mode and disconnect/remote-
   stop/owner-death/write-failure tests. Individual motor tests remain disabled.
4. Accurately measured encoder Run A candidate, explicit review/save, independent
   Run B with defined acceptance criteria. Never fit and validate one recording.
5. Separate physical stopping and measured CW/CCW IMU workflows. No unvalidated
   IMU fusion and no requirement to repair M4 just to commission the IMU.
6. Finish runtime graph/consumer/parameter sensor audit; qualified ultrasonic
   validity, provenance and debounce handling; known-distance sensor verification.
   Existing bounded distance observations already exist and must be reused.
7. Deterministic health/authority and prevalidated fallback profiles, including
   preservation/resume of goals only under approved safety conditions. No VO
   exists simply because the video works. No alternate profile is approved here.
8. Independent localization/TF/load, physical remote-stop and return-home evidence.
9. CPU/RAM/callback-age browser-open/closed benchmark and reboot persistence test.

The submitted document ends mid-sentence at implementation-order item 5. The
sections before that are retained as the phase-2 roadmap above; nothing beyond
the supplied text has been assumed. No physical test was requested by this update.

## Storage authority / rollback

Steering: existing motor owner and config/steering_calibration.json. Camera:
existing UNO owner/home environment. Encoder scales: existing base constants,
selection: encoder_selection.yaml. EKF: atlas_ekf.yaml. This increment changes
NONE of those values. SQLite is test evidence, never an actuator config source.

Rollback web code only; leave additive evidence tables in place. Old console
ignores them. Do not delete original observations or restore an old DB over new
tests. Reboot and hardware validity are not implied by a passing unit suite.

## Validation / deployment

- Windows: 31 commissioning/evidence tests passed; one PyYAML/ROS-runtime test
  skipped. Existing steering (16), remote-stop (10) and camera-link (6) tests
  passed: 63 passed plus one skip. JavaScript syntax and Python compile passed.
- Jetson: all 32 commissioning/evidence tests passed, including configuration-
  derived M4 EXCLUDED evidence. No motor channel was re-enabled.
- Browser/API: Continue opened Steering with jog/save controls disabled until
  owner entry. Evidence displayed retained encoder OBSERVED, M4 EXCLUDED,
  missing physical steering verification and unchanged autonomy restrictions.
  No steering entry/jog/exit or camera-motion button was pressed.
- New non-motion hardware observation completed and was recorded as WARNING,
  not physical PASS. Original four observation rows survived migration; the
  direction document was imported once. After a second web-only restart,
  evidence remained present and the next gate was still steering_front.
- Post-deployment `/cmd_vel` cache was zero; the mux remained manual-only,
  stop latched and the steering lock/targets unchanged. This is a stationary
  software deployment check, not wheel, emergency-stop or reboot validation.
- Seven console/web assets installed under `/home/jetson/project_atlas/scripts`;
  historical observation reference under `project_atlas/docs`. Only
  `rover-status-web.service` restarted. Existing service autostart unchanged.
- Previous code and pre-migration database backup:
  `/home/jetson/project-atlas-migration/phase2-evidence-20260920/backup/`.
- Motor ownership, calibration files, EKF, sensor rates, navigation parameters
  and remote controls unchanged. Resource benchmark and physical tests pending.
