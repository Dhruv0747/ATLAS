# ATLAS Remap Attempt — Rejected Safely (2026-10-04)

## Objective

Create a new Dhruv Room ↔ Hall map that supports collision-free Nav2 planning without changing the commissioned rover footprint, planner, or safety margins.

## Procedure

- Preserved the accepted map before starting.
- Started the versioned `manual_teaching` mapping session.
- Confirmed autonomous Explore Lite remained inactive.
- Manually drove the room-to-room route under remote control.
- Saved Hall, Dhruv Room, and Home in the candidate map frame.
- Recorded LiDAR, raw LiDAR, TF, odometry, IM10A, map, steering, command, and encoder-health topics.
- Saved a temporary preview and ran plan-only validation. No autonomous motor command was issued.

## Evidence

- Candidate mapping session: `47ecfb1d84654407b97f5514c6ed0993`
- Rosbag: `/home/jetson/project_atlas/data/commissioning/remap_hall_dhruv_return_20261004_120247`
- Rejected-session archive: `/home/jetson/project_atlas/data/remap_aborted_20261004_122415`
- Preview: `/tmp/atlas_remap_review_20261004_121734.{yaml,pgm}`
- The outbound leg contributed to live SLAM, but a recorder-launch error meant the dedicated bag began at Hall. The bag contains the Hall → Dhruv Room return leg and stationary validation, not the complete round trip.

## Results

### Live system health

- LiDAR, `/odom`, `map→odom`, `odom→base_link`, costmaps, map topic, planner, controller, BT navigator, and behavior server were live.
- `atlas-explore.service` remained inactive.
- The dedicated bag captured 118,634 messages over 1,128.5 seconds.
- LiDAR scan lag: 4.79 ms median, 12.72 ms p95, 666.88 ms maximum.

### Map geometry

- Raw free-space connectivity existed with 0–0.15 m test inflation.
- Connectivity failed at 0.20 m and above.
- The widest available path still narrowed to approximately 0.30 m full width near candidate-map coordinate `(3.71, -0.81)`.
- ATLAS is approximately 0.36 m wide, so this candidate cannot safely represent the physically traversable passage.
- Nav2 `ComputePathToPose` returned no collision-free path from Dhruv Room to Hall with unchanged commissioned parameters.

### SLAM stability

- Maximum `map→odom` translation jump: **1.3188 m**.
- Maximum `map→odom` yaw jump: **14.197°**.
- Accumulated correction: **19.342 m**.

These corrections explain the ghost/narrow corridor. The failure is mapping/localization consistency, not a planner defect.

### Exact event forensics

The bounded-memory, read-only analyzer in
`project_atlas/scripts/atlas_analyze_tf_event.py` classified the maximum event
with **high confidence** as a
`SLAM_POSE_GRAPH_OR_SCAN_MATCH_CORRECTION_DURING_TURN`:

- The event occurred at bag offset **+161.208456 s**. `map→odom` changed
  **1.318826 m / 14.197321°** in one publication step.
- The before and after transforms carried the **same TF header timestamp**.
  This is a retroactive SLAM correction, not elapsed-time motion between two
  ordinary transform samples.
- The corresponding `map→base_link` discontinuity was **0.229074 m /
  14.197321°** when aligned by TF header and **0.246805 m / 18.544334°** when
  aligned by bag receipt time.
- No matching odometry teleport occurred. The largest step anywhere in the
  full bag was **0.103827 m** on `/odom` and **0.054785 m** on
  `/yahboom/odom`.
- ATLAS was making a high-curvature turn: commanded angular velocity reached
  **1.2 rad/s**, while the corrected IM10A gyro reached **0.967 rad/s**.
- LiDAR remained live. **7,819** raw/filtered scans were paired
  (**99.76%** of the smaller stream); raw-to-filter receipt latency was
  **5.017 ms median / 12.399 ms p95**. The filter version active for this bag
  replaced scan timestamps, producing a **131.594 ms median header shift**;
  this is now reported explicitly rather than mistaken for missing scan pairs.
  The repository correction and stationary deployment gate are documented in
  [the LiDAR timing note](LIDAR_SCAN_TIMING_FIX_2026-10-04.md).
- Encoder consensus briefly became `CRITICAL/UNAVAILABLE` approximately
  **6.7 seconds before** the correction (13 health packets in the surrounding
  10-second window), then recovered to `AVAILABLE` before the exact event.
  This transient may have degraded the trajectory estimate, but the evidence
  does **not** prove it caused the SLAM correction.
- Independent systemd evidence showed **zero EKF and SLAM service restarts**.
  The event was therefore not a service-restart discontinuity.

The **19.342 m accumulated correction is not 19.342 m of net map drift**. It is
the sum of the absolute size of every incremental `map→odom` correction over
the full bag, so repeated corrections in opposite directions all add to that
number. It is useful as an instability indicator but must not be interpreted
as final position error or physical distance traveled.

## Decision and rollback

The candidate was **not accepted** and never replaced `atlas_latest`.

- The rejected session, preview, metadata, and bag reference were archived.
- Accepted map pair was verified unchanged.
- Home, localization seed, and named places were restored together for map ID `d12a1f183177212a3cc8`.
- Saved-map localization was restarted directly at the physical Dhruv Room pose.

Post-rollback stationary diagnostic over 30 seconds:

- AMCL drift: 0.0122 m and 1.60°.
- Maximum AMCL XY standard deviation: 0.0441 m.
- Final yaw standard deviation: 2.11°.
- EKF and wheel-odometry stationary drift: 0.
- Initial TF lookup errors occurred only while the map frame was starting; TF age afterward was healthy.

The accepted map still rejects a Dhruv Room → Hall plan, so room-to-room autonomous driving remains blocked.

## Next controlled attempt

1. Charge the main battery above 40%.
2. Start a fresh versioned manual-mapping session; never use the dashboard Auto Explore button for this test.
3. Record the entire session before movement starts.
4. Drive slowly through the measured bottleneck from both directions, centered in the opening, pausing for several LiDAR revolutions on both sides.
5. Abort immediately if live `map→odom` correction jumps exceed 0.15 m or 5°.
6. Before promotion, require:
   - settled round-trip pose closure;
   - no double walls or ghost obstacles;
   - full-footprint connectivity;
   - successful plan-only paths in both directions with unchanged safety parameters.
7. Promote only through `/atlas/stop_exploration` after every gate passes.

Do not reduce the footprint or obstacle safety margin to force a route through a bad map.
