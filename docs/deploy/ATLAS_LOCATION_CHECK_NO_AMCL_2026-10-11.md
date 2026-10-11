# CHECK MY LOCATION after a restart: UNAVAILABLE root cause and fix (stage 13), 2026-10-11

Branch `agent/sync-developer-20261011`; source `2e10355` (base `7f8ee2e`). Read-only change.
- **Deployed** 19:45:59 IST with the stop latched (Xbox B) and the rover still.
- **Restarted:** only `atlas-localization-monitor`.
- **Not touched:** AMCL (PID 8237), mux (1870) and motor base (3163) were not restarted. Nothing was
  reseeded, no pose was corrected, and no map, Nav2 or motor setting changed.

## 1. Exact reason the check returned UNAVAILABLE

| Stage | Live state at about 19:20 (boot `a0574e36`, started 19:06:33) |
|---|---|
| RPLIDAR | 15 failed starts; scanning at 216 s after boot (ATLAS-015 pattern) |
| `atlas-localization` | 5 failed starts while waiting for the LiDAR; up at about 220 s. map_server and AMCL **active** |
| Startup verifier (verify-before-seed) | 262 s: `LOCALIZATION UNKNOWN: AMCL not seeded; scan does not match the saved map well enough anywhere (best 0.90 < 0.93)` |
| AMCL | Active but **never given an initial pose**: "Please set the initial pose…" logged 320 times and still repeating. **No `/amcl_pose`, no map→odom TF** |
| Location monitor | `INPUT_STALE: AMCL pose stale` |
| `/scan`, scan-time base_link←laser_frame TF, `/map` | all fresh and valid |
| CHECK MY LOCATION | `atlas_location_check_ros.py` raised before any search: `if not n.scans or n.amcl is None: raise ValueError('SCAN UNAVAILABLE or AMCL reference unavailable')`. The job manager also required an AMCL pose, AMCL age and a map→odom chain |

**Conclusions:**
- The scan was available; AMCL simply had no pose.
- The independent LiDAR search does not use AMCL at all, but it was **blocked incorrectly** by the
  AMCL precondition, and the two conditions were merged into one message.
- The startup verifier refusing to seed at 0.90 was **correct behaviour**: it reported UNKNOWN
  instead of guessing. Why its boot-time fit was 0.90 when parked checks 40 minutes later score
  0.994–1.000 is an **evidence gap**. The owner was likely beside ATLAS restarting it, which would
  occlude the scan, but there is no recording.

## 2. What changed

**`atlas_location_check_ros.py` (runs inside the existing monitor process):**
- `evidence()` builds a stage table (scan, map, odom, imu, policy, cmd, stop, motion, coverage,
  scan_tf, amcl). Each stage has status, topic or frame, ages and errors.
- Each blocking condition raises its own code:

  | Code | Condition |
  |---|---|
  | `LIDAR_SCAN_UNAVAILABLE` | no scan received |
  | `LIDAR_SCAN_STALE` | scan too old |
  | `ACCEPTED_MAP_NOT_READY` | served map does not match the accepted map |
  | `ACCEPTED_MAP_CHANGED` | map file changed |
  | `ODOMETRY_UNAVAILABLE` | no fresh odometry |
  | `IMU_UNAVAILABLE` | no fresh IMU |
  | `STOP_STATE_UNKNOWN` | no valid stop policy |
  | `MOTOR_COMMAND_STATE_UNKNOWN` | no `/cmd_vel` received |
  | `SENSOR_TIMESTAMP_INVALID` | future or invalid sensor stamp |
  | `STOP_NOT_LATCHED` | drive stop not latched |
  | `MOTOR_COMMAND_ACTIVE` | non-zero `/cmd_vel` |
  | `ROVER_MOVING` | motion in the last 2 s |
  | `INSUFFICIENT_LIDAR_COVERAGE` | too few returns or an empty quadrant |
  | `SCAN_TIME_TF_UNAVAILABLE` | no laser transform at the scan time |
  | `SEARCH_BUSY` | the monitor's own search is running |
  | `RATE_LIMITED` | request within 2 s of the last |

