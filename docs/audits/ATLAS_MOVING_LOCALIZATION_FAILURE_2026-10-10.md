# Moving localization failure after a verified start: 2026-10-10 18:30

Operator test: ATLAS was LiDAR-verified at an unnamed spot between the Hall
and Dhruv Room. It was then driven quickly by remote to Dhruv Room. It
physically ended near the Dhruv Room reference (0.25, −1.54). AMCL reported
(4.131, −0.771, 159.7°), 3.96 m away, while the map page still showed
**LIVE / AMCL CONFIDENT (START VERIFIED)**.

No reboot, motion, reseed or configuration change was made during this
investigation. Autonomy stayed blocked (`navigation_validated: false`,
`autonomy_ready: false`).

## Evidence preserved

All on the Jetson in `~/project_atlas/data/diagnostics/moving_loc_20261010/` (22 MB):

- system and user journals for the boot, including **rf2o LiDAR-odometry
  logging at ~10 Hz through the drive**;
- startup verdict file;
- 60 s stationary recording of the wrong state at 18:44
  (`/scan /scan_raw /odom /yahboom/odom /lidar/odom /tf /tf_static /amcl_pose /particle_cloud`,
  IMU, encoders, `/cmd_vel`);
- experience-store events 18:24–18:50. These contain the EKF `/odom`
  position every ~5 s during the drive and the encoder-health fault.

**Gap:** no bag was recorded during the drive. Per-scan AMCL, `/scan`, IMU
and EKF heading during the 40 s drive are not available.

## Timeline (IST, boot at 18:24)

| Time | Event |
| --- | --- |
| 18:24–18:28 | LiDAR start failures again (bounded recovery gave up 18:27:39) |
| 18:28:57 | Start verified: (3.715, −0.695, 173.5°), fit 0.941, margin 0.149. Second place: Dhruv Room (0.295, −1.635) 0.792 |
| 18:30:22–18:31:02 | Remote drive, ~40 s. EKF `/odom` (0,0) → (0.70,0.13) → (1.48,0.41) → (2.16,1.06) → (2.44,1.37) |
| 18:31:01 | `encoder_health` **CRITICAL**: all four encoders consensus-rejected (`STOP REQUIRED`) as the rover stopped |
| 18:31–18:44 | Parked in Dhruv Room; AMCL stays at (4.13, −0.77, 160°) |

## Confirmed findings

1. **AMCL is 4.0 m and 84° wrong, and the LiDAR proves it.** A no-prior
   global search of the parked scans returns a unique answer, Dhruv Room
   (0.175, −1.395, 76°): fit 1.00, margin 0.128. The AMCL pose fits 0.80–0.81.
   The deployed mission start check (0.85) would refuse it.

2. **AMCL's wrong pose is a known alias of Dhruv Room, and it recurs.** In
   the live scans, the second-best place for the Dhruv Room view is
   (3.795, −0.635, 175.5°), fit 0.872. That is 0.42 m from where AMCL sits,
   and it is also where today's drive started. The same wrong pose appears
   while ATLAS was actually in Dhruv Room in **four separate recordings**:

   | Recording | AMCL pose | LiDAR (unique) | Error |
   | --- | --- | --- | --- |
   | passive 21:13, Oct 9 | (3.84, −0.48, 157°) | Dhruv Room, fit 0.99 | 3.65 m / 79° |
   | round trip end, Oct 9 | (3.84, −0.48, 156°) | Dhruv Room, fit 1.00 | 3.57 m / 75° |
   | 122252, t = 213 s, Oct 9 | (3.55, −0.61, 140°) | Dhruv Room, fit 1.00 | 3.26 m / 68° |
   | today 18:44 | (4.13, −0.77, 160°) | Dhruv Room, fit 1.00 | 3.95 m / 76° |

3. **Odometry over the drive was badly wrong, in both distance and
   heading.** The start pose (verified) and end pose (LiDAR-unique) give the
   true net motion in the start frame: forward 3.44 m, left 1.10 m (3.61 m),
   turn −97.5°.

   | Source | Net distance | Net turn | vs truth |
   | --- | --- | --- | --- |
   | EKF `/odom` (authoritative) | 2.77 m | −44.9° | 0.77 distance, **0.46 turn** |
   | wheel `/yahboom/odom` | 2.77 m | **+15.4°** | wrong turn direction |
   | rf2o LiDAR odometry (journal) | 3.75 m | −102.3° | 1.04 / 1.05 |

   rf2o tracked the drive itself well. But it drifted 16.5° while
   stationary before the drive and wandered ±20° while parked afterwards,
   so it is not trustworthy on its own either.

   The EKF heading is the IM10A gyro. On Oct 9 the same gyro matched LiDAR
   scan matching at all turn rates (0.87–1.15). Why it under-reported this
   turn by ~53° is **not established** (see hypotheses).

4. **The cloud collapsed again.** 2,000 particles at one unique pose;
   covariance −7e−13 / −3e−14. The map page's CONFIDENT label is that
   round-off, not confidence.

5. **"START VERIFIED" stayed green because nothing re-checked it.** The
   start verdict is per boot by design. The map page then rendered green on
   covariance plus a start verdict, which was a design error in the
   2026-10-10 change. A start check is not continuous proof.

6. The 18:31:01 encoder **CRITICAL** fault (all four rejected) shows the
   wheel feedback was unreliable at the end of the fast drive.

## Hypotheses (not confirmed: no drive recording)

