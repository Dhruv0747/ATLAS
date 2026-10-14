#!/usr/bin/env python3
"""Opt-in diagnostic timestamps visible on a LOCAL Jetson display for filming.

Publishes only /atlas/steering_validation/marker. Screen rendering/camera
exposure add uncertainty; these markers do not measure servo movement.
"""
import argparse
import json
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emit', action='store_true', help='explicit diagnostic-marker opt-in')
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not args.emit:
        parser.error('--emit is required; no marker published')
    if not 1 <= len(args.label) <= 48 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.label):
        parser.error('label must contain only letters, numbers, underscores or hyphens')
    import rclpy
    from std_msgs.msg import String
    rclpy.init()
    node = rclpy.create_node('atlas_stage17_visual_marker')
    pub = node.create_publisher(String, '/atlas/steering_validation/marker', 10)
    marker_id = uuid.uuid4().hex[:8]
    # Allow recorder discovery first, then show changing timestamped labels.
    warmup = time.monotonic() + 2
    while time.monotonic() < warmup:
        rclpy.spin_once(node, timeout_sec=.1)
    try:
        for sequence in range(20):
            payload = {'label': args.label, 'id': marker_id, 'sequence': sequence,
                       'ros_time_ns': node.get_clock().now().nanoseconds,
                       'monotonic_s': time.monotonic(),
                       'display_uncertainty_floor_s': .1}
            text = json.dumps(payload, separators=(',', ':'))
            pub.publish(String(data=text))
            print(text, flush=True)
            rclpy.spin_once(node, timeout_sec=.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
