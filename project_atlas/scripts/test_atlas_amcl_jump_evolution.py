"""Selection checks for the read-only AMCL jump-window analyzer."""

import unittest

from atlas_amcl_jump_evolution import nearest_before


class NearestBeforeTest(unittest.TestCase):
    def test_selects_latest_causal_sample(self):
        series = [(1.0, "old"), (1.4, "new"), (1.7, "future")]
        times = [item[0] for item in series]
        self.assertEqual(nearest_before(series, times, 1.5), (1.4, "new"))

    def test_rejects_stale_or_future_sample(self):
        series = [(1.0, "old"), (2.0, "future")]
        times = [item[0] for item in series]
        self.assertIsNone(nearest_before(series, times, 1.8))
        self.assertIsNone(nearest_before(series, times, 0.9))


if __name__ == "__main__":
    unittest.main()
