# Exact-live provenance integration — preparation only

Base: 4aba5cf. No live file changed, no subscription, service restart or deployment.
Recovery/Web and monitoring incident untouched. No camera, inference or movement.

## Exact live reconciliation

Read-only copies and metadata captured privately under:
C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/source-provenance-live-20261102
original/ is exact-byte rollback; metadata.json retains uid/gid/mode/mtime_ns/xattrs.
Candidate patch: SOURCE_PROVENANCE_EXACT_LIVE_20261102.patch.

Mux original e70df2baf9f77ef688d253a93f091394b33686f3f88a85ba8d7fd9c9ef6cc033
Mux candidate d297dc75c0862334313f525f9646eac3e882cbeeeffb7eb24070ad648591c463
Base original bb6db3a10c196be55ccd1bcb7bcbbf538643089c1a7bd5fe833f9b45453b473d
Base candidate 6899602d4f98a208daf4cf069042d8bec06f9abf9f823b3d33b300122a5fd780

Live differs from repository: mux has controller selection, FlySky stop/reset handlers;
base has RC report forwarding/frame publication. Preserve these and all other live
changes. Do not replace live publishers with repository copies. Add only reviewed
atlas_source_provenance.py helper and apply exact-live metadata patch.

Offline forward patch matched both candidate hashes; reverse patch restored both
original byte streams. After stripping ONLY added provenance AST nodes, each candidate
matches its original AST. This establishes no unrelated logic change, not runtime safety.

## Existing transport integration

Added opt-in observe_safety/SafetyTransport mode to existing local_bridge_observer.py.
Legacy diagnostic CLI remains unchanged and is not safety authority. Source-only mode
subscribes to control_policy and encoder_health; the six-component published command,
its sequence and timestamp travel inside policy. Unstamped /cmd_vel is unchanged and
is not used to assert source freshness. No camera topics, ROS node, rclpy initialization,
DDS participant, publisher or service client. Reuses pinned existing websocket wheel.
Strict CDR String decoder, frame caps, source identity pinned independently by caller;
bridge envelope time ignored. Original envelopes retained in existing snapshot format.
Existing Consumer can read output while Web is unavailable. Final consumption also
checks raw encoder time, preventing rounded packet age from extending the 1s bound.
Disconnect/unadvertise/timeout/failure removes owned output; no reconnect or retry.
No healthy output until both sources validate. Output expiry<=.75s; source age<=1s;
raw and combined encoder age<=1s. No MCU acquisition/execution timestamp claim.

15 focused new transport checks PASS (14 transport + 1 dependency gate), plus 2 exact-byte forward/reverse and 2 AST
preservation checks. Prior33 tests reused. Independent review PASS after fixing
raw packet-age boundary at final consumption. No live acceptance.

## Remaining gates and rollback

CPU overhead UNKNOWN: small CDR/JSON payloads only, bounded frames/session, no additional
ROS process. No evidence bounds Python/websocket startup cost on this Jetson. Do not
relax CPU<75%, RAM<80%, temp<70C. No session launched to measure it.

Deployment NO-GO until protected-publisher activation plan, package/dependency bindings,
independently verified live process identities and CPU risk are reviewed. Existing web
activation package is NOT rebuilt or activated; its old snapshot helper hash must not
be bypassed. Recovery is not a target and must not restart.

Separate execution approval needed for installation and one bounded restart of
atlas-cmd-vel-mux.service and rover-base-telemetry.service (user services), respectively.
Both are protected control services; approval must name them and define independent
supervision and fail-closed rollback. This document is not an execution authorization.
Later receive-only verification and Web activation remain separately gated.

Rollback preparation: require original/candidate hashes immediately before any write;
restore original exact bytes atomically, with metadata.json uid/gid/mode/mtime/xattrs.
Remove added helper only if it did not previously exist and its installed hash matches.
Do not overwrite later edits. Replacing files does not restore already running code:
any rollback restart needs its own explicitly bounded authorization. No automatic retry.
Private backups are not committed; preserve them alongside any future deployment package.
