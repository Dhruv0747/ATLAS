#!/usr/bin/env python3
"""Probe one bounded command through web -> mux -> base without guessing."""

import argparse
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Int32, String


class Probe(Node):
    def __init__(self, linear: float, angular: float, duration: float, topic: str) -> None:
        super().__init__("atlas_command_path_probe")
        self.linear = linear
        self.angular = angular
        self.duration = duration
        self.started = time.monotonic()
        self.command_topic = topic
        self.pub = self.create_publisher(Twist, topic, 10)
        self.web_samples = []
        self.output_samples = []
        self.modes = []
        self.encoder_first = {}
        self.encoder_last = {}
        self.create_subscription(Twist, topic, self.on_web, 50)
        self.create_subscription(Twist, "/cmd_vel", self.on_output, 50)
        self.create_subscription(String, "/atlas/drive_mode", self.on_mode, 10)
        for index in range(1, 5):
            self.create_subscription(
                Int32,
                f"/yahboom/encoder/m{index}",
                lambda msg, motor=index: self.on_encoder(motor, msg),
                20,
            )
        self.create_timer(0.05, self.tick)

    def on_web(self, msg: Twist) -> None:
        self.web_samples.append((float(msg.linear.x), float(msg.angular.z)))

    def on_output(self, msg: Twist) -> None:
        self.output_samples.append((float(msg.linear.x), float(msg.angular.z)))

    def on_mode(self, msg: String) -> None:
        self.modes.append(msg.data)

    def on_encoder(self, motor: int, msg: Int32) -> None:
        self.encoder_first.setdefault(motor, int(msg.data))
        self.encoder_last[motor] = int(msg.data)

    def tick(self) -> None:
        cmd = Twist()
        if time.monotonic() - self.started < self.duration:
            cmd.linear.x = self.linear
            cmd.angular.z = self.angular
        self.pub.publish(cmd)

    @staticmethod
    def summarize(samples):
        moving = [item for item in samples if abs(item[0]) > 1e-4 or abs(item[1]) > 1e-4]
        return {
            "total": len(samples),
            "moving": len(moving),
            "last_moving": moving[-1] if moving else None,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linear", type=float, default=0.08)
    parser.add_argument("--angular", type=float, default=-0.28)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument(
        "--topic",
        choices=("/cmd_vel_web", "/cmd_vel_teleop"),
        default="/cmd_vel_web",
    )
    args = parser.parse_args()
    rclpy.init()
    node = Probe(args.linear, args.angular, args.duration, args.topic)
    deadline = time.monotonic() + args.duration + 1.5
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        node.pub.publish(Twist())
        print("WEB", node.summarize(node.web_samples), flush=True)
        print("MUX_OUTPUT", node.summarize(node.output_samples), flush=True)
        print("MODES", sorted(set(node.modes)), flush=True)
        deltas = {
            motor: node.encoder_last.get(motor, start) - start
            for motor, start in node.encoder_first.items()
        }
        print("ENCODER_DELTAS", deltas, flush=True)
    finally:
        node.pub.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
