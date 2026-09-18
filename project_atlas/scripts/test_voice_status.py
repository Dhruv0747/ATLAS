"""Offline regressions: no ROS publishers, serial ports, network or motors."""
import ast
import json
import math
from pathlib import Path
import tempfile
import time
import os
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from atlas_voice_status import (FreshValues, Announcements, as_object,
                                motion_block, startup_reply, status_reply,
                                mission_announcement)


class VoicePolicyTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.values = FreshValues(lambda: self.now)

    def test_freshness(self):
        self.values['gps_status'] = 0
        self.values['bms_percent'] = 60.
        self.now = 4
        self.assertIsNone(self.values.get('gps_status'))
        self.assertEqual(self.values.get('bms_percent'), 60.)
        self.now = 21
        self.assertNotIn('bms_percent', self.values.context())

    def test_invalid(self):
        self.values['imu_live'] = math.nan
        self.assertIsNone(self.values.get('imu_live'))
        for value in ('bad', '[]', None, 'true'):
            self.assertEqual(as_object(value), {})

    def test_default_motion_block(self):
        self.assertIn('not commissioned', motion_block(self.values))
        self.assertIn('unavailable', motion_block(self.values, True))

    def ready(self):
        self.values['control_policy'] = json.dumps({'manual_only': False, 'stop_latched': False})
        self.values['readiness'] = 'AUTO_READY'
        self.values['encoder_health'] = '{"state":"READY","faults":[]}'

    def test_motion_guard(self):
        self.ready()
        self.assertIsNone(motion_block(self.values, True))
        self.values['control_policy'] = '{"manual_only":true,"stop_latched":false}'
        self.assertIn('manual-only', motion_block(self.values, True))
        self.values['control_policy'] = '{"manual_only":false,"stop_latched":true}'
        self.assertIn('latched', motion_block(self.values, True))
        self.now = 4
        self.assertIn('unavailable', motion_block(self.values, True))

    def test_bad_encoder_blocks(self):
        self.ready()
        self.values['encoder_health'] = '{"state":"CRITICAL","faults":["M4"]}'
        self.assertIn('Encoder', motion_block(self.values, True))

    def test_startup_truth(self):
        reply = startup_reply(self.values, 3)
        self.assertIn('night', reply)
        self.assertNotIn('safe, and ready', reply)
        self.assertIn('not commissioned', reply)

    def bms(self, soc, current=-2, age=0, ok=True):
        self.values['bms_status'] = json.dumps({'soc_percent': soc, 'current_a': current, 'age_s': age, 'ok': ok})

    def test_battery_reports(self):
        self.bms(45, 3)
        self.assertIn('charging', status_reply(self.values, 'battery'))
        self.bms(44, -2)
        self.assertIn('discharging', status_reply(self.values, 'battery'))
        self.assertIn('बैटरी', status_reply(self.values, 'बैटरी'))
        self.bms(45, age=100)
        self.assertIn('unavailable', status_reply(self.values, 'battery'))
        self.bms(45, ok=False)
        self.assertEqual(self.values.bms(), {})

    def test_gps_fix_not_connection(self):
        self.values['gps_status'] = -1
        self.assertIn('no current fix', status_reply(self.values, 'gps'))
        self.now = 4
        self.assertIn('stale', status_reply(self.values, 'gps'))

    def test_stationary_encoder_not_qualified(self):
        self.ready()
        self.assertIn('do not prove', status_reply(self.values, 'encoder'))

    def test_low_battery_hysteresis(self):
        a = Announcements(lambda: self.now)
        self.now = 16
        self.bms(20)
        self.assertEqual(len(a.evaluate(self.values)), 1)
        self.assertEqual(a.evaluate(self.values), [])
        self.bms(23)
        a.evaluate(self.values)
        self.bms(19)
        self.assertEqual(a.evaluate(self.values), [])
        self.bms(26)
        a.evaluate(self.values)
        self.bms(19)
        self.assertEqual(len(a.evaluate(self.values)), 1)

    def test_full_soc_not_voltage_guess(self):
        a = Announcements(lambda: self.now)
        self.now = 16
        self.bms(99, -2)
        self.assertEqual(a.evaluate(self.values), [])
        self.bms(99, .1)
        self.assertIn('not independently verified', a.evaluate(self.values)[0][1])

    def test_sensor_loss_debounce(self):
        a = Announcements(lambda: self.now)
        self.now = 16
        self.values['imu_live'] = True
        self.assertEqual(a.evaluate(self.values), [])
        self.now = 18
        self.assertEqual(a.evaluate(self.values), [])
        self.now = 20
        self.assertEqual(a.evaluate(self.values), [])
        self.now = 22
        self.assertIn('stale', a.evaluate(self.values)[0][1])
        self.assertEqual(a.evaluate(self.values), [])

    def test_mission_no_false_success(self):
        for status in ('RETURN HOME GOAL DISPATCHED', 'RETURN HOME FINISHED status=4', 'QUEUED save_map', 'READY'):
            self.assertIsNone(mission_announcement(status))
        self.assertIn('not yet confirmed', mission_announcement('RETURN HOME ACCEPTED'))
        self.assertIn('verified', mission_announcement('RETURN HOME VERIFIED error=0.05m'))
        self.assertIn('saved and accepted', mission_announcement('EXPLORATION STOPPED; MAP ACCEPTED id=test'))

    def test_sensor_report_not_hardware_claim(self):
        self.values['radar_targets'] = 'T1: X0 Y1000'
        reply = status_reply(self.values, 'are sensors working')
        self.assertIn('radar', reply)
        self.assertIn('not hardware qualification', reply)

    def test_embedded_and_receipt_age_combined(self):
        self.bms(40, age=18)
        self.now = 3
        self.assertEqual(self.values.bms(), {})


