# ATLAS offboard PC recording feasibility — 2026-10-14

## Decision

**GO for isolated PC preparation; NO-GO for live capture.** Offboard recording is
plausible, but reduced Jetson overhead is NOT measured. No live subscription,
recording, network change, service restart, motion or grant was performed.
Installed Stage20 service was observed inactive. Its75% CPU safeguard is unchanged.

## Verified host/network facts

- PC: Intel i5-14400,16 logical processors,34122760192 bytes RAM,
  234933469184 bytes free on C: at inspection. Python3.13 and `rosbags` available.
- `wsl --list --verbose`: WSL not installed. No `ros2` or Docker command found;
  `rclpy` unavailable in project Python. Therefore native ROS discovery and
  rosbag2_py tests cannot currently execute on this PC.
- PC Wi-Fi192.168.1.4, Tailscale100.98.59.32. Jetson Wi-Fi192.168.1.15,
  Tailscale100.87.208.71. Authenticated SSH over Tailscale succeeds.
- Existing Foxglove process listens on8765; process environment DOMAIN_ID0,
  LOCALHOST_ONLY0. Loaded libraries confirm `rmw_fastrtps_cpp`, Fast DDS2.6.11.
  This proves that process configuration, not universal configuration of every node.
- Jetson Wi-Fi5GHz, signal-50dBm, reported TX175.5/RX585 Mbit/s link rates.
  These are NOT application throughput or a stability test. No active throughput
  stress test performed. Packet-loss/long-term Wi-Fi stability UNKNOWN.
- All Windows firewall profiles enabled; effective DDS rules and multicast traversal
  unverified. No firewall changes. Tailscale SSH connectivity does not prove DDS discovery.
- Jetson reports NTPSynchronized=yes. Windows `w32tm /query /status` reports service
  not started. Actual clock offset/drift UNKNOWN; no clock changes performed.

## Architecture choice

Preferred first path: separately approved WSL2 Ubuntu22.04/ROS2 Humble preparation,
then isolated localhost ROS publisher/subscriber+rosbag2 tests. Reuse Stage20 raw
CDR/topic contracts and existing bounded writer. Do not install a background service.
Direct DDS must be qualified before any production subscription. WSL networking
mode, Windows/Hyper-V firewall and multicast may require separate owner decisions.
Microsoft documents mirrored-network multicast support on supported Windows11:
https://learn.microsoft.com/windows/wsl/networking . No assumption that it is enabled.

Alternative: existing Foxglove bridge through authenticated SSH local forwarding
or private Tailscale, with subscription-only client and raw CDR payloads. Avoids
adding a Jetson bridge and WSL multicast, but still costs Jetson bridge/DDS CPU.
The protocol permits CDR and also control operations; a future recorder must allow
only subscribe/unsubscribe and reject publish/service/parameter mutation operations.
Reference: https://github.com/foxglove/ws-protocol/blob/main/docs/spec.md (archived
protocol reference, not a recommendation to build another server). Bridge version,
schema coverage, subscription QoS and timestamps require qualification. No socket
was opened to the bridge in this task. Do not expose DDS/control over public networks.

## Prototype delivered and limits

`project_atlas/tools/diagnostics/offboard_storage_probe.py` is a **transport-free
storage prototype**, not a complete live recorder. It imports existing Stage20
`TOPIC_LIST` and `serialized_source_stamp`, writes original CDR through installed
`rosbags` into SQLite, and keeps a separate PC receipt/source-header/hash ledger.
No ROS publisher, socket, hardware interface or production activation path exists.
New directories only; no overwrites, no retention deletion. Conservative write
admission reserves space under a configurable ceiling capped at500MiB. This is not
yet a crash-hard aggregate retention quota for multiple live sessions.

Required inventory remains sourced from `atlas_motion_recorder.TOPICS`,
`STEERING_VALIDATION_EXTRA` and Stage20 `TOPIC_LIST/KNOWN_TYPES`, not a second list:

| Evidence | Inventory source/examples | Live qualification |
|---|---|---|
| M1–M4 counts/update/health | `/yahboom/encoder/m1`–`m4`, `/atlas/encoder_update`, `/atlas/encoder_health` | Pending |
| Wheel/EKF odometry | `/yahboom/odom`, `/odom` | Pending |
| IM10A raw/corrected/status | `/im10a/imu/unvalidated`, `/im10a/imu/bias_corrected_candidate`, `/im10a/status` | Pending |
| Steering/control | front/rear angle commands, control policy, cmd_vel variants | Pending |
| LiDAR/localization | scan/raw, lidar odom variants, AMCL pose, particle cloud | Pending |
| Transforms/provenance | tf/static, parameter events, map/config hashes | Pending |

