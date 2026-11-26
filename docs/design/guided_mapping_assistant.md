# Guided Mapping Assistant — design (2026-11-16)

Status: DESIGN + phase-1 offline modules. Nothing deployed. No motion authority anywhere in this feature.

Owner request (2026-11-16, paraphrased):
- "I drive the rover myself and the dashboard shows the map being built live."
- "Tell me in real time whether each area is good or whether I must drive there again, and when the map is acceptable."
- "Use the depth camera, the LiDAR and the ultrasonic sensors together, so that things the LiDAR cannot see are captured."
- Later: "the rover maps the whole home by itself."

## 1. What already exists (do not rebuild)

| Piece | Where | Status |
|---|---|---|
| Manual mapping session (owner drives, mission control runs slam_toolbox) | `atlas_mission_control.py`, `mapping_session.json` | live; light mapping profile pauses Nav2, voice, Astra etc. |
| Light mapping CPU budget | blockers 2026-11-13/14 | SLAM ~2–4 % CPU after the DDS buffer fix; the session recorder ~33 % |
| Mapping guard (stops a session on overload) | `atlas_mapping_guard_core.py` | live |
| Map acceptance gate | `atlas_map_acceptance_core.evaluate_acceptance_evidence` | live: closure ≤ 0.15 m / 10°, connectivity, both Nav2 plans, startup stillness, guard trips, tf-jump integrity |
| Final-map consistency path (replaces only the map→odom JUMP limits) | `atlas_final_map_consistency.py` | live since 2026-11-14 16:37 |
| Parked review + transactional promotion | `transactionally_promote_map_pair` | used for remap 13 (map 38253aab) |
| Live mapping page | `web/v2/mapping.html`, `/api/map`, `/map.png` | live; draws /map PNG + pose + plan; refreshes the PNG every 1.5 s only while the map is fresh |
| Stop-and-go coach (MOVING / WAIT / GO from scan fit) | `tools/drive/stop_and_go_coach.py` | terminal only |
| Scan-fit core | `atlas_scan_fit_core.py` | live (≥ 85 % of returns within 0.15 m) |
| Astra depth → 2D obstacle scan (base_link, ±30°, 0.35–3.0 m) | `atlas_astra_obstacle_core.py`, `/astra/obstacle_scan` | live |
| Ultrasonic validity (front/rear, VALID only) | `atlas_ultrasonic_validity.py`, `/ultrasonic/*` | live |
| Virtual obstacles (owner-confirmed polygons → /map_nav + guard) | `config/virtual_obstacles.json`, `atlas_virtual_obstacles.py` | deployed 2026-11-16 18:04 |
| Frontier exploration params | `config/atlas_explore_params.yaml` (explore_lite style) | not used since Oct |

Lessons this design must respect (from `ATLAS_CURRENT_BLOCKERS.md`):
1. **CPU / DDS.** Remaps 1–8 were rejected under a CPU-bound mapping mode; the "sticky overload" was a DDS packet storm from undersized socket buffers (fixed 2026-11-14). The dashboard socket still shows drop bursts about every 90 s. → every new live publisher is low-rate, small and best-effort; the heavy work stays offline.
2. **SLAM flip-flop in the hall** (remaps 9–13): local scan matching is under-constrained along the long hall wall; jumps of 1.3–1.5 m map→odom were frame corrections, and the final map was still consistent (median fit 100 %, pose offset ≤ 24 cm). → the quality score must show *where* scan matching was weak, and must not judge the map by map→odom jumps alone.
3. **Places saved during a session overwrite accepted places** (fixed with `merge_session_places`). → the assistant never writes places.
4. **The light profile did not start the footprint filter**, so there was no /map on the dashboard (open bug 1); **the mapping page drew old-map places** (open bug 3, fixed by `mappingMode()`).
5. **Owner-confirmed decisions are not relaxed by this feature**: acceptance limits, the 0.93 unique-place bar, and the jump/closure gates stay as they are.

## 2. Goals and non-goals

Goals (phase 1):
- Live map on the dashboard while the owner drives, throttled for CPU and Wi-Fi.
- A per-region quality verdict, ACCEPTED / WEAK / UNSEEN, with a reason, plus English prompts:
  "Weak area: drive here again", "Unexplored opening: drive closer", "Map ready for review".
- An *invisible objects* layer from Astra depth + ultrasonic where the LiDAR has no echo. It produces **candidate**
  polygons in the `config/virtual_obstacles.json` format, which the owner confirms one by one.
- The final accept/reject decision stays with the existing acceptance gate and the parked review.

