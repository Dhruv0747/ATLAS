"""Role-board readiness tests; no ROS initialization or robot commands."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


class TeamStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        path = Path(__file__).parents[1] / 'scripts/atlas_agent_team.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        cls.bases = []
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('update', 'snapshot')]
        ns = {'json': json, 'time': SimpleNamespace(monotonic=lambda: self.now)}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), ns)
        self.node = ns['AtlasAgentTeam']()
        self.node.values, self.node.seen = {}, {}
        for role in ('mission_director', 'safety_guardian', 'driver', 'mode_manager',
                     'recovery_specialist', 'localization', 'perception'):
            self.node.update(role, 'fresh')

    def ready(self):
        self.node.update('control_policy', '{"manual_only":false,"stop_latched":false}')
        self.node.update('encoder_health', '{"autonomy_ready":true}')
        self.node.update('readiness', 'AUTO_READY')
        self.node.update('recovery_specialist', '{"overall":"HEALTHY"}')

    def test_heartbeats_alone_not_ready(self):
        state = self.node.snapshot()
        self.assertTrue(state['communications_online'])
        self.assertFalse(state['autonomy_ready'])
        self.assertEqual(state['overall'], 'DEGRADED')

    def test_all_existing_gates_needed(self):
        self.ready()
        self.assertTrue(self.node.snapshot()['autonomy_ready'])
        self.node.update('control_policy', '{"manual_only":true,"stop_latched":true}')
        self.assertFalse(self.node.snapshot()['autonomy_ready'])

    def test_fault_and_stale_not_ready(self):
        self.ready()
        self.node.update('recovery_specialist', '{"overall":"FAULT"}')
        self.assertFalse(self.node.snapshot()['autonomy_ready'])
        self.ready()
        self.now += 7
        self.assertFalse(self.node.snapshot()['autonomy_ready'])

    def test_complete_json_not_truncated_before_readiness(self):
        self.ready()
        self.node.update('encoder_health', json.dumps({'detail': 'x' * 700, 'autonomy_ready': False}))
        self.assertFalse(self.node.snapshot()['autonomy_ready'])
        for bad in ('null', '[]', '{', 'true', 'x' * 17000):
            self.node.update('control_policy', bad)
            self.assertFalse(self.node.snapshot()['autonomy_ready'])


if __name__ == '__main__':
    unittest.main()
