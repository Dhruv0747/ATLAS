# Astra standalone vision audit and integration candidate

Status: repository preparation only. No camera activation, live installation,
rover restart, movement or pan-tilt command was performed. No six-feature hardware
success is claimed. Continues mapping baseline `4c252de`.

## Existing capabilities and gaps

| Capability | Repository evidence | Additional work / hardware verdict |
|---|---|---|
| Face recognition | `atlas_camera_tracker.py` uses Haar face detection | No identity recognition demonstrated. Add opt-in local gallery and identity model; Astra validation pending. |
| Gesture recognition | Dashboard `AI_MODES` includes gesture, but response says staged preview | No verified hand landmarks or gesture classifier. ARM64 runtime/model validation required. |
| Human body tracking | Existing person detections can guide camera centering | Not skeletal body tracking or persistent person IDs. Pose model and tracking validation required. |
| Target tracking | Existing tracker centers faces/person boxes | Publishes servo commands; MUST NOT enable for this integration. New read-only tracking IDs/depth association first. |
| Object detection | `ai_annotator_node.py`, `trt_yolo_detector.py`, dashboard inference use local TensorRT YOLO | Existing topics are `/camera/...`, not verified Astra input. Engine compatibility and real Astra inference pending. |
| RGB-D mapping | Existing Astra distance/diagnostic preview; isolated RTAB-Map and new onboard candidate | No real Astra-to-RTAB-Map reconstruction demonstrated. Registration, calibration, mounting TF and native Jetson validation blocked. |

Existing camera tracker publishes `/camera/bottom_servo_cmd_us` and
`/camera/second_servo_cmd_us`. Its automatic following is not approved. The
annotator's delayed auto-enable and dashboard's separate inference path must not
be carried into the new optional pipeline broker. Potential duplicate inference
exists in code; concurrent runtime duplication has NOT been established.

## Smallest integration design

Use one existing Astra producer, one shared decode/preprocessing path and latest-
frame bounded queues. Retain original stamps, encodings and calibration metadata.
Run local inference only on selected frames; reuse detections for target tracking.
Do not duplicate camera drivers or change production `/tf` ownership. Publish
vision results in an isolated namespace/domain through explicit allowlists.

`config/astra_features.json` is disabled by default. `feature_policy.py` is an
OFFLINE admission model, not a runtime launcher. Tests prove default selection,
priority, invalid observations, resource boundaries and consent decisions. A
future runtime must implement unloading, cancellation, guard supervision and
resource accounting before these toggles can control hardware.

Mapping and obstacle awareness have priority. One optional inference pipeline at
a time initially; shed optional work on mapping backlog and stop on safety failure.
Existing local one-second safety supervision remains authoritative. No Windows,
cloud API, Grafana availability or internet dependency is permitted at runtime.

Face identification is last: explicit enrollment consent, local-only private
storage, identity listing/deletion, deletion of templates and original images,
retention policy and backup deletion semantics must be implemented and tested
before enrollment. No gallery or biometric data was created in this work.

## Dependencies and planning budgets (not measured Jetson performance)

* Reuse the existing JetPack-compatible TensorRT YOLO nano engine first. Verify
  engine hash, TensorRT/CUDA versions and license; engines are not portable across
  arbitrary builds. Do not install a second inference stack unnecessarily.
* Lightweight box association/Kalman tracking can reuse detections without another
  neural model. Metric target position still requires validated depth/registration.
* Body pose/hand gestures require separately licensed models and ARM64 inference
  validation. MediaPipe Linux/Raspberry Pi support is not proof of a supported
  Jetson wheel or GPU implementation.
* OpenCV YuNet/SFace are candidate face detection/identification models, not built-in
  Astra features. Verify OpenCV API support, model provenance and local benchmarks.
* Initial optional inference target: 2–5 Hz object/pose/gesture, ~1 Hz face identity;
  rates are proposals, not demonstrated throughput. Use detection reuse for tracking.
* Mapping trial memory target 512 MiB, hard cgroup cap 768 MiB; optional candidate
  allowance 256–512 MiB only after measurement. Shared GPU memory counts toward 8 GB.
  No claim all six pipelines fit concurrently. CPU <75%, RAM <80%, temperature <70 C
  remain mandatory for this stationary design. Historical parked CPU ~60–63% leaves
  little headroom; estimates cannot authorize activation.

Official compatibility references:
https://docs.opencv.org/4.13.0/d0/dd4/tutorial_dnn_face.html
https://developers.google.com/edge/mediapipe/solutions/setup_python
https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html
https://developer.nvidia.com/tensorRT

## Safest order and approvals

1. Finish metadata/registration/TF checks using existing evidence; keep camera pose
   fixed. A pan-tilt mount requires measured dynamic joint transforms before moving.
2. Separately approved bounded stationary Astra input + onboard mapping validation.
3. Read-only object detection and obstacle awareness; benchmark shared preprocessing.
4. Read-only target IDs, then body/gesture candidates one at a time.
5. Opt-in face identification after privacy controls and accuracy tests.
6. Pan-tilt following only after separate actuator safety approval.

GO for further offline implementation; NO-GO for live six-feature activation.
See `ATLAS_ONBOARD_MAPPING_IMPLEMENTATION_20261030.md` for mapping evidence and limits.
