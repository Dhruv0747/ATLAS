# ATLAS manual-mapping session forensics — 2026-10-04

## Outcome

The rejected candidate map remains rejected. The accepted map with identity
`d12a1f183177212a3cc8` was not replaced. No steering calibration, steering
limit, steering direction, or steering response was changed during this
analysis.

## Evidence reviewed

- Bag: `fresh_manual_mapping-20261004-193348`
- Duration: 491.165 seconds
- Messages: 100,280
- Filtered LiDAR scans: 3,450
- Camera frames: 4,664
- `/odom` samples: 4,875
- `/yahboom/odom` samples: 4,695
- `/imu/data` samples: 4,695
- `/tf` messages: 13,681
- Remote samples: 9,227

The recording was made before the recorder included `/atlas/encoder_health`,
`/scan_raw`, `/atlas/control_policy`, `/cmd_vel_commission`,
`/cmd_vel_recovery`, and the IM10A shadow candidate. Their absence in this
specific bag is a recording-coverage limitation, not proof that those live
sources failed.

## Timeline finding

The manual-mapping request was queued at approximately 17.856 seconds.
`/atlas/mode` changed from `LOCALIZATION` through `IDLE` to `MAPPING` at about
48.296 seconds. Mission status continued to report only the queued request
until about 102 seconds. This allowed physical route movement before a durable
active mapping session and its acceptance observer existed.

The 3.2728 m / 43.855 degree `map -> odom` change at 55.725 seconds is the
saved-map localization to fresh-SLAM stack transition. It is not wheel motion
and must not be classified as an in-session SLAM teleport.

After fresh SLAM started, however, the bag still contains real scan-matching
corrections. From 60 seconds onward there were 60 publication-order changes
over the 0.15 m acceptance limit and 9 changes over the 5 degree yaw limit.
The largest was 0.5738 m / 8.398 degrees. The candidate therefore cannot be
salvaged by rebinding named places alone.

LiDAR publication remained present at about 7 Hz. Recorded LiDAR arrival lag
had median 136.31 ms, p95 265.75 ms, and maximum 489 ms. That timing plus the
early-drive/session race makes this run unsuitable as a production map.

## Corrections deployed

1. Manual mapping immediately writes `state=starting` and
   `drive_ready=false` and publishes an explicit keep-stopped status.
2. The session changes to `active` and `drive_ready=true` only after fresh
   SLAM, Nav2, a fresh map, and the navigation action server are ready.
3. Map-quality observation begins only after that readiness gate, excluding
   the localization-to-SLAM frame transition while retaining all subsequent
   SLAM corrections.
4. The demonstration recorder now includes raw and filtered LiDAR, encoder
   health, control policy, commissioning and recovery command paths, and the
   IM10A shadow candidate.

## Remaining gate

One new controlled manual mapping loop is still required after LiDAR is live.
Driving must begin only after the dashboard says `MANUAL MAPPING ACTIVE`.
The candidate may be promoted only when the existing closure, TF correction,
footprint, connectivity, and bidirectional plan-only gates all pass. After a
valid map exists, the final physical validation is one autonomous Dhruv Room
to Hall to Dhruv Room round trip followed by reboot/map-reload verification.
