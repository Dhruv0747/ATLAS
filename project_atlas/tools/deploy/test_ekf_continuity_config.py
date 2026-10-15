import math, sys, unittest
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent))
from ekf_continuity_config import build, only_initial_state_differs
CFG = Path(__file__).resolve().parents[2] / 'config'


class ContinuityConfig(unittest.TestCase):
    def test_candidate_b_gets_only_initial_state(self):
        src = yaml.safe_load(open(CFG / 'atlas_ekf_candidate_b.yaml'))
        out = build(src, 1.097, 0.337, 0.597)
        self.assertTrue(only_initial_state_differs(src, out))
        self.assertEqual(out['atlas_ekf']['ros__parameters']['initial_state'][:6], [1.097, 0.337, 0.0, 0.0, 0.0, 0.597])
        self.assertEqual(len(out['atlas_ekf']['ros__parameters']['initial_state']), 15)
        self.assertNotIn('initial_state', src['atlas_ekf']['ros__parameters'])   # source untouched

    def test_production_rollback_config_too(self):
        src = yaml.safe_load(open(CFG / 'atlas_ekf.yaml'))
        self.assertTrue(only_initial_state_differs(src, build(src, 0.0, 0.0, 0.0)))

    def test_non_finite_pose_refused(self):
        src = yaml.safe_load(open(CFG / 'atlas_ekf.yaml'))
        with self.assertRaises(ValueError):
            build(src, float('nan'), 0.0, 0.0)


if __name__ == '__main__':
    unittest.main()
