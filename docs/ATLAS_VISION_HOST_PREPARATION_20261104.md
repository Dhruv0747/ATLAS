# Vision Lab primary task / Neural trial closure — 2026-11-04

## Recorded outcome (not a new test)

Neural is **PARTIAL LIVE**: two paths (ultrasonic and camera-info) showed
directional displacement with fresh positive traffic. Continuous coverage is not
achieved. The owner accepted the single PC-only trial and browser reconnection.
The ATLAS-only Prometheus scrape interval remains 3 seconds; timeout remains
3 seconds. All other scrape settings and all visualization freshness limits stay
unchanged. No exporter restart or collection change is part of this task.

Two-minute trial: 39/39 scrapes UP, 215 samples each; Jetson peaks CPU 62.51%, RAM
58.90%, temperature 63.75 C. These are recorded observations, not a continuous
safety guarantee. Existing 15-second exporter cache optimization is a separate
follow-up, not a prerequisite for Vision development. Never animate stale data.

PC exact-byte configuration backup:
`C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/pulse-freshness-20261104/prometheus.exact-original.yml`

- Original SHA256: `9796b57f954f24f62df39046a114bf136f853eec02190d52add8ef90f73f083d`
- Installed candidate SHA256: `e016e614d27981b91b5955edae269583e1f2ebc33d2497667cc8223542774604`
- Live WSL path: `/opt/atlas-monitoring/prometheus.yml`.
- Keep backup private and outside Git. Rollback, if separately needed, must copy
  exact bytes in place (bind-mounted inode), preserve metadata, validate with
  existing promtool, then reload Prometheus. No rollback performed here.

## Primary development: Object Detection and read-only Target Tracking

Baseline: handover `95fe413`, existing offline acceptance `562d52d`.
Reuse `atlas_vision_feature_lab.py`, `atlas_vision_feature_worker.py`,
`atlas_vision_features.py`, `atlas_vision_feature_guard.py`, and the existing
six-panel UI. Never import the older servo-commanding tracker.
All processing, evidence storage and inference must remain on Jetson.
No Recovery snapshot, Mux/Yahboom upgrade or monitoring work is in scope.

### Confirmed integration differences from the handover proposal

1. `Lab.run()` imports `atlas_vision3d_runtime.SESSION` and reads a local viewer
   object. An independent process cannot reuse that camera/cache identity as-is.
   Introduce one injected frame/session provider, retaining the existing local
   provider for compatibility. Do not copy the worker or tracking implementation.
2. Existing GET `/api/vision3d/frame?kind=rgb` preserves `X-Source-Stamp`, but
   first calls `svc.touch()`. `VisionService.touch()` can create/start the viewer
   transport when absent and renews the camera lease. Therefore this endpoint is
   **not a guaranteed passive cache-only interface**. Merely polling it at 2 Hz
   does not prove the no-new-participant requirement.
3. `/api/vision3d/summary` explicitly avoids touching the lease, but lacks the
   exact driver PID/start identity needed by the existing Lab. `/status` exposes
   runtime identity but also passes through `touch()`.
4. A separate HTTP port is a separate origin. Dashboard authentication/access
   controls cannot be assumed to carry over to it. Public/LAN binding is not
   approved by this preparation.

## Minimal deployment design (not an executable installation package)

Prepare these bounded changes only:

- Existing camera Web adapter: add a cache-only RGB/identity read under the
  existing lock. Never call `touch()`, start a transport, import/create a ROS node,
  renew a lease or start a camera. Return unavailable if the existing transport,
  approved session identity, cached PNG or original timestamp is absent/stale.
  Use the timestamp belonging to the returned cached frame, not a newer message
  or HTTP receipt time. Preserve the existing 0.5-second frame gate.
- Existing Lab: inject that provider into the current lifecycle, keeping the
  worker, strict resource guard, metadata quota, manual verdicts and read-only
  tracker. Poll only during one approved session, maximum 2 Hz. Stop on changed
  camera identity, expired frame, Web failure or guard failure. No background
  frame polling at startup or while idle.
- Separate host: reuse the existing feature API/UI contract; launch with no
  rclpy/ROS imports, no camera control endpoints and no actuator publishers.
  Default execution disabled. Bind loopback until an authenticated access path
  is reviewed. Do not install an unrestricted proxy to Dashboard control routes.
- No edits to Recovery, Mux, Yahboom, exporter, monitoring or camera drivers.
  All other four features remain unavailable.

The existing safety reader may use Dashboard `/api/status` because this design
does not require Dashboard downtime during inference. If Web is unavailable,
stop the owned inference worker; never turn missing evidence into healthy data.
Do not claim this provides independent supervision of a Web restart.

## Installation and rollback preparation

Use a versioned, inactive Jetson directory for the separate host/worker/config/UI;
do not overwrite production scripts or enable autostart. Hash-pin all included
dependencies and the existing TensorRT engine. Record Python/Pillow/NumPy and
TensorRT compatibility before installation; do not install dependencies blindly.

For the cache-only Web addition, first reconcile the small patch with exact live
bytes. Preserve a verified byte-for-byte backup plus mode/owner and original
hash. Never replace the deployed Web adapter with the generic repository copy.
This addition requires its own reviewed deployment/reload path; do not restart
Web under the independent inference host's guard.

Rollback must stop only the newly owned feature host/worker, restore any approved
replacement from verified bytes, remove only recorded additions, and leave all
existing services/configuration untouched. Any required Web restoration/restart
needs its own supervision and authorization. No automatic restart or retry.

Focused future acceptance is limited to the new boundary: no transport/lease
side effects; source timestamp and cache-frame matching; missing/stale/changed
identity rejection; HTTP outage cleanup; disabled startup; bounded polling and
session timeout; authenticated access. Reuse earlier worker/UI green results
when unchanged. No completed suite was repeated for this preparation.

## Exact live gate

**Deployment NO-GO today:** the passive cache boundary and independent host/API
binding are not yet implemented/reviewed; exact live-file reconciliation and
rollback for the new boundary are not yet prepared. Do not label the old
three-replacement, Web-restarting package as the new independent deployment.

After offline completion, request separate installation/host-start approval.
Camera/inference requires another explicit stationary session approval, at most
60 seconds including camera startup and at most 30 seconds per feature test.
Immediately before it: E-STOP latched, zero commands, stable encoders, fresh
telemetry, CPU <75%, RAM <80%, temperature <70 C, validated engine and existing
camera shutdown. No motors, servos, recording or mapping. Live model accuracy
and whole-Jetson inference overhead remain unverified.
