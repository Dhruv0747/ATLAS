# Existing Vision Lab: six-feature integration candidate

Repository-only continuation of 689935d / 5194d05. No camera, inference model,
package install, servo command, TF publication or rover restart was activated.

## Implemented and reused

The existing `/v2/vision3d` page gains six panels, separate bounded Start/Stop,
manual PASS/FAIL and downloadable local JSON reports. Existing white-glass preview,
viewer controls and E-STOP remain in place. New API routes live under the existing
same-origin/client-allowed handler. GET feature status does not renew a camera lease.

New read-only adapters reuse `trt_yolo_detector.TensorRTYOLO` and the existing
VisionService RGB message cache. There are no new image subscribers, camera drivers,
ROS publishers or servo interfaces. A separate optional process owns the model and
is terminated to release its CUDA allocations; no changes to the working annotator.

| Panel | Implementation / actual status |
|---|---|
| Face Recognition | NOT INSTALLED: identity model/gallery/enrollment/deletion backend absent. Controls disabled; no biometric data collected. Haar face detection is not identity recognition. |
| Gesture Recognition | NOT INSTALLED: missing validated hand/gesture model/runtime. |
| Human Body Tracking | Person-class box tracking adapter implemented. NOT skeletal pose. UNAVAILABLE until approved runtime admission; no hardware verification. |
| Target Tracking | Class-aware 2D IoU tracks, expiring after one second; session-local IDs, not persistent identities. No pan-tilt commands. |
| Object Detection | Existing TensorRT YOLO adapter, confidence/class/boxes and original timestamps. No depth distance without validated registration. |
| RGB-D Mapping | Links local map viewer; Lab Start remains UNAVAILABLE pending calibration/registration/TF and approved onboard mapping runtime. Diagnostic distance preview is not mapping validation. |

Default `vision_feature_lab.json` is disabled. Installing code does not start any
test. READY means a bounded test completed; PHYSICALLY VERIFIED additionally requires
operator PASS, at least two processed real input frames and a detection. A failed,
interrupted or empty test cannot receive PASS. Reports are scoped to that test,
not a global certification of geometry, identity accuracy or reliability.

## Actual read-only Jetson dependency audit

* TensorRT Python 10.3.0; `python3-libnvinfer` 10.3.0.30-1+cuda12.5.
* Apt `python3-opencv:arm64` 4.5.4+dfsg-9ubuntu4; NumPy 1.21.5.
* MediaPipe and ONNX Runtime not found in the inspected Python distribution metadata.
  This is not an exhaustive search of every alternate virtual environment.
* Existing `/home/jetson/project_atlas/scripts/yolov8n_fp16.engine` SHA256:
  `97cd66586901c75707164e912e609253d1e71705055248b9c83430c3421721df`.
* No engine deserialization, inference, camera activation or ROS discovery was run.
  Existing reviewed topic manifest/cache is reused rather than probing new streams.

## Bounds, evidence and safety

One feature at a time; 30 seconds, maximum 2 Hz submissions. No automatic retries.
Fresh existing camera identity and RGB required. Original integer source stamps
are preserved, with an exact decimal string for browser display. RGB admission
500 ms; result deadline one second. Repeated frames are not processed twice.

Existing stationary `observe`/`safety` helpers enforce one-second CPU observations,
CPU <75%, RAM <80%, temperature <70 C, latched E-STOP, manual-only, commissioning
off, recording off, LIVE telemetry, zero commands and stationary encoders. The
camera's existing lease remains independently authoritative and is NOT renewed
by feature processing. Camera expiry stops the optional test; no camera restart.

The optional worker has Linux parent-death SIGKILL, five-second model-load deadline,
two-second IPC/inference alarm and 60-second defensive internal deadline. Parent
guard kills on failure. Whole-system RAM remains guarded; no GPU-specific memory
quota or measured safe concurrency is claimed. One optional process may still
compete with existing AI processes: a live headroom measurement is required.

Evidence: metadata/boxes/resources only, no saved RGB images or biometric templates.
Local `~/.local/share/atlas/vision-tests`, private directory/files, atomic replace,
SHA256, max 128 KiB/report, 100 reports/8 MiB admission quota. No automatic deletion.
After web restart reports reload; interrupted RUNNING state becomes FAILED without
resume. Reports are downloadable through the protected local dashboard. No cloud.

Overlays are drawn ONLY when displayed RGB and detection timestamps match and the
result is fresh. Otherwise UI explicitly says overlay unavailable. This may yield
intermittent overlays at mismatched display/inference rates; not tested on Astra.
Source dimensions, confidence and worker RSS/inference CPU time are shown where
available. Whole-Jetson CPU/RAM are clearly distinguished from per-worker metrics.

## Focused evidence

* 13 new tests PASS: RGB stride/channel order/staleness, malformed detections,
  person filtering, track identity/expiry, disabled config, concurrency rejection,
  PASS rejection, quotas/hash integrity, interrupted recovery, no-touch API,
  same-origin rejection, guarded no-launch, stop, native IPC and native hung-
  inference SIGALRM termination. Native tests use a synthetic model stub only.
* 37 existing Vision Lab core/web tests PASS; no unrelated suites repeated.
* JavaScript syntax checks PASS.
* Actual browser at `http://127.0.0.1:8770/v2/vision3d`: six panels visible, truthful
  NOT INSTALLED/UNAVAILABLE and unknown metrics, disabled controls, original
  preview/white-glass layout present. Local fixture only, not a Jetson deployment.
* Actual new Jetson CPU/RAM/GPU overhead: NOT MEASURED. Start with one <=2 Hz
  optional model, benchmark within existing limits. No six-model concurrency claim.

## Minimal deployment preparation and decision

New files: three feature Python modules, disabled JSON config, CSS/JS assets.
Targeted edits only: `atlas_vision3d_web.py` (two routes), `vision3d.html` (section),
`vision3d.js` (source-stamp attribute). Existing reviewed onboard guard helpers are
dependencies and must be hash-verified before enabling execution; do not blindly
replace live helper/server files. The mapping viewer comes from prior commits.

Before installation compare fresh live file hashes and apply only these hunks to
the actual live baseline. Back up originals, verify restoration hashes, validate
routes offline. A Python web-module reload may require `rover-status-web` restart:
that needs separate explicit approval. No protected ROS/controller restart needed.
Rollback restores only touched files/assets/config and stops only optional child
processing; camera/runtime controls and original services stay unchanged.

GO for controlled **disabled UI deployment review**, subject to live baseline and
dependency hashes. NO-GO for enabling inference yet: first validate guard/worker
lifecycle under the exact deployed environment, then obtain separate stationary
RGB camera/test approval. Face, gesture, skeletal pose and mapping activation are
still blocked as listed above. Intended Jetson URL remains
`http://192.168.1.16:8088/v2/vision3d`; new panels are NOT yet live at that address.
