# Localization: EKF heading diagnosis (2026-11-12)

Two recorded manual drives (dhruv room -> hall 13:38, 493 s; hall -> dhruv room 14:12, 746 s). Bags are in
`~/project_atlas/maps3d/m3_session_*_bag`. Tools: `project_atlas/tools/localization/` (`analyze_drive_bag.py`,
`heading_compare.py`, `turn_test.py`). Everything is read-only.

## Symptoms (drive 1)

* AMCL heading uncertainty: median +-47 deg, max +-179 deg.
* map->odom correction: 95 jumps (> 25 cm or > 10 deg); total 5.2 m / 160 deg.
* LiDAR scan fit to the saved map at the AMCL pose: median 0.22. That is a second problem: the map no longer
  matches the rooms well.

## Reference heading

* LiDAR keyframe ICP (scan matched to a keyframe, no map, no odometry).
* Validated on drive 1: 355 s of standing still gave 3.1 deg total (0.009 deg/s).
* (A first, scan-to-scan chained ICP drifted +0.5 deg/s and was discarded; a conclusion drawn from it was withdrawn.)

## Result (drive 2, recorded IM10A topics)

| Stretch | LiDAR | IM10A corrected (EKF imu0) | IM10A raw | Yahboom gyro | wheels |
|---|---|---|---|---|---|
| 189-374 s | +134.8 | **-133.0** | -133.0 | +136.4 | +162.0 |
| 374-560 s | -34.9 | **+46.5** | +46.5 | -42.8 | -76.6 |
| 560-745 s | +98.4 | **-98.9** | -98.9 | +107.1 | +79.9 |
| whole | +197.9 | **-185.4** | -185.4 | +201.6 | +165.3 |

Turn-rate correlation with the LiDAR while turning:
* IM10A: **-0.93**
* EKF turn rate: -0.94
* Yahboom gyro: +0.89
* wheels: +0.83

**Diagnosis: the IM10A gyro Z sign is inverted** relative to the body frame (`atlas_im10a_observer.py`
`corrected_gyro` keeps z). The EKF fuses only this yaw rate. Its wheel-position input implies the opposite turn,
so the EKF heading is wrong in both directions. AMCL's motion model then rotates the particles the wrong way at every
turn.

The September/October qualifications passed. The board may have been remounted since, or the earlier sign check did
not use an independent heading reference. Unknown.

## Proposed fix (owner approval required; rover parked, E-STOP latched)

1. Back up `scripts/atlas_im10a_observer.py`, then change corrected z to `-(raw[2] - bias[2])`. IM10A stays the only
   yaw source (owner instruction).
2. Restart `atlas-im10a` and `atlas-ekf`, then re-seed AMCL (`seed_atlas_localization.py --verify-place`).
3. Turn test: owner turns left about 90 deg. IM10A corrected, EKF heading and LiDAR must all read +.
4. Then rebuild the 2D map from corrected odometry and compare localization.

## 3D route maps (stored, `~/project_atlas/maps3d/`)

* `route_dhruvroom_to_hall_20261112.ply`: 35,596 points, 6.5 m path.
* `route_hall_to_dhruvroom_20261112.ply`: 47,887 points, 7.9 m path.
* Both are built on the faulty EKF heading, so their shape is distorted. Rebuild after the fix.
