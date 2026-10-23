import importlib.util
from pathlib import Path
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bench', ROOT/'tools/diagnostics/benchmark_executor_counts.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class CountCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rclpy.waitable import NumberOfEntities
        cls.C = NumberOfEntities

    def values(self, obj):
        return tuple(getattr(obj, f) for f in B.FIELDS)

    def test_random_counts_and_operands_preserved(self):
        rng = random.Random(42)
        for _ in range(2000):
            left, right = [self.C(*(rng.randrange(10000) for _ in range(6))) for _ in range(2)]
            before = self.values(left), self.values(right)
            self.assertEqual(self.values(left + right), self.values(B.add_direct(self.C, left, right)))
            self.assertEqual(before, (self.values(left), self.values(right)))

    def test_all_entity_kinds_and_zero(self):
        for i in range(6):
            values = [0]*6
            values[i] = 7
            self.assertEqual(tuple(values), self.values(B.add_direct(self.C, self.C(), self.C(*values))))

    def test_failed_add_does_not_mutate_original(self):
        left = self.C(1, 2, 3, 4, 5, 6)
        right = self.C(num_events='invalid')
        before = self.values(left)
        for call in (lambda: left + right, lambda: B.add_direct(self.C, left, right)):
            with self.assertRaises(TypeError):
                call()
            self.assertEqual(before, self.values(left))

    def test_wrong_source_fails_closed(self):
        with self.assertRaises(ValueError):
            B.candidate(b'not the installed source')

    def test_no_caching_or_scheduling_change(self):
        self.assertEqual(B.NEW.count('get_num_entities()'), 1)
        for word in ('sleep(', 'timeout', 'cache', 'destroy', 'callback', 'spin'):
            self.assertNotIn(word, B.NEW)

    def test_isolation_guard_before_ros_work(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'ROS_DOMAIN_ID': '0', 'ROS_LOCALHOST_ONLY': '1'}):
            with self.assertRaises(RuntimeError):
                B.native_suite('', '')


if __name__ == '__main__':
    unittest.main()
