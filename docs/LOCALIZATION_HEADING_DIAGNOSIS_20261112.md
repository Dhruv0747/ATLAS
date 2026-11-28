# Localization: EKF heading diagnosis and fix (2026-11-12)

> **CORRECTION (same day):** the first conclusion below ("IM10A sign inverted") was WRONG. The LiDAR keyframe reference
> had its sign inverted in my analysis code. A sign "fix" was applied at 14:30 and **reverted at about 14:45** (the original IM10A
> code is restored; the backup of the wrong change is kept as `atlas_im10a_observer.py.wrong-sign-fix-*`). The corrected
> analysis and the applied fix follow at the end of this file.

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


## Corrected analysis (LiDAR keyframe sign fixed; AMCL and the owner's reported turn agree)

Drive 2, heading change per stretch (deg):

| Stretch | LiDAR | IM10A = EKF turn rate | EKF heading (live) | AMCL | wheels | Yahboom gyro |
|---|---|---|---|---|---|---|
| 189-374 s | **-134.8** | -133.0 | +36.3 | -128.9 | +162.0 | +136.4 |
| 374-560 s | **+34.9** | +46.5 | -188.0 | -65.4 | -76.6 | -42.8 |
| 560-745 s | **-98.4** | -98.9 | -60.9 | -168.9 | +79.9 | +107.1 |

* **The IM10A is correct** (correlation +0.93).
* The **wheel odometry heading (from the Yahboom board) and the Yahboom gyro are inverted**.
* The EKF fused the wheel x/y POSITION, which is integrated with that inverted heading. That bent the EKF heading away
  from its own (correct) IM10A turn rate, and AMCL followed it.

Offline replay of drive 2 (isolated domain 92) through robot_localization:

| EKF config | Median heading error vs LiDAR | Max |
|---|---|---|
| live config (wheel x, y, vx, vy + IM10A) | 68 deg | 170 deg |
| wheel vx (+vy) only + IM10A | **1.3 deg** | 20 deg |

## Applied fix (owner-approved, 14:55, E-STOP latched)

* `config/atlas_ekf.yaml` `odom0_config`: wheel **vx only** (x, y and vy no longer fused).
* IM10A yaw rate is the only heading source (owner instruction: IM10A only, no Yahboom IMU).
* Backup: `atlas_ekf.yaml.before-vx-only-20261112-145502`. `atlas-ekf` restarted, and AMCL restored to its pose.

Validation:

| Test | LiDAR | IM10A | EKF heading | AMCL | Yahboom | wheels |
|---|---|---|---|---|---|---|
| Still, 90 s | +0.3 | 0.0 | 0.0 | +1.4 (std 1.0) | - | - |
| Turn, 120 s | **-16.9** | -19.6 | **-19.6** | **-14.0** | +15.8 | +14.2 |

The EKF heading now equals the IM10A and agrees with the independent LiDAR within about 3 deg.

Still open:
* Position accuracy during a full drive (AMCL against the map) is not yet verified.
* The saved 2D map fits only about 22 % of LiDAR hits, so build a new 2D map with the corrected odometry.
* Rebuild the two 3D route maps with corrected headings.

## Real drive with the fix (15:13, dhruv room -> hall), and the 2D map attempt

* Heading per stretch:
  * LiDAR -91.6 / -88.4 deg; EKF heading -91.0 / -98.6 deg.
  * The EKF heading now equals its IM10A turn rate.
* Parked in the Hall, AMCL rotated +53.7 deg on its own. Scan fit at the AMCL pose was 0.20 on the existing map, and
  the monitor reported LOST, 4.47 m / 65 deg from the LiDAR place search.
  * Cause class: map mismatch in the Hall. No longer odometry heading.
* dhruv room: before the drive, AMCL was 1.4 m off (it had been restored to a pose that was already wrong). The
  owner-confirmed verify-place re-seed fixed it (fit 0.51).
* Candidate 2D map (`maps/atlas_candidate_20261112`, offline slam_toolbox, both legs, AMCL map->odom dropped):
  **REJECTED**.
  * Partial: 1077 vs 1920 occupied cells.
  * Ragged walls.
  * Place test ambiguous (0.99 vs 0.99) where the existing map gives VERIFIED (1.0, margin 0.131).
  * The existing map stays active.
* Round-trip 3D map with corrected heading: `maps3d/round_trip_dhruvroom_hall_fixed_20261112.ply`, 47,984 points.
  The leg-2 end lies 0.7 m from the leg-1 start.
* Next: a dedicated, slow, full-coverage remap (Hall included, loop closures), now that odometry heading is fixed. Then
  re-test Hall localization.
