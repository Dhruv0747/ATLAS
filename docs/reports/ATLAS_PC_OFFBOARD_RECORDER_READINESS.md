# ATLAS PC offboard recorder readiness — 15 October 2026

## Decision

**GO: isolated PC development. NO-GO: live recording or deployment.**
Continued from `6d5e9d98b66fdb60c4ed90854d316da775f72706` on
`agent/sync-developer-20261011`; origin matched before work. No reinstall,
production subscription, motor command, service restart, clock/network change,
or localization tuning was performed. Stage20 capture service was observed
inactive. Stage17B remains HOLD. Fresh live E-STOP status was not subscribed to;
this report does not claim a fresh safety admission for live capture.

## Runtime and data contract

Existing Ubuntu22.04.5/WSL2 and ROS2 Humble retained. Native rclpy3.3.22,
rosbag2 0.15.17 and FastDDS2.6.12 are installed. All 21 required types resolve
and serialize/deserialize in the isolated native test.

| Topics | Type | Read-only Jetson graph snapshot |
| --- | --- | --- |
| `/yahboom/encoder/m1` … `/m4` | std_msgs/Int32 | Publishers present |
| `/atlas/encoder_update`, `/atlas/encoder_health`, `/atlas/control_policy` | std_msgs/String | Publishers present |
| `/yahboom/odom`, `/odom`, `/lidar/odom` | nav_msgs/Odometry | Publishers present |
| `/im10a/imu/unvalidated`, `/im10a/imu/bias_corrected_candidate` | sensor_msgs/Imu | Publishers present |
| `/scan` | sensor_msgs/LaserScan | Publisher present |
| `/scan_raw` | sensor_msgs/LaserScan | Type listed, zero publishers observed |
| `/amcl_pose` | geometry_msgs/PoseWithCovarianceStamped | Type listed, zero publishers observed |
| `/particle_cloud` | nav2_msgs/ParticleCloud | Absent |
| `/tf`, `/tf_static` | tf2_msgs/TFMessage | Publishers present |
| `/steering/front_angle_deg`, `/steering/rear_angle_deg` | std_msgs/Float32 | Publishers present |
| `/cmd_vel` | geometry_msgs/Twist | Publisher present |

This was a bounded 3-second discovery snapshot via SSH, not a sensor freshness
test or proof of a failed device. No subscriptions were created. All observed
publishers reported RELIABLE/VOLATILE except static TF RELIABLE/TRANSIENT_LOCAL.
Reported depth 0 is not interpreted as a measured publisher queue size.
Recorder requests compatible BEST_EFFORT/VOLATILE, depth200, except static TF
RELIABLE/TRANSIENT_LOCAL. DDS reported-loss events are captured, but zero such
events cannot prove zero upstream loss. Source sequence counts are not available
for every live message. AMCL/particles/static TF are event-driven; absence of
new pose messages alone is not a health failure. Initial evidence is required.

## Network and clocks

SSH to the existing trusted Jetson endpoint works. WSL has a separate NAT address
172.31.250.86/20, gateway172.31.240.1. No `.wslconfig` was found. Direct DDS
multicast, firewall traversal, packet delivery and sustained production transport
are **not qualified**. Matching FastDDS versions and SSH access do not prove DDS
discovery. The existing Foxglove bridge remains an untested fallback; it was not
opened or changed. No ports were exposed or firewall rules added.

Read-only persistent SSH clock exchange, six samples about four seconds apart:

| Sample | Jetson minus WSL wall clock (ms) | Half RTT bound (ms) |
| --- | ---: | ---: |
| 0 (includes connection setup) | +621.4 | 326.7 |
| 1 | +694.2 | 24.8 |
| 2 | +783.8 | 31.9 |
| 3 | +498.5 | 67.3 |
| 4 | +155.1 | 33.9 |
| 5 | -160.3 | 32.2 |

Non-overlapping bounds prove that one constant offset is not justified for this
interval. The maximum observed offset spread is about944ms. The responsible
clock/synchronization mechanism is **unverified**. No clock was adjusted.
The earlier Windows-clock probe is not interchangeable with the WSL clock.
Do not derive precise cross-host sensor latency from these results.
Recorder preserves raw CDR (including every embedded TF/header timestamp), PC
wall receipt and monotonic receipt separately. Offset metadata remains unknown
unless independently qualified; it never substitutes receipt time for sampling time.

## Implementation

