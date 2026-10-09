"""Offline regression tests for the safety-status AI camera heartbeat."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SAFETY_SOURCE = SCRIPTS / "atlas_safety_status.py"
ANNOTATOR_SOURCE = SCRIPTS / "ai_annotator_node.py"


def class_method(tree, class_name, method_name):
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def published_attribute(statement):
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    function = statement.value.func
    if not isinstance(function, ast.Attribute) or function.attr != "publish":
        return None
    owner = function.value
    if not isinstance(owner, ast.Attribute) or not isinstance(owner.value, ast.Name):
        return None
    if owner.value.id != "self":
        return None
    return owner.attr


class CameraHeartbeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safety_tree = ast.parse(SAFETY_SOURCE.read_text(encoding="utf-8"))
        cls.annotator_tree = ast.parse(ANNOTATOR_SOURCE.read_text(encoding="utf-8"))

    def test_safety_status_uses_lightweight_detection_json_heartbeat(self):
        init = class_method(self.safety_tree, "AtlasSafetyStatus", "__init__")
        subscriptions = [
            call
            for call in ast.walk(init)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "create_subscription"
            and len(call.args) >= 4
            and ast.unparse(call.args[2]) == "self.on_ai_camera"
        ]

        self.assertEqual(len(subscriptions), 1)
        subscription = subscriptions[0]
        self.assertEqual(ast.unparse(subscription.args[0]), "String")
        self.assertEqual(
            ast.literal_eval(subscription.args[1]), "/camera/detections/json"
        )
        self.assertEqual(ast.literal_eval(subscription.args[3]), 10)

    def test_json_heartbeat_trails_annotated_image_on_same_success_path(self):
        init = class_method(self.annotator_tree, "Annotator", "__init__")
        publishers = {
            ast.literal_eval(call.args[1]): call
            for call in ast.walk(init)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "create_publisher"
            and len(call.args) >= 3
        }
        self.assertEqual(
            ast.literal_eval(
                publishers["/camera/detections/compressed"].args[2]
            ),
            10,
        )
        self.assertEqual(
            ast.literal_eval(publishers["/camera/detections/json"].args[2]), 10
        )

        callback = class_method(self.annotator_tree, "Annotator", "cb")

        self.assertEqual(published_attribute(callback.body[-2]), "pub")
        self.assertEqual(published_attribute(callback.body[-1]), "detection_pub")

    def test_camera_freshness_keeps_existing_fail_closed_boundary(self):
        publish_status = class_method(
            self.safety_tree, "AtlasSafetyStatus", "publish_status"
        )
        freshness_nodes = [
            node
            for node in ast.walk(publish_status)
            if isinstance(node, ast.IfExp)
            and any(
                isinstance(child, ast.Attribute)
                and child.attr == "last_ai_camera"
                for child in ast.walk(node.test)
            )
        ]

        self.assertEqual(len(freshness_nodes), 2)
        subject = SimpleNamespace(last_ai_camera=0.0)
        for node in freshness_nodes:
            self.assertEqual(ast.literal_eval(node.body), "ONLINE")
            self.assertEqual(ast.literal_eval(node.orelse), "LOST")
            compiled = compile(
                ast.fix_missing_locations(ast.Expression(node.test)),
                str(SAFETY_SOURCE),
                "eval",
            )
            self.assertFalse(eval(compiled, {}, {"self": subject, "now": 100.0}))
            subject.last_ai_camera = 97.5
            self.assertTrue(eval(compiled, {}, {"self": subject, "now": 100.0}))
            subject.last_ai_camera = 97.499
            self.assertFalse(eval(compiled, {}, {"self": subject, "now": 100.0}))
            subject.last_ai_camera = 0.0

    def test_map_diagnostics_expose_mode_and_age_without_changing_gate(self):
        publish_status = class_method(
            self.safety_tree, "AtlasSafetyStatus", "publish_status"
        )
        rendered = ast.unparse(publish_status)
        self.assertIn("'operating_mode': self.operating_mode", rendered)
        self.assertIn("'received': self.last_map > 0.0", rendered)
        self.assertIn("'age_s': round(now - self.last_map, 2)", rendered)
        classify = ast.unparse(
            class_method(self.safety_tree, "AtlasSafetyStatus", "classify")
        )
        self.assertIn("self.operating_mode != 'LOCALIZATION'", classify)
        self.assertIn("if map_missing or map_stale:", classify)


if __name__ == "__main__":
    unittest.main()
