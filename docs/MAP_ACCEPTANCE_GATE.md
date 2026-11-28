# Candidate-map acceptance gate

`atlas_mission_control.py` now treats saving and accepting a map as separate
safety decisions. `/atlas/stop_exploration` saves a hidden candidate and
promotes it to `atlas_latest` only when all evidence belongs to the same
mapping session:

- publication-order `map -> odom` observation covered session start, is fresh,
  has fresh and monotonic TF source stamps, never has an uncovered five-second
  gap, and never jumped more than 0.15 m or 5 degrees;
- the final settled pose closes to session Home within 0.15 m and 10 degrees;
- an offline check reads the exact sanitized candidate YAML/PGM bytes, treats
  every unknown cell as blocked, inflates obstacles and map edges by the rover
  half-width (0.18 m), and proves Hall/Dhruv Room connectivity;
- `/global_costmap/published_footprint` is fresh and at least the commissioned
  0.50 m x 0.36 m footprint;
- Nav2 `ComputePathToPose`, using explicit starts and the live global costmap,
  returns paths from Dhruv Room to Hall and from Hall to Dhruv Room. These live
  Nav2 plans are a supplemental stack check; they do not substitute for the
  exact candidate-byte test.

Plan checks dispatch no navigation goal and publish no velocity. Hall, Dhruv
Room, Home, and the final localization seed must carry the active
`mapping_session_id`.

Every evaluation writes
`.atlas_candidate_<session>.acceptance.json` beside the candidate. Missing,
stale, malformed, wrong-session, or failing evidence rejects the map before
the first accepted-map or map-bound-coordinate write, preserving the previous
accepted pair and rollback backups. Promotion pre-stages the map pair together
with Home, localization seed, and named-place metadata. It commits metadata
first, the referenced image next, and the authoritative YAML last; a rename,
byte-verification, or metadata-verification failure restores the complete old
bundle with its YAML restored last. The old implementation's legacy-coordinate
binding therefore no longer writes anything before promotion. Unversioned
legacy places are staged with the previous map ID, so they fail closed on the
new map. If no previous map exists, they receive an explicit non-current legacy
marker instead of remaining implicitly trusted. Already-versioned old routes
keep their old `map_id` and remain ignored until re-taught against the new
accepted map.

Threshold parameters are `map_acceptance_max_tf_jump_m`,
`map_acceptance_max_tf_yaw_deg`, `map_acceptance_max_closure_m`, and
`map_acceptance_max_closure_yaw_deg`. Required endpoint names default to
`dhruv room` and `hall`. Threshold overrides may tighten, but cannot raise,
the commissioned limits. Never relax footprint or planner margins to pass a
bad candidate.

## Deployment status

The reviewed mission-control and acceptance-core pair was deployed together
while mapping and exploration were inactive, command velocity was zero, remote
stop was latched, and steering was centered. Mission control restarted
`active/running` with zero restarts and reported `READY`. The previously
accepted map remained unchanged with ID `d12a1f183177212a3cc8`; no map,
location, motor, steering, or navigation command was issued. Rollback copies
are in `data/deploy_backups/20261004_map_acceptance/`.

Runtime acceptance of a new map is intentionally untested until the next
complete manual remap supplies session-wide TF evidence, closure, exact
candidate connectivity, fresh footprint, and both no-motion plan checks.
