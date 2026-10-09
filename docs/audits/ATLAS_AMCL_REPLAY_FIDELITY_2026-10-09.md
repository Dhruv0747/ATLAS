# AMCL replay fidelity, continued from `99bd418`

This audit uses only the existing Hall→Dhruv Room rosbag. The new replay ran
in isolated ROS domain 179, published only `/scan`, `/odom`, `/tf` and
`/tf_static`, and launched AMCL/map server without EKF, Nav2 control, motors or
steering. It did not alter production settings.

## Input and state comparison

The recorded occupancy grid and `/home/jetson/project_atlas/maps/atlas_latest.pgm`
have identical dimensions, origin and **51,040/51,040 trinary cells**. Saved-map
file drift is excluded for this recording. The scan payload/header stamps
and original `/odom` and odom→base TF remain available in the original bag.

| 75.918 s window | Original | Earlier regenerated-EKF input | New recorded-odom input | New replay output |
| --- | ---: | ---: | ---: | ---: |
| LiDAR scans | 537 | 529 | 537 | 524 seen by recorder |
| Original `/odom` | 759 | 0 (EKF regenerated) | 759 | 743 seen by recorder |
| AMCL poses | 168 | — | — | 120 |
| Large AMCL steps >0.5 m | 5 | — | — | 0 |
| Maximum AMCL step | 2.206 m | — | — | 0.239 m |

The old extracted input omitted eight scans from the corresponding original
receipt-time window. The new replay restores all 537 and all 759 original
odometry messages in its **input**, but the output recorder sees only 524
scans and 743 odometry messages. The 13 absent scan header stamps are all in
the first ~1.7 s of the window. Its AMCL log explicitly reports an early scan
rejected because its header timestamp preceded the transform cache. Recorder
counts are not a direct count of scans AMCL processed; nevertheless the
recorded stream and startup TF availability differ from the live run.

At the clip boundary, the original last AMCL pose was only 0.333 s old and
had XY standard deviation ~0.001 m and yaw standard deviation ~0.07°. The
last particle cloud was 0.338 s old, with 2,000 particles and ~0.001 m XY
spread. The replay initializes AMCL from this **mean pose only**, not the
2,000 particle poses, resampling state, RNG state, TF buffer history or
earlier scan/odom update sequence. Its first reported cloud is also compact,
but that does not mean its hidden filter state matches the original.
Over the clip, original particle XY spread had median/max 0.810/1.414 m;
the new replay had 0.415/1.279 m. The 168-versus-120 AMCL update count and
different spread demonstrate that the particle-filter trajectory diverged.
The bag does not include a snapshot of AMCL's internal filter/RNG state or a
runtime parameter-event history that proves the exact live AMCL parameters.

## Closer replay result

The command-free recorded-odom replay was run twice from the same saved data.
Both outputs had 120 AMCL poses, 524 recorded scans, **zero** >0.5 m jumps,
maximum step 0.239 m, median XY pose uncertainty 0.415 m, final ~19 s
position span 0.462 m and maximum heading step 8.789°. This establishes a
repeatable *replay* result, but **not** reproduction of the original five
jumps. No EKF/AMCL candidate can pass a jump-reduction gate using this replay.

A 1× full 295.131 s replay from the earliest bag timestamp also yielded only
120 AMCL poses. Its last pose **header stamp** was `1791528989.010 s`, before
the first original post-stop jump at approximately `1791528993.627 s`;
recorded scans and odometry continued to the bag end. The AMCL startup log
reported a backward simulated-clock jump and TF buffer clear. Thus the full
replay did not exercise AMCL pose updates through the original failure window
either; it cannot validate zero jumps. The original first AMCL pose was
recorded near the beginning of the bag, so this cannot be attributed simply
to a seed chosen minutes after playback began.

