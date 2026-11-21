# Web shutdown CPU — cause UNKNOWN; activation NO-GO

Read-only historical investigation. No deployment, restart, camera, inference,
threshold/firewall change or rover operation. Existing corrected package unchanged.

## Evidence

Saved CPU79.1453% window ended monotonic22146.439869. Old web shutdown began
22145.484842, ended22147.582186; replacement started22147.586605. Candidate
initialization is excluded. Shutdown association is established, not causation.

Actual live shutdown calls server_close(), rclpy.shutdown() and bounded thread
join. ROS/DDS teardown is plausible. No synchronized PID/thread/cgroup CPU deltas
exist for this interval. systemd's2h42m3.581s CPU total spans the old process's
lifetime and cannot attribute shutdown CPU.

Surrounding15s journal:420 entries (LiDAR odometry344, localization52, Foxglove10,
systemd7, BMS3, two other processes2 each). During the rejected window LiDAR work
continued, localization logged missing map TF/no-motion updates, and Foxglove
removed two channels. Message counts and callback elapsed times are NOT CPU
counters; none proves the cause or justifies disabling services.

Prometheus raw range vectors ending Unix1793381260, preceding10min:39 up samples,
all0; CPU and service-restart vectors empty. Grafana cannot supply a missing trend.
Its15s scrape interval could not resolve this1s spike even with healthy scraping.
At inspection the target reported connection refused, exporter inactive, monitoring
watchdog failed. Monitoring recovery is separate; neither was modified/restarted.

Pre-install CPU61–62%, later recovery60.34–63.12%. Recovery is observed, but
transient versus sustained overload during the unsampled interval is UNDETERMINED.

## Safer deployment approach

Stage/hash-check candidate and exact rollback files outside live paths first.
Leave live UI/API unchanged and inference disabled. This needs no restart.

Functional activation is separate: actual live source imports atlas_vision3d_web
at startup. Disk replacement does not reload an existing Python module. No reviewed
hot-reload path exists. This package still needs one web-only restart to activate
APIs; no protected ROS/controller restart is required. Do not add dynamic reload or
a duplicate web/ROS process to evade the rejection. Do not publish functional UI
controls before APIs exist.

Keep75% admission and per-sample rejection unchanged. No shutdown exemption,
averaging away spikes, service disabling or scheduling changes. Any future bounded
shutdown-attribution capture would need separately reviewed approval, synchronized
aggregate/PID-starttime/thread/cgroup deltas and safety/rollback coverage. It is
not authorized here and must not be disguised as another deployment retry.

GO: staging preparation only. NO-GO: functional installation/live AI test.
Verified CPU correction: NONE, because attribution is insufficient.

## Focused offline validation

Two PC/WSL tests PASS: existing import retains old routes after disk replacement,
while a fresh interpreter sees new routes; staging/discard preserves exact live
fixture bytes. No ATLAS/ROS/device imports. Previous13 verifier tests reused.
Private Windows evidence: work/shutdown-cpu-prometheus-evidence.json and
work/shutdown-cpu-journal-summary.txt. No raw logs committed.
HTTP/camera-authority/evidence corrections remain in7dba9bd, offline only.
