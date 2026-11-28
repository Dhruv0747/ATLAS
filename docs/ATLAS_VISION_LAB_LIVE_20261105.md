# 3D Vision Lab: Object Detection + Target Tracking live (2026-11-04/05)

Owner-approved, stationary rover, E-STOP latched throughout. This branch records the exact bytes now
running on the Jetson. It is based on `codex/status-cache-nonblocking-20261104`.

## Result

| Feature | How it ran | Result |
|---|---|---|
| Object Detection | Scripted 30 s test | READY: 45 frames, 1.6 fps, 29 ms inference, 0 detections |
| Target Tracking | Scripted 30 s test | READY: 46 frames, 1.6 fps, 29 ms inference, 0 detections |
| Object Detection | **From the 3D Vision Lab page** | READY: 26 frames, 0.9 fps, **person detected at 80 %** |

Resources during tests: CPU 59–68 % (limit 75), RAM 53–63 % (limit 80), max 66.8 °C (limit 70),
worker RSS about 310 MiB, `cmd_vel` zero, encoders unchanged. Manual PASS is **not** pressed; it remains the
operator's decision. Face, Gesture, Body and RGB-D Mapping remain blocked (no models / no calibration).

## Live files (SHA256 on the Jetson)

| File | SHA256 |
|---|---|
| `project_atlas/scripts/atlas_vision3d_web.py` | `993852ced9a27bf502e7fd879c82ce8abbba77d67da329fa4467d8ae501cc772` |
| `project_atlas/scripts/atlas_vision_cache_only.py` | `b693798b938cd5bdc96b58e8f20ef2936b208bed4b28f87f41b35911f38c673a` |
| `project_atlas/web/v2/vision3d.html` | `f5a7ed53e434b12d3ecffbeea49f53f89348b4f9559948bf64477ab49ff66d2f` |
| `project_atlas/web/v2/vision_features.js` | `5aec1bcfed3e4b48ba3b06c023225e493a94712158d1a1c0a6788929f2c316ed` |
| `project_atlas/web/v2/vision_features.css` | `be7358fdb3573215c90791d42c58c23662608a9ca95ab0c1bdf1d0dacca47bf2` (unchanged) |
| staged `scripts/atlas_vision_feature_lab.py` | `cf9853ca81fb0eea1d82ddf9373932c8cfa89399b44906b8ca234ce3bbfa7b72` |
| staged `scripts/atlas_vision_feature_worker.py` | `2dbd27bbd93b4ba60cd1198e94b1f3fa32ed51615fc2976435ddc9ab7ad8e158` |
| staged `config/vision_feature_lab.json` | `38308918b8d7a3f64a879306b5769832f1b8efa0c982fe7ba1e879bc6bb09edd` |

"Staged" means the `atlas-vision-lab-host` service runs these from
`~/project-atlas-migration/vision-host-inactive-0855063-20261104/project_atlas/`, not from `~/project_atlas`.
The live `trt_yolo_detector.py` and `tools/vision3d/stationary_gate.py` were **not** replaced.

## What changed and why

1. **Web route (`atlas_vision3d_web.py`)**: `cached-rgb` (local-only, from candidate 02125b9), plus
   `/api/vision3d/features` and `/feature-report`. These forward to the host's private Unix socket. POST keeps
   the existing same-origin check (verified: no Origin gives 403). When the host is idle, GET reports Object and
   Target as startable. Start launches `atlas-vision-lab-host` and refuses if `atlas-foxglove` is off.
2. **Frame age 0.5 s to 1.0 s (`atlas_vision_cache_only.py`, worker)**; post-inference age 1.0 s to 1.5 s.
   Measured Astra frames are already 221–496 ms old when they reach the cache (bridge + web refresh), so 0.5 s
   was rarely met.
3. **Worker stdout is JSON-only**: TensorRT printed
   `Using an engine plan file across different models of devices...` to stdout, which broke IPC.
   fd 1 now goes to stderr; JSON goes through a private copy of stdout.
4. **Worker timers cleared after startup and after each answered frame**: the per-frame `alarm`/`setitimer`
   kept running while the worker was idle and killed it when frames arrived about 1 s apart (page use).
5. **Late frames skipped, not fatal (`atlas_vision_feature_lab.py`)**: in both the inference thread and the
   1 s supervision loop. A test still fails if there is no good frame for 3 s. A stale safety lease, a camera
   identity change and worker errors still abort immediately.
6. **Page panel**: the static "UI PREPARATION ONLY" block is replaced by the live panel
   (`vision_features.js`). The page keeps `/api/status` warm from Start until the test ends, because the guard
   fails closed on the status cache's empty first read after idle. The guard itself is unchanged.
7. **Config**: `enabled: true` in the staged `vision_feature_lab.json`.

`rover-status-web` was restarted three times. Each time the stationary gate passed before and after, and
`atlas-camera`, `rover-base-telemetry`, `atlas-cmd-vel-mux`, `atlas-ekf`, `atlas-localization` and
`atlas-lidar` kept the same PIDs and restart counts.

## Running a test from the page

1. `systemctl --user start atlas-foxglove`. It is disabled at boot and carries all Astra frames to the web
   server. It listens on `0.0.0.0:8765`, so see the Foxglove hardening plan.
2. `systemctl --user stop atlas-voice-companion atlas-localization-monitor`. Without this, model load pushes
   CPU over 75 % and the guard stops the test (observed 75.5 %).
3. On `/v2/vision3d` choose **Infrared + RGB**, then **Start 60-second view**, then **Start Test** (30 s).
4. Afterwards: stop `atlas-foxglove` and start the two paused services again.

## Open items

- Rebuild `yolov8n_fp16.engine` on this Jetson (`trtexec`); TensorRT warns it was built on another device model.
- Idle-host hint text still says "Depth + RGB"; it should say "Infrared + RGB". Fix on the next web restart.
- A CPU budget for vision on top of the always-on stack, for example by retiring unused shadow services, so step 2
  is not needed.
- `atlas-vision-lab-host` has `RuntimeMaxSec=120`. Reports stay on disk, but the download link only works while
  the host is up.

## Rollback

Backups are in `~/project-atlas-migration/vision-install-backup-20261104-234224/` on the Jetson. To roll back,
restore `atlas_vision3d_web.py` (original `2551d657…`), remove `atlas_vision_cache_only.py`, restore
`vision3d.html.placeholder`, delete `vision_features.js`/`.css` from `web/v2`, then restart only
`rover-status-web` with E-STOP latched.
