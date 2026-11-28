# Camera-path stationary CPU containment — 2026-10-04

## Scope

This change removes two proven payload costs without changing camera capture,
image quality, AI inference, safety thresholds, ROS interfaces, or motion
authority.

1. The camera driver continues to drain and process the Argus stream at the
   commissioned 1280×720, 10 FPS settings. It now materializes a raw ROS Image
   only while `/camera/image_raw` has a matched subscriber, and JPEG-encodes a
   compressed message only while `/camera/image_raw/compressed` has a matched
   subscriber.
2. The safety-status node used the annotated JPEG only as an AI-camera
   heartbeat. It now receives `/camera/detections/json`, produced on the same
   successful detector path immediately after the annotated image. Its
   2.5-second freshness boundary and all LiDAR/control logic are unchanged.

At 1280×720 BGR, avoiding an unused raw message prevents construction of
2,764,800 bytes per frame, or 27.648 MB/s at 10 FPS, before ROS copies. A newly
matched volatile subscriber may wait for the next camera tick, bounded by the
existing 100 ms period.

## Verification

- Four mocked camera-driver cases passed: no subscribers, raw only, compressed
  only, and both outputs with one shared stamp.
- Three safety-heartbeat regressions passed, including the unchanged
  fail-closed 2.5-second freshness boundary.
- Both changed Python files passed `py_compile`.
- The camera package rebuilt successfully on the Jetson.
- After a clean camera stop/start, `/camera.jpg` returned HTTP 200 with a fresh
  23,737-byte frame in 89 ms.
- Camera, safety-status, and sensor-recovery services were active with zero
  automatic restarts. Safety reported `READY: STOPPED`, velocity remained
  zero, steering remained 90°/90°, and the remote stop stayed latched.

During deployment, overlapping manual and bounded-recovery restarts briefly
left Argus reporting `No cameras available`. The recovery node was stopped,
the camera was allowed to release Argus fully, and services were then started
in camera-before-recovery order. This was a restart-order incident, not a
camera-driver regression; the fresh-frame gate passed afterward.

## Rollback

Jetson backups are stored under:

- `data/deploy_backups/20261004_camera_demand/`
- `data/deploy_backups/20261004_safety_json_heartbeat/`

Restore the backed-up file, rebuild `atlas_camera_driver` when rolling back
the driver, and restart only the affected user service while ATLAS is stopped.