Non-goals:
- Feeding depth or ultrasonic into SLAM. SLAM stays LiDAR-only (CPU budget, and depth noise would corrupt scan matching).
- Any motion command, goal, or change to mux/guard behaviour. The assistant is read-only advice.
- Changing acceptance thresholds.

## 3. Architecture

```
          LIVE (rover, during a manual mapping session)                 OFFLINE (Mac or parked Jetson)
 /scan ─┐                                                              session bag ─► replay_guided_mapping.py
 /tf  ──┼─► atlas_guided_mapping.py (1 Hz, nice 10) ─► /atlas/mapping_quality (String JSON, ≤ 4 KB)
 /map ──┤        uses atlas_map_quality_core          ─► /atlas/mapping_quality_png (≤ 1/5 Hz, ≤ 30 KB)
 /astra/obstacle_scan ─┤ atlas_invisible_objects_core  ─► /atlas/invisible_object_candidates (String JSON, on change)
 /ultrasonic/* ────────┘
                                   ▼
             atlas_status_web.py (/api/mapping_quality, /mapping_quality.png) ─► web/v2/mapping.html overlay
                                   ▼
          stop session ─► existing acceptance gate ─► parked review ─► promotion (unchanged)
          candidates   ─► owner confirms on the page ─► virtual_obstacles.json (after "Yes, deploy")
```

Both cores are pure Python (no ROS, no NumPy requirement) so the identical code runs live, in the offline replay and in
unit tests.

### 3.1 Live map view (throttled)

- Reuse the existing `/api/map` + `/map.png` path (PNG is already encoded once per /map message on the rover, and the
  page fetches it at most every 1.5 s while the map is fresh, otherwise every 30 s).
- New overlay layer, drawn on the same canvas transform (`worldPixel`):
  - quality tiles (0.5 m): green ACCEPTED, amber WEAK, no fill UNSEEN-but-driveable, red outline "drive here again";
  - frontier segments (cyan dashes) with a length label;
  - invisible-object candidates (magenta hatched polygons, labelled "Candidate 1…n").
- Bandwidth budget: quality JSON ≤ 4 KB at 1 Hz (tiles are sent as a run-length list of non-empty tiles only);
  the overlay PNG is optional and ≤ 30 KB every 5 s. The dashboard polls `/api/mapping_quality` every 2 s and pauses
  when the tab is hidden (same pattern as `refresh()`).
