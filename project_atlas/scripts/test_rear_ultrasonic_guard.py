#!/usr/bin/env python3
"""Non-moving integration check for ATLAS rear-ultrasonic reverse veto.

Run only while rover-base-telemetry.service is stopped. The test injects a
200 mm rear obstacle and a reverse recovery request, then verifies that the
command mux publishes only zero velocity and identifies the rear obstacle.
"""

import json
import os
import subprocess
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float32, String


class RearGuardCheck(Node):
    def __init__(self):
        super().__init__("atlas_rear_ultrasonic_guard_check")
        self.rear_pub = self.create_publisher(
            Float32, "/ultrasonic/rear_mm", 10
        )
        self.command_pub = self.create_publisher(
            Twist, "/cmd_vel_recovery", 10
        )
        self.create_subscription(Twist, "/cmd_vel", self.on_output, 10)
        self.create_subscription(
            String, "/atlas/motion_safety", self.on_safety, 10
        )
        self.outputs = []
        self.reasons = []
        self.started = time.monotonic()
        self.timer = self.create_timer(0.1, self.tick)

    def tick(self):
        # Allow discovery to settle before injecting test traffic.
        if time.monotonic() - self.started < 1.5:
            return
        self.rear_pub.publish(Float32(data=200.0))
        command = Twist()
        command.linear.x = -0.12
        self.command_pub.publish(command)

    def on_output(self, msg):
        self.outputs.append((float(msg.linear.x), float(msg.angular.z)))

    def on_safety(self, msg):
        self.reasons.append(msg.data)


def main():
    if os.environ.get("ATLAS_REAR_GUARD_TEST_ARMED") != "1":
        raise SystemExit(
            "Refusing to inject a reverse test command: set "
            "ATLAS_REAR_GUARD_TEST_ARMED=1 after stopping the motor service."
        )
    motor_state = subprocess.run(
        ["systemctl", "--user", "is-active", "rover-base-telemetry.service"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if motor_state == "active":
        raise SystemExit(
            "Refusing test while rover-base-telemetry.service is active."
        )
    rclpy.init()
    node = RearGuardCheck()
    deadline = time.monotonic() + 6.0
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.command_pub.publish(Twist())
        rclpy.spin_once(node, timeout_sec=0.1)

    nonzero = [sample for sample in node.outputs if any(abs(v) > 1e-4 for v in sample)]
    rear_reasons = [reason for reason in node.reasons if "REAR" in reason]
    result = {
        "passed": bool(node.outputs) and not nonzero and bool(rear_reasons),
        "output_samples": len(node.outputs),
        "nonzero_outputs": nonzero[:5],
        "rear_block_reason": rear_reasons[-1] if rear_reasons else None,
    }
    print(json.dumps(result, sort_keys=True))
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