- **AMCL is reported separately** as `OK`, `NOT_INITIALIZED`, `STALE`, `INVALID` or
  `TF_UNAVAILABLE`, and **never blocks** the independent search. Map→odom TF is looked up only when
  AMCL is OK.
- `compare()`: with no usable AMCL, the global search still runs with no prior, using the same
  existing matcher.
  - A unique match is **`LIDAR_ONLY_MATCH`, never `VERIFIED`**.
  - Otherwise the result is `AMBIGUOUS`, `INSUFFICIENT_LIDAR_COVERAGE` or `UNCERTAIN`.
  - With AMCL, behaviour is unchanged (`VERIFIED`, `MISMATCH`, `LOST`, `UNCERTAIN`), plus
    `AMBIGUOUS` when the search itself is ambiguous.
- If evidence goes bad mid-check (motion, latch released, stale scan), the result is voided as
  `STALE` with the code.

**`atlas_location_check_job.py`:**
- AMCL age, pose and TF chain are mandatory only when AMCL is OK.
- An AMCL status change mid-check voids the result.
- New result states are accepted.
- The last success is kept as a separate, timestamped `last_success`; the status file also carries
  `last_block`.

**`web/v2/location-check.js`** (shared by the command center and the mapping page) shows:
- the code and request id;
- the stage table;
- the AMCL status and its reason;
- the LiDAR verdict and endpoint count;
- a current rejection versus the newest result (a rejection older than the newest result is not
  shown as current);
- the last success, labelled "historical, not a live confirmation".

## 3. Tests

- **Python:** 56 location tests (28 new in `tests/test_location_check_unavailable.py`; 0 failures).
  - Stage cases: AMCL not initialized, stale, or without map→odom TF; no scan; stale scan; scan-time
    TF missing; map not ready; stop not latched; moving; non-zero command; missing sectors; missing
    odometry; future sensor stamp.
  - Matching on the synthetic two-room map: no-AMCL unique match; never VERIFIED without AMCL;
    ambiguous symmetric room; thin scan; AMCL correct versus wrong room.
  - Job: AMCL appearing mid-check; motion mid-check; last success separate; late finish from an old
    worker; timeout.
  - Adapter: rejection recorded for both pages; status file carries `last_block`; motion during a
    run becomes STALE; the search mutex is never leaked.
- **UI:** 17 assertions (11 new).
- **Isolated Jetson replay** (`tools/diagnostics/replay_location_check.sh`): the real monitor with
  stage 13 installed on a scratch copy, on a private DDS domain with a private HOME and sim time,
  replaying the Oct 10 parked Dhruv Room bag, with the accepted map served by its own map_server.

  | Input | Result |
  |---|---|
  | AMCL withheld | **LIDAR_ONLY_MATCH** (0.235, −1.435, 84°), fit 1.000, margin 0.096, 3.2 s |
  | Bag's recorded AMCL | **MISMATCH 3.95 m / 76°**. The recorded AMCL sat on the known alias (4.13, −0.77, 160°): the Oct 10 failure, reproduced |

  An earlier replay with `/clock` at 50 Hz voided one run on a −1.7 ms IMU stamp. The rate is now
  1 kHz, and that condition now has its own code.
- **Package:** rehearsal and rollback identity pass; tamper tests pass; Jetson checksums OK; 3/3
  MATCH on the scratch copy and live; live tree unchanged by the rehearsal.

## 4. Live results on the Jetson (latched, parked in Dhruv Room)

**Before**, 19:43 (`POST /api/location-check`): HTTP 409,
`{"state":"UNAVAILABLE","reason":"SCAN UNAVAILABLE or AMCL reference unavailable"}`. Rendered by the
old widget, this is exactly the owner's screen.

