# ATLAS SLAM turn-correction analysis — 2026-10-08

## Evidence

The controlled manual-mapping bag is:

`manual_mapping_debdd698e59b-20261008-113519`

Recorder process creation does not prove subscriptions were ready before SLAM
startup. Also, starting an already-active SLAM service does not reset its map.
These runs must not be described as independently initialized fresh maps.

The route was manually driven, so joystick timing and exact wheel tracks are
not expected to be identical between runs.

## Result

The latest run passed round-trip closure:

- translation closure: **0.082 m**
- heading closure: **2.99 deg**

It still failed the TF continuity gate:

- largest `map -> odom` correction: **0.747 m**
- largest yaw correction: **10.70 deg**

The prior run measured 1.199 m / 14.20 deg. This is an improvement, but different
manual trajectories and retained SLAM state prevent attributing it solely to
gentler turns. The remaining correction exceeds the current promotion gate.

## Attribution

The prior `c6c7d28d` run was classified by the analyzer as a SLAM
scan-matching/pose-graph correction during a turn. In that run:

- largest `/odom` step: 0.061 m
- largest `/yahboom/odom` step: 0.057 m
- filtered LiDAR remained live
- encoder feedback was live

This locates the discontinuity in map correction; it does not establish the
root cause. Smooth odometry can still have scale/heading error. Loop closure
can legitimately correct accumulated drift. Duplicate TF authority must also
be excluded before assigning blame. Preserve the acceptance threshold and map
while investigating.

## Next gate

Perform one software-only SLAM A/B evaluation against this bag. Keep steering,
encoder selection, and the accepted map unchanged. Only a configuration that
reduces the TF correction while preserving closure may proceed to one final
controlled mapping loop. Rebind Dhruv Room and Hall only after the candidate
map passes all acceptance gates. Candidate endpoints must first be measured
in that candidate's frame for connectivity checks; merely relabeling old
coordinates with a new map ID is invalid.

## Completed offline comparison

On 2026-10-08, replayed the exact `debdd698e59b` input twice in localhost ROS
domain 177. The input bag contained only 1,236 scans and non-map transforms;
recorded map transforms and all command topics were excluded. Each variant
started a separate SLAM process using the live service's parameters, changing
only `do_loop_closing`. Playback ran at 0.5x under Nice=15 and a one-core CPU
quota. Neither run logged scan drops. Both output recordings closed normally.

| Metric | Loop closure on | Loop closure off |
| --- | ---: | ---: |
| Recorded replay scans | 1,236 | 1,236 |
| Map messages | 243 | 243 |
| Largest map correction | 0.770482 m | 0.770482 m |
| Largest yaw correction | 11.197887 deg | 11.197887 deg |
| Approximate endpoint displacement | 0.087227 m | 0.087227 m |
| Approximate endpoint heading difference | 1.503205 deg | 1.503205 deg |

Endpoint values use the most recently received correction, not interpolated
time-aligned TF, and are diagnostic estimates, not acceptance certification.
Scan counts prove recording completeness, not that every scan was matched.

**Decision:** keep the live loop-closure setting. Disabling it did not improve
this input. The replay reproduces the correction with one SLAM map-transform
publisher, so duplicate live TF publishers are not required to reproduce it.
This narrows investigation to scan matching/its odometry prior and does not
prove encoder scale or heading estimates are accurate. No live steering,
navigation, IMU, or encoder parameter was changed.

A further manual loop is not needed to investigate this comparison. Next use
the saved input to inspect odometry-versus-scan alignment around the jump and
map geometry; do not promote a map solely because endpoint closure is small.
