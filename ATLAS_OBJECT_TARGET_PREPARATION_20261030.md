# First Object Detection / read-only Target Tracking — repository preparation

GO for installation-only review; NO-GO for starting a live test before deployment
and fresh safety/compatibility checks. No Jetson deployment, camera activation,
model deserialization/inference, service restart or rover change occurred.

## Verified dependencies and input contract

Read-only Jetson inspection: TensorRT10.3.0, NumPy1.21.5, cv2 available (earlier apt
audit OpenCV4.5.4). Existing YOLO engine hash remains
`97cd66586901c75707164e912e609253d1e71705055248b9c83430c3421721df`.
Existing `trt_yolo_detector.py` hash:
`102ef486e37e671d6f0776ef2599a76ecc7df44f930df260eee6a1caaa97e6a9`.
Deployed stationary_gate.py hash:
`0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9`.

Live manifest declares `/astra/color/image_raw`, concurrent RGB320x240 rgb8,
private existing Astra runtime. Adapter accepts rgb8/bgr8 with checked dimensions,
stride and byte count; synthetic stride/channel-order tests PASS. Actual next RGB
frame and TensorRT engine loading remain untested under this adapter. No model
loading is hidden in the dependency audit. MediaPipe/ONNX Runtime remain unnecessary
for these two tests. No added camera driver or ROS subscriber.

## Improvements to existing candidate

* Only Object and Target may be admitted; Body/Face/Gesture/Mapping controls and
  server operations remain blocked. Global execution configuration stays false.
* Replaced missing onboard-mapping helper dependency with a small local guard
  reusing deployed stationary CPU/control-policy predicates. Required Orin thermal
  sources, recorder OFF and fresh stationary encoders are checked directly. Recorder
  systemctl timeout is now bounded to0.3s instead of legacy unbounded wait.
* Worker announces model readiness before parent captures an RGB frame. This avoids
  queuing an already-stale frame during engine startup.
* Parent performs one-second safety observations; frames require a fresh guard
  lease. Worker enforces its absolute local lease via SIGALRM, so a stalled parent
  guard cannot keep inference alive through continued frame submissions. Parent
  death also kills worker. Existing camera lease is never renewed by AI.
* At most30s/session and2Hz submissions. Startup timeout5s; inference/IPC bounded
  by remaining safety lease (<=2s). One worker at a time; no automatic retry.
* Read-only class/box/confidence output and session-local IoU track IDs. No servo,
  motor, TF or navigation publication. No metric distance without registration.
* Stop kills only the optional worker; guard failure preserves cause/evidence and
  closes IPC handles. Full completion remains READY until explicit manual verdict;
  no auto-PASS. Failed/incomplete/empty tests cannot be marked PASS.

Resource limits unchanged: CPU75%, RAM80%, temperature below70 C; E-STOP latched,
manual-only, commissioning off, zero commands, LIVE telemetry, recorder off and
stationary encoders. New inference CPU/GPU/RAM overhead is NOT MEASURED because
inference is not authorized. UI reports whole-Jetson values distinctly from worker
RSS/inference CPU time. Safety admission may reject even a compatible model.

## Focused validation

21 focused Python checks passed (13 adapter/API/evidence tests, 3 native lifecycle
tests, 5 guard checks). Native lifecycle uses a synthetic model and fake camera/
safety inputs only: complete session, operator stop, concurrent-start rejection,
safety abort, no orphan worker, report checksum and closed IPC handles. Native
worker tests include model-hash rejection, original timestamp preservation and
hung inference termination. No production service, device or domain involved.

Desktop1440px/mobile390px intercepted browser tests PASS: Object Start/Stop and
Target Start/Stop reach the matching API feature IDs; other four panels' controls
remain disabled, six panels present, no overflow or script errors. No actual
camera or inference request reaches a device. Earlier unchanged core tests reused.

## Exact-live targeted package

`prepare_object_target_lab.py` verifies current installed HTML hash
`6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57`, existing JS/backend
hashes, and builds only these three targeted candidates:

* vision3d.html: replace the marked static feature section with functional panels;
  preserve all other bytes including material.css and original camera controls.
* vision3d.js: add displayed RGB source-stamp metadata only, for matching overlays.
* atlas_vision3d_web.py: add feature status/command/report routes behind existing
  client/same-origin validation; no change to camera start/stop routes.

Seven additional files: four optional feature Python modules, disabled config,
feature CSS and feature JavaScript. Existing YOLO/model/stationary helper remain
unchanged dependencies. Package contains exact rollback copies and individual diffs.
Local package directory: sibling `object-target-review-final`.
SHA256SUMS hash:
`a75bbd94a2f6218be9170507ac1a1c6267cadcca03e401477a2bfb0373a086e1`.
No package files were copied to Jetson. Original static UI remains deployed.

## Next approval and rollback

First approve installation-only of reviewed backend/assets and exact-live patches,
with execution disabled. A rover-status-web reload/restart will be required to load
new Python routes; request that specifically, never restart protected ROS/controller
services. Reverify original hashes, backup existing three files and confirm new
file destinations do not overwrite unrelated files. Validate disabled controls,
camera OFF, service identities and rollback before enabling a test.

Then separately approve ONE stationary RGB camera session and30s Object test
after fresh stopped/resource checks, model/dependency hashes and existing viewer
heartbeat. The camera must have enough remaining lease/session time; no implicit
camera start. Test Target separately after Object passes. Abort immediately on a
guard/model/input failure, preserve metadata and do not retry automatically.

Rollback: stop only optional feature processing, restore the three exact-byte
backups, remove only newly installed candidate files, and perform only an explicitly
approved web reload if necessary. Preserve private local reports. Never reset the
camera, touch production TF or restore unrelated services/configuration.

Intended URL remains http://192.168.1.16:8088/v2/vision3d . These functional adapters
are NOT deployed there yet; the currently visible panels remain static/disabled.
