import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_daly_transport import collect_until


class TransportTests(unittest.TestCase):
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
