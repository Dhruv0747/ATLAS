# Local map audit (read-only)

Used for the 2026-10-10 Dhruv Room -> Hall analysis
(`docs/audits/ATLAS_LOCAL_MAP_REPAIR_DHRUV_HALL_2026-10-10.md`).
Nothing here publishes to ROS, moves the rover or writes the active map.

1. On the Jetson: `extract_bag.py <bag> <out.npz>` for each drive, and
   `live_scans.py live.npz 25` while parked.
2. Put the npz files, `atlas_latest.pgm/.yaml` in one folder and set
   `ATLAS_MAP_AUDIT_DIR` to it.
3. `anchors.py` (LiDAR-verify parked ends) -> `register.py` (map-independent
   anchored ICP per drive) -> `evidence.py` (per-cell see-through/hit votes) ->
   `candidate.py` (local candidate in `candidate/`) -> `bundles.py` +
   `score_replays.py` (AMCL core replay, needs the motion_replay build) and
   `gs_eval.py` (global-search verdicts, old vs candidate).
