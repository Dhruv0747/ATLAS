# Voice-specific executor candidate — offline only, 2026-10-24

## Outcome

Prepared a minimal exact-live-baseline candidate reusing the private executor
already installed for Dashboard. Ten alternating PC comparisons show median
process CPU reduction3.086%,8/10 positive pairs,820000 messages delivered without
errors. This is a modest candidate, NOT a verified fix for whole-Jetson CPU or
Astra startup. Nothing installed/restarted; Astra OFF/no movement requested or
performed. White glass, production safety/resource policy and working services
were not changed.

## Evidence and implementation

The successful voice capture had64/65 GIL samples in MainThread,54 samples
including wait_for_ready_callbacks, and native main-thread CPU approximately
22–23% of one core. It motivates executor bookkeeping work, not disabling speech
recognition, wake word, announcements, AI or QoS events.

Fresh voice source was downloaded read-only. Its SHA256 is
`37f275ddb5e259466b909b0da2654fdaaf8a06b06cf02d969813c8affc0c2f72`.
Repository source has different bytes; it was NOT substituted or blindly merged.
The prepared patch changes only:

```python
from atlas_dashboard_executor import spin as _atlas_voice_spin
# in main(), instead of rclpy.spin(node):
_atlas_voice_spin(node)
```

The entire AtlasVoice class and main exception/finally handling remain unchanged.
The shared adapter creates a private SingleThreadedExecutor for the node's
context and shuts it down in finally; no global rclpy modifications. Dependencies
must exactly match the two already-reviewed installed helper hashes below.
The rejected accumulator experiment is NOT included.

## Voice-derived workload

AST extraction from verified live constructor yielded41 subscriptions,
23 publishers,1-second announcement timer and5-second heartbeat timer. Workload
retains message classes, queue-depth10 QoS and two sensor-data/raw subscriptions
(LaserScan and IM10A Imu). Native ROS2 Humble on WSL Ubuntu22.04,
ROS_LOCALHOST_ONLY=1, domain213. All endpoints renamed /offline/...; no production
domain participation, live control, audio hardware, service restart or network
request. AtlasVoice is never imported/constructed by the benchmark.

Each run sends1000 rounds across41 channels,41000 messages;10 AB/BA pairs total
820000. String payloads are synthetic, scan contains360 ranges. Callbacks check
delivery/raw payload type and latency; they DO NOT execute actual speech/AI
business logic. Publisher creation occurs in the same process as receiver, so
CPU includes publishing and DDS, not just the voice executor. Rates are synthetic
fixed-work bursts, not replayed production timing. Different timer counts and
shared PC load limit precision; no inference of Jetson percentage-point savings.

| Measurement | Original captured executor | Existing private executor candidate |
|---|---:|---:|
| Process CPU total, seconds |14.13636|13.82330|
| Messages delivered |410000|410000|
| Mean of run p95 latency, ms |1.24107|1.21374|
| Maximum observed latency, ms |2.65447|3.47944|

Paired CPU savings percent:4.673,-6.142,3.290,2.195,2.781,6.624,-1.860,
3.564,2.881,3.870. Median3.086%, pooled total reduction2.215%. Worst latency
increased; no safety-deadline guarantee or active-conversation performance pass.

## Tests

Seven focused tests passed: exact subscription/type/QoS/raw/timer inventory;
wrong source hash rejection; unchanged entire voice-class AST; byte-exact inverse
patch; unchanged main shutdown/exception structure; package hashes/original
preservation/no overwrite; native5.25-second timer run proves both original
periods fire and executor cleanly closes. Six initial tests passed; seventh
package check added and full seven rerun. An initial harness attribute collision
was corrected before measurements; no production defect inferred from it.

Previously verified cancellation/QoS/concurrent-shutdown evidence for the SAME
private implementation is reused, not represented as newly repeated. Audio,
mute/wake-word/conversational end-to-end behavior and live resource impact remain
unverified; preservation here is source-level plus executor integration evidence.

## Package, approval and rollback

Local only: `artifacts/voice_executor_20261024/candidate/`.
Candidate atlas_voice_companion.py SHA256
`a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870`.
Manifest SHA256 `aeec7b5f7f585f497852e25baab2a446352b5817b057c3aa9571536f8c0ce91a`.
Required existing files:
- atlas_dashboard_executor.py: `2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab`
- atlas_dashboard_executor_impl.py: `543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1`

Benchmark result local `artifacts/voice_executor_20261024/loaded.json`, SHA256
`1da008b1c6653cc3672896dd4385622c2132d4d4efccbdad7210280079062ca7`.
Generated originals/results are not committed; reproducible builder/tests are.

No production deployment authorized. A future deployment would require separate
owner approval for one voice-file replacement and voice-only restart (brief voice
interruption), fresh safety/resource/hash checks, verified live backup and matched
CPU/voice-health validation. Do not restart Dashboard or remove its shared helper
files. Rollback would restore the exact original voice file, preserve its mode,
restart only voice with approval, and verify health. No rollback needed now.

Actual Jetson savings, active voice behavior, sustained CPU headroom and Astra
readiness remain pending. Do not treat this small offline gain as the complete
CPU solution.
