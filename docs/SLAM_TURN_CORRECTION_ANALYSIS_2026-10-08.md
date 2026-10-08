# ATLAS SLAM turn-correction analysis — 2026-10-08

## Evidence

The controlled manual-mapping bag was recorded before SLAM startup:

`manual_mapping_debdd698e59b471d9b9af9cb073d7c8e-20261008-113519`

The route was manually driven, so joystick timing and exact wheel tracks are
not expected to be identical between runs.

## Result

The latest run passed round-trip closure:

- translation closure: **0.082 m**
- heading closure: **2.99 deg**

It still failed the TF continuity gate:

- largest `map -> odom` correction: **0.747 m**
- largest yaw correction: **10.70 deg**

The prior run measured 1.199 m / 14.20 deg. The reduction confirms that
gentler manual turns help, but the remaining correction is still too large for
map promotion.

## Attribution

The correction is classified as a SLAM scan-matching/pose-graph correction
during a turn. In the event window:

- largest `/odom` step: 0.061 m
- largest `/yahboom/odom` step: 0.057 m
- filtered LiDAR remained live
- encoder feedback was live

Therefore this is not evidence of a wheel-odometry teleport or a missing
encoder packet. Do not loosen the acceptance threshold or replace the accepted
map to hide the event.

## Next gate

Perform one software-only SLAM A/B evaluation against this bag. Keep steering,
encoder selection, and the accepted map unchanged. Only a configuration that
reduces the TF correction while preserving closure may proceed to one final
controlled mapping loop. Rebind Dhruv Room and Hall only after the candidate
map passes all acceptance gates.
