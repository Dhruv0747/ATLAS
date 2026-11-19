# Recovery startup attribution preparation — 2026-10-31

Base: 41a6f8c. Repository/PC-only work. No Jetson connection, service operation,
ROS participant, camera, inference, control or firewall change was performed.
The incident remains OPEN; Recovery's last verified state is STOPPED, not freshly
rechecked during this preparation.

## Confirmed historical findings

Reuse ATLAS_RECOVERY_STARTUP_ROOT_CAUSE_REVIEW_20261031.md and its retained evidence:
07:44:13 IST original recovery PID349210 started; 07:44:15 aggregate CPU93.624%
rejected. First PID observation contained0.69CPU-s since birth; systemd lifetime
accounting was1.828CPU-s. The rejected process/cgroup endpoint was not retained.
Node initialization had not reached custom subscriptions, timers or recovery scans.
The later invalid-context traceback follows termination and is not a measured hot
function. Localization, DDS discovery, Python initialization and concurrent work
remain possible contributors, not proven causes. Whether overload would persist
is unknown because the safety guard stopped the attempt.19 historical Prometheus
scrapes failed; no historical CPU series can fill the missing interval. No further
restart or repeated Grafana request was made to reproduce those facts.

## Implemented collector

project_atlas/tools/vision3d/startup_cpu_attribution.py uses stdlib only:
- One /proc/PID/stat read per visible PID, including visible kernel threads; records
  PID, name, birth tick, user/system CPU ticks, RSS and monotonic endpoint.
- Aggregate first-eight CPU counters (guest not double counted), wall/monotonic
  timestamps, HZ, logical CPU count, IRQ/softIRQ deltas.
- Explicit selected cgroups, v1 cpuacct.usage or v2 cpu.stat. No repeated per-PID
  membership lookup or cgroup path discovery. Record inode/device/path identity;
  reject reuse/reset as a valid interval. Never sum nested groups.
- New PID lifetime counters stay labeled cumulative, not falsely assigned to a
  measured interval. Missing/exited PID/group observations are explicit.
- One-second sampling, maximum30s,4096PIDs,16selected groups,16MiB output. A150ms
  measured collection budget rejects slow scans. This is not a hard I/O deadline:
  the separately supervised process requires an outer timeout.
- Each completed numbered JSON file is atomically renamed after file fsync, then
  directory fsync. SHA256 can be checked independently. Completed files survive
  SIGKILL; the current incomplete sample may be lost. A .tmp is never a valid
  completed sample. Failure records are best effort if storage itself fails.
- READY means only that baseline000.json was saved. It is NOT a safety approval;
  it can survive SIGKILL. Supervisor must verify collector PID/start identity,
  fresh numbered-file monotonic timestamps and independent safety observations.
- Collector includes its own process CPU and peak RSS. It has NO ROS, API calls,
  service commands, restart logic or implicit safety bypass.

All-process sampling is deliberately retained rather than top-ten-only. Cgroups
must be selected from verified service configuration immediately before a future
approved capture: recovery, localization, dashboard, existing safety observer and
collector, plus other relevant non-overlapping groups. A stopped recovery group's
absence is recorded; its first appearance supplies cumulative usage, not an
invented zero baseline. Raw counters allow later inspection even where a delta
cannot be computed.

Coverage limits: sequential process endpoints have skew; short-lived processes
may disappear between polls; group deletion can lose final accounting. Aggregate
CPU covers intervening activity but cannot assign all of it to visible PIDs.
Do not label an aggregate-minus-process residual as exact kernel/scheduler CPU.
The independent guard's rejection endpoint may differ from collector endpoints;
retain both and report the offset rather than claiming exact synchronization.

## Focused validation and overhead

11 unittest cases PASS in PC Ubuntu22.04 WSL: genuine CPU spike retained; PID reuse/
exit; cgroup replacement; invalid/reset intervals; both cgroup formats and missing
cgroup; inventory/budget rejection; atomic/quota/no-overwrite; native child SIGKILL
retention; capture failure evidence; STOP cleanup; bounded completion.

Command (PC only, from tools/vision3d):
`python3 -m unittest test_startup_cpu_attribution -v`

Native12s run:12samples,12.001s elapsed,0.045941CPU-s =0.383% of one core,
15156KiB peak RSS (14.80MiB). This excludes interpreter/import startup CPU and the
independent safety watcher. Production admission must include both startup and
watcher costs. No Jetson savings or maximum-load guarantee is claimed.

