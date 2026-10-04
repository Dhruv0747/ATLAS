import ast
import math
from pathlib import Path
import unittest


SOURCE = Path(__file__).parents[1] / "scripts" / "yahboom_base.py"


def load_cadence():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name)
            and target.id == "DIAGNOSTIC_PUBLISH_PERIOD_S"
            for target in node.targets
        ):
            body.append(node)
        elif (
            isinstance(node, ast.FunctionDef)
            and node.name == "diagnostic_publish_due"
        ):
            body.append(node)
    namespace = {"math": math}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class YahboomDiagnosticCadenceTests(unittest.TestCase):
    def test_dashboard_diagnostics_run_at_two_hz_without_catch_up_bursts(self):
        values = load_cadence()
        due = values["diagnostic_publish_due"]
        period = values["DIAGNOSTIC_PUBLISH_PERIOD_S"]

        self.assertEqual(period, 0.5)
        self.assertTrue(due(10.0, float("-inf")))
        self.assertFalse(due(10.1, 10.0))
        self.assertFalse(due(10.499, 10.0))
        self.assertTrue(due(10.5, 10.0))
        # A delayed executor callback produces one update, not a replay burst.
        self.assertTrue(due(20.0, 10.5))
        self.assertFalse(due(20.1, 20.0))

    def test_safety_and_navigation_publications_are_not_decimated(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YahboomBase"
        )
        method = next(
            node
            for node in owner.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_publish_board_state"
        )
        parent = {}
        for node in ast.walk(method):
            for child in ast.iter_child_nodes(node):
                parent[child] = node

        authoritative_calls = {
            "_publish_board_imu",
            "_publish_yahboom_odom",
            "_publish_encoder_health",
        }
        found = set()
        for node in ast.walk(method):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
            ):
                continue
            if node.func.attr not in authoritative_calls:
                continue
            found.add(node.func.attr)
            ancestor = parent.get(node)
            while ancestor is not None and ancestor is not method:
                if isinstance(ancestor, ast.If):
                    test_text = ast.unparse(ancestor.test)
                    self.assertNotIn("publish_diagnostics", test_text)
                ancestor = parent.get(ancestor)
        self.assertEqual(found, authoritative_calls)

    def test_only_dashboard_telemetry_is_inside_low_rate_blocks(self):
        source = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YahboomBase"
        )
        method = next(
            node
            for node in owner.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_publish_board_state"
        )
        blocks = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.If)
            and "publish_diagnostics" in ast.unparse(node.test)
        ]
        combined = "\n".join(
            ast.get_source_segment(source, node) or "" for node in blocks
        )
        for publisher in (
            "_pub_motion_vx",
            "_pub_motion_vy",
            "_pub_motion_vz",
            "_wheel_rpm_pubs",
            "_wheel_mps_pubs",
            "_wheel_distance_pubs",
            "_pub_fl",
            "_pub_fr",
            "_pub_rl",
            "_pub_rr",
            "_pub_left",
            "_pub_right",
            "_pub_speed",
        ):
            self.assertIn(publisher, combined)

        # These are the streams that must retain the 10 Hz board-state cadence.
        for publisher in (
            "_enc_pubs",
            "_pub_system_imu",
            "_pub_odom",
            "_pub_encoder_health",
        ):
            self.assertNotIn(publisher, combined)

    def test_control_and_board_state_timers_remain_ten_hz(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YahboomBase"
        )
        init = next(
            node
            for node in owner.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        timer_periods = {}
        for node in ast.walk(init):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
            ):
                continue
            if node.func.attr != "create_timer" or len(node.args) < 2:
                continue
            callback = node.args[1]
            if isinstance(callback, ast.Attribute):
                timer_periods[callback.attr] = ast.literal_eval(node.args[0])

        self.assertEqual(timer_periods["_motor_keepalive"], 0.1)
        self.assertEqual(timer_periods["_publish_board_state"], 0.1)


if __name__ == "__main__":
    unittest.main()
