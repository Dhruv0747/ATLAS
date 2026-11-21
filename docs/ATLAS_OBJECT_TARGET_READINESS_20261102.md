# Object Detection / read-only Target Tracking — 2026-11-02

Backend offline integration READY; live installation/activation BLOCKED.

Reuse existing /api/vision3d/features and feature-report routes, four adapter/worker
files and vision_features UI assets. Existing viewer RGB cache only, no new driver
or ROS subscriptions. Worker imports TensorRTYOLO, not atlas_camera_tracker; no
publisher interfaces. Target IDs are image-space associations, not identity or 3D
tracking. Existing face/gesture/body/mapping blockers remain unchanged. Execution
configuration remains enabled=false. At most one 30s feature session, with separate
approved camera lease <=60s; no frame recording, only bounded local metadata.

Confirmed fix: feature guard previously accepted CPU exactly75 and RAM exactly80;
now strict below75/below80. Existing below70 temperature and all policy/telemetry
gates retained.21 focused guard/API/lifecycle checks PASS, including native synthetic
IPC and hung-worker termination; independent two-file review PASS. No live inference.

Read-only Jetson: existing YOLO engine matches
97cd66586901c75707164e912e609253d1e71705055248b9c83430c3421721df.
All three original rollback byte streams match current live files. Metadata
UID/GID/mode/mtime/xattrs captured privately with backup files. No live file changed.
Web PID2182 and Recovery PID2089 remain active with zero restarts. Recovery environment
has no ATLAS_RESTART_SNAPSHOT; /run/user/1000/atlas-restart-safety/state.json is absent.
No fresh independent observation through HTTP downtime can therefore be claimed.
M2 count change643->641 remains UNKNOWN; no tolerance or latch reset added.

## Prepared minimal payload, NOT an execution-ready installer

Private PC archive: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/vision-object-target-20261102.tar.gz
SHA256:0c5c9fa9e81d540d74231de8914d7a94808598668ebefb149bf3d3acddcf29b3
20 outer and16 inner manifest entries verified with Linux sha256sum.
Three replacements: atlas_vision3d_web.py, vision3d.html, vision3d.js.
Seven additions: four existing feature Python modules, disabled JSON configuration,
vision_features.js and vision_features.css. Main web script, installed mapping files,
Recovery, camera runtime, production drivers and monitoring are not payload targets.
Originals are under package/rollback; LIVE_ROLLBACK_METADATA.json records metadata.
Rollback restores only those three originals and removes only the seven added files
matching installed hashes. Any later owner edits must stop rollback for review.

The archived existing controller remains NOT executable: its REVIEW path targets
older staging, its adjacent bounded_process_cpu.py dependency is absent in that older
bundle, and independent producer runtime validation is still missing. Do not run
the standalone installer: it restarts web without the required external supervision.
No additional activation package or false GO is issued here.

Shortest safe next step: separately resolve the existing independent snapshot
producer runtime gate (no new ROS node), then finalize the existing controller's
staging/dependency pins. Web-only activation needs explicit approval. A separate
stationary camera-inspection approval is required after API activation/readiness;
no recording, mapping, servos, automatic retry, or other four-feature enablement.

Follow-up: staging/dependency binding is complete in ATLAS_WEB_BINDING_READY_20261102.md. The missing real Recovery snapshot remains the sole live activation gate; this supersedes the earlier packaging blocker, not the historical evidence.

## Offline acceptance — 2026-11-03

No camera, inference, Jetson access or service restart.

- **UI (browser): 21/21 PASS** with `tests/vision_features_ui_acceptance.cjs`. It runs headless Chromium
  against the existing preview fixture plus sample API data. Verified:
  - all six cards render, and face/gesture show NOT INSTALLED;
  - missing metrics show UNAVAILABLE, never 0;
  - Start is enabled only when the backend allows it, and face stays disabled even if the backend offers Start;
  - Manual PASS needs READY evidence (at least 2 frames and 1 detection);
  - the exact source timestamp is shown as a string;
  - an overlay appears only for a fresh, exactly matching RGB frame (stamped by the real frame path), with
    the text "2D only, distance UNAVAILABLE"; a mismatched frame shows no overlay;
  - when the backend fails, every card is UNAVAILABLE and Start is disabled;
  - only `/api/vision3d/*` was requested. The only POSTs were the operator's Start and the existing
    fail-safe camera-viewer stop on page hide.
- **Post-processing: 4/4 PASS.** The real `TensorRTYOLO.infer()` runs with the CUDA calls stubbed:
  - letterbox inverse at 640×480 and 1280×720 is exact;
  - the 0.45 confidence threshold, per-class NMS (same class suppressed, other class kept) and edge
    clamping all hold;
  - empty and degenerate outputs are handled.
  There are no real camera still images in the repository, so the model outputs are synthetic YOLOv8
  tensors. Real-image detection quality is still unverified.
- **Read-only tracking: 4/4 PASS.** Verified:
  - IDs persist across moving frames (IoU ≥ 0.3);
  - a jump or a class change gets a new ID, and two boxes never share one;
  - expiry is kept at exactly 1.0 s and expires after more than 1.0 s;
  - a frozen or regressed source frame raises an error, and a new session never resumes old IDs;
  - the track table is bounded at 100.
  The Lab's disconnect handling (worker exit or EOF, RGB older than 0.5 s, camera-session change, stale
  safety lease, 5 s model timeout → FAILED, optional worker killed, no resume) was reviewed and is
  covered by the existing lifecycle tests.
- **Command boundary: PASS.** The five feature modules have no rclpy, geometry_msgs, serial or Rosmaster
  imports, and their code has no publisher, cmd_vel, servo, pan-tilt, motor or navigation identifiers.
  The one exception is the guard *reading* the cached `cmd_vel` age to require fresh zero commands.
- The 21 existing feature tests still pass (30 Python checks in total).
- No product defect was found, and no product code changed.
- Known limitation: labels are COCO class numbers ("class 56"); there is no name table.

**Live activation stays BLOCKED** on the existing gate: the web restart needs independent supervision
from the Recovery snapshot producer, which is off by owner decision while its startup CPU risk is open.
After that come separate web-activation approval and a stationary camera-inspection approval.
