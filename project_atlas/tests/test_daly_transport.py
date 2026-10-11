import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_daly_transport import collect_until, PersistentDalyClient, ReconnectBackoff


class TransportTests(unittest.TestCase):
    def test_healthy_link_reused_and_old_input_drained(self):
        client = PersistentDalyClient('test', 'random', '0x11', '0x14')
        proc = Mock()
        proc.poll.return_value = None
        with patch('atlas_daly_transport.subprocess.Popen', return_value=proc) as launch:
            client._read = Mock(side_effect=['old', '', 'older', ''])
            client._exchange = Mock(return_value='fresh')
            self.assertEqual(client.read_snapshot({'pack': 'command'}, lambda s: {}), 'fresh')
            self.assertEqual(client.read_snapshot({'pack': 'command'}, lambda s: {}), 'fresh')
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(client.connections, 1)
            self.assertEqual(client._exchange.call_count, 5)  # three setup, two fresh polls
            proc.terminate.assert_not_called()
            client.close()
            proc.terminate.assert_called_once()

    def test_failed_link_closed_before_reconnect(self):
        client = PersistentDalyClient('test', 'random', '0x11', '0x14')
        proc = Mock()
        proc.poll.return_value = None
        with patch('atlas_daly_transport.subprocess.Popen', return_value=proc):
            client._exchange = Mock(side_effect=TimeoutError('connect'))
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    client.read_snapshot({}, lambda s: {})
                self.assertIsNone(client.proc)
            self.assertEqual(client.connections, 2)
            self.assertEqual(proc.terminate.call_count, 2)

    def test_backoff_bounded_and_reset_after_success(self):
        clock = [0]
        backoff = ReconnectBackoff(lambda: clock[0])
        for delay in (10, 20, 40, 80, 120, 120):
            backoff.failed()
            self.assertEqual(backoff.remaining(), delay)
            clock[0] += delay
            self.assertEqual(backoff.remaining(), 0)
        backoff.succeeded()
        backoff.failed()
        self.assertEqual(backoff.remaining(), 10)

    def test_fragmented_response_returns_without_fixed_sleep(self):
        chunks = iter(['not', 'ify ', 'ready'])
        self.assertEqual(collect_until(lambda _: next(chunks),
                                     lambda s: 'ready' in s, 10, lambda: 0),
                         'notify ready')

    def test_eof_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            collect_until(lambda _: None, lambda s: False, 10, lambda: 0)

    def test_silence_is_bounded(self):
        ticks = iter([0, 0, 1, 1, 2])
        with self.assertRaises(TimeoutError):
            collect_until(lambda _: '', lambda s: False, 2, lambda: next(ticks))

    def test_timeout_identifies_failed_stage(self):
        for stage in ('connect', 'mtu', 'notifications', 'pack', 'cells', 'cell_extreme'):
            with self.subTest(stage=stage), self.assertRaisesRegex(TimeoutError, 'during ' + stage):
                collect_until(lambda _: '', lambda s: False, 0, lambda: 0, stage=stage)

    def test_eof_identifies_stage(self):
        with self.assertRaisesRegex(RuntimeError, 'during cells'):
            collect_until(lambda _: None, lambda s: False, 10, lambda: 0, stage='cells')
