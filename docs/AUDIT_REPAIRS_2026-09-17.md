# ATLAS audit repairs and local-LLM decision — 2026-09-17

## Scope and evidence

Software-only repair of confirmed faults. ATLAS was stopped with `manual_only`
and the remote stop latch both true. No motors, steering, camera servos, mission
goals, navigation parameters, IMU calibration, or encoder scale were commanded
or altered. Three-encoder commissioning remains incomplete; M4 feedback stays
excluded, not its motor output.

The old recovery process parsed only the first 240 characters of a roughly
475-character `/atlas/encoder_health` JSON message. A fresh `DEGRADED` report
with no faults and M4 explicitly excluded became invalid JSON and triggered
`rover-base-telemetry.service` restarts. Runtime logs reproduced this before the
repair. This is evidence for one avoidable source of communication interruptions,
not proof that every historical encoder or navigation failure had this cause.

## Changes

1. **Recovery:** retain bounded full structured messages; validate object/state;
   truncate only displayed details. Keep existing legacy text-monitor behavior
   for other sensors. Stale/invalid data still faults. Motor-link restarts need
   fresh stop-latch evidence and at least two seconds of fresh zero commands.
   Recheck the guard after service queries; cancel if data recovered meanwhile.
   Zero command is not independent proof of physical wheel standstill.
2. **Voice:** a recognized standalone English/Hindi wake phrase receives a short
   local acknowledgement. The eight-second command window begins after playback
   and echo suppression; transcription latency does not invalidate a command
   captured in that window. Empty/ignored/privacy-discarded turns clear the
   TRANSCRIBING stage. Recheck privacy after synthesis; report specific TTS errors.
   Buffered playback and all existing motion/remote-stop gates are preserved.
3. **Agent role board:** fresh communication is shown separately from readiness;
   existing control policy, encoder qualification, readiness and recovery reports
   determine the displayed readiness. This is read-only reporting, not new authority.
4. **Visual Cloud:** reliable transient-local map/static-TF subscriptions support
   late joiners. Retained snapshots show CACHED and true receive age, without
   pretending that a static map publishes continuously. The overlay is explicitly
   marked unverified for frame alignment; TF panel shows latest received samples,
   not a complete time-buffered TF tree.

## Validation and deployment

- Reviewed targeted pure tests only; never ran broad test discovery because some
  legacy test scripts can actuate hardware on import.
- Test coverage includes long DEGRADED JSON, malformed/non-object/oversize data,
  stale feedback, missing/stale/moving/NaN stop commands, stop latch requirements,
  cancellation of unnecessary recovery, and a simulated legitimate recovery.
- Voice regressions cover English/Hindi acknowledgement, no cloud fallback for
  offline speech, privacy, ignored speech, transcription latency, motion guards,
  remote stop and existing status replies. All robot publishers are mocked.
- Python syntax checks and Visual Cloud JavaScript parsing passed.
- Final targeted regression count: **50 passed** (10 recovery, 32 voice,
  4 role-board readiness, 4 Visual Cloud statistics).
- English acknowledgement generated locally in 1.973 s (2.069 s audio); Hindi
  in 2.413 s (1.825 s audio). Both cached without playback or a cloud request.
- A 45-second stationary post-deployment observation received 418 encoder-health
  messages, 1,534 zero velocity commands, and no nonzero command. Base PID 50434
  was unchanged; recovery reported no attempts and no false encoder fault.
- Agent board reported communications online but autonomy not ready, with the
  actual manual-only, stop-latch and commissioning reasons.
- Visual Cloud received the retained 187 x 218 map and static TF. This verifies
  data delivery, not geometric overlay correctness or map suitability for driving.
- Last sample in that observation: CPU 74.1%, RAM 4,649 / 7,620 MB (61%), 61 C.
  Earlier CPU samples were roughly 70–76%, with a 95.1% diagnostic-time sample.
  These are workload observations, not an LLM benchmark or thermal certification.
- A second 45.02-second check after the final stop-latch and voice-window changes
  received 440 encoder-health messages and 1,570 zero commands, with no nonzero
  command. Base PID was still 50434 and recovery attempts remained zero. Final
  resource sample: CPU 75.4%, RAM 4,816 / 7,620 MB (63%), 61 C. Voice USB was online,
  state IDLE, and intercom mode `ai_voice`. Manual-only/stop-latch remained true.

