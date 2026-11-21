# ATLAS local voice recognition evaluation

Added 2026-10-09 as a lower-priority track to the reliability program. This is a plan, **not an installed Whisper implementation or completed benchmark**. BMS Bluetooth, motor timing, encoder and localization gates remain ahead of it. No rover movement, model download, service restart or control-path change is authorized by this document.

## Current baseline to preserve

`project_atlas/scripts/atlas_voice_companion.py` records clips from the ESP32-S3 USB interface and posts them to the cloud `/audio/transcriptions` endpoint (default `gpt-4o-mini-transcribe`). It checks the wake phrase *after* transcription. Thus spoken commands currently need internet, even though local telemetry responses, Piper speech output and optional stopped-only local text reasoning have offline elements. The retired VC-02 bridge is under `services-disabled`; do not mistake it for the active recognizer. Preserve microphone privacy/mute, echo suppression, ignored-speech filtering, action confirmation, safety mux and remote B priority. Verify exact deployed configuration before benchmarking.

At the Oct9 stopped-runtime check, `atlas-voice-companion.service` was active with PID 2068 and zero reported restarts. This is a service-health snapshot, not an ASR accuracy or offline-command pass.

## Candidate comparison, only after reliability gates

1. Capture a consented, labelled **local** test corpus through the existing microphone: quiet/noisy and near/far English, Hindi and Hinglish; wake phrases, ordinary commands, confirmation/cancel words, silence and background speech. Keep private audio out of Git.
2. Run the same clips through the current cloud recognizer and candidate local Whisper/faster-whisper `tiny` and `base` multilingual variants. Before installing a runtime on Jetson, verify its exact JetPack/CUDA/ARM64 compatibility and licenses; do not assume a desktop package will run there. A PC experiment may rank candidates but cannot establish Jetson performance.
3. Compare word/character error by language and code-switching, wake false accepts/misses, command/confirmation classification, end-of-speech-to-text p50/p95 latency and failure under lost internet. Never count recognition alone as successful safe actuation.
4. On Jetson, measure idle and active CPU/GPU, peak/available RAM, temperature, and *control-relevant* motor-heartbeat, sensor-age and Nav2/TF timing with and without local ASR under the same workload. Start with offline replay and stationary tests. Reject a candidate that violates existing safety deadlines, starves navigation, weakens privacy or gives no meaningful recognition/offline benefit.
5. If a candidate passes, make a bounded, reversible **ASR-only** selection with the present recognizer retained as fallback. Do not replace the wake/intent safety gates or let model output command motors directly. The Jetson must still function when the Windows PC is off; report accurately whether voice works without internet.

## Decision and report

Record source/config commit, Jetson software version, model/runtime/version, corpus size, per-language results, resource/timing distributions, network-failure behavior, exact rollback and limitations. The decision is **not to deploy yet**: there is no comparative corpus or Jetson load evidence, and active reliability faults take priority.
