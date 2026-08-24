# Tight-recovery and localization validation — 2026-08-24

## Outcome

ATLAS safely completed a manually driven recovery from the failed autonomous
Hall start to the physical Dhruv Room. The demonstration is preserved on the
Jetson at:

`/home/jetson/project_atlas/data/demonstrations/teach_tight_recovery_to_dhruv_room-20260824-202332`

Dataset integrity manifest:

- Directory size: 9,144,514 bytes
- Bag database SHA-256:
  `454a02c463cf93ce8fede85e7eee0135465a4fb1ec314dad7beaf21884c38392`
- Metadata SHA-256:
  `af6397e670e4742683aff75141ad4ac7fe0642e2f776461233f14ff14bce7817`

No autonomous success is claimed. The run exposed a map-frame/localization
misalignment that must be corrected before another named-room mission.

## Evidence

- Recording duration: 144.02 s
- Recorded messages: 12,760
- Wheel-odometry integrated distance: 5.565 m
- LiDAR lag: 3.21 ms median, 10.39 ms p95, 28.96 ms maximum
- Accumulated `map -> odom` correction: 2.06 m
- Maximum correction step: 0.341 m and 8.006 degrees
- Physical final location: Dhruv Room (operator confirmed)
- Live localized final pose: approximately `(2.715, -2.355, -114.3 deg)`
- Saved Dhruv Room pose: `(-0.327, -0.060, -1.84 deg)`
- Final safety state: stopped; 0.46 m front clearance

## Failure classification

The preceding native Nav2 Hall-to-Dhruv-Room goal was accepted but aborted.
Smac Hybrid repeatedly reported no valid path and ultimately reported that the
starting point was in lethal space. Motion during that attempt was recovery
motion, not successful route following.

The steering odometry sign is not the cause: separately recorded left and
right arcs now agree with physical motion. LiDAR and wheel odometry remained
live during the failed mission.

## Next controlled work

1. Keep ATLAS stationary at the physical Dhruv Room start.
2. Validate the accepted map identity and map image against the physical room.
3. Re-establish the Dhruv Room pose on the accepted map; do not reuse the stale
   named-place coordinate merely because it exists.
4. Inspect global-costmap occupancy beneath the full rectangular footprint at
   both room poses before dispatching a goal.
5. Recreate/validate Hall only after Dhruv Room localization is trustworthy.
6. Generate a path while stationary; require a non-empty collision-free plan.
7. Only then run a short guarded autonomous segment and compare it with the
   successful teaching bag.

Change one localization/planning variable at a time and retain it only when
recorded evidence improves. Do not treat manual demonstration replay as a
substitute for collision-checked Nav2 planning.