def isolated_methods(file, methods, namespace):
    """Compile actual method bodies with inert dependencies, not duplicate logic."""
    tree = ast.parse(Path(__file__).with_name(file).read_text(encoding='utf-8'))
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and any(
        isinstance(m, ast.FunctionDef) and m.name in methods for m in x.body))
    cls.bases = []
    cls.body = [x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name in methods]
    module = ast.Module(body=[cls], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), file, 'exec'), namespace)
    return namespace[cls.name]


class VoiceControlTest(unittest.TestCase):
    def setUp(self):
        names = {'handle_agent_request', 'execute_agent_action', 'asks_weather',
                 'gps_callback', 'handle_safe_hardware_request', 'vision_reply',
                 'mute_callback', 'set_state'}
        ns = {'time': time, 'json': json, 'math': math, 'Bool': SimpleNamespace,
              'Empty': SimpleNamespace, 'motion_block': motion_block, 'STATE': 0x82,
              'os': os, 'queue': queue}
        cls = isolated_methods('atlas_voice_companion.py', names, ns)
        self.node = cls()
        self.node.pending_agent_action = None
        self.node.pending_agent_deadline = 0
        self.node.rover = FreshValues()
        self.node.voice_motion_enabled = False
        self.node.mic_muted = False
        for name in ('publish', 'publish_voice_stop', 'send_packet'):
            setattr(self.node, name, Mock())
        for name in ('voice_stop_pub', 'follow_pub', 'tracker_pub', 'ai_pub'):
            setattr(self.node, name, SimpleNamespace(publish=Mock()))
        self.node.agent_pubs = {'stop_exploration': SimpleNamespace(publish=Mock())}

    def test_stop_beats_pending_cancel(self):
        self.node.pending_agent_action = 'voice_forward'
        self.node.pending_agent_deadline = time.monotonic() + 45
        self.assertIn('Latched stop requested', self.node.handle_agent_request('stop'))
        self.node.voice_stop_pub.publish.assert_called_once()
        self.assertIsNone(self.node.pending_agent_action)

    def test_movement_blocked_without_publish(self):
        for command in ('move forward', 'start mapping', 'return home', 'follow me'):
            self.assertIn('not commissioned', self.node.handle_agent_request(command))
        self.node.follow_pub.publish.assert_not_called()

    def test_confirmation_not_substring(self):
        self.node.pending_agent_action = 'voice_forward'
        self.node.pending_agent_deadline = time.monotonic() + 45
        self.node.execute_agent_action = Mock()
        self.node.handle_agent_request('yesterday was good')
        self.node.execute_agent_action.assert_not_called()
        self.node.handle_agent_request('yes')
        self.node.execute_agent_action.assert_called_once_with('voice_forward')

    def test_weather_does_not_control_camera(self):
        self.assertFalse(self.node.asks_weather('start tracking'))
        self.node.tracker_pub.publish.assert_not_called()

    def test_generic_up_not_camera(self):
        self.node.command_servo = Mock()
        self.assertIsNone(self.node.handle_safe_hardware_request('what is up today'))
        self.node.command_servo.assert_not_called()

    def test_gps_clears_stale_position(self):
        self.node.gps_callback(SimpleNamespace(status=SimpleNamespace(status=0), latitude=28., longitude=77.))
        self.assertEqual(self.node.rover.get('latitude'), 28.)
        self.node.gps_callback(SimpleNamespace(status=SimpleNamespace(status=-1), latitude=28., longitude=77.))
        self.assertIsNone(self.node.rover.get('latitude'))

    def test_missing_camera_does_not_claim_sight(self):
        self.assertIn('unavailable', self.node.vision_reply('what can you see'))

    def test_muted_led_supported_firmware(self):
        self.node.mic_muted = True
        self.node.set_state('IDLE')
        self.node.publish.assert_any_call('state', 'MUTED')
        self.node.send_packet.assert_called_with(0x82, b'STATE ERROR')

    def test_mute_persists_clears_queue_and_pending_action(self):
        with tempfile.TemporaryDirectory() as directory:
            self.node.mute_path = str(Path(directory) / 'microphone-muted')
            self.node.privacy_epoch = 0
            self.node.audio_q = queue.Queue()
            self.node.audio_q.put(b'old captured audio')
            self.node.pending_agent_action = 'voice_forward'
            self.node.publish_privacy = Mock()
            self.node.mute_callback(SimpleNamespace(data=True))
            self.assertTrue(Path(self.node.mute_path).exists())
            self.assertTrue(self.node.audio_q.empty())
            self.assertIsNone(self.node.pending_agent_action)
            self.assertEqual(self.node.privacy_epoch, 1)
            self.node.mute_callback(SimpleNamespace(data=False))
            self.assertFalse(Path(self.node.mute_path).exists())

    def test_offline_speech_cannot_fallback_to_cloud(self):
        # Missing local model must fail explicitly, never silently send text out.
        import hashlib
        from unittest.mock import patch
        ns = {'os': os, 'hashlib': hashlib, 'json': json}
        cls = isolated_methods('atlas_voice_companion.py', {'local_speech'}, ns)
        node = cls()
        node.publish = Mock()
        node.speech = Mock(side_effect=AssertionError('cloud forbidden'))
        with tempfile.TemporaryDirectory() as directory, patch('os.path.expanduser', return_value=directory):
            with self.assertRaises(RuntimeError):
                node.local_speech('offline only', offline_only=True)
        node.speech.assert_not_called()

    def test_voice_stop_latches_mux_and_flushes(self):
        from atlas_remote_stop import RemoteStop
        cls = isolated_methods('atlas_cmd_vel_mux.py', {'on_voice_stop'}, {})
        mux = cls()
        mux.remote_stop = RemoteStop()
        mux.remote_stop.latched = False
        mux.hold_remote_stop = Mock()
        mux.on_voice_stop(None)
        self.assertTrue(mux.remote_stop.latched)
        self.assertIn('voice stop', mux.remote_stop.reason)
        mux.hold_remote_stop.assert_called_once()


