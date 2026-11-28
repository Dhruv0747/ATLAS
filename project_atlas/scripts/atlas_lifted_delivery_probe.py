#!/usr/bin/env python3
"""Bounded, rejected-only ROS delivery probe for the lifted motor owner.

This never requests enter, arm or pulse. The motor owner must be IDLE with
its software stop latched, raw commissioning disabled and all outputs zero.
"""

import argparse
import json
import time


REQUEST_TOPIC = "/atlas/drive_pid/lifted/request"
STATUS_TOPIC = "/atlas/drive_pid/lifted/status"


def probe_request(sequence):
    if type(sequence) is not int or not 1 <= sequence <= 10:
        raise ValueError("probe sequence must be 1..10")
    return json.dumps({"op": "probe", "seq": sequence}, separators=(",", ":"))


def safe_idle(status):
    return (
        isinstance(status, dict)
        and status.get("state") == "IDLE"
        and status.get("stop_latched") is True
        and status.get("raw_interface_enabled") is False
        and status.get("final_zero") is True
        and status.get("applied_motor_outputs") == [0, 0, 0, 0]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.count <= 10 or not 0.5 <= args.interval <= 5.0:
        parser.error("count must be 1..10 and interval 0.5..5 seconds")

    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    rclpy.init()
    node = Node("atlas_lifted_delivery_probe")
    latest = {"status": None}

    def on_status(message):
        try:
            latest["status"] = json.loads(message.data)
        except (TypeError, ValueError):
            latest["status"] = None

    node.create_subscription(String, STATUS_TOPIC, on_status, 10)
    publisher = node.create_publisher(String, REQUEST_TOPIC, 10)

    def wait_for(predicate, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if predicate():
                return True
        return False

    try:
        if not wait_for(lambda: safe_idle(latest["status"]), 6.0):
            raise RuntimeError("no safely stopped IDLE owner status; no probe sent")
        if not wait_for(lambda: publisher.get_subscription_count() > 0, 6.0):
            raise RuntimeError("owner request subscriber not matched; no probe sent")
        for sequence in range(1, args.count + 1):
            if not safe_idle(latest["status"]):
                raise RuntimeError("owner ceased to be safely IDLE")
            previous = latest["status"].get("owner_request_received_monotonic_s")
            sent_at = time.monotonic()
            publisher.publish(String(data=probe_request(sequence)))

            def acknowledged():
                status = latest["status"]
                if not safe_idle(status):
                    return False
                received = status.get("owner_request_received_monotonic_s")
                return (
                    type(received) in (float, int)
                    and received >= sent_at
                    and (previous is None or received > previous)
                    and str(status.get("result", "")).startswith("REJECTED:")
                )

            if not wait_for(acknowledged, 3.0):
                raise RuntimeError(f"probe {sequence} not safely rejected/acknowledged")
            status = latest["status"]
            received = float(status["owner_request_received_monotonic_s"])
            published = float(status["owner_status_published_monotonic_s"])
            print(json.dumps({
                "probe": sequence,
                "result": status["result"],
                "send_to_owner_ms": round((received - sent_at) * 1000, 3),
                "owner_to_status_ms": round((published - received) * 1000, 3),
                "final_zero": status["final_zero"],
            }, separators=(",", ":")), flush=True)
            end = time.monotonic() + args.interval
            while time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.05)
        if not safe_idle(latest["status"]):
            raise RuntimeError("owner did not finish in safe IDLE state")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
