"""2026-11-16: the dashboard keeps the live Nav2 plan while a goal is active (pure helpers; no ROS)."""
import ast
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / 'scripts' / 'atlas_status_web.py'
tree = ast.parse(SRC.read_text(encoding='utf-8'))
ns = {}
body = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in ('nav_goal_active', 'visible_plan'))
        or (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') == 'NAV_ACTIVE_MARKERS' for t in n.targets))]
exec(compile(ast.Module(body=body, type_ignores=[]), str(SRC), 'exec'), ns)
visible_plan, nav_goal_active = ns['visible_plan'], ns['nav_goal_active']

PLAN = lambda age: {'value': [[0, 0], [1, 1]], 'age': age}
GOAL = lambda age: {'value': {'x': 1, 'y': 1}, 'age': age}
MISSION = lambda text, age=0.5: {'value': text, 'age': age}


class PlanVisibleTests(unittest.TestCase):
    def test_fresh_plan_always_shown(self):
        self.assertIsNotNone(visible_plan(PLAN(5), None, None))

    def test_old_plan_hidden_when_idle(self):
        self.assertIsNone(visible_plan(PLAN(45), GOAL(50), MISSION('READY')))
        self.assertIsNone(visible_plan(PLAN(45), GOAL(50), MISSION('NAMED GOAL FINISHED name=hall status=4')))

    def test_old_plan_kept_during_active_goal(self):
        self.assertIsNotNone(visible_plan(PLAN(60), GOAL(62), MISSION('NAMED GOAL ACCEPTED name=hall')))

    def test_plan_from_before_this_goal_hidden(self):
        # e.g. an old map-acceptance plan-only check: older than the current goal
        self.assertIsNone(visible_plan(PLAN(300), GOAL(40), MISSION('NAMED GOAL ACCEPTED name=hall')))

    def test_stale_mission_status_is_not_active(self):
        self.assertFalse(nav_goal_active(MISSION('NAMED GOAL ACCEPTED name=hall', age=20)))
        self.assertIsNone(visible_plan(PLAN(60), GOAL(62), MISSION('NAMED GOAL ACCEPTED name=hall', age=20)))

    def test_missing_inputs(self):
        self.assertIsNone(visible_plan(None, GOAL(1), MISSION('NAMED GOAL ACCEPTED')))
        self.assertIsNone(visible_plan(PLAN(60), None, MISSION('NAMED GOAL ACCEPTED')))
        self.assertFalse(nav_goal_active(None))


if __name__ == '__main__':
    unittest.main()