class WakeResponseTest(unittest.TestCase):
    def setUp(self):
        import re
        cls = isolated_methods('atlas_voice_companion.py',
                               {'process_utterance', 'remove_wake_phrase'},
                               {'time': time, 're': re, 'status_reply': status_reply})
        self.node = cls()
        self.node.privacy_epoch = 0
        self.node.mic_muted = False
        self.node.awake_until = 0
        self.node.ignore_mic_until = 0
        self.node.pending_agent_action = None
        self.node.publish = Mock()
        self.node.set_state = Mock()
        self.node.transcribe = Mock(return_value='Hey ATLAS')
        self.node.local_speech = Mock(return_value=b'ack')
        self.node.play = Mock()
        self.node.handle_agent_request = Mock(return_value=None)
        self.node.handle_safe_hardware_request = Mock(return_value=None)

    def test_wake_gets_local_ack_not_motion(self):
        for wake, expected in (('Hey ATLAS', "Yes Dhruv, I'm listening."),
                               ('हे एटलस', 'हाँ ध्रुव, बोलिए।')):
            self.node.transcribe.return_value = wake
            self.node.process_utterance(b'captured')
            self.node.local_speech.assert_called_with(expected, offline_only=True)
            self.node.play.assert_called_with(b'ack')
            self.assertGreater(self.node.awake_until, time.monotonic() + 7)
        self.node.handle_agent_request.assert_not_called()
        self.node.handle_safe_hardware_request.assert_not_called()

    def test_command_window_starts_after_playback(self):
        self.node.play.side_effect = lambda _: setattr(self.node, 'ignore_mic_until', time.monotonic() + 2)
        self.node.process_utterance(b'captured')
        self.assertGreaterEqual(self.node.awake_until, self.node.ignore_mic_until + 8)

    def test_no_transcribing_stuck_for_empty_or_ignored_audio(self):
        for text in ('', 'thanks for watching'):
            self.node.transcribe.return_value = text
            self.node.process_utterance(b'captured')
            stages = [c.args[1] for c in self.node.publish.call_args_list if c.args[0] == 'cloud']
            self.assertTrue(stages[-1].startswith('IDLE:'))
        self.node.play.assert_not_called()

    def test_privacy_change_during_ack_prevents_play(self):
        def synth(*args, **kwargs):
            self.node.privacy_epoch += 1
            return b'private'
        self.node.local_speech.side_effect = synth
        self.node.process_utterance(b'captured')
        self.node.play.assert_not_called()
        self.assertEqual(self.node.awake_until, 0)

    def test_muted_audio_never_sent_to_transcription(self):
        self.node.mic_muted = True
        self.node.process_utterance(b'captured')
        self.node.transcribe.assert_not_called()

    def test_transcription_delay_does_not_expire_captured_command(self):
        from unittest.mock import patch
        self.node.awake_until = 10.
        self.node.transcribe.return_value = 'battery status'
        self.node.handle_agent_request.return_value = 'Test status reply'
        with patch('time.monotonic', side_effect=[0., 30.]):
            self.node.process_utterance(b'captured')
        self.node.handle_agent_request.assert_called_once_with('battery status')
        self.node.play.assert_called_once()


if __name__ == '__main__':
    unittest.main()
