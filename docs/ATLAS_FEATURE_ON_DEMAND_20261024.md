# On-demand AI features — built and tested offline, NOT installed

**Owner request (24 Oct 15:00):** AI features should start when needed and stop automatically when not used.
**Status:** manager, config and systemd unit written; 15 unit tests + 8-check ROS integration test pass. Nothing is
installed on ATLAS; installation needs a separate approval.

## What is managed (fixed allowlist in code)

| Unit | Wakes on | Idle before stop | Measured cost 24 Oct (% of one core) |
|---|---|---:|---:|
| atlas-ai-annotator | autonomy, Dashboard AI object mode with viewer, follow-person, tracking | 300 s | 8.9 |
| atlas-agent-team | autonomy | 300 s | 8.6 |
| atlas-person-sensor-fusion | autonomy, follow-person | 300 s | 5.0 |
| atlas-follow-person | follow-person enabled (command replayed after start) | 120 s | 4.6 |
| atlas-experience-store | autonomy | 300 s | 4.2 |
| atlas-active-vision | active-vision request (replayed) | 120 s | 3.4 |
| atlas-vision-lidar-fusion | autonomy (feeds Nav2 semantic obstacles) | 300 s | 3.0 |
| atlas-camera-tracker | camera tracking enabled (replayed) | 120 s | 3.0 |

Total while parked/manual ≈ 40% of one core ≈ **6–7 points of whole-Jetson CPU**. During autonomous navigation the
autonomy features run (they are needed), so there is no saving then.

**Not managed, deliberately:** voice companion (the wake phrase is checked on the Jetson after transcription of
clips from the ESP32, so it must always run), local LLM (voice offline fallback), agent supervisor, visual-cloud
agent/server (own viewer-based demand logic; ~1.4%), and every safety, motion, sensor, localization, camera and
Dashboard service.

## Safety design

- "autonomy" = control policy `manual_only` false, OR mission not READY, OR either topic stale/missing →
  **fail-open** (unknown means features on).
- Boot grace 300 s; minimum on-time 60 s; idle timers per feature; state checked every 15 s (not per second).
- Never starts camera tracker / follow-person while a mapping session (`atlas-slam-fast`) is active — mission
  control owns those during mapping and restarts only what it stopped.
- Replays only the owner's latest follow/tracking/active-vision command, only if < 60 s old and still the latest.
- systemd unit: `Restart=always`; `ExecStopPost=… restore-all` starts every managed unit if the manager stops or
  crashes (= today's always-on behaviour). Not ordered after `default.target` (avoids the boot cycle documented
  in `atlas-remote.service`).
- Only `start`/`stop`/`is-active` are ever called; never restart/enable/disable/mask; no unit files edited.
- Dependencies checked against the live sources: no Requires/BindsTo/PartOf on these units; sensor recovery does
  not monitor them; their outputs feed the Dashboard display, voice chatter, an INFO field in safety status, and
  `/camera/semantic_obstacles` (Nav2 obstacle source without `expected_update_rate`).

## Files

`project_atlas/scripts/atlas_feature_on_demand.py`, `project_atlas/config/atlas_feature_on_demand.yaml`,
`project_atlas/systemd/user/atlas-feature-on-demand.service`.

## Tests

- `tests/test_feature_on_demand_unit.py` — 15 pass: fail-open (no/stale/invalid policy, unknown mission),
  autonomy triggers, trigger windows, replay never invents and expires, boot grace, idle stop, needed-feature
  start, min-on time, mapping guard, always_on, allowlist excludes essential services, config cannot add units or
  invalid triggers, repo config loads, restore-all starts all, unit file fail-open/no boot cycle.
- `tests/fod_ros_scenario.py` (private netns, real rclpy topics, fake systemctl) — 8/8: parked → all stopped;
  follow-person on → exactly its 3 features start, others stay off, command replayed after start; autonomy →
  fusion features start; policy silent → fail-open restart; manager stopped → restore-all brings all back; no
  restart/enable/disable calls.

## Known trade-offs (owner should accept before install)

- Start-up delay: a feature needs a few seconds; AI detections ~20–25 s (YOLO warm-up built into the annotator).
- Voice "what do you see" while parked gets no detections until AI object mode/another trigger wakes the annotator.
- Experience store and agent team are off while parked; they come back with any autonomy/mission.

## Install (needs separate approval; not done)

Copy the 3 files, `systemctl --user daemon-reload`, `enable --now atlas-feature-on-demand`; boot grace means nothing
stops for 5 minutes; verify; rollback = `systemctl --user disable --now atlas-feature-on-demand` (ExecStopPost
restores all features).
