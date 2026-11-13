"""2026-11-13: during mapping the on-demand manager must not start the AI extras mission control pauses."""
import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'atlas_feature_on_demand.py'
spec = importlib.util.spec_from_file_location('fod_under_test', PATH)
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)

AI = ['atlas-vision-lidar-fusion', 'atlas-person-sensor-fusion', 'atlas-ai-annotator', 'atlas-agent-team',
      'atlas-experience-store']   # experience store: light mapping profile (2026-11-13 evening)


class MappingPause(unittest.TestCase):
    def deciders(self):
        cfg = dict(F.DEFAULTS)
        feats = {u: dict(F.MANAGED[u]) for u in F.MANAGED}
        return [c for c in vars(F).values() if isinstance(c, type) and hasattr(c, 'decide')][0](cfg, feats)

    def test_ai_extras_not_started_while_mapping(self):
        d = self.deciders()
        acts = d.decide({'autonomy': True}, {u: 'inactive' for u in F.MANAGED}, lambda: True)
        started = {u for a, u in acts if a == 'start'}
        for u in AI:
            self.assertNotIn(u, started)

    def test_ai_extras_started_when_not_mapping(self):
        d = self.deciders()
        acts = d.decide({'autonomy': True}, {u: 'inactive' for u in F.MANAGED}, lambda: False)
        started = {u for a, u in acts if a == 'start'}
        for u in AI:
            self.assertIn(u, started)

    def test_lists_match_mission_control(self):
        mc = (PATH.parent / 'atlas_mission_control.py').read_text()
        for u in AI:
            self.assertIn(f'"{u}.service"', mc)
            self.assertIn(u, F.MAPPING_PAUSED)


if __name__ == '__main__':
    unittest.main()
