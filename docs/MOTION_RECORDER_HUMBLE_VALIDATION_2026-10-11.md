# Isolated Jetson recorder validation — 2026-10-11

Decision: **serialization and SQLite writer PASS; supervised live recorder deployment HOLD** pending removal of synchronous preroll-flush blocking and validation of bounded ingress under that load. No continuous recorder or service was enabled. This is recorder validation, not localization or autonomy validation.

## Test boundary and identity

- Source baseline: `5fddb746e55f15af4dcb8ca86a50bc220440621e`, branch `agent/sync-developer-20261011`.
- Jetson: Python 3.10.12, kernel 5.15.148-tegra; Humble rosbag2_py and SQLite storage plugin 0.15.16.
- New isolated directory: `/home/jetson/atlas_recorder_smoke_KWJkzy`. Scripts were copied only into that directory. Existing project deployment and all existing diagnostics were preserved.
- Synthetic messages only; the harness never calls `rclpy.init`, creates a ROS node, subscribes, publishes, or calls a ROS service. Synthetic nonzero motion is a direct recorder-state-machine call, never a robot command.
- Before and after: `stop_latched=true`, source STOPPED, linear/angular command zero; Nav2, exploration and SLAM inactive. Command mux PID 1872, base telemetry PID 1878 and remote PID 1930 remained unchanged, with the same activation timestamps. No reboot, service modification, motor, servo, or drive action.

## Verified results

The 60-second paced fixture exercises 25 topics from the existing recorder allowlist: two 720-ray scans at 10 Hz, two odometry streams and four encoders at 50 Hz, two IMU streams at 100 Hz, TF at 50 Hz, command and steering streams at 20 Hz, and status/pose streams at lower rates. It is a stated synthetic load, not a measurement of current live ROS rates.

| Capture | Trigger | Bag interval (synthetic seconds) | Messages | Result |
| --- | --- | --- | --- | --- |
| 1 | 12–24 s and 28–30 s | 2.00–39.99 | 29,831 | repeated short movement merged; 10 s preroll and postroll |
| 2 | 45–48 s | 35.00–57.99 | 18,056 | independent capture; full 10 s preroll and postroll |

All 47,887 stored messages were read with `rosbag2_py.SequentialReader`, deserialized, and checked for semantic round-trip equality. SHA-256 streams over topic, timestamp and original payload matched exactly before and after storage, including ordering. Both SQLite `PRAGMA integrity_check` results were `ok`; metadata.yaml and capture manifests were finalized.

One code defect was confirmed and corrected in the isolated source: the original core stopped filling its ring while recording, so a closely following new capture could lack ten seconds of preroll. A new regression reproduced a first sample at 22 s when 15 s was required. Keeping the ring current during active recording fixes this without duplicate messages inside a bag. Overlapping evidence across adjacent bags is intentional. All **9 offline unit tests pass**. Corrected isolated core SHA-256: `3ecccb3917f7f00281b624d417ffc513fab7ccc4fe81c658a5b32c62dc805145`.

Initial harness limitations were retained as evidence: `/proc/self/io` is absent on this kernel; a naive serialize-after-deserialize byte comparison failed on IMU CDR padding. The harness now compares decoded values and independently hashes the untouched bag payload, avoiding an invalid padding comparison. Neither limitation demonstrates sensor or recorder corruption.

## Measured resource impact

Recording/generation window: 59.991 s. Readback verification ran afterward and is excluded from recording CPU time.

| Measurement | Result |
| --- | --- |
| Test process CPU, including synthetic message generation/serialization | 10.299 CPU-seconds; 17.17% of one core |
| Peak recording RSS | 60.49 MiB |
| Process high-water RSS including later readback | 62.67 MiB |
| Peak serialized ring payload | 2.57 MiB |
| Retained bags + manifests | 19,707,131 bytes / 18.79 MiB |
| Allocated bag disk blocks | 19,718,144 bytes / 18.80 MiB |
| Whole-NVMe writes during recording | 32,813,056 bytes / 31.29 MiB; includes other services |
| Free storage before / after recording | 396,671,336,448 / 396,651,261,952 bytes |
| Available system RAM before / after | 2,034.63 / 2,016.57 MiB |
| System CPU during test | 72.17% across CPUs; includes existing services |

The kernel lacks per-process I/O accounting, so exact physical writes attributable to this process are unavailable. Bag bytes and allocated blocks are directly measured; system NVMe writes are not attributed entirely to the recorder. Filesystem cache and other services also influence free-storage changes. DDS/executor overhead is excluded because no live subscriptions existed.

## Remaining blocker and evidence limits

There were 131 synthetic scheduler ticks more than 100 ms late; no synthetic messages were discarded, because the generator caught up. That is not evidence of zero DDS losses. The `prebuffer_evicted=39248` counter represents normal expiry of old ring samples in this fixture, not lost bag messages; the name remains a reporting limitation.

A focused three-run preroll probe wrote 7,874 buffered messages per attempt. The synchronous `RecorderEngine.motion()` call blocked for **0.4663, 0.4633 and 0.5116 seconds**. The live adapter currently writes from its single subscription executor and uses depth 50. At 100 Hz this leaves little or no queue margin. Actual live DDS loss has not been tested; the risk is supported by measured callback blocking, not a claim that the rover lost messages.

Next necessary change: move bag writes/preroll drain to a bounded worker queue, preserve order/timestamps, explicitly count queue overflow, and validate worker failure/close handling in isolation. Then a short approved, supervised opt-in subscription trial can measure real DDS QoS compatibility, topic rates, losses and resource overhead. No drive is needed to validate subscriptions. This report does not approve background deployment.

## Installation status and rollback

No package or production file was installed, no unit was created, and all finite test processes exited. Raw results remain in `run_corrected/smoke_result.json` and `flush_probe/flush_result.json` under the isolated directory; earlier attempts and their bags are retained.

There is no live rollback action required. For a future explicitly approved manual trial, run the recorder in the foreground with its dedicated capture root and stop it with Ctrl-C; retain its bags. A worker implementation must also pass graceful-shutdown validation before that step. Do not restart control units or delete diagnostics as part of rollback.
