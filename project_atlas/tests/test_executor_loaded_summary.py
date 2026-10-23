import importlib.util
from pathlib import Path
import sys
import unittest

DIRECTORY = Path(__file__).resolve().parents[1]/'tools/diagnostics'
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('loaded', DIRECTORY/'benchmark_executor_loaded.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class LoadedSummaryTests(unittest.TestCase):
    def rows(self):
        return [dict(pair=0, variant=v, cpu_s=c, sent=100, received=100, errors=[])
                for v,c in [('cancellation_only', 2), ('combined', 1.8)]]

    def test_equal_work(self):
        self.assertAlmostEqual(M.summarize(self.rows())['median_saving_percent'], 10)

    def test_negative_results_retained(self):
        rows = self.rows()
        rows[1]['cpu_s'] = 3
        self.assertEqual(M.summarize(rows)['median_saving_percent'], -50)

    def test_missing_messages_rejected(self):
        rows = self.rows()
        rows[1]['received'] = 99
        with self.assertRaises(ValueError): M.summarize(rows)

    def test_unequal_work_rejected(self):
        rows = self.rows()
        rows[1].update(sent=90, received=90)
        with self.assertRaises(ValueError): M.summarize(rows)

    def test_duplicate_and_incomplete_pairs_rejected(self):
        for rows in (self.rows()[:1], self.rows()*2):
            with self.assertRaises(ValueError): M.summarize(rows)

    def test_invalid_cpu_rejected(self):
        for value in (0, float('nan'), float('inf')):
            rows = self.rows()
            rows[1]['cpu_s'] = value
            with self.assertRaises(ValueError): M.summarize(rows)
