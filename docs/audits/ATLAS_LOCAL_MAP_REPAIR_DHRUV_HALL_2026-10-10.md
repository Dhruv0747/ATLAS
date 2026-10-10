# Local map repair analysis — Dhruv Room → Hall (2026-10-10)

Read-only analysis. **The active map was not changed**: `atlas_latest.pgm` sha
`4beb26d5…`, dated 2026-10-02 16:29, and its yaml are unchanged. The candidate
was written separately to
`~/project_atlas/maps/candidates/local_dhruv_hall_20261010/` with
`candidate_metadata.json` (status `candidate_only_not_promoted`). No motion,
service or parameter changes. Tools are in `project_atlas/tools/local_map_audit/`.

## Inputs

**Active map**
- `atlas_latest.pgm/.yaml` (5 cm cells, origin −3.89, −8.46).
- It is the final `/map` of the manual SLAM run
  `commissioning/manual_mapping_dhruv_to_hall_20261002_162438`: 200 s, Dhruv
  Room → Hall → Dhruv Room. 1,869 of its 1,882 occupied cells match.

**Recordings**
- That mapping run.
- Four Oct 9 drives: `hall_to_dhruv_…122252`, `amcl_roundtrip_…final`,
  `amcl_hall_outbound_…retry2` and `amcl_hall_return_…retry2`.
- Together: 7 traversals of this section, 13 parked windows.

**Live**
- 179 parked scans at 22:4x.
- The no-prior LiDAR search placed ATLAS at (0.135, −1.755, 74°), fit 1.00,
  margin 0.123.

**Operator camera views (front wall, doorway, curtain, right-side edge)**
- Used qualitatively, to orient the analysis; the camera gives no metric
  positions.
- The LiDAR confirms the front wall ahead of the parked pose: the live scan
  lies on the mapped wall (y ≈ 0.1–0.45, with a ~0.3 m step at x ≈ 0.65).
  That wall and doorway are not where the map is wrong.

## Method

1. **Anchors.** All 13 parked ends of the recordings were LiDAR-verified with
   the deployed global search: fit ≥ 0.948, margin ≥ 0.076.
2. **Map-independent trajectories.** Each traversal was rebuilt by
   scan-to-submap ICP (seeded by rf2o), then pinned at both verified ends by a
   small pose graph. Chain drift before pinning was 0.2–0.9 m and 0.3–13°.
3. **Cell evidence.** For each map cell, count how many drives hit it versus
   saw through it. Leave-one-out agreement between drives was 0.87–0.93. The
   mapping return leg reached only 0.66 and was excluded from the
   reconstruction; it is the least reliable reconstruction.
4. **Candidate rules.** Inside the box x −1.6…7.6, y −3.6…1.8 only:
   - remove a wall cell when ≥ 3 drives see through it, none hit it, and no
     parked LiDAR-verified scan hits it;
   - add a wall cell when ≥ 3 drives hit it and it is > 10 cm from any mapped
     wall.

   Result: 258 cells removed, 17 added, 0 changed outside the box.
   Thresholds and policies are unchanged.

## Confirmed findings

- **63% of this section is right.** 985 of 1,573 mapped wall cells are
  confirmed by ≥ 3 drives. 272 are contradicted: ≥ 3 drives see through them
  and none hit them.
- **The mapping run's return leg drew shifted copies of existing walls.**
  - SLAM's own map snapshots grew during the Hall → Dhruv Room return
    (114 s → 163 s), over walls that were already mapped:

    | Area | Cells before | Cells after |
    |---|---|---|
    | Corridor south wall | 95 | 163 |
    | Corridor north | 144 | 237 |
    | Dhruv Room left | 56 | 91 |

  - The 666 cells it added sit 0.05–0.6 m from first-pass walls, 465 of them
    0.15–0.6 m away: parallel copies.
  - 172 of the 272 contradicted cells came from that leg.
- **Wrong geometry, by area.** "Return" is how many removed cells the mapping
  return leg drew.

  | Area | Location | What is wrong | Return |
  |---|---|---|---|
  | A | Dhruv Room, left / back | Second wall copy at x −0.7…−0.4, y −2.5…−1.1; diagonal corner pieces | 12 of 21 |
  | B | Corridor south wall, x 2.2–3.6, y ≈ −1.0 | Doubled top edge, about 1 cell thick; this is the operator's "failure zone" | 10 of 20 |
  | C | North of corridor, x 2.0–3.9, y −0.2…0.5 | Scattered phantom clutter right next to the recurring alias pose (3.8–4.1, −0.6) | 34 of 53 |
  | D | Hall | Cross-shaped object (5.1–5.6, −3.2…−2.6): a return-leg artifact, not furniture | 30 of 32 |
  | D | Hall | Inner duplicates of the north / east walls | 34 of 39 |
  | D | Hall | Missing wall at x 6.6–6.8, y −0.9…−0.4 (added) | — |