`offboard_native.py` reuses Stage20 inventory, timestamp decoder, RosbagSink,
QueuedWriter and Sample. No separate storage framework or production service.
Manual 30s bound; 8MiB/4000-message queue; conservative 500MiB managed-root budget,
1GiB free-disk admission. Existing evidence is counted, never deleted. Per-message
reservation includes 16KiB overhead; this is a conservative application budget,
not an OS filesystem quota against unrelated external writers.
Exclusive root lock prevents overlapping captures; incomplete cleanup retains
the lock for manual review. Writer errors, missing initial sources, continuous
source gaps, cancellation and overflow mark capture incomplete. No silent retries.
No hash verification is claimed while a writer remains active.

Current executable intentionally refuses ordinary host networking: isolated WSL
network namespace, domain187 and localhost-only are required. No live adapter,
autostart, safety override or activation grant is supplied. Future live approval
requires a separately tested bounded admission/monitoring adapter, not bypassing
this isolation check. Publisher fixture exists only in the isolated test script.

## New tests and measured results

Full native synthetic contract: 30.023s, **22,779/22,779 messages**, 21 topics,
zero per-topic sent/received differences, exact transmitted CDR hashes and source
timestamps. Static TF was published before subscriber creation and received by
late join. SQLite integrity and ledger checks pass. Native Humble
SequentialReader independently reads all22,779 messages with exact timestamps
and payload hashes. This is synthetic—not live ATLAS data.

- Combined synthetic publisher + recorder CPU:13.136 CPU-seconds, **43.75% of one
  core**. Peak combined-process RSS:138,260KiB (**135.02MiB**).
- Stored capture:20,535,205bytes (~19.58MiB), ~0.684MB/s logical output. This is
  not measured physical device write throughput or live network traffic.
- Missing `/scan_raw`: stopped at5.02s, incomplete,3,421 messages, integrity pass.
- Simulated publisher cessation: stopped at5.03s, incomplete,1,155 messages,
  integrity pass. This does not simulate every Wi-Fi/DDS failure mode.
- Cancellation:2.02s, incomplete,1,155 messages, integrity pass.
- Queue overflow: bounded BufferError, incomplete, valid empty bag. Rechecked
  after cleanup correction. The earlier fixture named this `quota`; it tested
  the queue, NOT full-disk exhaustion; renamed `queue` to avoid ambiguity.
- Four offline guard tests pass: host-network refusal, existing lock preservation,
  storage admission refusal before worker creation, failed-shutdown lock retention.

Development failures preserved: initial Humble import was corrected to
`rclpy.qos_event`; fixture was corrected to serialize once and transmit those
exact bytes instead of comparing a second independent serialization. Neither
failed attempt counts as a passed capture. No source calibration was changed.
The cleanup-only patch followed the full capture; its affected guard and queue
tests passed without repeating the already successful 30s contract experiment.

Jetson before/during/after subscription CPU, RAM, temperature, transmission,
publisher overhead and sensor/estimator freshness remain **unmeasured** because
live subscriptions are not authorized. No Jetson CPU saving or localization
improvement is claimed. PC figures include the fixture, not recorder-only cost.

## Evidence and rollback

Full capture in WSL:
`/root/atlas_pc_diagnostics/full_none_u5cq_dl7/capture_20261015T031353Z_cd548960`.
Database SHA256:
`3ecf4e4255a709cf5e0c3c810aac67aa09e820f3ac82a96f7d9b658daac6e232`.
Other run folders: `full_missing_3p5zjh22`, `full_disconnect__1yokmli`,
`full_cancel_uj0_prsk`, `full_quota_crnybrj3`, `full_queue__n7c0nvf`.
Each contains manifests, counts, receipt ledger and file checksums. Generated
evidence stays local, outside Git. Copy retained under repository-local
`artifacts/offboard_pc_20261015/`; never commit raw diagnostics.

Rollback: stop only a PC isolated test with Ctrl+C; retain its evidence. No
Jetson rollback is necessary: nothing was deployed. Do not remove stale locks
until confirming the writer has exited. No new WSL/systemd service exists.
Source checkpoint is the Git commit adding this report (`git log -1 --format=%H
-- ATLAS_PC_OFFBOARD_RECORDER_READINESS.md`); exact pushed SHA is in the handoff.

## Next necessary action / approval gate

1. Qualify the WSL clock relationship and investigate the three unavailable
   publisher entries read-only; do not restart production to manufacture data.
2. Obtain separate approval for bounded production DDS discovery/subscriptions
   (or a narrowly specified bridge test). Any network change requires its own
   plan/approval. Preserve Wi-Fi → cellular → AP priority.
3. Only after transport and source readiness: approve one stationary 30s live
   capture, with fresh E-STOP/zero-command/autonomy-disabled admission and retained
   resource limits, before/during/after PC+Jetson measurements and abort monitoring.

No drive is needed now. Public evidence cannot supply private EKF/AMCL state.
Five historical AMCL jumps and the candidate wheel-pose fusion correction remain
unresolved; no localization investigations were repeated without new evidence.