Steering values remain commands, not measured angles. Map identity must be captured
as hashed metadata. Private estimator topics being in an inherited inventory does
not make those states available; absence must be explicit, never synthesized.
Native transport should discover offered types/QoS, verify schema compatibility,
retain reliable/transient-local static TF and record missing topics. The synthetic
storage test does NOT establish QoS or discovery. No complete topic set is claimed.

## Synthetic results

Corrected run:30.0514s wall,4.15625 process CPU-seconds,13.8305% of ONE PC core,
126195 bytes peak traced Python allocations during loop (NOT full process RAM),
2812831 disk bytes, approximately93.6kB/s aggregate stored output.
6300 messages verified: four Int32 encoders at50Hz and one720-range LaserScan at10Hz.
This is a small storage fixture, NOT the full required workload or native ROS test.
Payload source timestamp is deliberately fixed fixture data, not a clock accuracy result.
SQLite integrity, count, exact payload hashes and independent source/receipt stamps pass.
Native Humble bag metadata compatibility remains untested (`rosbags` writes version8).

Three regression tests pass: partial close/cancel with preserved payload; refusal to
overwrite/use an unlisted topic; quota refusal preserving existing output. An initial
Windows cleanup failure occurred in readback; replaced library readback with explicit
SQLite connection closure and verified clean completion. No cleanup failure is hidden.
Network interruption, full topic discovery/QoS, process crash recovery, native ROS
readback, queue overflow and live sensor timing are **NOT TESTED**. Transportless
tests must not be reported as those passes. No Jetson CPU reduction is inferred.

## Timing/completeness strategy

Retain raw source headers unchanged. Record PC wall-clock receipt and monotonic
receipt separately in the future transport adapter; current storage probe only
records PC wall-clock receipt. Estimate clock offset using repeated bounded SSH
timestamp round trips, with RTT/2 uncertainty and before/after drift; NTP status alone
is insufficient. Until qualified, cross-host latency UNKNOWN. Preserve TF individual
timestamps in payload: ledger extraction summarizes only first transform.
Standard ROS2 headers generally provide no sequence counter; report unobservable
loss UNKNOWN. Transport counters/diagnostic sequences are evidence of gaps where
available, not proof of encoder failure. Receipt never proves EKF/AMCL consumption.
Public data cannot reconstruct unavailable private estimator initialization history.

## Comparison (not controlled head-to-head)

| Metric | Installed Jetson recorder | PC prototype |
|---|---|---|
| Jetson CPU | Historical whole-host76.23% refusal, attributable overhead unknown | No production subscription; incremental overhead UNKNOWN |
| PC CPU | N/A | 13.83% one core, partial synthetic workload |
| Network | Historical recorder network not measured | No live traffic; bandwidth requirement UNKNOWN |
| Recording size | Failed approved attempt produced no bag | 2.813MB synthetic |
| Timing | Historical resource interval preserved | Exact fixture source+receipt separation; clock offset unknown |
| Completeness | No successful live capture | Five fixture topics only |
| Failure behavior | Supervisor safely aborted75% exceedance | Three storage tests; transport not tested |
| Evidence quality | Public-only, private-state gap | Same gap plus network/clock uncertainty |

## Next approval, installation and rollback

First request: approve **PC-only WSL2/Ubuntu22.04/ROS2 Humble setup**, potentially
requiring administrator rights and a PC restart. No Jetson changes. Do not silently
install Windows features or alter firewall. If WSL setup is unwanted, choose bounded
Foxglove adapter development instead; it must pass synthetic protocol tests first.

Only after native/protocol gates pass, request a separate stationary30s subscription
test: fixed existing topic allowlist, E-STOP latched/commands zero/autonomy disabled,
fresh75% CPU/80% RAM/70C admission, before/during/after same `/proc/stat` measurement,
network byte deltas, PC CPU/RAM/disk, source/receipt timing and loss evidence. Stop
on failing limit, disconnect once, no automatic retry. No route or motion needed.
This test is not approved or executable-ready under the current result.

No live installation needs rollback. Close the optional future PC receiver/tunnel
to stop its subscriptions; do not restart Jetson production. Existing recorder stays
OFF. Git branch `agent/sync-developer-20261011`; commit provided in final handoff.
