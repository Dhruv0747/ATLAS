import importlib.util
import os
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'tools/diagnostics/benchmark_localization_fit.py'
spec = importlib.util.spec_from_file_location('fit_benchmark', PATH)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class FitCandidateTest(unittest.TestCase):
    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            B.candidate(b'unknown')

    @unittest.skipUnless(os.environ.get('ATLAS_LOCALIZATION_BASELINE'), 'exact live capture required')
    def test_reference_equivalence(self):
        raw = Path(os.environ['ATLAS_LOCALIZATION_BASELINE']).read_bytes()
        original = B.load(raw, 'test_fit_original')
        candidate = B.load(B.candidate(raw), 'test_fit_candidate')
        self.assertEqual(B.equivalence(original, candidate), 216)


if __name__ == '__main__':
    unittest.main()
