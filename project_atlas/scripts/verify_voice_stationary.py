#!/usr/bin/env python3
"""Stationary deployment check. Subscribes only; never sends motion or goals."""
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import rclpy
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from atlas_voice_companion import AtlasVoice


def main():
    def no_cloud(*args, **kwargs):
        raise AssertionError('Cloud request forbidden in local speech test')
    fake = SimpleNamespace(publish=lambda *args: None, speech=no_cloud)
    tts = []
    with patch('requests.post', no_cloud), patch('requests.get', no_cloud):
        for text in ('Dhruv, this is a local speech verification.', 'ध्रुव, यह स्थानीय आवाज़ की जाँच है।'):
            start = time.monotonic()
            pcm = AtlasVoice.local_speech(fake, text, offline_only=True)
            assert len(pcm) > 3200
            tts.append({'bytes': len(pcm), 'audio_s': round(len(pcm) / 32000, 2),
                        'generation_s': round(time.monotonic() - start, 2)})
    rclpy.init()
    node = rclpy.create_node('atlas_voice_stationary_verification')
    observations = {}
    nonzero = []
    def receive(key, msg):
        observations[key] = {'value': msg.data, 'rx': time.monotonic()}
    for topic in ('/atlas/control_policy', '/atlas/voice/state', '/atlas/voice/privacy',
                  '/atlas/voice/cloud', '/atlas/voice/alert', '/atlas/voice/response'):
        node.create_subscription(String, topic, lambda msg, key=topic: receive(key, msg), 10)
    def command(msg):
        if abs(msg.linear.x) + abs(msg.angular.z) > 1e-6:
            nonzero.append([msg.linear.x, msg.angular.z])
    node.create_subscription(Twist, '/cmd_vel', command, 10)
    deadline = time.monotonic() + 18
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=.1)
    now = time.monotonic()
    result = {'offline_tts': tts, 'nonzero_commands_observed': nonzero,
              'topics': {k: {'value': v['value'], 'age_s': round(now - v['rx'], 2)}
                         for k, v in observations.items()}}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    assert not nonzero, 'Unexpected motion command during stationary check'
    assert '/atlas/control_policy' in observations, 'No mux policy telemetry'
    assert '/atlas/voice/privacy' in observations, 'No voice privacy heartbeat'
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
