#!/usr/bin/env python3
"""ATLAS autonomy narrator (2026-11-15): speaks why the rover stops / replans while in Autonomous mode.

Listens only (mux /atlas/control_policy and /atlas/motion_safety, mission control /atlas/mission_status, Nav2
NavigateToPose feedback) and publishes sentences to the voice companion's speech-only /atlas/voice/test_speak.
It never publishes any motion, stop, or navigation command. Wording and rate limits: atlas_autonomy_voice_core.
"""
import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from atlas_autonomy_voice_core import AutonomyVoice


class AutonomyVoiceNode(Node):
    def __init__(self):
        super().__init__('atlas_autonomy_voice')
        self.core = AutonomyVoice()
        self.say_pub = self.create_publisher(String, '/atlas/voice/test_speak', 10)
        self.create_subscription(String, '/atlas/control_policy', self.on_policy, 10)
        self.create_subscription(String, '/atlas/motion_safety', self.on_safety, 10)
        self.create_subscription(String, '/atlas/mission_status', self.on_mission, 10)
        try:
            from nav2_msgs.action import NavigateToPose
            self.create_subscription(NavigateToPose.Impl.FeedbackMessage, '/navigate_to_pose/_action/feedback',
                                     self.on_feedback, 10)
        except Exception as exc:                        # narrator still works without recovery counts
            self.get_logger().warn(f'Nav2 feedback unavailable: {exc}')

    def say(self, sentence):
        if sentence:
            self.say_pub.publish(String(data=sentence))
            self.get_logger().info('SAY ' + sentence)

    def on_policy(self, msg):
        try:
            self.say(self.core.on_policy(json.loads(msg.data), time.monotonic()))
        except (ValueError, TypeError):
            pass

    def on_safety(self, msg):
        self.say(self.core.on_safety(msg.data, time.monotonic()))

    def on_mission(self, msg):
        self.say(self.core.on_mission(msg.data, time.monotonic()))

    def on_feedback(self, msg):
        self.say(self.core.on_recoveries(int(msg.feedback.number_of_recoveries), time.monotonic()))


def main():
    rclpy.init()
    node = AutonomyVoiceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
