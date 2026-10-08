import ast
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from atlas_drive_pid_lifted import MAX_POLICY_AGE_S


class PolicyHeartbeatTests(unittest.TestCase):
    def test_period_has_margin_without_weakening_guard(self):
        tree = ast.parse((SCRIPTS / 'atlas_cmd_vel_mux.py').read_text())
        periods = [ast.literal_eval(n.args[0]) for n in ast.walk(tree)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == 'create_timer' and len(n.args) >= 2
                   and isinstance(n.args[1], ast.Attribute)
                   and n.args[1].attr == 'publish_mode']
        self.assertEqual(periods, [0.1])
        self.assertEqual(MAX_POLICY_AGE_S, 0.5)
        self.assertLessEqual(periods[0], MAX_POLICY_AGE_S / 5)
