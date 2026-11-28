# LiDAR Acquisition-Time Correction (2026-10-04)

## Scope and decision

The ATLAS chassis self-filter still performs the same range removal from
`/scan_raw` and publishes the result on `/scan`, but it now preserves the
driver header exactly. No topic, frame, geometry, QoS, service, Nav2, EKF,
SLAM, safety, or actuator setting changed. The reviewed filter was deployed to
the Jetson while ATLAS was stationary and remote-stop latched. No rover
movement was requested.

This is required by the ROS `sensor_msgs/LaserScan` contract: the header stamp
is the acquisition time of the first ray, and `time_increment` locates later
rays within the scan. The upstream RPLIDAR implementation likewise records the
scan start before collecting a revolution and publishes that value in the
header. See the official
[`LaserScan.msg`](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/LaserScan.msg)
and [Slamtec ROS 2 driver source](https://github.com/Slamtec/rplidar_ros/blob/ros2/src/rplidar_node.cpp).

Filter publication time is therefore transport metadata, not a replacement
measurement time. Downstream SLAM, AMCL, costmaps, and RF2O must request the
rover transform at the acquisition stamp associated with the ranges.

## Recorded evidence

The read-only report in
`artifacts/atlas_tf_event_report_20261004.json`, generated from the rejected
Hall → Dhruv Room remap bag, measured:

| Measurement | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Raw receipt minus raw header | 131.27 ms | 261.37 ms | 364.72 ms |
| Filtered receipt minus rewritten header | 4.65 ms | 13.05 ms | 666.88 ms |
| Filtered header minus raw header | 131.59 ms | 261.81 ms | 361.25 ms |
| Absolute raw-to-filter receipt latency | 5.02 ms | 12.40 ms | 49.68 ms |

The filter was not taking 131 ms. It was replacing a scan-start timestamp with
a timestamp near publication after the revolution had already been acquired.
During the largest map correction, commanded yaw rate reached 1.2 rad/s. The
median 131.59 ms shift therefore corresponds to approximately 0.158 rad, or
9.05°, of possible pose-time mismatch during such a turn. This calculation
identifies a credible contributor to turn-time wall smearing; it does not by
itself prove that timestamp replacement caused the complete 1.32 m SLAM
correction.

The old comment claiming a persistent 1.6 s raw-scan delay is not supported by
this current bag. The raw stream was monotonic, had no zero timestamps or
regressions, and had a 131.27 ms median age. The historical bag analyzer keeps
its receipt-time fallback so it can still pair bags recorded under the former
restamping behavior.

## TF and service compatibility audit

- `atlas-lidar.service` remains the sole raw scan producer and still remaps the
  RPLIDAR output to `/scan_raw` in `laser_frame`.
- `atlas-scan-filter.service` still starts the same filter after the driver and
  before SLAM/Nav2. `/scan_raw` → filter → `/scan` is unchanged.
- The filter retains its reliable, volatile, keep-last depth-one output. This
  prevents dashboard load from turning latency into a scan backlog.
- `base_footprint -> laser_frame` remains a static measured transform, so it is
  valid at every scan timestamp.
- The production EKF still publishes `odom -> base_link` at 10 Hz with its
  existing 0.2 s transform-time offset.
- SLAM Toolbox still has a 30 s TF buffer, 1.5 s transform timeout, and a scan
  queue of 20. The measured raw ages (365 ms maximum in this bag) fit inside
  that existing history by a wide margin. Increasing tolerances would hide a
  timing error rather than restore measurement semantics, so no configuration
  change was made.

At process startup, scans older than the first available dynamic TF may still
be dropped normally until the TF buffer is populated. The filter must not make
those samples appear current by changing their timestamps.

## Offline validation

The focused test imports the ROS-facing filter with inert message stubs and
executes the real callback. It verifies that:

- publication-time clock access is not used;
- header seconds, nanoseconds, frame, `scan_time`, and `time_increment` survive
  unchanged;
- the source ranges remain unchanged while chassis returns are removed from a
  copied output range array;
- the existing `/scan_raw` input, `/scan` output, depth-one QoS, and systemd
  entry point remain present.

Run from the repository root:

```bash
python3 -m unittest -v \
  project_atlas.tests.test_atlas_scan_self_filter \
  project_atlas.tests.test_atlas_analyze_tf_event
```

## Stationary deployment result

The stationary capture
`data/commissioning/scan_timing_stationary_20261004_144852` passed the gate:

- all 82 matched `/scan_raw` and `/scan` pairs had byte-identical header
  seconds/nanoseconds and no zero, duplicate, or regressing timestamps;
- absolute filter-pipeline latency was 4.98 ms median, 19.16 ms p95, and
  31.64 ms maximum;
- `/scan` remained approximately 7 Hz;
- `odom -> laser_frame` resolved at the scan acquisition timestamp; and
- no scan-drop, TF extrapolation, or transform-error burst appeared in the
  LiDAR/filter/localization logs.

The deployment backup is
`data/deploy_backups/20261004_scan_timing/atlas_scan_self_filter.py.before`.
This validates stationary timing only. The next remap must still start its full
bag before movement and pass the separate map-quality, closure, footprint, and
autonomous-navigation gates.
