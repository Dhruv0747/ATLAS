# rover-status-web performance audit (read-only), 2026-10-11

Status: **audit and benchmark only.** No subscription, callback, executor, topic, QoS, service
or network setting was changed on ATLAS.

The benchmark ran in a **separate private DDS domain** (`ROS_DOMAIN_ID=77`,
`ROS_LOCALHOST_ONLY=1`). It had synthetic publishers, so it never joined or loaded the live
ATLAS graph. It used about one CPU core for about 5 minutes while ATLAS was parked. Tool:
`project_atlas/tools/perf/bench_status_executor.py`.

## Live measurements (Jetson Orin Nano, 6 cores, rover parked, no dashboard client connected)

| Item | Value |
|---|---|
| Process CPU (60 s `/proc` sample) | **57.2% of one core** |
| Busiest thread | the rclpy executor thread (`rclpy.spin(node)`): **53.9%**. All HTTP threads together: ~2.8% |
| RSS / threads | 174 MB / 22 |
| Subscriptions | 105 in source. 103 at idle: the two camera image subscriptions are created only while an HTTP client wants frames. There are also TF listener subscriptions (`/tf`, `/tf_static`) and 3 timers (0.1 s, 0.5 s, 0.1 s) |
| Messages delivered to Python | ≈ 290/s. The sum of the server's own `observed_hz` across 114 keys is 247/s, plus the throttled `/scan` 7.6, `/radar/targets` 19.9, `/ultrasonic/status` 7.9, `/im10a/dashboard_json` 10.1, and `/tf` |
| Highest-rate inputs | `/radar/hub/status` 20.6 Hz, `/radar/targets` 19.9, `/joy` 19.4, then **16 topics at 10 Hz**: 4 encoders, `encoder_health`, 3 board-IMU Float32s, 3 steering topics, `drive_pid`, `steering_calibration`, `control_policy`, `/odom`, `/im10a/dashboard_json` |
| `/api/status` | 39.7 KB per request; the browser polls it every 2 s |
| System context | load average 12–19 on 6 cores during the audit |

**Diagnosis.** The cost is per message, not per byte. Almost every callback is a one-line
`_set()` (lock, dict write, deque append). Even so, each delivered message costs ~1.9 ms of CPU
in the executor thread. The heavier callbacks are already throttled:
- `/scan` summarises at 2 Hz;
- `/map` encodes at most every 0.75 s;
- camera JPEGs are handled only while a client watches.

The rclpy executor in Humble rebuilds and scans its wait set over every entity on the node
(~110 subscriptions, timers, guard conditions) on each wake. About 290 wakes per second × ~110
entities is the dominant cost. The callbacks themselves are cheap.

## Benchmark: same topics, rates, message types and callbacks; only the executor layout differs

Synthetic publishers replay the 102 non-camera, non-map topics parsed from
`atlas_status_web.py`, at the live rates above, plus `/tf` at 10 Hz. Each variant ran for 45 s,
twice.

| Variant | CPU (% of one core) | msgs/s | CPU per message |
|---|---:|---:|---:|
| **current**: one node, `rclpy.spin()` (as deployed) | **55.7 / 55.5** | 287.6 | 1.93 ms |
| **split**: topics ≥5 Hz plus TF on a "hot" node, the rest on a "cold" node, one `SingleThreadedExecutor` thread each | **39.5 / 39.7** | 287.8 | 1.38 ms |
| split_raw: split, plus hot String/Float32/Int32 received as raw bytes and decoded lazily | 37.1 / 38.4 | 287.7 | 1.31 ms |

Fidelity check: "current" in isolation (55.6%) matches the live process (57.2%). The benchmark
therefore reproduces the real cost driver.

## Proposals (none implemented; each needs separate approval)

| # | Change | Expected saving (evidence) | Risk / what must be preserved | Verdict |
|---|---|---|---|---|
| S1 | **Split the executor into hot and cold nodes.** Same topic names, QoS, callbacks, publishers and HTTP API. The drive watchdog timer, the camera subscription tick, the camera subscriptions and `/cmd_vel_web` stay on the hot executor | **−16 points of one core (−29%)**, measured | Callbacks run in two threads, so all shared state must go through the existing `self.lock`. Audit `previous_amcl_pose`, `last_scan_summary`, camera state and `ai_mode`; each is touched by one callback group only, but this must be proven. The node name `atlas_web_control` changes to two names (for example `atlas_web_control` + `atlas_web_status`); check that no tool filters on it | **Recommended**: the largest measured gain without touching any other node |
| S2 | Lazy raw decode of hot scalar topics | a further −1.5 points (within noise) | More code paths for no real gain | **Rejected** |
| S3 | Upstream consolidation (fewer, combined messages for encoders, board IMU and steering, which the dashboard needs at ≤2 Hz) | estimated 10–15 points (from 1.38 ms/msg × the messages removed); not benchmarked | Changes other nodes' interfaces. Other consumers (mux, PID, odometry) need the originals, so this would be *additional* topics. | **Defer.** Benchmark first if wanted |
| S4 | `/joy` (19 Hz) is subscribed only to report "controller input received" (axes/buttons counts). `/radar/hub/status` (20.6 Hz) is a link-status string | estimated ~5 points for the two together | Removing or replacing them changes what the Xbox-remote and radar tiles prove. A rate-limited relay would be a new node | Needs a design decision; not proposed now |
| S5 | Browser side: Glass UI V2 polls the camera and radar only while visible | Camera 160 → 0 req/10 s and radar 80 → 0 req/10 s when off screen. Radar is never polled unless its panel is shown; camera stays 160 req/10 s while visible. Jetson cost per client is ~0.01 core, so this saves **bandwidth** (≈350 KB/s per hidden camera), not Jetson CPU | Done in the prototype; covered by tests | Ships with V2 |

Out of scope, seen during the audit (not investigated further):
- **Visual Cloud agent:** 11.4% of a core with zero useful output. See
  `ATLAS_VISUAL_CLOUD_AUDIT_2026-10-11.md`.
- **Other high-CPU processes:** the camera node (~20–28%) and several python nodes at 10–28%.
- **BMS gatttool:** a fresh `gatttool` process roughly every few seconds (parent PID 1987), and an
  apport crash report on Oct 8.
- **No action taken** on any of these.

## How to reproduce

```bash
# On the Jetson, in a scratch directory containing tools/perf and scripts/atlas_status_web.py
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1          # never 0: the script refuses the live domain
python3 tools/perf/bench_status_executor.py pub &      # synthetic publishers
for v in current split split_raw; do python3 tools/perf/bench_status_executor.py sub $v 45; done
kill %1
```
