# Full 2D remap plan (next session)

Goal: a new accepted 2D map that matches the rooms as they are now, especially the Hall. On the current map the Hall
LiDAR fit is only 0.20 and AMCL self-rotates while parked there. The remap is worth doing now because the EKF heading
was fixed on 2026-11-12 (wheel vx + IM10A yaw only). Previous maps were built on a heading that turned the wrong way.

We use the project's own accepted workflow (mission control "manual teaching" mapping), not an offline script:
`/atlas/start_manual_mapping`, then drive with the remote, then stop mapping (`/atlas/stop_exploration`), then the map
is saved (`map_saver_cli`), then `accept_saved_map()` validates it.

Acceptance checks, already in code (`atlas_map_acceptance_core.py`):
* loop closure <= 0.15 m / 10 deg (home pose vs final pose);
* map->odom jumps <= 0.15 m / 5 deg during the session;
* footprint clearance >= 0.18 m at the "dhruv room" and "hall" places.

On acceptance the old map is backed up to `maps/accepted_backups/` and replaced atomically. On rejection the old map
is untouched.

## Before starting (owner, about 5 min)
1. Battery >= 60 %. Floor along the route clear. Doors open.
2. **Tape mark** on the floor in Dhruv Room at the start spot: a line under the front bumper and one along a side, so
   the rover can be parked back within a few cm and a few degrees. The 0.15 m / 10 deg closure needs this.
3. Optional: a second tape mark in the Hall where "hall" will be saved.
4. Park exactly on the Dhruv Room mark and press **B** (E-STOP latched).

## Before starting (me)
* Rover still; E-STOP latched; EKF config is the vx-only version; IM10A healthy.
* Stop the Astra obstacle pipeline and bridge for the remap to keep CPU headroom. The mapping stack replaces
  AMCL/Nav2, and an earlier RTAB-Map session peaked at 88 % CPU. Restart them afterwards. No RTAB-Map during the
  remap: 3D comes separately.
* Start a side recording (LiDAR, odometry, IM10A, TF) for analysis.

## The drive (owner, about 15-20 min, slow)
1. Start manual mapping (dashboard, or me on your OK). Wait for **"MANUAL MAPPING ACTIVE"**; home is set here
   automatically.
2. Save the place **"dhruv room"** right there, before moving.
3. Release the E-STOP. Drive **slowly** (walking pace or slower; turn slowly, about 10-15 deg/s):
   * Dhruv Room: one slow lap along the walls, about 0.5 m from them, then back near the door.
   * Corridor to the Hall.
   * Hall: a full slow lap along all walls, including the far end.
   * Stop on the Hall mark; save the place **"hall"**.
   * Return along the corridor (passing it twice gives the map a second look).
   * Back in Dhruv Room: park **exactly on the tape mark, same direction**. Press **B**.
4. Stop mapping. The map is saved and checked automatically: **ACCEPTED** or **REJECTED** with the reason.

## After (me)
* Report the acceptance result, closure numbers and the old-vs-new map picture.
* If accepted:
  * place tests in both rooms (must be unique VERIFIED);
  * 2 min parked in the Hall: AMCL must not self-rotate (today +54 deg);
  * a short test drive with live localization monitoring.
* Restart the Astra and bridge (parked).
* If rejected: the old map stays. I analyse the recording and we repeat only what failed.
* Rollback at any time: the previous map pair in `maps/accepted_backups/<timestamp>-<session>`.

## Not in this session
3D colour / higher-resolution mapping. That follows once the 2D map and localization are solid.

## Attempt 1 result (2026-11-12 16:00-16:16): REJECTED, old map kept

* Closure **passed**: 0.061 m / 1.98 deg.
* Rejected for:
  * a SLAM map->odom jump of 0.92 m / 12 deg at about 16:06:18 (just after leaving the Hall);
  * "observation did not cover session start" (the window starts at stack-ready, 79 s after the session start).
* Restored normal localization on the old map (VERIFIED). Named places restored with reconstructed headings.
* **Home pose must be re-saved.**
* Before attempt 2:
  1. find the jump cause in `maps3d/remap_20261112-160012_bag` (suspected odometry distance scale);
  2. confirm whether the start-coverage gate can ever pass for manual teaching, without weakening any gate.
