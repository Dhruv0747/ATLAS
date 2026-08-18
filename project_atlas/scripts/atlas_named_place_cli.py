#!/usr/bin/env python3
"""Reliably publish an ATLAS named-place save or navigation request."""

import argparse
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("save", "navigate"))
    parser.add_argument("name")
    args = parser.parse_args()
    topic = (
        "/atlas/save_named_place"
        if args.action == "save"
        else "/atlas/navigate_named_place"
    )

    rclpy.init()
    node = Node("atlas_named_place_cli")
    publisher = node.create_publisher(String, topic, 10)
    deadline = time.monotonic() + 5.0
    while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if publisher.get_subscription_count() == 0:
        raise RuntimeError(f"no subscriber is available on {topic}")
    message = String(data=args.name)
    # A named-place request is a command, not telemetry. Publishing it more than
    # once creates multiple Nav2 goals and causes each new goal to preempt the
    # previous one. Wait for the mission-control subscriber above, then send
    # exactly one request.
    publisher.publish(message)
    rclpy.spin_once(node, timeout_sec=0.5)
    node.get_logger().info(f"Published {args.action} request for {args.name!r}")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
