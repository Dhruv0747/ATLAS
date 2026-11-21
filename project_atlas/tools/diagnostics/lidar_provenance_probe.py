#!/usr/bin/env python3
"""Finite read-only parked scan/TF probe; publishes no ROS messages."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener
from atlas_lidar_view import project


def scan_payload(scan):
    # JSON cannot represent IEEE infinity/NaN. Explicit strings retain which
    # invalid value occurred, instead of conflating every missing return.
    return dict(angle_min=scan.angle_min, angle_increment=scan.angle_increment,
                range_min=scan.range_min, range_max=scan.range_max,
                time_increment=scan.time_increment, scan_time=scan.scan_time,
                ranges=[r if math.isfinite(r) else str(r) for r in scan.ranges])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--seconds', type=int, default=20)
    args = ap.parse_args()
    if args.out.exists() or not 5 <= args.seconds <= 60:
        ap.error('new output file and 5..60 seconds required')
    rclpy.init()
    node = rclpy.create_node('atlas_lidar_provenance_probe')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    raw, scans, results = deque(maxlen=16), deque(maxlen=16), []
    node.create_subscription(LaserScan, '/scan_raw', raw.append, qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/scan', scans.append, qos_profile_sensor_data)
    started = time.monotonic()
    next_sample = 0
    last_stamp = None
    try:
        while time.monotonic()-started < args.seconds:
            rclpy.spin_once(node, timeout_sec=.05)
            if not scans or time.monotonic() < next_sample:
                continue
            scan = scans[-1]
            stamp = scan.header.stamp.sec+scan.header.stamp.nanosec/1e9
            if stamp == last_stamp:
                continue
            next_sample = time.monotonic()+.5
            last_stamp = stamp
            row = dict(stamp_s=stamp, frame=scan.header.frame_id,
                       stamp_age_s=node.get_clock().now().nanoseconds/1e9-stamp,
                       time_increment=scan.time_increment, scan_time=scan.scan_time,
                       range_min=scan.range_min, range_max=scan.range_max)
            row['filtered_scan'] = scan_payload(scan)
            try:
                tf = buffer.lookup_transform('base_link', scan.header.frame_id,
                                             rclpy.time.Time.from_msg(scan.header.stamp))
                row.update(project(scan, tf.transform))
                row['transform'] = dict(translation=[getattr(tf.transform.translation,k) for k in 'xyz'],
                                        rotation=[getattr(tf.transform.rotation,k) for k in 'xyzw'])
                original = next((s for s in raw if s.header.stamp == scan.header.stamp), None)
                row['raw_pair_found'] = original is not None
                if original is not None:
                    row['raw_scan'] = scan_payload(original)
                    same_geometry = (original.header.frame_id == scan.header.frame_id and
                                     original.angle_min == scan.angle_min and
                                     original.angle_increment == scan.angle_increment and
                                     len(original.ranges) == len(scan.ranges))
                    row['raw_same_geometry'] = same_geometry
                    row['finite_raw_count'] = sum(math.isfinite(r) and original.range_min <= r <= original.range_max for r in original.ranges)
                    if same_geometry:
                        row['changed_finite_ranges'] = sum(math.isfinite(a) and math.isfinite(b) and a != b for a,b in zip(original.ranges,scan.ranges))
                        row['minima_raw_matches'] = {k: original.ranges[v['index']] == v['raw_range_m']
                                                    for k,v in row['minima'].items() if v}
            except Exception as exc:
                row['error'] = str(exc)
            results.append(row)
        graph = {}
        for topic in ('/scan_raw','/scan','/amcl_pose','/odom','/map'):
            graph[topic] = {kind: [i.node_name for i in getter(topic)] for kind,getter in (
                ('publishers',node.get_publishers_info_by_topic),
                ('subscribers',node.get_subscriptions_info_by_topic))}
        args.out.write_text(json.dumps(dict(samples=results, graph=graph), allow_nan=False, indent=2))
        args.out.chmod(0o600)
        print(json.dumps(dict(samples=len(results), errors=sum('error' in r for r in results), graph=graph)))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
