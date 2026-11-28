# Voice companion idle-ingress optimization — 2026-10-04

## Finding

With ATLAS stationary, `atlas_voice_companion.py` used roughly 26.8% of one
CPU core. Live thread sampling showed the ROS executor/main thread doing most
of that work; the audio worker was normally blocked and near idle. The LiDAR
and IM10A subscriptions used no message fields and existed only to mark those
streams live, but `rclpy` still constructed full Python `LaserScan` and `Imu`
objects for every sample.

## Bounded change

Only those two liveness subscriptions now request serialized delivery with
`raw=True`. Topic names, ROS types, SensorData QoS, per-arrival freshness,
voice states, USB/audio handling, wake behavior, privacy rules, cloud fallback,
and all motion-authority restrictions remain unchanged. The callbacks never
read the serialized payload.

The deployment also reconciled the already-tested stopped-only local-LLM client
hook that was present in the repository but absent from the Jetson copy. It is
still opt-in through `ATLAS_LOCAL_LLM_ENABLED=1`; the live environment does not
set that variable, so this deployment did not enable or load a local model.

## Validation and deployment

- 33 voice regression tests passed, including an AST guard proving both raw
  callbacks remain payload-independent.
- The script compiled, and the Jetson Humble `rclpy` installation was checked
  to support raw subscriptions.
- The voice service restarted active with zero restarts, reported its USB
  device online, returned to `IDLE`, and continued the normal blue/green status
  cycle and spoken alerts.
- The first post-start sample was about 19.2% of one core versus the earlier
  26.8% lifetime sample. This is an indicative stationary improvement, not a
  long-duration voice/audio benchmark.
- The rollback copy is
  `data/deploy_backups/20261004_cpu_voice/atlas_voice_companion.py.before`.

No drive, steering, navigation, or mapping command was issued.
