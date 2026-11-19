# Existing-observation supervisor integration — offline PASS

Continues 80f7c8a. No live files, services, camera, inference, controls or firewall
changed. Existing staged backend and rollback package are untouched.

## Implementation

- `atlas_sensor_recovery.py`: optional ATLAS_RESTART_SNAPSHOT=1 producer, default
  disabled. Copies full raw policy, six Twist components and encoder JSON with
  original callback receipt times. No additional subscriber, timer or ROS node.
  Existing recovery decisions are unchanged; their tolerant summaries are NOT used.
- `existing_safety_snapshot.py`: throttles atomic writes to at most10Hz; write
  failure disables producer and attempts to remove snapshot, otherwise expiry
  rejects it. Consumer permanently latches any rejection for that session.
- `web_activation_supervisor.py`: consumes fixed local runtime path, checks boot
  identity and freshness, never starts the old ROS observer. Missing snapshot is
  rejected before mutation. Existing process/cgroup CPU monitoring and resource
  checks remain unchanged. CPU75%, RAM80%, temperature70C rejection preserved.

Producer is independent of HTTP and rover-status-web; its existing recovery node
must stay running. Producer death leaves a snapshot that expires within0.75s.
Original observation age is at most1s, encoder packet age is added to receipt age.
Detection occurs at the next supervisor check; Python scheduling is not a hard
real-time guarantee. The existing one-second resource collector can still be
costly or delayed. No claim that this change resolves total startup CPU is made.

## Focused evidence

Ubuntu22.04 WSL PC: 8 unittest tests PASS (test_existing_safety_snapshot).
Tests exercise the actual recovery callback method bodies with simulated ROS
messages, exact-zero versus permissive-summary distinction, missing/malformed
snapshots, stale source/producer, wrong boot, future timestamp, motion, failed
atomic replacement, producer loss and permanent rejection after later recovery.
HTTP-down test prohibits socket creation and still verifies fresh local safety.
Structural test confirms supervisor has no observer Popen.

1000 publish/verify pairs:0.083353547 process CPU seconds, approximately83us/pair.
No ROS imports or DDS initialization in that benchmark. Prior Jetson observer
consumed0.76CPU-seconds by its first sample; these different workloads/platforms
are NOT a before/after savings measurement. Jetson risks remain unmeasured.
Saved92.93% event attribution remains incomplete as documented in prior report.

## Minimal separately approved installation plan

1. Compare exact live recovery script and supervisor dependencies with reviewed
   baselines; stop on drift. Back up exact bytes, modes, environment/drop-ins and
   hashes. Do not replace a drifted live file wholesale.
2. Stage only recovery callback patch, existing_safety_snapshot.py and its strict
   restart_safety_observer.py Safety dependency, plus supervisor candidate. Verify
   hashes and inert imports offline. No backend reinstall.
3. Installation-only staging can leave opt-in absent: no process changes and no
   snapshots expected. This alone does NOT enable a web activation attempt.
4. Future producer activation needs separate approval for atlas-sensor-recovery
   configuration/restart. Create /run/user/1000/atlas-restart-safety as0700 owned by
   jetson; use0600 snapshot files. Review ownership, symlink safety, reboot directory
   creation and single-writer constraint before activation. Never trust HTTP fallback.
5. Validate producer with fresh authoritative observations and measured Jetson
   overhead; confirm no extra ROS participant and safety rejection during producer
   interruption using an isolated harness first. Only then evaluate a separate web
   restart approval. No old activation command is valid for this new dependency.

Rollback: before activation, remove staged candidate only, retaining reviewed
original package. After separately approved producer activation, first stop any
maintenance consumer; remove opt-in, restore exact recovery bytes/configuration
and helper versions from verified backups. A recovery-service restart would need
explicit authorization. Remove only owned snapshot after consumer is stopped.
Never restart telemetry or the web automatically as part of producer rollback.

Verdict: GO for separately approved non-activating file staging only. NO-GO for
web activation or a test claiming independent safety is live. Native Jetson
callback overhead, private runtime setup, existing recovery scheduling/recovery
interactions and full service lifecycle validation remain pending. No execution
approval requested here; no retry performed.