To test the update gate *without changing production*, two isolated 75.918 s
replay set only `update_min_d/a` to zero in generated replay YAML. It produced
512 AMCL poses and one 1.827 m correction in **each repeat**, with ~1.49 m XY uncertainty and
only 0.0116 m recorded-odom change at that event. The diagnostic same-scan
endpoint fit changed from 65.0% to 98.1%. This demonstrates that continuing
AMCL updates under near-stationary motion can expose a large competing-pose
correction. It is **not** the original five-event sequence: the update count
greatly exceeds 168 live, the event timing/pose differs, and the live
`update_min_d/a` values were not recorded. The production AMCL service was
inactive at audit time, so current runtime values could not be read back.

## Conclusion and smallest next evidence

The replay failure has concrete fidelity causes: the earlier EKF replay
regenerated odometry and dropped eight source scans; even the closer replay
loses startup observations, has a different AMCL update count, and cannot
restore the original particle filter and pre-clip processing history. These
factors are sufficient to invalidate a zero-jump success claim. Which one is
decisive for the live instability is **not** verified. The live failure remains
stationary AMCL hypothesis switching; its upstream cause remains unresolved.

The full-bag attempt also failed to reproduce the live update sequence. The
recording lacks AMCL's exact internal state/RNG and a runtime parameter-event
history. If a new recording is ultimately needed, the smallest
safe test is **stationary observation only** with motor power off after normal
localization startup: record AMCL parameters/config identity, particle cloud,
pose, scan, odom and TF with their timestamps before and after any spontaneous
pose correction. Do not physically drive, reseed, restart services, or change
parameters without separate operator permission. A stationary-only run may
still fail to create the uncertainty that developed during the original drive;
that limitation must be reported rather than assumed away.

## 2026-10-09 follow-up: the missing live update trigger

Read-only inspection of the original Jetson journal and mission-control source
found a specific replay-fidelity omission: `atlas_mission_control.py` calls
`/request_nomotion_update` once per second, and AMCL logged those requests
throughout the original 12:26:33–12:26:44 IST jump window. The original bag
contains the resulting AMCL messages but not the service calls. After the last
remote command, recorded `/odom` and odom→base TF moved at most **0.01221 m**
and **0.504°**, below the replay gates of 0.05 m and 0.05 rad, while the
original emitted 80 more AMCL poses and 80 particle clouds. Recorded motion
alone could not account for that continuing pose stream.

One isolated, full-295-second replay in localhost ROS domain 179 now issues
the approximately 1 Hz no-motion calls at the journal's 0.578-second clock
phase. Its inputs include only scan, odom and TF; no actuator topics were
played. The client sent 294 calls with zero service-unavailable skips, and
replay AMCL logged 294 requests. Both original and replay emitted **384 total
/ 80 post-stop** AMCL poses. The omitted service trigger therefore explains
why the earlier full replay stopped publishing before the failure window.
The local Jetson output is
`/home/jetson/project_atlas/data/diagnostics/amcl_nomotion_full_20261009/`;
generated bags and logs are deliberately not committed.

| Same Hall return | Original | No-motion replay |
| --- | ---: | ---: |
| AMCL poses, total / post-stop | 384 / 80 | 384 / 80 |
| Post-stop steps >0.5 m within 2 s | 5 | 2 |
| Largest post-stop step | 2.206 m | 3.470 m |
| Large-step time after last command | 2.693–12.780 s | 10.682–13.702 s |

This **reproduces stationary AMCL hypothesis switching as a failure class**,
not the original five-event trajectory. The periodic request explains pose
*updates*, not why AMCL selected a distant hypothesis. Initial particle/RNG
state, exact startup ordering and full live scheduling still differ: the
replay seed pose was taken from the first original AMCL pose **4.779 s after**
the bag began, because there was no earlier pose in the bag. Do not
remove the production heartbeat or tune AMCL/EKF based on this one replay;
the mission-control freshness watchdog depends on it. No production service,
parameter, motor or steering setting was changed. The next discriminating
offline step is to compare particle/scan likelihood evolution around the two
replay jumps against the five live jumps; no candidate fix is ready yet.