## Hypotheses (not proven)

- **Speed.** Straight-line speed is not the main cause.
  - The mapping run averaged 0.19–0.27 m/s, peaking at 0.56 m/s. The Oct 9
    drives were 0.17–0.23 m/s.
  - Every drive turned in place at 54–60°/s with a 7 Hz LiDAR, and SLAM
    applied 135 map→odom corrections (up to 0.25 m / 9.4° each) on the first
    pass alone.
  - The doubled walls come from the return leg, where SLAM's pose disagreed
    with the anchored reconstruction by up to 0.5–0.9 m. That
    reconstruction is the weakest, so this is suggestive only.
  - Best supported reading: **fast in-place turning while mapping, with no
    loop closure on the return pass**. A pure high-speed straight-line
    distortion is less likely.
- **Remaining failure is not only the map.** On the candidate, AMCL replays
  are still lost 1–48% of the time while moving. The known IM10A/EKF turn
  under-read (ATLAS-010/011) remains a separate cause.

## Expected localization impact (offline)

| Check | Active map | Candidate |
|---|---|---|
| Parked LiDAR verify (13 + live) | 15/15 correct, mean margin 0.128 | 15/15 correct, mean margin 0.139 |
| Dhruv Room alias: 2nd-best fit (live) | 0.877 | 0.839 |
| Round-trip Dhruv Room margins | 0.10 / 0.10 | 0.18 / 0.18 |
| Moving windows (127, leave-one-out) | 72% correct, 4 wrong | 85% correct, 1 wrong |
| …in corridor x 1–5 m | 40/48 | 37/48 |
| AMCL replay, ends correct (20 seeds, leave-one-out): H→D / round trip / out / return | 65 / 5 / 100 / 100% | 100 / 90 / 100 / 100% |
| AMCL replay, time lost: H→D / round trip / out / return | 29 / 69 / 8 / 22% | 17 / 48 / 1 / 16% |

**Limitations**
- The ground truth for moving segments is the anchored ICP reconstruction:
  map-independent, but carrying about 0.1–0.3 m uncertainty.
- Parked-wall protection used the same parked data.
- The replay is the Nav2 AMCL core library, not a full ROS replay.
- The candidate was not tested on the rover.
- The corridor's moving verdicts got slightly worse (40 → 37 of 48).

**Status:** SIMULATED / TESTED OFFLINE only. Not deployed. Not verified on
the Jetson.

## Recommendation

1. **Partial local repair is possible** (this candidate). It removes
   duplicated walls and phantom clutter, and its offline effect is clearly
   positive. It cannot reconstruct geometry the evidence does not cover, such
   as the corridor's exact edges.
2. **Do not promote yet.** Promotion changes the map identity
   (`map_id`/named places), Nav2's costmap and the seeder's map, so it needs
   separate approval. Proposed check first: run the monitor and global search
   against the candidate in shadow while parked at Dhruv Room, the corridor
   midpoint and the Hall. No AMCL map swap.
3. **The corridor section (x ≈ 1–5 m) needs a controlled slow re-map, rather
   than more deletion.**
   - Use local SLAM, not a full-house remap.
   - Drive one out-and-back between the verified Dhruv Room and Hall
     anchors.
   - Limits: ≤ 0.15 m/s; turns ≤ 15°/s; stop 3 s at each end and at the
     corridor midpoint.
   - Merge the submap into the existing frame, aligned at the verified anchor
     poses.
   - Then rerun this audit on the result.

## Validation phase (approved read-only, 2026-10-10 23:37–00:00)

Nothing deployed. Unchanged:
- active map (`4beb26d5…`/`d957f0fe…`);
- `named_places.json`;
- `nav2_params.yaml`;
- localization settings and safety controls.

**Fresh Dhruv Room scans** (231 scans, 6 windows, LiDAR-verified at
(0.155, −1.775, 73.5°)):

| Map | Verdicts | Margin | 2nd place | Within 5 cm | Through-wall rays |
|---|---|---|---|---|---|
| Active | 6/6 | 0.106–0.125 | alias 0.878 | 0.868 | 47/288 |
| v1 | 6/6 | 0.150–0.156 | 0.840 | 0.868 | 47/288 |
| v3 | 6/6 | 0.106–0.125 | alias 0.878 | 0.868 | 47/288 |

The through-wall rays show three errors in the active map that no candidate
fixes, because drive data never sees them:
- **Front wall / door recess** (camera view): the wall is mapped at
  y ≈ 0.05 for x 0.56–1.03, but the real surface is 0.15–0.34 m further back.
- **Exit jamb** at (0.66, −1.06): seen through for 1.4 m.
- **Inner left-wall copy** at x ≈ −0.15, y −1.85…−2.1: the real wall is
  0.15–0.34 m further out.

