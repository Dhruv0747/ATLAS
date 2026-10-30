import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from feature_policy import decide, FEATURES


class FeaturePolicyTests(unittest.TestCase):
    def setUp(self):
        self.safe = dict(estop=True, telemetry_fresh=True, stationary=True,
                         commands_zero=True, cpu=60, ram=60, temperature=60)
        self.available = dict.fromkeys(FEATURES, True)

    def test_priority_and_independent_disable(self):
        r = decide(FEATURES, self.available, self.safe)
        self.assertEqual(r['active'], ['mapping', 'obstacle_awareness', 'object_detection'])
        self.assertFalse(r['pan_tilt_allowed'])
        self.assertEqual(decide([], self.available, self.safe)['active'], [])

    def test_backlog_sheds_optional(self):
        self.assertEqual(decide(FEATURES, self.available, self.safe, mapping_backlog=True)['active'],
                         ['mapping', 'obstacle_awareness'])

    def test_fail_closed_each_input(self):
        for key in self.safe:
            for bad in (None, float('nan'), 'true'):
                state = dict(self.safe); state[key] = bad
                self.assertEqual(decide(FEATURES, self.available, state)['active'], [])
            state = dict(self.safe); del state[key]
            self.assertEqual(decide(FEATURES, self.available, state)['active'], [])
        for key, boundary in [('cpu',75), ('ram',80), ('temperature',70)]:
            state = dict(self.safe); state[key] = boundary
            self.assertEqual(decide(FEATURES, self.available, state)['active'], [])

    def test_consent_and_missing_dependencies(self):
        self.assertEqual(decide(['face_identification'], self.available, self.safe)['active'], [])
        self.assertEqual(decide(['face_identification'], self.available, self.safe, face_consent=True)['active'],
                         ['face_identification'])
        self.assertEqual(decide(FEATURES, {}, self.safe)['active'], [])
        self.assertEqual(decide(['unknown'], self.available, self.safe)['active'], [])


if __name__ == '__main__': unittest.main()
