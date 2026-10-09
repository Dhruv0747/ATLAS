# ATLAS AMCL internal trace — stationary diagnostic

Date: 2026-10-09. This is a **diagnostic-only shadow instance**, not a
production localization fix. ATLAS was stationary; no motor, steering or Nav2
goal command was issued. Production AMCL, its parameters and its map→odom TF
publisher were not replaced or restarted.

## What was built

- Pinned upstream `ros-navigation/navigation2` tag `1.1.20` (commit
  `a097086719c88f781aa59788eca29ac6ca5e56db`), matching the Jetson's
  `ros-humble-nav2-amcl` version `1.1.20`.
- Applied [the small trace patch](../../project_atlas/patches/nav2_amcl_1.1.20_shadow_trace.patch)
  to that tag and built only `nav2_amcl` in
  `/home/jetson/atlas_amcl_trace_ws`. The installed ROS package under
  `/opt/ros/humble` was not overwritten. The patch is zero-context for a
  clean whitespace check; apply it **only** to the pinned tag with
  `git apply --unidiff-zero`.
- The patch publishes `/atlas_shadow/atlas_debug/amcl/pre_resample_particle_cloud`
  **before** resampling removes likelihood differences. Its structured
  `ATLAS_AMCL_TRACE_PRE` log includes scan time, weight sum, effective sample
  count, maximum weight, running likelihood, no-motion trigger and odometry
  delta. `ATLAS_AMCL_TRACE_CLUSTER` records the eight heaviest
  post-resampling clusters' weights and means, including the selected one;
  the total cluster count is retained. This bounds diagnostic log volume.
- The [bounded capture helper](../../project_atlas/scripts/atlas_amcl_shadow_stationary_capture.py)
  launches only the separate `/atlas_shadow/amcl` node, verifies its actual
  `tf_broadcast=false` and input-topic parameters before activation, seeds
  it from a fresh production pose, records inputs and both outputs, issues
  no-motion updates at **1 Hz**, then stops the shadow and bag recorder.
  It is not an autostart service. The [shadow parameters](../../project_atlas/config/atlas_amcl_shadow_trace.yaml)
  use the current AMCL tuning with `tf_broadcast=false` and absolute live
  `/map` and `/scan` inputs.

## Validation and evidence

- Isolated `nav2_amcl` build: **passed** on Jetson. Patch reverse-applies to
  the pinned source; Python syntax and Git whitespace checks passed.
- A first capture attempt reached shadow `inactive` but its lifecycle RPC
  reply timed out under load. The helper now verifies actual lifecycle state
  before proceeding, instead of assuming the transition failed.
- The next attempt exposed a helper pacing bug: it sent 1,623 requests in
  10 seconds. The shadow terminated cleanly, but Jetson load average rose
  temporarily. This run is **not** a valid steady-state capture. The helper
  was changed to a monotonic 1 Hz schedule before the accepted run.
- Accepted bounded run:
  `/home/jetson/project_atlas/data/diagnostics/amcl_shadow_stationary_20261009_paced2`.
  It sent **10 requests in 10 seconds**, produced 11 shadow pose messages,
  and recorded an 8.10 s bag containing 7 pre-resampling weighted clouds,
  7 shadow poses, 25 scans, `/map`, `/tf`, and `/rosout`. The shadow log has
  11 pre-weight and 11 cluster-selection traces. Its observed cluster was
  single and stable (weight 1); effective sample count remained about
  1,999.95–1,999.97 out of 2,000. The traced pose changed by less than
  0.2 mm during this short stationary run. This confirms the capture path,
  **not** long-run localization reliability.
- The shadow exited after capture; no continuous diagnostic process remains.
  The production `/amcl_pose` continued publishing afterward.
- After this capture, cluster logging was bounded to the eight heaviest
  clusters and the isolated package rebuilt successfully. That final binary
  has **not** been used for another live capture; no claim of post-change
  runtime validation is made.

## Limits and next use

The original Hall→Dhruv Room run did not record these internal weights,
clusters or RNG state. This new stationary capture cannot retroactively
explain its five jumps. The shadow also starts from today's production pose,
not the original uncertain particle state; a stable 10-second run is not a
reproduction or a fix. The Jetson was already heavily loaded before this
test, so the shadow must remain **bounded and off by default**. If a future
stationary jump recurs, compare its pre-resampling cloud, cluster weights,
scan/TF/odom and no-motion events. Do not deploy AMCL tuning or resume
autonomous navigation from this short diagnostic pass.
