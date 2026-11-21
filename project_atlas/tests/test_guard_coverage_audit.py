import importlib.util
import math
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'tools/diagnostics/audit_lidar_guard_coverage.py'
spec = importlib.util.spec_from_file_location('coverage_audit', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CoverageAuditTests(unittest.TestCase):
    def test_infinity_not_free_or_proven_out_of_range(self):
        self.assertEqual(module.classify(math.inf, math.inf, dict(range_min=.15, range_max=12)),
                         'raw_positive_inf_unknown')

    def test_raw_finite_filter_distinguished(self):
        self.assertEqual(module.classify(.2, math.inf, dict(range_min=.15, range_max=12)),
                         'finite_raw_removed_or_changed')

    def test_valid_boundary(self):
        self.assertTrue(module.valid(12., dict(range_min=.15, range_max=12)))
        self.assertFalse(module.valid(12.01, dict(range_min=.15, range_max=12)))

    def test_missing_pair_not_assumed(self):
        result = module.audit(dict(samples=[{}]))
        self.assertEqual(result['samples'], 0)
        self.assertFalse(result['movement_authorized'])

    def test_nan_and_negative_inf(self):
        scan = dict(range_min=.15, range_max=12)
        self.assertEqual(module.classify(math.nan, math.nan, scan), 'raw_nan_unknown')
        self.assertEqual(module.classify(-math.inf, -math.inf, scan), 'raw_negative_inf_invalid')


if __name__ == '__main__':
    unittest.main()