Deployed script changes are in `/home/jetson/project_atlas/scripts/` and use the
existing enabled user services. Backups are in
`/home/jetson/project-atlas-migration/software-fixes-20260917/backup/`.
The recovery, voice, role-board and Visual Cloud agent services were restarted;
the motor base, mux, EKF, Nav2 and sensor-hub services were not restarted by this
deployment. No new GitHub push or reboot-validation is claimed in this record.

All six deployed source files matched their local SHA-256 and original runtime
file permissions were retained. Existing recovery/voice/role-board/Visual Cloud
agent user services were verified enabled for autostart.

| Deployed file | SHA-256 |
| --- | --- |
| `atlas_sensor_recovery.py` | `5056bbf5eb5258973dd1fc08be4ef8f798e904a9a544f4d7e6e198b29b365efd` |
| `atlas_voice_companion.py` | `26831f81ddf61a78d2a6dea5bc9198ab2bbdea132f016d05f9d589756c457896` |
| `atlas_agent_team.py` | `07919f80e95a2c7f480d333a08d34e672bd0cb71175d9f4b0146f397f16191bc` |
| `atlas_visual_cloud_agent.py` | `dc4a0294e78d580e6d59d6cbc04be7b2e50473230d5c05865f640e29aa637f28` |
| `atlas_visual_cloud_core.py` | `2242f6320172ea465f33e8619dced98d3b3223f955d1ab144f6c7d5eb2593ce3` |
| `atlas_visual_cloud_dashboard.html` | `43655dfea00f055f825d412e9932d287bc103305ccbe05f5c41f48dd8754e6f5` |

## Local LLM: useful, but not the current fix

A small local language model can help with offline conversation, interpreting
natural-language requests and summarizing retrieved logs. It does not replace
Nav2, verified sensor data, motor feedback, deterministic watchdogs or explicit
command authorization. It cannot obtain live internet facts while disconnected.

No local LLM, model download, new serving runtime, offline ASR or new wake-word
engine was installed. Existing Piper speech synthesis is local; recognition and
general conversation remain cloud-dependent. An LLM alone cannot make the whole
microphone-to-response path offline.

**Decision:** keep navigation headroom first; evaluate one small on-demand model
later, not several always-running agents. Benchmark Hindi/Hinglish accuracy,
end-to-end voice latency, RAM/GPU peaks and ROS timing under the real navigation,
camera and dashboard workload before allowing simultaneous operation. The test
must compare idle versus model-loaded versus actively generating, and must
reject a setup that increases feedback staleness, TF errors or control deadlines.
Do not assume systemd CPUQuota is enforced: this host's user cgroup CPU controller
was unavailable during the audit. Memory, queue limits and real measurements matter.

[NVIDIA's local assistant example](https://www.jetson-ai-lab.com/tutorials/reachy-mini-jetson-assistant/)
demonstrates an optimized local voice/vision stack on Orin Nano 8 GB; it does not
prove that the same stack fits alongside all ATLAS workloads. The
[OpenAI Docs voice-agent guide](https://developers.openai.com/api/docs/guides/voice-agents)
separates speech recognition, language reasoning and speech generation in a
chained architecture. These layers must be evaluated separately here as well.

## Remaining work / limits

- Physical wake/microphone/speaker response and noise robustness need operator
  confirmation. Silent synthesis and mocked logic tests are not end-to-end audio.
- The obsolete root `atlas-ptz-home.service` still points to old direct Jetson
  I2C camera control. It was failed/not running, but remains enabled: the attempted
  disable required an administrator password unavailable to this session. It
  still needs `sudo systemctl disable --now atlas-ptz-home.service` on the Jetson.
  No password was requested in chat, no privilege bypass was attempted, and no
  legacy camera-homing script was run.
- Full Visual Cloud TF accumulation/frame-aligned rendering and truthful
  event-driven/idle navigation-link semantics remain future observability work.
- IM10A production EKF fusion, measured three-encoder distance/turn/stopping tests,
  and repeatable room-to-room/return-home validation remain separate physical tests.
- The stationary observation is not a long endurance test or a guarantee that
  USB/power/hardware faults can never recur. Keep the remote stop authoritative.