**Corridor regression** (48 windows, x 1–5 m, leave-one-out):

| Map | OK / UNKNOWN / WRONG |
|---|---|
| Active | 40 / 5 / 3 |
| v1 | 37 / 11 / 0 |
| v2 | 41 / 5 / 2 |
| v3 | 41 / 5 / 2 |

v1 cleared all 3 confidently wrong verdicts (0.26–0.33 m off near the alias),
but dropped 6 correct ones to UNKNOWN. Fit at the true pose fell from 0.93
to 0.88–0.90, because v1 removed surfaces those scans hit. 138 of v1's 258
removals were within one cell of returns from ≥ 2 drives.

**Passage safety.** v1 makes new space reachable from Dhruv Room and the Hall
at robot radii 0.18 / 0.25 / 0.28 m:
- north of the corridor, about 500–630 cells;
- south of the corridor's west end, 353–458 cells;
- into unknown space, which matters because `nav2_params.yaml` has
  `allow_unknown: true`.

**v1 is REJECTED** (metadata updated on the Jetson).

**Candidate versions** (all separate files; none promoted):
- **v2:** removes only cells never hit by any scan.
- **v3:** v2, plus every removal that opens new reachable space is restored
  (96 cells). Final: 31 removed, 17 added, 0 newly reachable cells at any
  radius.
  - Saved in `maps/candidates/local_dhruv_hall_v3_20261010/`.

AMCL replay, leave-one-out, 20 seeds:

| Map | Ends correct (H→D / round trip / out / return) | Time lost |
|---|---|---|
| Active | 65 / 5 / 100 / 100% | 29 / 69 / 8 / 22% |
| v1 | 100 / 90 / 100 / 100% | 17 / 48 / 1 / 16% |
| v2 | 80 / 40 / 100 / 100% | 25 / 62 / 6 / 21% |
| v3 | 75 / 30 / 90 / 100% | 26 / 67 / 7 / 23% |

v3 sits within seed noise of the active map.

**Conclusion.** Under the safety rules (keep every surface any scan hit, open
no new passage), local deletion gives no material localization benefit.
v1's gain came from deleting real or passage-opening cells. The corridor
section needs a controlled slow re-map.

**Still to do:** fresh scans at the corridor midpoint and the Hall. This
needs the operator to place ATLAS there; there is no remote driving.

## Supervised slow-speed recording plan (corridor re-map; operator drives)

Purpose: record clean data to rebuild only the Dhruv Room → Hall section
offline. There is no live SLAM, no mode switch, and no change to Nav2, AMCL,
EKF, motor or safety settings.

1. **Preconditions**
   - Battery above 40% and not charging.
   - Monitor VERIFIED at Dhruv Room.
   - Autonomy disabled; e-stop in hand.
   - People out of the corridor.
   - Doors in their normal positions; note which are open or closed.
2. **Start the recording** (Claude, with your go-ahead at that moment). This
   is read-only:

   ```
   ros2 bag record -o ~/project_atlas/data/commissioning/slow_remap_dhruv_hall_<time> \
     /scan /scan_raw /odom /yahboom/odom /lidar/odom /im10a/imu/bias_corrected_candidate \
     /tf /tf_static /cmd_vel /atlas/drive_mode /amcl_pose /atlas/localization_check
   ```
3. **Route** (operator drives manually; ≤ 0.15 m/s; turns ≤ 15°/s, so a 90°
   turn takes ≥ 6 s):
   1. Dhruv Room: parked 10 s.
   2. Room exit: stop 5 s.
   3. Corridor west end: stop 5 s.
   4. Corridor midpoint: stop 5 s, then one slow full turn in place (≥ 24 s),
      then stop 5 s.
   5. Corridor east end: stop 5 s.
   6. Hall entrance: stop 5 s.
   7. Hall: parked 10 s.
   8. Return the same way with the same stops.
   9. Dhruv Room: parked 10 s.

   Expected time: about 4 minutes each way.
4. **Stop the recording.** Claude checks compliance from `/odom` and
   `/cmd_vel`. Any segment over 0.15 m/s or 15°/s is excluded or repeated.
5. **Offline processing** (`tools/local_map_audit`):
   - verify both ends with the LiDAR;
   - anchored ICP, with chain closure before pinning ≤ 0.15 m / 3°;
   - build a local submap for the corridor box only, merged at the verified
     anchors.
6. **Acceptance before any promotion request**
   - No parallel duplicate walls 0.15–0.6 m apart.
   - Front wall / door recess, room exit and left wall match the fresh
     parked scans (beyond-15 cm ≤ 1%, through-wall rays roughly halved).
   - Parked checks 15/15.
   - Corridor windows: WRONG = 0 and OK ≥ 40/48.
   - AMCL replays improve on the active map.
   - No new reachable space unless you confirm it physically.
   - Promotion is a separate approval.
