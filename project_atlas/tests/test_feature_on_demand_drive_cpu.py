"""2026-11-16: AI annotator / agent team are not started by autonomy demand (owner: free CPU while driving)."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_feature_on_demand as fod  # noqa: E402

CFG = Path(__file__).parents[1] / 'config' / 'atlas_feature_on_demand.yaml'


class DriveCpuTests(unittest.TestCase):
    def test_repo_config_drops_autonomy_trigger_for_ai_extras(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('PyYAML not installed (runs on the rover)')
        _, features = fod.load_config(str(CFG))
        self.assertEqual(features['atlas-agent-team']['triggers'], [])
        self.assertNotIn('autonomy', features['atlas-ai-annotator']['triggers'])
        self.assertIn('ai_object', features['atlas-ai-annotator']['triggers'])
        self.assertIn('autonomy', features['atlas-vision-lidar-fusion']['triggers'])   # untouched

    def test_unknown_trigger_still_rejected(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('PyYAML not installed (runs on the rover)')
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
            f.write('features:\n  atlas-agent-team: {triggers: [bogus]}\n')
        with self.assertRaises(SystemExit):
            fod.load_config(f.name)


if __name__ == '__main__':
    unittest.main()
