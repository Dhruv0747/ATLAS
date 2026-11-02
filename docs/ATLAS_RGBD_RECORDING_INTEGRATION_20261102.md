# Existing-session RGB-D recording integration

Offline binding PASS; deployment/capture NO-GO until the remaining host providers
and calibration are verified. No hardware capture, deployment or restart occurred.

## Implemented

rgbd_recording.existing_binding(observer, context) obtains the existing web-process
SESSION and SERVICE; no separate controller, driver, ROS context or subscription.
Recording.run(..., approved=True) is single-use and refuses an already-owned
camera/transport. It uses existing concurrent-mode admission, lease and cleanup.
It polls original immutable cached ROS messages, waits for all four advancing
stamps within30ms, and reuses calibration_capture.Supervisor and Evidence.

Capture limit60s includes pre-start work. Missing bundle10s, stale delivery1s,
image age500ms, original timestamps/dimensions/encoding/CameraInfo and independent
calibration document checks remain fail-closed. Existing observer must provide
fresh one-second CPU<75/RAM<80/temp<70, E-STOP/manual-only/zero/stationary data.
No defaults substitute for missing observers or context providers.

Context provider must return ORIGINAL TFMessage tf/tf_static, Odometry odom and
LaserScan scan from existing caches. Local tf2 Buffer checks transforms at image
and scan timestamps, finite transforms/unit quaternions, odom/base frame identity
and dynamic freshness. It creates no ROS node/listener/publisher. Context is CDR
serialized unchanged alongside image messages. Invalid or missing input aborts.

## Format and storage

capture.sqlite retains original CDR, per-message SHA256, integer source stamps,
separate receipt timestamps, full CameraInfo CDR and metadata. No image restamping
or calibration inference. TFMessage original per-transform timestamps remain in
CDR; its envelope explicitly uses receipt time because TFMessage has no header.

After verified shutdown only, export_bag(session_dir) creates replay.db3 with
standard rosbag2 topics/messages tables and original CDR/receipt timestamps.
TF-static metadata retains transient-local durability. It rejects failed captures,
modified DB/message checksums, missing streams, existing conversion output and low
free disk. Failed conversion retains diagnostics and cannot overwrite/retry itself.
Native Humble SequentialReader and existing astra_replay.validate_recorded_bundles
accept the tested output. This proves format compatibility, not real calibration
or RTAB-Map reconstruction. Existing replay admission still rejects unregistered
geometry, unverified scale/TF and missing mapping inputs.

Evidence DB128MiB and converted DB128MiB page limits. Journals can add another
DB-sized allocation; reserve at least1GiB and plan512MiB for the whole transaction.
No new frame cache, unbounded queue, map deletion or unlimited retention introduced.
The existing onboard map DB quotas/viewer remain unchanged.

## Cleanup

At timeout/safety/input/storage failure, stop only the owned controller child.
Require matching worker PID, driver_stopped/cloud_stopped confirmations and absent
worker/driver/cloud process groups. Worker exit alone is NOT shutdown proof.
Changed ownership refuses stop. Cleanup failure marks ABORTED and preserves
result.json and checksums. Existing controller stop has bounded6+3+2s waits;
these are cleanup time after the60s capture window, not extra capture time.
Existing worker lease/death protection remains the crash fallback. Actual host
integration must independently bound provider calls and prove lease expiry when
its recording thread stalls; tests with injected providers do not prove that.

## Exact deployment/rollback scope (not executed)

1. Build existing review-only package with build_onboard_package.py OUTPUT. Review
   SHA256SUMS. This only copies source; it never connects to Jetson.
2. Before any installation, compare exact live runtime/web modules and helper
   dependencies. Back up affected helper files byte-for-byte and hash the backup.
3. Install only rgbd_recording.py plus reviewed missing helper dependencies under
   /home/jetson/project_atlas/tools/vision3d. No changes to current driver/runtime,
   production topics/TF, launch configuration or existing viewer controls.
4. No HTTP route or button has been enabled. The existing web process must supply
   verified bounded observer/context cache callables before calling existing_binding.
   A new web process must NEVER be launched to import a second SESSION. Do not
   enable any route until reviewed exact-live binding and independent deadline
   enforcement are available. Any web restart needs separate approval.
5. Installation rollback: restore only backed-up helper bytes; remove only new
   approved helper files if absent beforehand. No service restart or fault reset.
   Preserve all recording/evidence directories. Runtime rollback is owned-session
   stop and verified process shutdown, never an automatic camera retry.

## Remaining blockers / approval

Actual Astra factory calibration remains invalid, registration disabled and
camera mounting TF unverified (read-only inventory in f32385f). Existing host
safety/context provider availability and maximum call duration are not verified.
Thus this is completed offline composition, NOT an executable live deployment.
No capture approval requested until these concrete prerequisites pass. No real
Astra RGB-D recording or new map has been produced. Windows/WSL is used only for
these tests; all module paths, storage and eventual execution belong on Jetson.

Focused validation: 20 tests PASS using native ROS Humble serialization/rosbag reader and fake controller/cache. Includes staggered unequal-resolution frames, missing inputs/TF/calibration, exact CPU boundary, interruption, storage failure, checksum tampering, single-use deadline and driver/transport cleanup failure. Independent review passed the geometry, synchronization and shutdown-evidence corrections. Conversion page-size refinement separately rechecked with the native bag test.
