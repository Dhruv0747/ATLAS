from types import SimpleNamespace
import sys
from pathlib import Path
from unittest.mock import Mock
import unittest
from test_daly_freshness import isolated_methods
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_daly_transport import ReconnectBackoff


class NodeBackoffTests(unittest.TestCase):
    def test_offline_heartbeat_does_not_retry_or_refresh_old_sample(self):
        clock = [100.0]
        node = isolated_methods('daly_bms_node.py', 'DalyBmsNode',
                                ('poll', 'publish_unavailable'),
                                {'time': SimpleNamespace(monotonic=lambda: clock[0]), 'MAC': 'test'})()
        node.last = {'ok': True, 'soc_percent': 90}
        node.last_success_at = 90.0
        node.backoff = ReconnectBackoff(lambda: clock[0])
        node.link = SimpleNamespace(close=Mock(), connections=1)
        node.read_ble = Mock(side_effect=TimeoutError('connect'))
        node.publish_data = Mock()
        node.get_logger = Mock(return_value=SimpleNamespace(warn=Mock()))
        node.poll()
        first = node.publish_data.call_args.args[0]
        self.assertFalse(first['ok'])
        self.assertEqual(first['age_s'], 10)
        clock[0] = 105
        node.poll()
        self.assertEqual(node.read_ble.call_count, 1)
        second = node.publish_data.call_args.args[0]
        self.assertEqual(second['age_s'], 15)
        self.assertFalse(second['ok'])
        self.assertEqual(second['reconnect_in_s'], 5)
        self.assertTrue(node.last['ok'])  # copied historical data, not falsified

    def test_no_previous_measurement_has_no_invented_age(self):
        node = isolated_methods('daly_bms_node.py', 'DalyBmsNode', ('publish_unavailable',),
                                {'time': SimpleNamespace(monotonic=lambda: 100)})()
        node.last, node.last_success_at = {}, None
        node.link = SimpleNamespace(connections=1)
        node.backoff = ReconnectBackoff(lambda: 100)
        node.publish_data = Mock()
        node.publish_unavailable('offline')
        data = node.publish_data.call_args.args[0]
        self.assertIsNone(data['age_s'])
        self.assertFalse(data['ok'])
        self.assertNotIn('soc_percent', data)


if __name__ == '__main__':
    unittest.main()
