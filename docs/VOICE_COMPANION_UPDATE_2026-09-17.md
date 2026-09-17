# ATLAS voice companion — deployment and verification

## Existing features retained

ESP32-S3 USB audio, buffered playback, English/Hindi Piper voices, cloud
transcription/conversation, camera commands, Key2 long-press shutdown, and
exclusive AI/intercom ownership. No speaker firmware was flashed.

## Changes

Fresh-data-only deterministic status answers; truthful once-per-boot greeting;
debounced battery/sensor/stop/mission announcements; explicit software microphone
mute persisted across voice-service restarts; dashboard controls and LED/privacy
legend; no invented camera view or physical action completion. Voice question
recognition still uses cloud transcription, including wake-phrase recognition.
Unaddressed background transcripts are no longer published into the dashboard.

Added `/atlas/voice/stop` (Empty, latch-only) and `/atlas/control_policy` (String
JSON, read-only). Existing mux/remote safety remains authoritative. No voice reset
path exists. Voice driving defaults disabled until separately commissioned and
does not override manual-only mode or the encoder/IMU qualification gates.

## Verification

- 26 voice policy/control tests pass locally: stale/invalid data, BMS inner and
  transport age, bilingual battery status, GPS loss, strict confirmation,
  no accidental camera action from weather/generic words, stop-before-cancel,
  software mute persistence/queue clearing, firmware-compatible red mute,
  no cloud fallback when offline-only TTS fails, and guarded motion requests.
- Existing 10 remote-stop tests pass; remote reset logic was not modified.
- Initial 22-test suite also passed on the Jetson before service restarts.
- Both installed local Piper voices generated audio with HTTP calls forbidden:
  English 3.06 s audio / 3.85 s generation; Hindi 3.15 s audio / 7.11 s generation.
  These are synthesis checks, not microphone recognition or listening-quality
  measurements. Speech stays buffered to preserve the earlier stutter repair.
- Read-only 18-second ROS check observed no nonzero `/cmd_vel`. Fresh policy
  reported `manual_only=true`, `stop_latched=true`, source `STOPPED`.
- Browser-tested MUTE AI MIC acknowledged `MUTED`; the preference persisted
  across a voice-service restart. ENABLE AI MIC restored an `ACTIVE` acknowledgement.
- Voice, intercom, command mux and web services active; autostart enabled.
  No automatic voice-service restarts observed (`NRestarts=0`). Voice service
  memory measured about 56 MiB after startup, excluding synthesis peaks.
- Startup greeting was logged once for this OS boot; it did not repeat after
  the subsequent service restart. Voice stop state can still be announced again
  after service startup. No wheel/camera movement was requested in validation.

## Deployment

Changed only the voice companion, its new pure policy helper, the mux's additive
stop/status interface, web companion UI, and intercom privacy text. Existing
navigation parameters, live EKF inputs and firmware were not changed for this task.

Runtime files: `/home/jetson/project_atlas/scripts/`.
Rollback copies: `/home/jetson/project-atlas-migration/voice-backup-20260917/`.

SHA256 at deployment:

| File | SHA256 |
|---|---|
| atlas_voice_companion.py | 1b8c95d05f951f56ae4eca431bdb889d92c2cc795499080be5f813c30936b403 |
| atlas_voice_status.py | 034b4b3c973de91ab3613795333f641dbfa6dcbd8a8ba62d7eecd5e21f5e2bec |
| atlas_cmd_vel_mux.py | 1e82d408b50abdecdf2fd2d6be400aefe5d4fb649440e1bcc48d89ab36d0d143 |
| atlas_status_web.py | 50402e7bef8d4214cb8e7ddb2ba2a0f256aa25338ed8b33beff54a4523224498 |
| atlas_intercom.py | 16d6930b26cd010b8eabefaa6d4f8f8c73615e62977d32851b4bcb9670550b24 |

## Remaining limitations / operator test

1. Say “Hey ATLAS, battery status”, then “Hey ATLAS, बैटरी कितनी है?” and
   confirm audible clarity and recognition. A new live microphone-to-answer
   round trip and two-room intercom listening test require Dhruv's participation.
2. No offline speech recognition/wake engine or physical microphone disconnect
   was added. Mute drops new audio on the host; it cannot recall an already-sent
   cloud request. Intercom is a separate explicitly started capture session.
3. Remote B is the immediate software stop. Voice stop depends on recognition
   and is not a replacement for the remote or a physical emergency stop.
4. No autonomous-drive readiness is claimed. M4/IMU navigation qualification
   and controlled movement tests remain a separate task.
5. Local alerts do not run while intercom owns the speaker, while the voice
   service is down, or while USB is disconnected. Speech is best-effort,
   rate-limited and non-safety-critical; stale/busy announcements may be dropped.
6. AI cannot install packages, self-edit rover code, reset safety latches, or
   invent successful repairs. Mission announcements rely on controller reports,
   not an independent arrival/map-quality measurement.

Source saved in the current working tree. No GitHub push is claimed by this task.
