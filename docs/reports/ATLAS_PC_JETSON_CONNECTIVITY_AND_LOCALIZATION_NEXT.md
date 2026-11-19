# PC–Jetson connectivity and localization next action

15 October 2026. Source baseline: `563956b26a809d619fb54fd014ecc39146f2e421`;
branch `agent/sync-developer-20261011`, fetched origin matched. Read-only audit,
no production subscriptions, movement, service restarts, clock/network changes,
or recording. No reinstall or repeated full synthetic capture.

## Decision

**Three publisher-presence blockers cleared. Direct DDS not qualified.**
Existing bridge TCP reachability is verified; actual ROS payload delivery is not.
Request approval for one bounded receive-only stationary bridge qualification.
Do not begin full capture or moving localization validation yet.

## 1. Missing publishers: new evidence

Jetson graph-only observer, no subscriptions or ROS service calls; snapshots at
3,10,20 seconds. All three endpoints appeared at3s; AMCL publisher ownership
was initially UNKNOWN and resolved by10s. All remained visible at20s.

| Topic | Actual publisher/type | Offered QoS |
| --- | --- | --- |
| `/scan_raw` | `/rplidar_node`, sensor_msgs/msg/LaserScan | RELIABLE, VOLATILE |
| `/amcl_pose` | `/amcl`, geometry_msgs/msg/PoseWithCovarianceStamped | RELIABLE, TRANSIENT_LOCAL |
| `/particle_cloud` | `/amcl`, nav2_msgs/msg/ParticleCloud | BEST_EFFORT, VOLATILE |

The LiDAR unit explicitly remaps `scan:=scan_raw`. No rename or namespace mismatch
was found. AMCL process8833 exists. Localization unit PID8798, active,
NRestarts8 before and after audit. LiDAR unit PID8719, active, NRestarts8 at final
inspection; these historical counters are not restarts initiated by this audit.
Existing journal: AMCL activated08:41:43 IST; awaiting initial pose through
08:42:08; initial pose received08:42:10. This precedes today's missing-publisher
snapshot. Existing no-motion-update requests continue in its journal; we did
not trigger those requests or reseed it.

**Confirmed:** publishers are present now, same expected names and types. Earlier
3s absence was not proof of sensor failure. Delayed graph convergence is supported
by observed UNKNOWN→named endpoint ownership. **Not proved:** the exact reason
each endpoint was absent in the earlier snapshot, present message freshness,
current particle updates or localization accuracy. Do not equate lifecycle logs
or publisher presence with fresh usable sensor samples.

AMCL output is event-driven. Its retained pose may be old. Future recorder must
label retained evidence and preserve its source timestamp; receiving it does not
prove a new localization update. Particle output has no retained-history promise.
If no particle message arrives, declare that evidence missing—not a fake empty
cloud and not an automatic AMCL failure. Do not reseed solely to fill the bag.

## 2. Clocks: narrower findings, no unauthorized correction

- Windows `W32Time` is **Stopped**; `w32tm /query /status` returns0x80070426.
- WSL reports timesyncd active/synchronized, but only one NTP packet and initial
  offset about **-1.0925s**, delay177.6ms. Its journals show repeated WSL boot/
  timesync startup and shutdown boundaries. WSL uptime was65s at probe end.
- Jetson reports synchronized NTP; latest sample offset+6.066ms, delay30.545ms,
  jitter2.304ms, packet count5. These are NTP estimates, not cross-host proof.
- Repeated six-exchange SSH probe: Jetson-minus-WSL midpoint offsets in ms:
  **+294.9,+122.4,+21.5,-53.2,-284.8,-600.1**; half-RTT bounds:
  **305.2,132.8,59.7,30.3,31.8,30.2**. First exchange includes setup.
  The later bounds do not overlap; a constant precise offset remains invalid.
- Separate12-sample local probe found wall-minus-monotonic interval residuals
  within about5 microseconds. This rules out a large isolated wall-clock step in
  that particular interval, not a common VM clock-rate issue or earlier correction.

**Unproven hypothesis:** WSL initialization/host synchronization contributes to
the unstable relationship. Windows Time being stopped alone does not prove the
cause; monotonic and wall clocks can share underlying VM timing behavior. SSH
asymmetry and scheduling are bounded by the exchange interval, not assumed zero.
No clocks or time services were changed. No precise one-way sensor/callback
latency may be claimed. Original Jetson headers/TF and PC wall/monotonic receipts
remain separate. Clock correction requires a separately specified approval;
do not blindly start multiple clock authorities or modify Jetson NTP.

## 3. Network qualification

Windows Wi-Fi192.168.1.4, Tailscale100.98.59.32; Jetson Wi-Fi192.168.1.15,
Tailscale100.87.208.71. WSL NAT172.31.250.86/20 via172.31.240.1; not a mirrored
LAN address. Windows firewall profiles are enabled. Effective DDS/Hyper-V UDP
filtering is not established by that fact alone.