- **H1 (most likely): wrong odometry steered AMCL's cloud into the
  alias.** EKF under-reported the turn by ~53° and the distance by ~0.8 m.
  AMCL propagates particles by odometry and injects no recovery particles.
  So its estimate would land far from Dhruv Room, among poses near the
  start-like alias, where the Dhruv Room view still fits 0.80–0.87. Parked
  1 Hz updates then collapsed the cloud there.
- **H2: IM10A under-reported the turn during fast driving.** Possible
  causes: samples dropped or delayed on USB, the sensor's static dead-band
  (it outputs exactly 0 at rest), or saturation of a fast spin. On Oct 9 the
  gyro matched the LiDAR at all turn rates, which argues against a plain
  scale error.
- **H3: traction/slip and encoder dropout** inflated the wheel-yaw error
  (+15° vs −97°). The 18:31 consensus failure supports some fault.

**Offline replay of the mechanism was inconclusive.** I ran the AMCL core
with the real end scans and each candidate odometry, 80 runs. Without the
real scans along the way, even the true odometry did not reliably recover:
the cloud spreads over a blind 40 s. Testing H1 needs a recorded drive.

## Correction built and tested offline (not deployed)

**Continuous LiDAR check of the live AMCL pose**
(`atlas_localization_monitor.py` plus `assess_tracking()` in
`atlas_localization_verify_core.py`):

- **Moving** → `MOVING_UNVERIFIED`. No claim while moving: motion blur drops
  the fit even when AMCL is right (Oct 9 moving fits were 0.55–0.76).
- **Parked ≥ 2 s** → median of the last 2 s of scans. It scores the AMCL pose
  and runs the no-prior global search, then decides:
  - **VERIFIED**: the unique LiDAR place is within 0.3 m / 10° of AMCL, and
    the AMCL pose fit is ≥ 0.90.
  - **LOST**: the unique LiDAR place is more than 0.5 m / 20° away, or the
    AMCL pose fit is below 0.70.
  - **DEGRADED**: anything else.
  - It re-checks every 30 s while parked.
- **Recovery** (`~/.config/project_atlas/relocalize_mode`):
  - `suggest` (default): report the LiDAR pose and change nothing.
  - `auto`: reseed AMCL only after two consecutive parked LOST checks agree
    on the same LiDAR pose (≤ 0.3 m / 10°). It then demands a fresh VERIFIED
    check.
  - `off`: report only.
  - Any motion resets the streak.
- **Map page**: green **LIVE / LOCALIZATION VERIFIED BY LIDAR** only with a
  VERIFIED check younger than 60 s. Otherwise it shows:
  - LOCALIZATION LOST (red);
  - MOVING – NOT VERIFIED;
  - NOT CONFIRMED – PARK TO CHECK;
  - **START VERIFIED ONLY, NOT RE-CHECKED** (amber) when the monitor is not
    running.
- **Authority**: none. It publishes a JSON status only. It never commands
  motion and never touches encoders, EKF, AMCL parameters, the map or the
  network.

**Evaluation on 29 parked checks across 8 recordings** (Oct 9, the Hall cold
start and today):

| Rule result | Count | What they were |
| --- | --- | --- |
| VERIFIED | 14 | AMCL within 0.02–0.22 m and ≤ 9.7° of the unique LiDAR place, fit 0.91–1.00 |
| LOST | 12 | **all 12 known-wrong states**: the alias ×6, Hall cold start ×2, 1636 hand-move offset ×2 (0.57 m; 0.41 m with fit 0.60), round trip ×2 (2.65 m, 3.68 m) |
| DEGRADED | 3 | within 0.16–0.23 m but heading 3–9° off or fit 0.81–0.89 |

No wrong state was VERIFIED, and no correct state was LOST. The thresholds
were chosen on these same recordings, so this is not an independent test.
A LOST result that rests only on low fit (no unique LiDAR place) can be
caused by people nearby. That errs safe: it reports LOST and never reseeds,
because reseeding needs a unique LiDAR place twice. The start-pose people
stress test (484 runs, 0 wrong places) covers the global search used here.

Tests: 64 pass in the related suites, including the new monitor, tracking
and dashboard cases.

## Safe recovery proposal

1. Deploy the monitor in `suggest` mode first. Dashboard only; no reseeding.
2. When it reports LOST, the operator confirms where ATLAS is, then accepts
   the LiDAR pose. The `suggest` record shows it.
3. Consider `auto` only after a recorded validation (below) shows zero wrong
   VERIFIED results and zero reseeds to a wrong place.
4. Autonomy stays blocked regardless. Before any autonomous start, mission
   control should additionally require a VERIFIED check under 10 s old with
   no motion since. That is a reviewed change, not part of this commit.

## Recording needed (supervised; no autonomy)

Repeat the drive from the unnamed spot to Dhruv Room twice: once slowly,
once at today's speed. Record:

```
ros2 bag record -o ~/project_atlas/data/diagnostics/moving_repro_<time> \
  /scan /scan_raw /odom /yahboom/odom /lidar/odom /tf /tf_static /amcl_pose /particle_cloud \
  /im10a/imu/unvalidated /im10a/imu/bias_corrected_candidate /im10a/status /imu/data \
  /yahboom/encoder/m1 /yahboom/encoder/m2 /yahboom/encoder/m3 /yahboom/encoder/m4 \
  /atlas/encoder_health /cmd_vel /cmd_vel_joy /joy
```

This decides H1–H3: IMU sample gaps or under-reading versus LiDAR, encoder
dropouts, and whether AMCL followed scans or odometry into the alias. The
same recording then validates the monitor end to end.
