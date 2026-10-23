# Voice executor deployment — 2026-10-24

## Result

DEPLOYED, installed hash and parked health verified. Only
`atlas-voice-companion.service` restarted. Owner separately authorized CPU-report-
only for this installation. Production75% CPU/80% RAM/70C limits unchanged;
RAM, temperature, policy, freshness and service checks remained enforced.
Astra OFF, recording OFF, E-STOP latched, commands zero, manual-only enabled,
commissioning disabled. No movement, calibration, UI or other service change.

Reviewed candidate from673e6b5a77121135578acf80c12e2a49f37ffeb7:
`/home/jetson/project_atlas/scripts/atlas_voice_companion.py` installed SHA256
`a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870`.
Fresh original matched
`37f275ddb5e259466b909b0da2654fdaaf8a06b06cf02d969813c8affc0c2f72`.
Manifest verified `aeec7b5f7f585f497852e25baab2a446352b5817b057c3aa9571536f8c0ce91a`.
Existing private executor helpers, Dashboard source, white-glass CSS and both
stationary safety modules matched their reviewed hashes before/after.

## CPU and resource result

Twenty health samples per parked window with persistent1-second CPU telemetry
started before restart. Voice was already MUTED; this privacy setting remained
preserved. The post window followed bounded recovery to fresh MUTED heartbeats.

| Metric | Before | After |
|---|---:|---:|
| Window seconds |24.125|23.942|
| Whole-Jetson mean CPU % |71.399|71.469|
| Whole-Jetson sampled peak CPU % |74.959|78.583|
| Voice process CPU, % one core |25.161|24.016|
| Maximum RAM % |68.391|69.568|
| Maximum temperature C |59.406|59.500|

Voice process observed reduction1.144 one-core percentage points (4.55% relative).
Whole-system savings NOT demonstrated: mean slightly higher and a78.583% peak.
No rollback for that CPU-only peak under explicit installation exception; it
would exceed the unchanged production camera admission limit. No Astra
readiness or end-to-end active-conversation performance claim. Short sequential
windows cannot establish causal/system-wide or sustained savings.

## Service recovery and observed shutdown issue

Voice PID2021 ->108742, final active/Result=success/NRestarts=0. USB ONLINE,
fresh heartbeats and preserved MUTED state verified. Existing automatic battery
and stop announcements ran during recovery, then returned to MUTED; they were
not newly commanded by the installer. Audible quality/wake-word/conversation
were not physically tested.

The OLD PID2021 emitted an RCLError on its system rclpy WaitSet during shutdown:
context invalid after shutdown. This occurred before the new process started;
not a new-candidate startup failure. Preserve it as unresolved shutdown-race
evidence; do not claim the new adapter fixes every shutdown interleaving. New
PID startup and postflight show no corresponding exception/restart loop.

Protected PIDs/restart counts stayed active and unchanged:
Pi Camera1858/0, telemetry3351/1, mux1852/0, EKF2982/0,
localization8060/7, LiDAR7887/12, Dashboard94624/0. Historical restart counts
were not introduced here. Existing seven offline candidate tests and820000
message benchmark reused; installer compiled offline and live guarded checks
passed. No physical drive or camera test performed.

## Evidence and rollback

Remote evidence:
`/home/jetson/project-atlas-migration/voice-deploy-20261024/evidence-ikiqa0lr/`.
Backup `atlas_voice_companion.original` verified against original hash above.
`result.json`: `83f045056dd19521fdb909cd5e28e531711b8b79646d7cc71510e0de14588ae1`.
`trace.jsonl`: `cb60c0f82863869d3b197917b8f8ca8920d884c3081fb40a92dce2708e7a1736`.
Local copies: `artifacts/voice_executor_20261024/deployment-result.json` and
`deployment-trace.jsonl`; raw runtime artifacts are not committed.
One-shot installer preserved in parent directory as `install_once.py`.

Rollback if separately needed: verify original backup and current candidate
hash; restore only that voice file preserving its original mode; restart only
voice; verify fresh heartbeat, USB, privacy, resources, protected identities and
safety. Do not remove shared Dashboard executor helpers. No rollback needed
on this attempt. Previous profiler manifests intentionally reject the now-changed
voice source; update/review them before any future approved capture.

Remaining: sustained whole-system headroom, active voice operator validation,
and separately approved Astra testing. The overall CPU problem is not resolved.
