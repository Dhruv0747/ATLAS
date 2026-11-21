import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from atlas_single_person_steering_web import SinglePersonSteeringService


class Message:
    def __init__(self, data=None): self.data = data
class Pub:
    def __init__(self): self.sent = []
    def publish(self, message): self.sent.append(message)
class Ros:
    def __init__(self):
        self.ready = True
        self.steering_cal_pub, self.commissioning_stop_pub = Pub(), Pub()
        self.steering_test_event_pub, self.steering_test_status_pub, self.steering_test_speech_pub = Pub(), Pub(), Pub()
        self.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=time.time_ns())))
        self.surround_scan = (None, time.time())
        owner = {'saved': {'front': {'center': 90}, 'rear': {'center': 90}}, 'locked': False,
                 'targets': {'front': 90, 'rear': 90}, 'session': None, 'lease_active': False,
                 'zero_motor_command': True, 'applied_motor_outputs': [0, 0, 0, 0], 'remote_b_stop': False}
        self.data = {k: {'value': v, 'ts': time.time()} for k, v in {
            'steering_calibration': owner, 'control_policy': {'stop_latched': True},
            'cmd_vel': {'lin': 0, 'ang': 0}, 'encoder_health': {'packet_fresh': True, 'serial_write_errors': 0},
            'imu_full': {'gz': 0}, 'front_steer': 90, 'rear_steer': 90}.items()}
    def _item(self, key): return self.data.get(key)
    def _set(self, key, value): self.data[key] = {'value': value, 'ts': time.time()}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'new_session'
        self.ros = Ros()
    def tearDown(self): self.temp.cleanup()
    def controller(self, enabled=True, **kwargs):
        return SinglePersonSteeringService(self.ros, Message, Message, root=self.root, enabled=enabled, **kwargs)
    def request(self):
        return {'op': 'prepare', 'session': 'a'*32,
                'confirmations': dict(lifted=True, charger_disconnected=True, hands_clear=True, cutoff_ready=True)}

    def test_disabled_prepare_does_not_spawn_or_move_or_write(self):
        controller = self.controller(False)
        with patch('atlas_single_person_steering_web.subprocess.Popen') as spawn:
            with self.assertRaises(ValueError): controller.command(self.request())
            spawn.assert_not_called()
        self.assertFalse(self.root.exists())
        self.assertEqual(self.ros.steering_cal_pub.sent, [])

    def test_confirmed_prepare_starts_only_finite_diagnostic_child(self):
        controller = self.controller()
        child = SimpleNamespace(poll=lambda: None, terminate=lambda: None)
        with patch('atlas_single_person_steering_web.subprocess.Popen', return_value=child) as spawn:
            result = controller.command(self.request())
            args = spawn.call_args.args[0]
            self.assertIn('steering-validation', args)
            self.assertIn('420', args)
            self.assertEqual(result['state'], 'PREPARING')
            self.assertEqual(self.ros.steering_cal_pub.sent, [])
            self.assertEqual(self.ros.commissioning_stop_pub.sent, [])
        controller.log.close()

    def test_missing_traction_metadata_blocks_old_owner(self):
        del self.ros.data['steering_calibration']['value']['zero_motor_command']
        with self.assertRaises(ValueError): self.controller().command(self.request())
        self.assertEqual(self.ros.steering_cal_pub.sent, [])

    def test_stale_owner_nonzero_motor_and_shutdown_fail_closed(self):
        controller = self.controller()
        self.ros.data['steering_calibration']['ts'] -= 2
        self.assertFalse(controller.observations()['safe'])
        self.ros.data['steering_calibration']['ts'] = time.time()
        self.ros.data['steering_calibration']['value']['applied_motor_outputs'] = [0, 20, 0, 0]
        self.assertFalse(controller.observations()['safe'])
        self.assertFalse(self.controller(shutdown_check=lambda: True).observations()['safe'])

    def test_emergency_has_only_existing_stop_output(self):
        self.controller(False).command({'op': 'emergency'})
        self.assertEqual(len(self.ros.commissioning_stop_pub.sent), 1)
        self.assertEqual(self.ros.steering_cal_pub.sent, [])

    def test_forged_api_client_cannot_cancel_an_owned_test(self):
        controller = self.controller()
        controller.engine.client = 'a'*32
        with self.assertRaises(ValueError):
            controller.command({'op': 'cancel', 'session': 'b'*32})
        self.assertEqual(self.ros.commissioning_stop_pub.sent, [])


if __name__ == '__main__': unittest.main()
