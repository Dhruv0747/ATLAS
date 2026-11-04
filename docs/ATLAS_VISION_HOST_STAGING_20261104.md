# Inactive Vision host staging — 2026-11-04, 12:28–12:30 IST

Owner-authorized one staging attempt completed PASS. Source0855063; archive
SHA2569c1cd41e12253d67c3291acdaa6035772786bdb11f91d0e4a82f4cf92f0a1ba6.

New boot962c3639-1421-4c3c-8f53-6b42ea465c81; uptime275.46s at initial read.
Jetson192.168.1.16 reachable by authenticated SSH. Fresh software safety evidence:
stop latched, manual-only, commissioning false, zero drive commands/motor speed,
encoders[-5,4,-3,5] unchanged across three samples; MCU LIVE, packet fresh, zero
encoder interval deltas. CPU samples60.10–62.73%; staging admission61.15%,
RAM47.33%, six thermal sources valid, maximum59.75C. This is a bounded observed
state, not an independent physical certification.

Staged ONLY in:
`/home/jetson/project-atlas-migration/vision-host-inactive-0855063-20261104/`.
16 archive files (15 checksum entries plus checksum manifest), all regular0644,
under private0700 staging. Additional local STAGING_RESULT.json records identities
and exact original metadata. No Python payload was imported or executed.
Config enabled=false; service remains a template with unresolved @VERSION@,
Restart=no, no Install section. No unit registered, enabled or started; no new
socket, DDS participant, viewer lease or camera created by staging.

Original Web adapter and packaged rollback byte-for-byte match:
2551d6578aa9429ac8f4fd5ff35f2c16a185c3cd027fafc563b7fff339857190.
Production file unchanged; mode0644 uid1000 gid1000,
mtime_ns1792903589200609668. Exact backup remains in staged rollback directory.
Rollback for this inactive operation requires only removal of the recorded
staged additions, after verifying their identity; no production restoration or
restart is required. No completed functional test suite was repeated.

Service identities unchanged before/after staging:

| Service | PID | Restarts | State |
|---|---:|---:|---|
| Dashboard Web | 2124 | 0 | active |
| Recovery | 2027 | 0 | active |
| Mux | 1919 | 0 | active |
| Yahboom | 3373 | 1 | active |
| Existing CSI camera | 1937 | 0 | active |
| Monitoring exporter | 0 | 0 | inactive |
| Monitoring watchdog | 0 | 0 | inactive |
| Monitoring firewall | 0 | 0 | failed |

## Activation remains gated

Object Detection and read-only Tracking are OFFLINE READY, not LIVE. The running
Web process lacks cached-rgb; no safe no-restart module loading method is verified.
A Web-loading procedure must first have independent safety coverage during HTTP
downtime and strict CPU admission, then separate restart authorization. The new
host's guard consumes Web and cannot supervise Web's own outage. No hot-patching
or Recovery/Mux experiment was attempted. Real host/inference CPU and engine
memory/task-limit compatibility remain unmeasured.

Subsequent distinct gates: cache endpoint acceptance without a camera (must reject
missing cache), bounded host activation with disabled inference and SSH access
verification, then separately approved stationary camera/inference session under
the existing 60-second camera/30-second feature bounds. All safety limits stay.

## Owner-requested reboot monitoring check (read-only)

Current-boot journal12:23:12IST: firewall guard rejected with exit78/CONFIG,
then watchdog/exporter startup failed by dependency. Prometheus target DOWN,
connection refused. Grafana database health OK. This supersedes the earlier live
state for the current boot; earlier successful recovery evidence is preserved.
The journal directs inspection of the private fault latch, but noninteractive
sudo denied access. Exact retained rejection reason remains UNKNOWN; do not
assume this is the original M2 reason without reading current evidence.
No latch, firewall, service or monitoring configuration changed.