One10s WSL graph-only probe used existing FastDDS, domain0, localhost-only0,
no rosout/parameter service or topic subscriptions. At5s and10s it discovered
only itself and `/parameter_events`, **no Jetson nodes**. This does not prove a
particular firewall rule is wrong. NAT/multicast/routing/interface advertisement
remain possible causes. Do not change production DDS domain or guess port rules.
Jetson AMCL/LiDAR environments have localhost-only0 and default domain (unset);
localization sets UDPv4 transports. Foxglove unit explicitly uses domain0.

WSL TCP-connect-only probes succeeded to192.168.1.15:22,192.168.1.15:8765 and
100.87.208.71:8765. No WebSocket subscription was sent. Existing Foxglove PID4363
listens on8765; its unit has CPUQuota55%, CPUWeight50, Nice8.

**Least-invasive next transport:** existing Foxglove endpoint over encrypted
Tailscale, receive-only channel subscription. It avoids a new bridge, DDS/router
changes or Windows restart. It is NOT yet demonstrated lower CPU than DDS; bridge
serialization/copy cost and its existing quota can affect delivery. Prefer this
bounded qualification to redesigning WSL networking now. No untrusted exposure.

## 4. Exact next test proposal — separate approval required

One manually initiated **10-second** stationary qualification, no automatic retry:

1. Fresh owner confirmation parked/E-STOP latched/charger and power safe; verify
   zero motor commands, autonomy/commissioning disabled, Stage20 OFF. Abort if
   policy cannot be verified. Do not release B or send any control command.
2. Collect comparable10s pre/post Jetson resource baselines via existing SSH and
   existing read-only dashboard status. During capture monitor resource/safety
   state at1Hz. Preserve75% CPU,80% RAM,70°C limits; abort on any exceeded limit,
   unavailable safety state or monitoring gap. No CPU exemption.
3. Connect existing bridge through Tailscale. Validate advertisements and CDR
   schemas before subscribing. Client operation allowlist: subscribe/unsubscribe
   only; no client-advertise, publish, parameters, services, actions or goals.
4. Limited payload subset: `/scan`, `/im10a/imu/unvalidated`,
   `/atlas/encoder_update`, `/atlas/control_policy`, `/cmd_vel`. Raw encoder
   values remaining unchanged while stationary are valid; messages must be fresh.
   Stop if a required source has no arrival within2s, then any arrival gap>2s,
   malformed CDR, E-STOP release, nonzero command or explicit unsafe policy.
5. Preserve CDR and source headers with existing writer/ledger, not another
   recorder. Keep bridge-server timestamp separate if provided. No header is
   invented for headerless messages. Clock offset stays UNKNOWN.
6. Measure Jetson CPU mean/p95/max, RAM/temp, interface byte-counter deltas and
   service identity; PC process CPU/RSS, bytes received, logical bag bytes,
   counts, arrival gaps, receipt/callback processing duration and writer errors.
   Interface counters include unrelated traffic; don't call their delta pure
   recorder overhead. Bridge loss accounting may be UNKNOWN, not falsely zero.
7. At10s unsubscribe and close, flush bounded writer, verify native SQLite/CDR/
   hashes. On failure preserve incomplete evidence and stop. Stage20 remains OFF.

This test establishes limited transport delivery only. Live bridge adapter must
be checked against the operation allowlist before execution; none was deployed
or activated in this audit. No new production publisher or bridge is authorized.
Full21-topic30s capture remains a separate follow-on gate, not included here.

## 5. Full contract and evidence boundaries

Reuse the21-topic inventory and native tests in
[readiness report](ATLAS_PC_OFFBOARD_RECORDER_READINESS.md). Previous22,779/22,779
synthetic/native readback remains valid; not rerun. Correct the previously unknown
AMCL QoS interpretation with today's RELIABLE/TRANSIENT_LOCAL observation. Existing
BEST_EFFORT/VOLATILE AMCL request is compatible for future samples but does not
request retained pose. Treat optional retained history explicitly in the eventual
adapter; never use it to satisfy live-freshness checks.

New tests this task were graph metadata, clock diagnostics and TCP reachability,
not sensor recording. Exact clock precision, DDS delivery, actual bridge CDR
delivery and incremental Jetson CPU/network costs remain unverified.
No wheel/IMU/LiDAR fusion change, map replacement or steering change was made.
Stage20 unit at final inspection: inactive, PID0, NRestarts0. This audit did not
subscribe to policy; fresh E-STOP admission remains mandatory before the live test.

## 6. Return to localization / checkpoint

After qualified full capture, the smallest justified experiment remains paired
offline replay: unchanged baseline versus removal of wheel X/Y pose fusion only,
same raw input/time history and documented initialization. Compare heading and
distance against IM10A/LiDAR, AMCL correction sizes/counts, parked pose stability,
map matching and covariance. Commanded steering is not measured steering.
Public recording still does NOT restore private EKF/AMCL checkpoint state. If
original jumps cannot be reproduced, report that limitation rather than claim a
fix from zero jumps or improved matching alone. No additional drive requested now.

This documentation checkpoint follows563956b on the existing branch. Resolve its
exact commit with `git log -1 --format=%H -- ATLAS_PC_JETSON_CONNECTIVITY_AND_LOCALIZATION_NEXT.md`;
the final handoff provides the pushed SHA/URL. Rollback: no production change to
undo; all temporary observers and TCP sockets closed. Preserve historical reports.
