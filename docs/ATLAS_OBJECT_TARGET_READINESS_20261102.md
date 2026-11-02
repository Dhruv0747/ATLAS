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
