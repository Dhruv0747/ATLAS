# AMCL stationary particle-support finding

Read-only continuation from `ec0b061`, 2026-10-09. The operator authorized a stationary capture. No motor command, navigation goal, initial pose, service restart or production parameter change was issued.

## Confirmed new evidence

A bounded passive recorder captured all requested topics at
`/home/jetson/project_atlas/data/diagnostics/amcl_stationary_passive_20261009_2113`.
The bag includes map, scan/raw scan, TF/static TF, wheel/EKF odometry, IMU,
encoder health, safety status, AMCL poses, particle clouds and ROS logs.
It stopped cleanly; no continuous recorder remains. Initial short-lived ROS
discovery omitted AMCL, but the recorder discovered every topic within about
four seconds. That omission was not evidence of a failed AMCL process.

The AMCL publication window spans 59.394 s with 60 poses and 60 clouds.
No >0.5 m pose step occurred. The pose remained approximately
`(3.8424, -0.4833, 2.7336 rad)`, the previously identified wrong return pose.
Wheel/EKF odometry and map-to-odom stayed stationary. No new physical pose
measurement was taken in this capture.

Each cloud contains 2,000 entries but only **one geometric support point**
when x/y/yaw are rounded to 1e-6 m/rad. Five bitwise-distinct points differ
only at numerical precision: x extent is zero and y extent is 2.78e-16 m.
Normalized-weight effective sample size is approximately 2,000 despite this
collapse. Therefore published particle count, uniform-weight ESS and tiny
covariance do not establish localization confidence. AMCL X/Y covariance
was approximately -1.44e-12/-1.51e-14, consistent with roundoff at zero
spread; this is not meaningful negative physical uncertainty.

There were 451 scans. Header-to-bag-receipt age was 0.137 s median,
0.264 s 95th percentile, and 0.277 s maximum; largest scan-header gap was
0.274 s. These are observer/recording latencies, not AMCL callback latency.

The same audit of the earlier `amcl_roundtrip_20261009_final` bag found:

| Observation | Entries | Distinct support at 1e-6 m/rad |
| --- | ---: | ---: |
| First cloud | 501 | 29 |
| First collapsed cloud, 104.009 s after first cloud | 2,000 | 1 |
| Last cloud | 501 | 7 |
| New stationary capture, first and last | 2,000 | 1 |

The earlier bag contains 610 clouds. At the first collapse, x/y extents
were 4.68e-9/2.85e-8 m. The last cloud again spans multiple positions, so
the earlier collapse was not permanent throughout subsequent motion. These
results establish that impoverishment occurred during the saved sequence,
not only after today's long idle period.

## Verified mechanism and remaining causal boundary

The deployed mission controller requests `/request_nomotion_update` every
second unconditionally to satisfy a pose-age watchdog. The inspected AMCL
1.1.20 implementation sets `force_update_`; its next scan updates weights
and `resample_interval=1` resamples every update. Resampling copies existing
particle poses. Configured `recovery_alpha_fast=0` and
`recovery_alpha_slow=0` disable adaptive random-pose recovery; zero odometry
delta supplies no motion-model spread. Repeated forced updates therefore
provide a concrete mechanism for eliminating particle alternatives while
stationary. Once support has collapsed, uniform weights cannot recreate
the missing locations.

The current geometric collapse is verified. The exact likelihood/cluster
history that selected the original wrong pose and caused the five historic
jumps is still unrecorded and unverified. This finding does not isolate the
contribution of wheel-heading error, map ambiguity or scan timing during
motion. Zero jumps at an already collapsed wrong pose is not a fix.

## Next necessary software experiment

Test the forced-update/resampling policy in isolation with controlled
initial particle support and recorded scans/odometry. Compare geometric
support and pose accuracy as well as jumps. A candidate must preserve
sensor/TF freshness checks and safe rejection of uncertain localization;
simply stopping pose publications or relaxing the 2.5 s watchdog cannot be
counted as a pass. The desired design separates health reporting from
repeated Bayesian assimilation of stationary scans. Existing production
settings remain unchanged; no additional manual loop is requested now.

## Reproduction and validation

`atlas_amcl_particle_diversity.py` reads saved clouds without creating a ROS
node or publisher. Four unit tests passed: duplicate uniform clouds, broad
clouds, floating-point duplicate handling and invalid inputs. Both bags
above completed successfully with the diagnostic. Existing jump analysis
found no events in the new capture. This validates the measurements, not an
AMCL repair or autonomous release.

Deployed parameter file SHA-256:
`24620bf4416a1a5b215353876b4fb63458e974a41425103c7b157fb03df80706`.
Saved-map YAML SHA-256:
`d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4`.
AMCL PID remained 8075, running since 10:52. Snapshot temperature was
60.25 C; RAM 5,091/7,620 MiB, no swap usage. These snapshots are not a load
endurance qualification. Raw bags remain on the Jetson and are not committed.
