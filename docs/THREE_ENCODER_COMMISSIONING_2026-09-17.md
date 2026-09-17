# Three-encoder commissioning — 2026-09-17

## Decision

M1 rear-left, M2 rear-right and M3 front-left are the selected feedback channels.
M4 front-right feedback is faulty and explicitly excluded; its drive motor is
unchanged and remains usable. Three working encoders can support autonomous
navigation; requiring replacement of M4 before *any* further commissioning was
too restrictive. This is reduced-redundancy operation, not a repaired encoder.

## Changes

- Persistent `project_atlas/config/encoder_selection.yaml`: exclude M4, require
  measured navigation validation, encoder packet timeout 1.0 s.
- Correct physical wheel topic/channel mapping; no motor polarity/steering change.
- Atomic counts/receipt timestamp in the existing Yahboom library. A live ROS
  callback repeating cached counts no longer proves encoder packet freshness.
- M4 is never reconsidered automatically, even if its raw count changes.
- Use median per-wheel distance increments, not differences of cumulative
  medians. Selection changes and stale/reconnect intervals cannot create a
  catch-up position jump. Fewer than three accepted channels yield no integrated
  motion; uncertainty increases and autonomous feedback readiness is false.
- A second selected-encoder fault or stale link blocks autonomous commands.
- Dashboard displays selected/excluded channels, packet age and validation reason.
- Existing B emergency-stop latch, remote controls, manual-only configuration,
  LiDAR and other obstacle protections remain unchanged. No motion commands sent.

## Tests and deployment

- 76 offline regressions passed: encoder selection/odometry, actual mux gate,
  motor-output mapping, remote stop, camera mapping/link, serial queue, voice
  safety and IM10A bias/navigation-exclusion tests.
- 37 changed/new Python files passed syntax checks; both dashboard JavaScript
  blocks passed `node --check`. These are standalone ROS Python entry points,
  not changes to a compiled ROS package.
- Before deployment: 8-second observation, 252 zero velocity messages, 69 finite
  odometry messages, zero measured odometry displacement, remote stop latched.
- During deployment: 35-second observation, 532 zero velocity messages, 219
  finite odometry messages, zero displacement and unchanged saved pose.
- Live feedback after restart: selected `[1,2,3]`, excluded `[4]`, `DEGRADED`,
  fresh encoder packets (last observed age 0.011 s), no additional faults,
  `navigation_validated=false`, `autonomy_ready=false`, manual-only true.
- Base, mux and dashboard restarted successfully and remain boot-enabled.
- A further 18-second post-deployment check passed: 652 zero velocity messages,
  180 finite odometry messages, zero displacement; encoder packet age 0.039 s
  at the final sample. This is packet freshness, not per-wheel motion proof.
- Deployment exposed an existing recovery interference: `atlas_sensor_recovery`
  restarted the base during its planned startup after 3.6 s without encoder
  health. The interrupted process reported an invalid ROS context; its next
  start succeeded and remained stable. This was not an encoder selection
  exception. No recovery-policy rewrite is included here. Future planned base
  maintenance must coordinate with recovery, and this race needs follow-up.
- Backup: `/home/jetson/project-atlas-migration/three-encoder-20260917/before/`.
  Candidate source and tests are beside this directory. No firmware flashed.

## What is still required

Stationary receipt proves the communication/configuration path, **not** that
three individual wheel encoders are correct under load. Existing per-channel
counts/revolution predate motor replacements. First compare a measured straight
distance with each selected encoder, then low-speed left/right arcs and stopping.
The existing steering-based yaw approximation also needs that ground check.
Only then consider setting `navigation_validated: true` and separately clearing
the manual-only gate for a supervised low-speed Nav2 test. Qualified three-channel
feedback permits reduced autonomous speed; it does not require a fourth encoder.

IM10A production EKF fusion remains unchanged/not enabled by this work. Raw M4
counts are still exposed for diagnosis, never claimed as working feedback.
Individual-wheel fault detection is based on absence of count changes under
traction, not an independent hardware validity signal; coherent shared counter
errors, slip, EMI and mechanical faults still need physical validation.
