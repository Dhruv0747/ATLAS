#!/usr/bin/env python3
"""Lightweight role board for the ATLAS offline-first agent team.

This node does not plan motion.  It exposes which deterministic specialist is
responsible for each part of a mission and whether its live evidence is fresh.
"""

import json
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import Trigger


class AtlasAgentTeam(Node):
    def __init__(self):
        super().__init__("atlas_agent_team")
        self.values = {}
        self.seen = {}
        self.state_pub = self.create_publisher(String, "/atlas/agent_team/state", 10)
        self.status_pub = self.create_publisher(String, "/atlas/agent_team/status", 10)
        topics = {
            "mission_director": "/atlas/agent/state",
            "safety_guardian": "/atlas/safety_status",
            "driver": "/atlas/autonomy_state",
            "mode_manager": "/atlas/mode/detail",
            "recovery_specialist": "/atlas/recovery_state",
            "experience_recorder": "/atlas/experience/status",
            "voice_interface": "/atlas/voice/state",
            "control_policy": "/atlas/control_policy",
            "encoder_health": "/atlas/encoder_health",
            "readiness": "/atlas/readiness",
        }
        self.command_subscriptions = [
            self.create_subscription(
                String, topic, lambda msg, role=role: self.update(role, msg.data), 10
            )
            for role, topic in topics.items()
        ]
        self.command_subscriptions.extend(
            [
                self.create_subscription(Odometry, "/odom", lambda _msg: self.update("localization", "fused odometry live"), 10),
                self.create_subscription(LaserScan, "/scan", lambda _msg: self.update("perception", "LiDAR scan live"), 10),
            ]
        )
        self.create_service(Trigger, "/atlas/agent_team/status", self.status_service)
        self.create_timer(2.0, self.publish)
        self.get_logger().info("ATLAS specialist role board is online")

    def update(self, role, value):
        text = str(value)
        self.values[role] = text if len(text) <= 16384 else 'INVALID: oversized status'
        self.seen[role] = time.monotonic()

    def snapshot(self):
        now = time.monotonic()
        roles = {}
        critical = {
            "mission_director", "safety_guardian", "driver", "mode_manager",
            "recovery_specialist", "localization", "perception",
        }
        for role in sorted(critical | {"experience_recorder", "voice_interface"}):
            age = now - self.seen.get(role, 0.0) if role in self.seen else None
            fresh = age is not None and age <= 6.0
            roles[role] = {
                "state": "ONLINE" if fresh else "STALE",
                "age_s": round(age, 1) if age is not None else None,
                "evidence": self.values.get(role, "waiting for first report")[:500],
            }
        offline = [role for role in critical if roles[role]["state"] != "ONLINE"]
        # Fresh heartbeats prove communication, not readiness to drive. Keep
        # this role board read-only and report the existing safety gates.
        def fresh_value(role):
            age = now - self.seen.get(role, -100.)
            return self.values.get(role) if 0 <= age <= 6. else None

        def report(role):
            try:
                value = json.loads(fresh_value(role) or 'null')
                return value if isinstance(value, dict) else {}
            except (ValueError, TypeError):
                return {}

        policy, enc = report('control_policy'), report('encoder_health')
        blocked = []
        if offline:
            blocked.append('critical role evidence missing or stale')
        if policy.get('manual_only') is not False:
            blocked.append('manual-only mode or control policy unavailable')
        if policy.get('stop_latched') is not False:
            blocked.append('stop latched or stop state unavailable')
        if fresh_value('readiness') != 'AUTO_READY':
            blocked.append('autonomous readiness not confirmed')
        if enc.get('autonomy_ready') is not True:
            blocked.append('encoder navigation qualification not confirmed')
        if report('recovery_specialist').get('overall') != 'HEALTHY':
            blocked.append('recovery diagnostics degraded, faulty or unavailable')
        return {
            "overall": "READY" if not blocked else "DEGRADED",
            "communications_online": not offline,
            "autonomy_ready": not blocked,
            "readiness_reasons": blocked,
            "offline_critical_roles": sorted(offline),
            "roles": roles,
            "architecture": "one planner; deterministic specialist roles; offline-first",
            "internet_research": "STOPPED-ONLY AND HUMAN-REVIEWED",
        }

    def publish(self):
        state = self.snapshot()
        self.state_pub.publish(String(data=json.dumps(state, separators=(",", ":"))))
        offline = ",".join(state["offline_critical_roles"]) or "none"
        reasons = '; '.join(state['readiness_reasons']) or 'existing readiness gates passed'
        self.status_pub.publish(String(data=f"{state['overall']}: critical_offline={offline}; {reasons}"))

    def status_service(self, _request, response):
        state = self.snapshot()
        response.success = state["overall"] == "READY"
        response.message = json.dumps(state, separators=(",", ":"))
        return response


def main():
    rclpy.init()
    node = AtlasAgentTeam()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