- Fix open bug 1 as part of phase 1b: the light mapping profile starts `atlas-map-footprint-filter` (or the page reads
  slam_toolbox's /map directly).

### 3.2 Quality score (`scripts/atlas_map_quality_core.py`)

Inputs per accepted scan sample (decimated to ≤ 2 Hz and only after the rover moved ≥ 0.1 m or 5°, like SLAM itself):
SLAM pose (map→base_link at the scan stamp), the scan, and the current /map grid.

Per cell (map resolution, 5 cm):
- `hits` — LiDAR endpoints in the cell; `passes` — beams that crossed it (Bresenham ray cast, capped at 6 m).
- `views` — number of distinct viewpoints (0.3 m / 30° buckets) that observed the cell.

Per tile (0.5 m × 0.5 m, aggregated from cells):
- **coverage**: fraction of the tile's known cells observed from ≥ 2 viewpoints;
- **scan-match confidence**: the median scan-fit (fraction of returns within 0.15 m of an occupied cell of the *current*
  map; the same metric as `atlas_scan_fit_core`) of the samples taken while the rover was inside or looking into the tile;
- **pose jumps**: any map→odom correction ≥ 0.25 m or ≥ 5° whose rover position falls in the tile (SLAM flip-flop marker);
- **frontier**: free cells adjacent to unknown cells; segments ≥ 0.30 m wide (the rover is 0.36 m wide) are reported.

Verdict per tile:
- ACCEPTED: coverage ≥ 0.6, median fit ≥ 0.85, no pose jump in the last pass;
- WEAK: observed, but fails one rule → reason text ("few viewpoints", "scan match weak (fit 0.72)",
  "position jumped 1.3 m here");
- UNSEEN: no observations (not shown unless it borders driven area).

Session verdict: "Map ready for review" when all tiles on the driven corridor are ACCEPTED, no frontier ≥ 0.6 m is
inside the area the owner said to map, and the rover is back within 0.5 m of the start (closure is judged by the gate,
not here). It is advice only; the acceptance gate decides.

The hall lesson: in remap 10 the live fit at the turnaround was 79–96 % while SLAM alternated, so the hall tiles
would show WEAK with "position jumped" — exactly the prompt the owner needs ("drive slowly past the long wall again" /
"do the turn where the room has corners").

### 3.3 Invisible objects layer (`scripts/atlas_invisible_objects_core.py`)

Evidence only where depth/ultrasonic see something **and the LiDAR does not**:
- Astra `/astra/obstacle_scan` (base_link, ±30°, 0.35–3.0 m): for each bin with a finite range r_d, look up the LiDAR
  range in the same bearing (±2.5°, the min). If the LiDAR has no echo, or its echo is farther than r_d + 0.25 m, the
  depth endpoint is an *invisible-object hit*. Otherwise it is LiDAR-visible and ignored.
- Ultrasonic front/rear (VALID only, ±10° cone, 0.03–2.0 m): the same test against the LiDAR min in the cone. A hit marks
  the cone arc cells at the range (weaker weight 0.5, the cone is wide).
- Map test: hits on cells that are already occupied in /map (±1 cell) are dropped (the wall is mapped already).
- Accumulate in an evidence grid (5 cm): `hit_weight`, plus `views` (distinct viewpoints). Depth "free" observations
  through a cell (a depth ray passing it) count as misses, so moving people fade out.
- Candidate cell: hit_weight ≥ 3, ≥ 2 viewpoints, hit ratio ≥ 0.5.
- Cluster (8-connected), drop clusters < 0.02 m², pad 0.05 m, output an axis-aligned rectangle (oriented box later if
  needed) as a polygon, with evidence: hit count, viewpoints, sources (depth / ultrasonic), min distance to named places.
- Output format = `virtual_obstacles.json` entries plus `"candidate": true` and `"evidence": {...}`. **Nothing is added to
  Nav2 until the owner confirms a candidate** and says "Yes, deploy" (restart parked + latched).
- Evidence is pooled over ±2 cells (±10 cm), because hits move between 5 cm cells as the rover moves. For depth and
  ultrasonic the hit ratio is pooled too, which keeps sparse depth noise out (a per-cell ratio produced a 0.76 m² false
  blob over the Dhruv Room place in the bag-8 replay).

### 3.3b Map-change layer (same core, separate instance)

The hall sofa is not fully invisible: the LiDAR answers on it part of the time (black leather), and the saved map is
simply out of date there. `InvisibleObjects.add_unmapped_lidar` with `MAP_CHANGE_POLICY` collects LiDAR returns on
cells the map says are FREE, with no mapped wall within 2 cells. LiDAR rays through a cell count against it, so people
fade out. The hit ratio here is per cell with a lower bar (0.25), because grazing rays cross the cells just in front of
a real surface and the LiDAR flickers on dark materials. Output: "Map change N" polygons (orange on the page). In a live
mapping session SLAM maps these by itself; on an existing map they say "remap here, or confirm a virtual obstacle".

Why not into SLAM: depth noise and a ±30° field would degrade scan matching, CPU goes up, and the virtual-obstacle path
already gives Nav2 and the guard what they need without touching localization.

### 3.4 Prompts (dashboard, English only)

| Condition | Prompt |
|---|---|
| WEAK tile within 2 m of the rover | "Weak area ahead: drive slowly through here again" |
| WEAK because of a pose jump | "Position jumped here: stop, wait for GO, then continue slowly" |
| Frontier ≥ 0.6 m inside the driven area | "Unexplored opening: drive closer to fill it in" |
| New invisible-object candidate | "Object the LiDAR cannot see: candidate N (check it on the map)" |
| All corridor tiles ACCEPTED and back near start | "Map ready for review: stop the session when parked" |
| Fit < 0.60 while stopped (coach rule) | "Wait: LiDAR does not match the new map yet" |

The voice narrator may speak a Hindi version of the same prompt (narrator only; the dashboard stays English).

### 3.5 Acceptance (unchanged)

The assistant's verdict is shown next to the gate's result but never replaces it. On stop: existing evaluation
(closure, connectivity, Nav2 plans, stillness, guard trips, final-map consistency) → parked review → transactional
promotion. The assistant only adds evidence to the review screen (tile summary, candidate list).

## 4. CPU, Wi-Fi and safety budget

- `atlas_guided_mapping.py`: one node, `Nice=10`, `CPUQuota=15%`, best-effort subscriptions with depth 1, scans decimated
  to ≤ 2 Hz, work bounded per tick (ray casting of ≤ 360 beams × ≤ 120 cells; tile summary every 1 s).
  Abort rule: if the mapping guard reports CPU idle < 25 %, the node pauses itself (publishes "paused: CPU").
- Started only in a manual mapping session (feature-on-demand trigger "mapping"), never during autonomous drives.
- No new reliable large topics (DDS storm lesson). The dashboard reads via the status web, not via rosbridge.
- Read-only: no cmd_vel, no goals, no place writes, no map writes. Candidates only become obstacles through the owner's
  confirmation + deploy.
- No rclpy probes during drives: all evaluation of this design is done on recorded bags.

## 5. Phase plan

**Phase 1a (this change, offline-first) — DONE 2026-11-16, see section 7:**
- `scripts/atlas_map_quality_core.py` + tests;
- `scripts/atlas_invisible_objects_core.py` + tests;
- `tools/mapping/bag_reader.py` (pure sqlite3 + CDR for the few message types needed, so replays run on the Mac);
- `tools/mapping/replay_guided_mapping.py`: run both cores on a saved bag + map, write a PNG overlay and JSON.
- Acceptance for 1a: on `stage3_roundtrip8_20261116`, candidates appear at the owner-confirmed hall objects
  (sofa ≈ x −0.3…0.75, y −6.4…−4.7; glass table ≈ x 0.8…1.35, y −6.3…−5.6) and not along mapped walls.

**Phase 1b (needs the owner's "Yes, deploy"; parked + latched):**
- `scripts/atlas_guided_mapping.py` live node + systemd unit (feature-on-demand trigger "mapping");
- status web endpoints + mapping page overlay + prompts;
- footprint-filter start in the light profile (open bug 1).
- Test drive: one short owner-driven manual mapping session in Dhruv Room → corridor, parked review afterwards.

**Phase 2 (only after Stage 3 passes):** autonomous frontier exploration.
- Frontier goals from the same quality core (frontiers + WEAK tiles as targets, with the "drive slowly" speed cap),
  validated by Nav2 on the inflated costmaps, through the existing mux / LiDAR guard / E-STOP chain.
- Owner holds the remote; the rover stops at every goal (stop-and-go), and the explorer never enters a tile with an
  unconfirmed invisible-object candidate.
- `config/atlas_explore_params.yaml` values are the starting point (min_frontier_size 0.10, progress_timeout 30 s).
- Not started before: Stage 3 PASS, the turn_sign issue understood, and the owner's explicit OK.

## 6. Open questions for the owner

1. Tile size 0.5 m: fine for rooms; the corridor may need 0.25 m.
2. Should ultrasonic-only candidates (no depth confirmation) be shown, or only depth-confirmed ones?
3. Glass and mirrors: depth also fails on clear glass. The table was seen by the LiDAR legs / depth frame edge; a
   glass panel may need a manual polygon drawn on the page (phase 1b: "draw obstacle" tool).

## 7. Phase 1a results (2026-11-16, offline only, nothing deployed)

Files:
- `project_atlas/scripts/atlas_map_quality_core.py`: tiles, frontiers, prompts, session verdict, `pose_jumps`.
- `project_atlas/scripts/atlas_invisible_objects_core.py`: depth/ultrasonic candidates, map-change layer, `overlaps`.
- `project_atlas/tools/mapping/bag_reader.py`: pure sqlite3 + CDR reader (LaserScan, Float32, String, TFMessage, PoseWithCovarianceStamped).
- `project_atlas/tools/mapping/replay_guided_mapping.py`: replay → `<out>.json` + `<out>.png`.
- Tests: `test_map_quality_core` 10, `test_invisible_objects_core` 11, `test_guided_mapping_replay` 3 (synthetic CDR bag end to end). 24/24 pass on the Mac (pure Python, no NumPy).

Replay of `stage3_roundtrip8_20261116` on `atlas_latest` (map 38253aab) with the owner's virtual obstacles
(`docs/design/guided_mapping_replay8_20261116.png`; 15 s on the Mac):
- Pose from map→odom (AMCL) ∘ odom→base_link; 12 483 scans → 71 decimated samples (path 12.2 m; the rover reached
  y = −5.14, i.e. the hall entrance, not the table area).
- Quality: 120 ACCEPTED, 33 WEAK (31 "seen from too few positions" at the map edges, 1 scan match 0.82–0.83), 6 openings
  ≥ 0.6 m near the path. Verdict "Keep mapping … drive back to the start". This is expected for a one-way localization
  drive, not a mapping session; no AMCL map→odom step reached the 0.25 m / 5° jump threshold.
- Invisible (depth/ultrasonic, LiDAR silent) candidates:
  - 1: x 1.7–2.35, y −2.7…−1.8, depth + ultrasonic. The hall-door / corridor frame, a known LiDAR no-echo spot (blockers: door-frame blind bins).
  - 4: x −0.1–0.45, y −7.25…−6.95, depth only, very strong. The dark wallpaper wall where the map has no wall (Astra saw it at y ≈ −6.5…−7.1).
  - 6: x 1.8–2.05, y −3.55…−3.2, depth + ultrasonic. The corridor point earlier seen as LiDAR hits at (1.5–1.7, −3.0…−3.5).
  - 2, 3, 5: ultrasonic only, in Dhruv Room. Low objects or floor echoes; unconfirmed (open question 2).
- Map changes (LiDAR on map-free cells): "Map change 7" x 0.45–0.75, y −5.0…−4.7 **overlaps the confirmed sofa** (its
  near corner, the only part seen from the hall entrance). Others in Dhruv Room / corridor (furniture moved since the map,
  per the 2026-11-14 note "accepted map is stale there"); unconfirmed.
- Not found: the glass table (the rover never got close; glass is a depth and LiDAR weak spot, see open question 3), and
  the cabinet (outside the field of view on this route).

Evidence gap, to verify on the rover (read-only, parked): with `free_thresh: 0.25` the map_server threshold rule alone
would load PGM value 205 as FREE (1 − 205/255 = 0.196 < 0.25). The replay therefore treats 205 explicitly as unknown. Whether
the live `/map` shows 205 cells as −1 or 0 was not checked here; the guard's map-known-gaps logic and the costmaps depend
on it.

## 8. Phase 1b (2026-11-26, owner "Yes, start 1b") — DEPLOYED 13:31 (live mapping-session check pending)

- `scripts/atlas_guided_mapping_engine.py` (pure): session handling (a new session id resets everything), CPU pause
  (< 25 % idle, resume > 35 %; unknown CPU never pauses), compact payload (run-length tile rows, <= 4 KB, detail lists
  trimmed first), English prompts and notes. The frontier scan (whole map) is refreshed at most every 5 s.
- `scripts/atlas_guided_mapping.py` (node): subscriptions and the TF listener exist only while the session is `active`.
  It publishes only `/atlas/mapping_quality`. Rates: scans <= 2 Hz, depth <= 2.5 Hz, ultrasonic <= 4 Hz, payload every 2 s.
  Engine times are wall/ROS time (scan stamps); the monotonic clock only paces work.
- `systemd/user/atlas-guided-mapping.service`: Nice 10, CPUQuota 15 %, CPUWeight 20, MemoryMax 250M.
- `atlas_status_web.py`: `/api/map` gains `mapping_quality` (None when missing, older than 10 s or not schema 1).
- `web/v2/mapping-quality.js` + one script tag in `web/v2/mapping.html`: overlay (green/amber tiles, cyan openings,
  magenta objects) and a "MAPPING ASSISTANT" card. It makes no request of its own and is hidden outside a session.
  No Node.js on the Mac or the Jetson, so the JS is checked statically only (read-only, English, escaping, fields).
- Tests (Jetson copy `/tmp/guided1b`): engine 15, node with stubbed rclpy/tf2 6, web/overlay 8; with the affected suites
  (quality core, invisible objects, replay, status-web plan, web v2, default route, systemd ordering, virtual obstacles)
  83/83 OK.
- Cost, measured offline on the Jetson (bag 8, real map, 29 min): scan 0.27 ms, depth 4.4 ms, ultrasonic 0.5 ms,
  payload median 76 ms (max 86) every 2 s → about 4.3 % of one core; payload <= 2.2 KB.
- Known limit: the light mapping profile pauses `atlas-astra-obstacles`, so during a mapping session the depth source
  is absent and the page says so ("Depth camera: no data …"). Keeping Astra on while mapping is a separate owner
  decision (CPU), not part of this change.
- Not done: deploy (owner "Yes, deploy"; parked + E-STOP latched), a live mapping session check, commit/push ("Yes, push").

## 9. Saved-map check (2026-11-26, owner "Yes, build it") — DEPLOYED 17:02

Outside mapping sessions the same node answers "is my saved map still right?". The map-change layer of section 3.3b
runs live against `/map_nav` (accepted map + confirmed virtual obstacles), with the pose from `/amcl_pose` (a scan counts
only with an AMCL pose within 0.5 s). A frame is used only while the scan fits the map (at least 85 % within 0.15 m), so
a localization error is never reported as a changed room. It is paused while autonomy is armed and when the CPU is
busy. The mapping page shows a "SAVED MAP CHECK" card with orange "Map change N" boxes and the advice "update the map,
or confirm it as a fixed object". Cost on bag 8: about 0.4 % of one core. Details and evidence: blockers log, 2026-11-26.
