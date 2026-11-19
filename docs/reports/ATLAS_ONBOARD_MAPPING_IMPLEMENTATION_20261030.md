# Standalone onboard mapping implementation — offline candidate

Continues `4c252de`. All new runtime code is repository-only and disabled by
default. Windows/WSL was used for testing, not designed as an operating dependency.

## Implemented

* Existing-topic RGB-D adapter with original payloads/stamps, CameraInfo checks,
  30 ms synchronization limit, 500 ms input age limit and explicit TF allowlist.
* Separate camera, production-input and mapping ROS contexts; publishes only in
  the isolated mapping domain. External odometry/LiDAR copied read-only. RTAB-Map
  `publish_tf=false`; no second production localization or camera driver.
* Bounded 60-second local supervisor, one-second CPU/safety observations, strict
  resource/telemetry/E-STOP gates, child monitoring, matching-session camera cleanup.
* Independent systemd three-second watchdog, cgroup cleanup, no restart/autostart,
  768 MiB memory cap and no automatic retry. Existing camera four-second lease is
  renewed locally, so a PC viewer is not required.
* Local SQLite integrity/hash checks; interrupted sessions quarantined without
  automatic replay or mutation. Per-session 2 GiB sampled budget, 1 GiB free reserve,
  retained-root 8 GiB admission budget. Sampling can overshoot: this is not a disk
  quota. RLIMIT_FSIZE bounds individual files, not aggregate storage.
* Jetson-hosted read-only map list/cloud API and white-glass canvas viewer; no CDN,
  ROS connection or external rendering server. Bounded 20,000-point snapshot,
  manual refresh, rotate/zoom/pan. Targeted homepage route/import changes only.

## Actual validation evidence

* Seven focused `test_onboard_mapping.py` tests PASS (native ROS message types,
  missing/stale inputs, calibration admission, domain isolation configuration,
  storage/quarantine, API traversal and foreign-camera cleanup refusal).
* Native PC synthetic ROS adapter test: 131 bundles forwarded, payload preserved,
  clean exit. Initial threaded executor shutdown failed; replaced by explicit
  single-thread polling and retested successfully.
* That synthetic test: 1.99 CPU seconds over 8.94 seconds, ~22% of one PC core;
  maximum process RSS 68,188 KiB (~66.6 MiB). This includes test harness work and is
  NOT an incremental Jetson or full RTAB-Map measurement.
* Isolated native fake systemd watchdog test PASS: missing heartbeat produced
  watchdog failure and stopped the fake child. No production units were touched.
* Browser synthetic UI fixture: 1,681 points displayed, rotate/zoom exercised;
  label explicitly SYNTHETIC UI TEST. Not real Astra map evidence.
* Reused prior RTAB-Map synthetic native result: 17 nodes, SQLite integrity PASS,
  ~202 MiB maximum RSS. Not an accurate physical map or onboard benchmark.

## ARM64 readiness

Read-only Jetson apt index confirms Humble ARM64 packages (not installed):

| Package | Version | Archive SHA256 from apt metadata |
|---|---|---|
| rtabmap-slam | 0.23.13-1jammy.20261008.162341 | 5c32da7361097f04cbfb38c9db392fd8029f69421de262b3ae096495441a36ce |
| rtabmap-util | 0.23.13-1jammy.20261002.114910 | 3e01720caa5a72ead629afd813ffa16c7309818145426fb61f7a9a4262f4f326 |

Downloaded archive verification, dependency transaction review and native Jetson
runtime remain PENDING. Current disk observation: 363 GiB available. Package sizes
are not dependency disk/RAM estimates. Mapping initial target 512 MiB/cap 768 MiB,
1 Hz keyframe processing, two OpenMP threads; actual Jetson CPU/GPU use unknown.

## Deployment and rollback preparation

`build_onboard_package.py OUTPUT` creates a review-only package with SHA256SUMS and
source commit. It cannot install or activate anything. Default config rejects
activation: domains, calibration paths, registered-depth topic, odometry and TF
evidence must be explicitly reviewed. Do not fabricate these fields.

Before any approved deployment: capture exact live hashes, back up touched files,
review ARM64 apt transaction and package hashes, verify rollback originals. Apply
only targeted web import/route/card changes against the current live white-glass
baseline; NEVER replace the live server or homepage with an older full file.
No web restart is currently authorized. Install optional unit only after review,
with no enable/autostart. Verify generated unit and source environment natively.

A later separately approved camera session is required before the supervisor can
attach. Camera activation is never performed by this candidate. Validate session
ownership/cleanup against the actual API first, including watchdog timeout and
service-failure paths. On abort stop only owned children/camera, preserve evidence,
quarantine uncertain database, restore reviewed files if deployment was made.
No production service stop, reboot, automatic resume or map deletion is permitted.

## Remaining blockers / verdict

Real RGB-D payload replay was not available in the searched evidence. Existing
preview images/distances cannot recreate original frames. Calibration, RGB-depth
registration and measured mounting TF remain unverified. Full native Jetson
supervisor failure/cleanup validation, aggregate storage overshoot characterization
and real resource measurements remain pending. Onboard accurate mapping: NOT
VERIFIED. GO for review/offline work; NO-GO for live activation until these inputs
and a separately approved bounded stationary procedure are ready.
