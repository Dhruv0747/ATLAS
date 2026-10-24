# Isolated Jetson localization comparison: admission abort

## Result

ABORTED before the benchmark child or isolated ROS participant launched.
First admission interval CPU was **79.66386554621849%**, above the unchanged
75% limit. No automatic retry. Actual ARM64 CPU savings remain unmeasured.
The earlier owner's CPU exception covered diagnostic profiling; it was not
applied to this newly authorized comparison with unchanged safety limits.

No production installation, service restart, camera start, recording or movement.
Voice, Dashboard white-glass theme, steering and all production safety limits
remain unchanged. The package exists only in a new migration test directory.

## Preparation

Added an isolated supervisor, inert package builder and four supervisor tests.
11 focused tests passed (4 supervisor, 4 paced harness, 3 candidate contract).
Supervisor verifies package/production hashes, disk headroom, protected service
identities and fresh safety. During a permitted run it samples one-second CPU,
RAM/temperature, sensor and command state, enforces deadlines, and stops only
its owned benchmark process group on failure. No CPU-exception argument exists.
Exclusive trace creation prevents accidental reuse of the same test directory.
The intended comparison was two interleaved pairs of a six-second saved window,
localhost-only Domain 213. No production-domain participant is authorized.

Initial read-only snapshot (before preparation): CPU72.3404%, RAM67.2758%,
maximum temperature59.906C. E-STOP/manual-only/zero commands, recorder/Astra OFF,
fresh required sensors and service health passed. This did not guarantee that
later admission would pass.

Package archive SHA256:
`1e3b8b11450f5a2d10027da30d12ae622a0909b5f50a4a59bb70a22415367d64`.
Manifest SHA256:
`c9bba542412a71aaeb60bd45b17d157416c4fe4e0e7cad600e8af16640bb90b2`.
Both verified after transfer. All manifest-listed input/source/production hashes
passed before admission. No production source was replaced.

## Abort evidence and postflight

Remote retained directory:
`/home/jetson/project-atlas-migration/localization-arm64-20261024-szE6NL/`.
Private PC copy: `artifacts/localization_arm64_20261024/`.

- result.json SHA256:
  `0f6d0712d91ace11329642676e89a9ffbd60d4f10261bf37b4df186c56bfb97f`
- guard-trace.jsonl SHA256:
  `01c8e69c9bfdbf8c5ea6b6066edde5209af2bb1968a0387aa64d0cadbf736efe`
- Single baseline interval1.000826769s, monotonic38760.197981394,
  CPU79.66386554621849%. CPU failed before RAM/temperature sampling in that
  interval. No benchmark-result.json or benchmark process was created.
- Protected PIDs/NRestarts unchanged: camera1858/0, telemetry3351/1,
  mux1852/0, EKF2982/0, AMCL8060/7, LiDAR7887/12, web94624/0,
  voice108742/0, safety119178/0, localization monitor1948/0. All active.

Separate read-only follow-up: CPU71.8855%, RAM65.2272%, temperature59.75C;
latched E-STOP/manual-only/zero commands, recorder/Astra OFF, fresh sensors and
zero wheel-output commands confirmed. Voice/UI/safety-source hashes unchanged.
This was a recovery snapshot, NOT a retry or proof that the spike disappeared
permanently. The profile does not identify the source of this CPU spike, so do
not attribute it to the candidate (which never ran) or to hashing without evidence.

## Remaining work / rollback

No production rollback is needed. Retain inert test files and evidence; they
have no service/autostart integration. The candidate remains OFFLINE ONLY with
the previous PC results, not Jetson-qualified or deployment-ready.
An additional bounded attempt requires owner direction; preserve normal production
limits regardless. Do not repeatedly launch until a favorable CPU sample occurs.
No manual drive or Astra test is needed to resolve this benchmark blocker.
