# Status-web idle camera CPU containment — 2026-10-04

## Finding

`rover-status-web.service` runs `atlas_status_web.py` directly. The first
optimization stopped copying and decoding camera payloads without a viewer,
but it remained subscribed to the 1280×720 compressed camera stream. DDS and
`rclpy` therefore still had to receive, deserialize, and dispatch every JPEG
before the callback could return.

A stationary follow-up measurement on 2026-10-04 found the service at 49.7%
of one CPU core with `camera_info.streaming=false`. Per-thread accounting put
46.6% in the ROS spin thread, not the HTTP handler. The idle health record
showed 22,951-byte compressed frames, and ROS graph inspection still listed
`atlas_web_control` as a `/camera/image_raw/compressed` subscriber. This is
strong evidence that the remaining hot path is executor-side camera ingress;
it is not yet a measured before/after result for the repository change below.

That is an avoidable status-web hot path. It does not prove that status web is
the only contributor to the rover's total CPU load; the camera publisher,
ROS/DDS delivery, navigation, and other nodes continue running independently.
A controlled Jetson before/after measurement is still required before quoting
a CPU reduction.

## Repository change

Camera HTTP reads renew one shared two-second monotonic activity lease. While
that lease is active, the ROS executor creates the existing raw compressed
subscription, and, in Object mode only, the annotated compressed subscription.
The latest-frame cache, motion estimate, AI-frame preference, CrowPanel
resizing, topic names, QoS, and browser behavior remain active. After the last
camera request, an executor-owned timer destroys both JPEG subscriptions, so
idle DDS traffic is not deserialized or dispatched to Python.

At startup a single short lease captures a real frame size for the unchanged
commissioning check. While unsubscribed, a 1 Hz ROS graph check keeps
`camera_info` fresh and reports the publisher count without receiving image
payloads. If the publisher disappears, `bytes` is set to zero so camera health
fails closed. On the next HTTP image request, the executor recreates the
subscription within its 100 ms lifecycle tick and the request waits briefly
for a new frame.

The callback itself keeps its earlier defensive idle behavior. Therefore, in
the short interval before the timer removes a subscription:

- compressed camera ingress records only `len(msg.data)` and lightweight
  `camera_info` health at 1 Hz;
- it does not call `bytes(msg.data)` or JPEG-decode for motion detection;
- it clears the old motion baseline so a later client session is not compared
  with an image captured before the idle period;
- annotated JPEGs are copied only when Object mode and a camera client are
  both active; and
- cached frames older than two seconds are not served when a client returns.

The first request after an idle period waits for up to 350 ms for a new frame,
which preserves one-shot consumers such as the local MCP camera capture. It
returns HTTP 404 only if the camera publisher does not provide a fresh frame in
that window. The dashboard's existing retry loop still handles that offline
case. A cached stale image is never presented as live.

`camera_info` remains fresh while the camera publisher exists and includes
`streaming: false` plus `publisher_count` during the no-client state. This is a
graph-availability check, not proof that image frames are advancing. Opening a
camera endpoint performs the stronger live-frame check and never returns a
cached frame from the prior idle subscription.

## Boundaries

No systemd unit settings, ROS topic names/types, QoS, camera capture settings,
AI enable state, HTTP/API surface, pan/tilt controls, motion authority, or
safety behavior changed. The reviewed file was deployed while ATLAS was
stationary and no physical-motion command was issued.

## Offline verification

From the repository root:

```bash
python3 -m py_compile project_atlas/scripts/atlas_status_web.py
python3 -m unittest \
  project_atlas.tests.test_status_web_idle_camera \
  project_atlas.tests.test_status_web_smart_panels -v
```

The focused tests exercise lease expiry/renewal, the no-copy idle path, active
latest-frame caching, raw and annotated subscription lifecycle, no duplicate
subscriptions, idle cache removal, publisher-loss fail-closed behavior, a
first-request wake-up, stale-frame rejection, and lease renewal by all three
camera endpoints.

## Jetson acceptance result and remaining bottleneck

The demand-driven camera path passed its stationary integration checks:

1. with no camera client for more than two seconds, `camera_info.streaming` is
   false, its age remains below the existing camera-health threshold, and ROS
   graph inspection does not list `atlas_web_control` as a JPEG subscriber;
2. opening the dashboard produces a new (not cached stale) frame and sets
   `streaming` true without a service restart, while the raw subscription
   reappears;
3. closing all clients removes the raw and annotated subscriptions within the
   two-second lease plus one 100 ms lifecycle tick;
4. camera, LiDAR, odometry, TF, mux, and base-command freshness do not regress.

The first fresh frame after idle returned HTTP 200 in about 279 ms; the camera
subscription then disappeared again after the two-second lease, with zero
service restarts and no stale frame served. The deployed source matched the
reviewed SHA, and the rollback copies are under
`data/deploy_backups/20261004_cpu_status_web*`.

Process CPU nevertheless remained about 48–50% of one core with no camera
client. A deeper live audit proved this is not camera or HTTP work: the ROS spin
thread processes roughly 270 callbacks/s across 102 permanent non-camera
telemetry subscriptions plus timers. The configured user-service `CPUQuota`
is not enforced because the user cgroup has no delegated CPU controller.
Further reduction therefore requires a separately tested aggregate telemetry
snapshot or a demand/first-refresh protocol. Blind callback throttling was not
applied because it could make displayed ages and rates misleading.
