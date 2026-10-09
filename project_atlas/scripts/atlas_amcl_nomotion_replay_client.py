#!/usr/bin/env python3
"""Request AMCL scan updates at the original run's one-second clock phase.

Use only in an isolated replay ROS domain. This node has no actuator topics.
"""

import argparse

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from std_srvs.srv import Empty


NSEC = 1_000_000_000


def next_phase_ns(clock_ns, phase_ns):
    target = (clock_ns // NSEC) * NSEC + phase_ns
    return target if target > clock_ns else target + NSEC


class NoMotionReplay(Node):
    def __init__(self, phase_ns):
        super().__init__("atlas_amcl_nomotion_replay_client")
        self.phase_ns = phase_ns
        self.next_target_ns = None
        self.sent = 0
        self.skipped = 0
        self.client = self.create_client(Empty, "/request_nomotion_update")
        qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(Clock, "/clock", self.on_clock, qos)

    def on_clock(self, msg):
        now_ns = msg.clock.sec * NSEC + msg.clock.nanosec
        if self.next_target_ns is None:
            self.next_target_ns = next_phase_ns(now_ns, self.phase_ns)
            return
        if now_ns < self.next_target_ns:
            return
        target_ns = self.next_target_ns
        self.next_target_ns += NSEC * (1 + (now_ns - target_ns) // NSEC)
        if not self.client.service_is_ready():
            self.skipped += 1
            print(f"SKIP {target_ns} service-unavailable", flush=True)
            return
        self.client.call_async(Empty.Request())
        self.sent += 1
        print(f"CALL {target_ns} observed-clock-ns={now_ns}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-ns", type=int, default=578_000_000)
    args = parser.parse_args()
    if not 0 <= args.phase_ns < NSEC:
        parser.error("phase must be in [0, 1 second)")
    rclpy.init()
    node = NoMotionReplay(args.phase_ns)
    try:
        rclpy.spin(node)
    finally:
        print(f"SUMMARY sent={node.sent} skipped={node.skipped}", flush=True)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
