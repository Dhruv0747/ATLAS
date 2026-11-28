# Independent Vision host — offline result, 2026-11-04

Neural remains PARTIAL LIVE; the successful 3-second scrape and its rollback are
unchanged. No monitoring work or service changes occurred in this task.

## Implemented

- `atlas_vision_cache_only.py`: reads only an already-rendered RGB PNG and its
  original message timestamp/receipt timestamp under the existing cache lock.
  Rejects missing/inactive/disconnected/stale/future data and camera identities.
- `atlas_vision3d_web.py`: additive local-only `GET /api/vision3d/cached-rgb`,
  before any lease/touch path. No conversion, new subscriber, transport start,
  camera activation or lease renewal. Existing rendering records the receipt
  time belonging to the cached message, not a later message's receipt time.
- Existing `Lab` accepts an injected frame provider, avoiding camera-runtime
  imports in the independent process. Reuses the same worker, detector, tracker,
  reports, manual verdicts and resource guard. Independent sessions include
  admission/startup in their maximum 30 seconds; no automatic retry.
- Local client preserves timestamp provenance, has a 0.5-second total network
  deadline and cancellation, rejects redirects, bounds payload/dimensions,
  and rejects changed session identity. Maximum four cache HTTP reads/second
  accommodates guard and worker readers; inference remains at most 2 Hz.
  The previous proposed 2 Hz HTTP budget is superseded here, not silently assumed.
- Independent API reuses the six-card JS/CSS, Object/Target only. Face, Gesture,
  Body and Mapping remain unavailable. No camera/control/proxy endpoints exist.
  This metadata UI does not yet display an image overlay: it has no camera lease
  control or frame-polling loop, and does not substitute another frame as a match.

## Authentication and bounded host

Actual read-only live inspection found Dashboard uses private/LAN/Tailscale IP
filtering, not user login cookies. Such filtering is not claimed as authentication.
The new host reuses existing Jetson SSH authentication: no TCP listener, only a
0700 owner directory and 0600 Unix socket, with Linux SO_PEERCRED UID checking.
Unauthenticated remote browsers cannot reach it; the authenticated SSH user can
forward it locally. Same-host processes under that same trusted Unix account are
within the trust boundary. No new credentials or public access are introduced.

After separate activation approval, the intended access command is:

```sh
ssh -N -L 127.0.0.1:8099:/run/user/1000/atlas-vision-lab-host/host.sock jetson@192.168.1.16
```

Open `http://localhost:8099/`. The existing trusted SSH key/agent is used; no
passwords or private keys belong in the package. Windows is an optional browser
client, not a processing, mapping, safety or storage dependency.

The API requires the exact Host and same-origin POST/custom header, limits bodies
to 512 bytes, eight requests/second, a four-connection backlog, 0.75-second request
deadline and bounded responses. The service template has Restart=no, no boot
enablement, 120-second first-validation runtime, five-second systemd stop bound,
512 MiB group memory limit and 16-task limit. These resource bounds have NOT been
validated with the real TensorRT engine. Existing CPU <75%, RAM <80%, temperature
<70 C admission/continuous checks remain; CPUQuota is not falsely presented as
effective on the Jetson user manager.

## Focused evidence

15 new boundary/lifecycle tests passed on WSL Python with Pillow/NumPy. Includes
passive route behavior, original timestamps, missing/stale/future/disconnected
cache, identity validity, interleaved cache-age handling, slow-response deadline,
cancellation, Unix peer rejection, Host/CSRF, request size/rate limits, no control
routes, provider cleanup before worker launch, synthetic worker completion and
safety-abort cleanup. The existing lifecycle harness was reused for the NEW
provider branch only; previously completed detection/tracking suites were not run.

Independent review passed after correcting receipt-based cache reuse and the
HTTP inactivity-only timeout. No camera, model, native inference or ROS node ran.
Jetson CPU/inference overhead remains UNKNOWN, not inferred from offline tests.

## Exact-byte rollback and deployment limit

Live Dashboard remained ACTIVE, PID 2077, NRestarts=0 during this read-only task.
Read original Web adapter SHA256:
`2551d6578aa9429ac8f4fd5ff35f2c16a185c3cd027fafc563b7fff339857190`.
Original metadata: mode0644, uid1000, gid1000, size24861, mtime1792903589.
Private exact-byte backup:
`C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/vision-host-20261104/original_atlas_vision3d_web.py`.
It is excluded from Git. The candidate must be patched from these exact bytes,
not replaced by the generic repository Web file. Recheck drift before installation.

Minimal installation-only transaction: verify package and live-original hashes;
copy the versioned host directory inactive; retain its disabled config; retain
the small exact-live Web candidate beside the backup, NOT over the running file;
verify all hashes/modes. Do not install/enable/start the unit or alter production
imports. Rollback removes only recorded inactive additions. Production rollback
bytes are ready if a later approved replacement is needed; restore0644/1000/1000
and the recorded original timestamp. No automatic restoration restart.

**Runtime deployment remains BLOCKED under the no-Dashboard-restart restriction.**
The cache is process-local and the running process lacks the new endpoint.
Copying a Python file does not update its loaded module. There is no verified
hot-load mechanism; process injection/reload hacks are not an acceptable bypass.
An inactive package can be installed without a restart, but cannot make inference
operational. A separately reviewed safe Web load/restart window (or an independently
verified existing passive export, not currently found) is required before host
activation. Do not reopen Recovery/Mux work as an implied prerequisite.

After that gate, approval must separately cover the bounded new-host start and
then a stationary camera/inference session: maximum60 seconds including camera
startup, maximum30 seconds per feature, fresh safety admission, no recording,
movement or servos, and verified existing camera shutdown. No features are LIVE.

## Prepared inactive archive

`C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/vision-host-20261104/vision-host-inactive-20261104.tar.gz`

SHA256: `9c1cd41e12253d67c3291acdaa6035772786bdb11f91d0e4a82f4cf92f0a1ba6`.
Linux extraction verified 15 manifest entries with actual `sha256sum -c` and
0644 regular-file modes. Exact-live candidate SHA256:
`02125b91da940e0d96d01938bc7ffde35e6e30389f9fec2c52d8c567fdec4093`.
Applying the two narrow insertions in reverse reproduced the original bytes.
The archive includes the disabled configuration, not models or credentials.
Independent review of the service template also passed; its real engine memory
and task-limit compatibility is explicitly pending.

The only currently preparable no-restart execution approval is **one inactive
staging installation**, with no production replacement, unit registration/start,
boot enablement, camera or inference. It does not confer live activation readiness.
