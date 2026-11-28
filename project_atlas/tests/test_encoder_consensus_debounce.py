"""Encoder consensus debounce (2026-11-23): one bursty 0.1 s interval is not a fault; two in a row are."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from atlas_encoder_selection import ConsensusDebounce  # noqa: E402


class DebounceTests(unittest.TestCase):
    def test_single_interval_is_ignored(self):
        d = ConsensusDebounce(2)
        self.assertEqual([d.update(x) for x in (False, True, False, True, False)], [False] * 5)

    def test_two_consecutive_intervals_trip_and_stay_while_failing(self):
        d = ConsensusDebounce(2)
        self.assertEqual([d.update(x) for x in (True, True, True, False, True)], [False, True, True, False, False])

    def test_required_one_keeps_old_behaviour(self):
        d = ConsensusDebounce(1)
        self.assertTrue(d.update(True))
        self.assertFalse(d.update(False))

    def test_recorded_pattern_from_stage3_runs(self):
        # 20 isolated single-interval failures among normal intervals (as in the four bags): none trips
        d = ConsensusDebounce(2)
        pattern = ([False] * 50 + [True]) * 20 + [False] * 10
        self.assertFalse(any(d.update(x) for x in pattern))


class BaseWiringTests(unittest.TestCase):
    def test_yahboom_base_debounces_consensus_with_two_intervals(self):
        src = (ROOT / 'scripts' / 'yahboom_base.py').read_text(encoding='utf-8')
        self.assertIn('ENCODER_CONSENSUS_DEBOUNCE_INTERVALS = 2', src)
        self.assertIn('self._consensus_debounce = ConsensusDebounce(ENCODER_CONSENSUS_DEBOUNCE_INTERVALS)', src)
        tree = ast.parse(src)
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_publish_encoder_health')
        assigns = [n for n in ast.walk(method) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'consensus_failed' for t in n.targets)]
        self.assertEqual(len(assigns), 1)
        self.assertIn('self._consensus_debounce.update', ast.unparse(assigns[0].value))
        # hardware freeze faults and stale packets are not debounced (still immediate)
        self.assertIn('self._encoder_fault_since.setdefault(index, now)', ast.unparse(method))


if __name__ == '__main__':
    unittest.main()