**After:**

| Check | State | Independent LiDAR | Fit | Margin | Next place | Time |
|---|---|---|---|---|---|---|
| 19:46:30 | **LIDAR_ONLY_MATCH** | (0.235, −1.435, 72°) | 1.000 | 0.107 | (3.875, −0.635, 171°) fit 0.893, 3.73 m / 99° away | 2.49 s calc, 3.1 s wall |
| 19:46:40 | **LIDAR_ONLY_MATCH** | (0.235, −1.535, 78°) | 0.994 | 0.079 | — | 2.43 s |

- **Every stage READY:** scan age 0.15 s; 213 endpoints across quadrants [44, 58, 63, 48];
  base_link←laser_frame at the scan time.
- **AMCL:** NOT_INITIALIZED, as above.
- **Accepted map:** `6da76a70…` matches the served `/map`.
- **Both V2 pages** (`/`, `/v2/`, `/v2/mapping`) load the deployed widget (served hash `4d4d32dc`).

**Does it agree with Dhruv Room?**
- **Position:** yes. The candidate is 0.06–0.12 m from the saved Dhruv Room seed (0.254, −1.539)
  and the operator-confirmed pose (0.187, −1.477).
- **Heading:** 72–84° across checks today. This is consistent with earlier Dhruv Room parks
  (73–84°), but the 6–12° spread between repeated checks is larger than a parked rover moves.
- **Margin:** 0.079–0.107, above the 0.06 threshold but not large. The runner-up is the known
  Dhruv Room / corridor alias near (3.9–4.1, −0.7).
- **Treat it as strong evidence of the room, not as a validated pose.** Correction stays disabled.

## 5. Resource impact (monitor process, 60 s, idle)

- **Before:** 11.0% of one core, 88 MB RSS.
- **After:** 11.4% of one core, 107 MB RSS, after two searches; this includes numpy working buffers
  from the search.
- **Per check:** about 2.4–2.5 s of search, under the existing 30 s bound, sharing the monitor's
  search mutex.
- **System:** load average 10.8 before and 22.9 / 15.6 / 12.1 just after the two checks (1-, 5- and
  15-minute). That is not attributable to this change alone; the machine was already at about 11 on
  6 cores.

## 6. Control-state disagreement (investigated; backend consistent)

From the mux, the event log and the journal:
- **19:07:36:** the voice module said "Remote safety stop is latched … Only the remote can release
  it". This was the boot latch, "joystick unavailable".
- **19:12:55:** the owner released with LB, so the drive panel's NOT LATCHED was correct.
- **19:45:38:** latched again with B.

The voice module announces only the latch edge, never the release, so its words went stale.
"Stopped" on the dashboard is the motion state, not the latch. **No E-STOP behaviour changed.**

**Built, not deployed** (commit `27ccfcd`, 34 voice tests pass):
- announce both edges;
- announce a release only after an announced latch;
- mention the web reset.

It needs a `atlas-voice-companion` restart and owner approval.

## 7. Rollback

- **Backup:** `~/project_atlas/data/backups/2026-10-11-194559-575361028-stage13-location-check-no-amcl/`
- **Steps:** run its `ROLLBACK.sh`, then `systemctl --user restart atlas-localization-monitor.service`
  (rover latched), then reload both dashboard pages.

## 8. Still open

**ATLAS is not localized for navigation.**
- AMCL has no pose since this boot. Seeding it from the LiDAR-only candidate needs the owner's
  decision, ideally with physical confirmation of the place.
- The existing named-place seed and "Set location" flows are unchanged.

**Remaining defects, unchanged:**
- moving-localization drift (VERIFIED → LOST after a short drive, twice);
- encoder distance about 0.6×;
- IMU heading disagreement;
- the corridor/Hall map defects and the alias near (3.9–4.1, −0.7);
- the Nav2 observation-coverage guard vetoing all directions;
- LiDAR start delay (216 s this boot).
