# Snapshot verification preparation — 2026-10-31

Baseline2625327. No Jetson test, installation, environment change or restart.
Backend and reviewed activation package unchanged.

## Actual read-only Jetson evidence

Recovery active PID2005, NRestarts0; web active PID182915, NRestarts0.
Both have empty PartOf/BindsTo. Recovery ExecStart runs its own Python process;
its Environment contains ATLAS_GNSS_ENABLED=0, not ATLAS_RESTART_SNAPSHOT=1.
Snapshot /run/user/1000/atlas-restart-safety/state.json absent.
Live recovery SHA256:5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Producer is therefore NOT live. No actual incremental Jetson adapter CPU/RAM
measurement exists. Do not report zero overhead or claim lifecycle validation.

Existing recorded Jetson startup:70.65 then92.93% aggregateCPU, observer0.76CPU-s
by first sample, supervisor about20% one core; these are historical, not current
resource admission. Exact full-spike attribution remains UNKNOWN.

## Lifecycle audit

Candidate producer is constructed once during existing recovery-node startup,
only with opt-in. It is driven by existing policy/Twist/encoder callbacks under
rclpy.spin(node); adds no ROS node, participant, subscription, timer or camera use.
No HTTP dependency. Writes at most10Hz, original receipt times preserved. Atomic
replace exposes complete old/new JSON; source/producer expiry fails closed.
Write errors latch producer off without changing existing recovery decisions;
consumer latches rejected safety. Recovery callback stalls imply stale snapshot,
not a fresh PASS. Producer has no separate automatic restart mechanism.

Enabling it in the currently running process requires a future reviewed service
change/restart. File staging alone cannot verify actual callback lifecycle. Do not
inject code or start a duplicate recovery node to evade that restriction.

## Focused preparation and tests

Added standalone benchmark_safety_snapshot.py: synthetic callback-shaped baseline
and enabled phases, ABBAAB, six phases of at most2seconds (12s scheduled workload).
Uses private disposable temp directory, no ROS/network/systemd or production files.
No hardware result, actuation or authoritative safety observation is simulated as
real. CPU is measured with process_time separately from wall time and ROS startup.
MaxRSS is high-water, not incremental RAM; never subtract it as proof of savings.
It is NOT a safety supervisor and must not be run on Jetson unattended.

Two new focused lifecycle tests PASS: throttling with old-source expiry and atomic
replacement showing complete old/new records. Prior eight passing tests reused.
PC WSL benchmark smoke test six0.2s phases PASS; baseline CPU0.000105–0.000201s,
active0.000996–0.001568s per phase. MaxRSS12536–12664KiB. Too short and PC-only;
not a Jetson overhead estimate or performance acceptance result.

## Shortest safe next step and gates

GO for review of this preparation. NO-GO for executing the bare benchmark on the
Jetson or activating backend. First prepare/review a bounded safety wrapper using
fresh local authoritative observations while HTTP stays UP (no web downtime),
with 1s CPU/RAM/temperature/telemetry checks, E-STOP, exact zero commands and
stationary encoder requirements. CPU75%, RAM80%, reject temperature>=70C unchanged.
Wrapper must kill only its benchmark child on violation/deadline, preserve evidence,
verify child exit, and never retry. No new ROS observer is needed for this isolated
benchmark since HTTP remains available; this does NOT replace independent safety
for a later web restart. Separate owner execution approval is still required.

For comparable measurements, collect matched aggregate/process counters around
ABBAAB phases with same cadence/workload; report benchmark CPU separately from
supervision, per-phase RSS and run-order effects. Run once only. Do not stop HTTP,
producer or other services to manufacture failures; lifecycle faults stay simulated.

Cleanup: benchmark's TemporaryDirectory removes only its own synthetic snapshot
and temporary file on normal exit. Wrapper records the generated path before start;
on abnormal exit verify child PID/start identity has ended and remove only that
owned private directory. Preserve results/checksums outside it. No system rollback
is needed because no production paths, environment or services are modified.

After isolated cost measurement, actual producer lifecycle still requires separately
reviewed exact-live recovery patch installation/activation, original-byte backups,
private runtime directory provisioning, bounded safety observation and rollback.
Do not request a web activation until independent snapshots are live and resource
headroom demonstrated. A future recovery rollback must restore exact original files
and opt-in configuration; service restart requires its own explicit authorization.