30interleaved microbenchmark iterations per implementation, including durable
writes on WSL /tmp,40visible PIDs:

| Collector | Mean CPU/sample | Mean / max wall/sample | Groups |
|---|---:|---:|---:|
| New selected-group collector |1.081ms|3.151 /3.949ms|1|
| Existing bounded_process_cpu |4.812ms|6.837 /8.329ms|23|

These are different cgroup coverage workloads, not an equal-work speedup claim.
Combined benchmark peak RSS19820KiB. Reproduction script:
benchmark_startup_cpu_attribution.py --old <retained bounded_process_cpu.py>.
The old scanner's prior Jetson272–722ms scan cost is historical, not measured in
this PC comparison. New collector Jetson performance remains PENDING.

## Single bounded diagnostic procedure — NOT execution authorization

Next safe gate is one passive30s collector feasibility capture with Recovery still
STOPPED, separately approved. No restart is contained in this collector.
1. Verify approved file hashes and fresh original-service/snapshot-disabled state.
   Existing independent HTTP-based safety watcher can operate because Dashboard
   is not restarted; verify it has no dependency on Recovery. Do not launch ROS.
2. Before launching collector, require E-STOP latched, fresh zero commands,
   stationary encoders, LIVE fresh telemetry, CPU<75%, RAM<80%, temperature<70C.
   Supervise continuously from before Python startup; abort CPU>75, RAM>80,
   temperature>=70, missing/stale/malformed data or watcher failure. Do not average
   away startup samples. Existing watcher and raw rejection evidence are reused.
3. Validate explicit cgroup configuration against actual mounts/service identity;
   no fabricated paths. Start collector as separately owned child/process group
   with max35s external lifetime and no Restart policy. Use a new private evidence
   directory; never overwrite prior evidence. Collector self-duration is30s.
4. Observe its own overhead and first-second baseline; measure total host resources
   with unchanged watcher. Missing collector heartbeat,150ms collection rejection,
   storage error or any guard failure ends the capture. No automatic retry.
5. Retain all completed samples and the independent guard's raw endpoints, SHA256
   manifest, versions, PID identities, cgroup configuration and collection gaps.
   Keep raw machine telemetry private; commit only sanitized findings.

Future recovery-start attribution (NOT ready for execution yet): start collector
BEFORE the one approved recovery start, retain multiple baseline samples, and keep
it independent of the restart supervisor so supervisor failure does not kill all
evidence. Join guard and collector timelines explicitly. Any safety failure stops
the attempted recovery start immediately; evidence collection must never postpone
that action. Existing one-start/no-retry/fail-closed policy still applies. This
wiring needs focused offline end-to-end validation and Jetson collector overhead
before requesting a recovery start. Do not reuse previous start commands.

## Exact collector cleanup / rollback

For the uniquely selected capture directory, create its STOP marker:
`touch -- "$CAPTURE_DIR/STOP"`
This ends collection at the next sampling boundary (normally <=1s plus bounded
scan). External owner must TERM only its recorded child on failure and KILL only
that same child/process group at the35s outer deadline if needed. Never use pkill
python, killall, broad unit stops or any recovery start in diagnostic cleanup.
A prepared wrapper must own/reap the child, verify exit and remove stale READY only
after identity-checked exit. Preserve numbered JSON files; ignore incomplete .tmp.
Create checksums after exit: `sha256sum "$CAPTURE_DIR"/*.json`.
No production file/policy is changed, so collector rollback is stop/reap only.
Do not delete evidence or change the stopped Recovery service as cleanup.

## Safety implications and verdict

Central stale-sensor recovery/restart coordination remains unavailable while
Recovery is stopped. Independent mux E-STOP/deadman and base watchdog paths are not
replaced by this collector; their existence is not a movement authorization.

PASS: offline collector/tests and measured PC overhead.
GO: preparation for one separately approved passive feasibility capture, subject
to fresh safety preflight and a verified watchdog/child-cleanup wrapper.
NO-GO: recovery restart now. The guarded collector wrapper/end-to-end integration
and actual Jetson overhead are not yet validated; dominant CPU cause remains
UNKNOWN. No performance correction or restoration success is claimed.
