# Recovery startup type-loading correction — 2026-10-31

Base a2073b4. OFFLINE implementation only; Recovery remains STOPPED. No live
service restart, package deployment, camera/inference/mapping or movement.

## One concrete change

Recovery now loads its existing message type-support libraries before rclpy.init(),
instead of allowing first publisher/subscriber construction to import them while
DDS discovery is already active. Unique required types only; imports fail closed.
Humble's installed rclpy/type_support.py confirms lazy import when _TYPE_SUPPORT
is None and reuse afterward. This is startup phase separation, not reduced DDS
entity count or an executor replacement. No new monitor, observer or benchmark.

All AtlasRecovery method bodies remain AST-identical. Subscription topics, QoS,
raw freshness policy, fault classification, grace period, maintenance coordination,
E-STOP/zero-command checks, watchdogs and recovery limits are unchanged. The new
helper creates no ROS entity, thread, timer, sleep or subprocess.

Repository source differs from actual original Recovery (live has Stage28 base
maintenance integration). Therefore also supply a minimal exact-live unified patch:
project_atlas/tools/vision3d/recovery_type_preload_live.patch
Patch SHA256: eeb827e86955e1e9f615fb1f942d0de0a5ec2937a509902262770b897626659b.
It was generated against verified original SHA256
5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Do NOT deploy the full repository script over the live version. No restoration
package or automatic deployment was built. A future candidate needs a new reviewed
hash; the previous original-code restoration approval does not cover this change.

## Audit findings from actual code and saved interval

Recovery constructs its Node, initializes maintenance coordination, publishers and
subscriptions synchronously, then logs READY. Fault scan has a 30-second grace;
state publisher timer first fires after five seconds. Neither explains the observed
pre-READY/READY interval. Existing raw subscriptions already avoid deserialization.
No repeated Node construction or repeated initialization loop was found.

Read-only inspection confirms Localization is already running (PID4618,
NRestarts0); its launch has map_server/AMCL and delayed Nav2 lifecycle startup.
Recovery does not relaunch Localization. Localization cgroup increase 16.80 to
48.22 percent of one core does NOT prove which callback/DDS operation consumed it.
No basis to defer its safety callbacks, reduce heartbeat/QoS handling, or alter TF.

Saved rejection: Recovery cgroup54.71, Dashboard32.88, mux19.73 percent of one core.
Dashboard fell from38.54; mux rose from17.32. Neither warrants a new optimization
from this interval alone. Existing profiles show executor/QoS work but no confirmed
removable duplicate. Do not count nested PID and cgroup values twice.

Recovery launches through a login shell sourcing ROS. Read-only profile inspection
showed .bashrc returns for noninteractive shells BEFORE ROS sources; no confirmed
duplicate ROS setup there. Accordingly no shell/environment-cache change was made.
No library, parameter-service or subscriber removal is justified by current data.

## Focused evidence / predicted improvement

- Four deterministic tests PASS: unique required types, load-before-init/node,
  import failure prevents ROS startup, no hidden entities/sleep/subprocess.
- Native PC ROS2 Humble check PASS: nine required types load; rclpy remains
  uninitialized; second checks reuse identical type-support handles.
- PC first type-loading CPU time0.016315391 seconds; cached recheck0.000005545s.
  This is a single import check, not a matched Jetson performance comparison.
- AST comparison proves all existing Recovery methods unchanged. Exact-live patch
  inserts only the same helper and its main() call, retaining maintenance code.

Prediction, UNVERIFIED ON JETSON: removes message-library import work from the
post-DDS-initialization phase, potentially reducing simultaneous discovery/import
load. Total startup work is essentially unchanged; steady-state saving expected
near zero. No numerical Jetson CPU saving can honestly be predicted from PC16ms.
This small correction is not demonstrated sufficient to bridge the11.93 percentage
point overload, and does not establish DDS discovery as the root cause.

No safety limit changed: CPU75%, RAM80%, temperature below70C. A true overload
still rejects. Root cause of remaining aggregate contention UNKNOWN.

## Disposition

Offline candidate complete. NO-GO to claim CPU fixed or to restart automatically.
Recovery remains stopped pending separately approved safe restoration. Review this
minimal candidate and retained rejected interval, not another diagnostic framework.