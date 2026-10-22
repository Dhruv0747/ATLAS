# ATLAS reliability optimization — first bounded checkpoint, 23 October 2026

Branch: `agent/reliability-optimization-20261023`, based on `ee97d85`.
This is NOT a completed whole-system audit or autonomous-navigation qualification.
No production deployment, restart, camera Start, ROS participant creation,
permission change, steering change or movement occurred.

## Current evidence and boundaries

Git fetch completed; origin continuation branch still points to ee97d85.
Existing developer branches were inventoried without merging or resetting them.
The localization-motion branch ends at 248d42c; its historical handoff is not
permission to replace the newer continuation baseline. Existing untracked
diagnostic artifacts and unrelated USB-validation work were left untouched.

Wi-Fi SSH at 192.168.1.15 timed out; existing Tailscale SSH worked. No network
changes. Jetson uptime showed a recent boot. Fresh one-second admission sample:
CPU 68.1431%, RAM 69.1883%, maximum reported temperature 57.125 C. Policy:
manual-only, commissioning disabled, stop latched (joystick unavailable),
STOPPED source, zero commands, recorder OFF. Subsequent sensor preflight failed
with `Astra identity/access changed`. This does not identify which identity or
ACL condition changed; do not declare ACL loss proved from this generic error.

Read-only process inspection found no llama-server, ollama or Astra driver
process beyond the search command itself. This is a point observation, not
proof that AI inference never duplicates. sudo still requires a password.
The previously identified process-stack profiling access problem remains a
blocker to the dominant dashboard CPU investigation.

Six inspected services active, zero reported restarts:
dashboard PID2096, voice2131, agent-team2141, local-LLM broker2948,
authoritative EKF2946, shadow EKF2947. Lifetime ps CPU: dashboard32.6%,
camera27.3%, voice17.7%, update-manager14.4% of one core. These are NOT matched
interval measurements and must not be added to the one-second whole-machine
sample. No background process was killed or reprioritized.

## Duplication audit: observations, not deletion instructions

Static AST inventory of top-level scripts found 390 subscription call sites,
including33 dynamic-topic sites. Literal-topic consumers: /scan29 files,
/odom17, /atlas/control_policy5, /atlas/encoder_health6. These counts include
offline/commissioning tools and omit dynamic expansions. They do NOT represent
simultaneously running subscriptions or unnecessary duplication.

| Area | Finding | Decision |
|---|---|---|
| Language AI | Broker already unloads model after15s idle; read-only inference and existing admission checks | Preserve; no duplicate idle-unload mechanism |
| Voice | Existing local speech/fallback and shared local-LLM client; companion's cloud path checks wake phrase after transcription | Preserve; independent offline wake recognition is not certified by this source review |
| Agent role board | Re-parses unchanged policy, encoder-health and recovery JSON every snapshot | Small parse-only cache prepared below |
| Visual Cloud | Already has viewer/activity gating and slower idle publication | Preserve; do not replace diagnostics with web automation |
| EKFs | Authoritative and explicitly shadow candidate services both active | Distinct roles; not evidence of accidental duplicate authority |
| Camera/tracking/fusion | Camera publisher, tracker, annotator, person fusion and active-vision adviser active | Distinct functions; no duplicate decoding/inference proved |
| Raw sensor fan-out | Many source subscriptions including safety and temporary tests | Do not consolidate or remove without runtime dependencies and timing evidence |

No service or sensor subscription was removed. No stale script was deleted.
Reporting, conversational AI, perception, remote control, sensor fusion and
safety interfaces are retained.

## Offline candidate: cache parsing, NOT freshness

Only runtime source changed: `project_atlas/scripts/atlas_agent_team.py`.
The role board now retains the parsed result for each of the three structured
report roles when its exact text is unchanged. At most three cache entries;
existing16384-character input limit remains. Invalid/non-object JSON caches
an empty dictionary, never the previous valid report. Every snapshot still
checks receipt age and every received update still refreshes its timestamp.
Readiness decisions, publication period, QoS and subscriptions are unchanged.
Cache contents are only inspected, never returned as mutable public state.

This is confirmed redundant parsing elimination, not the cause of the two
expensive dashboard threads. Do not prioritize a service restart for this tiny
candidate over obtaining meaningful thread profiles.

## Tests and performance

-7 role-board tests pass in Windows Python3.13 and WSL Python3.10: readiness,
 invalid JSON, changed reports, stale data, unchanged report reuse and bounds.
-2000 deterministic differential update/time cases match baseline snapshots.
-23 local-LLM tests and12 agent-core tests pass in WSL (42 unit tests total).
-Windows local-LLM test collection failed because requests is absent; the
 existing WSL environment passed. No package installed on Jetson or PC.
-Benchmark uses AST-extracted update/snapshot methods; no ROS initialization.
 Seven alternating runs,20000 snapshots/run, identical repeated status payloads.

| PC synthetic metric | Baseline | Candidate |
|---|---:|---:|
| WSL median CPU microseconds/snapshot |8.5196904|5.8817784|
| WSL traced peak Python bytes (warm cache) |2822|1908|
| Windows median CPU microseconds/snapshot |8.59375|7.03125|

WSL reduction30.96% of this small function; Windows18.18%. Warm traced peak
excludes persistent cache allocation and is NOT a process-RAM improvement.
At the default0.5Hz timer, WSL saved only~1.32 microseconds CPU per second;
there is no credible claim of meaningful whole-Jetson CPU headroom. High-rate
status service calls were not measured live. Whole-Jetson before/after CPU and
RAM savings are NOT measured because nothing was deployed.

Reproduce: `python3 project_atlas/tools/diagnostics/benchmark_role_report_cache.py`.
The script compares against ee97d85 and asserts all2000 differential cases.

## Localization and Astra readiness

Historical localization jumps and wheel/IMU disagreement remain unresolved;
this reporting-only change cannot fix or validate AMCL, TF or moving odometry.
No drive replay or physical test repeated. Existing historical failure registry
and safety gates remain in force. Astra readiness is NOT established: current
identity/access preflight failed, and one68.14% sample does not establish enough
sustained CPU headroom. Existing75%/80%/70C safeguards are unchanged.

## Deployment and rollback

Live role-board SHA256 exactly matches baseline Git blob:
`07919f80e95a2c7f480d333a08d34e672bd0cb71175d9f4b0146f397f16191bc`.
Candidate is source-only; no installation package or runtime activation.
Before any later deployment: reverify exact baseline, safety and dependencies,
back up live bytes, hash the approved candidate and obtain owner approval for
the necessary agent-team restart. Restore the backed-up file and restart only
that service if approved deployment health checks fail. No live rollback is
needed now. Git changes are reversible independently of other ATLAS work.

Next necessary work: administrator-assisted bounded thread-tagged dashboard
sampling, with matched no-profiler/profile windows and no global ptrace-policy
change. Separately investigate the fresh Astra access error read-only before
proposing any permission repair. Do not launch a camera to test access.

Files changed: this report, README, CHANGELOG, current blockers,
atlas_agent_team.py, test_atlas_agent_team_status.py and
tools/diagnostics/benchmark_role_report_cache.py. No live services modified.
