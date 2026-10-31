"""Focused startup-order tests; no ROS initialization or hardware."""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).parents[1] / 'scripts/atlas_sensor_recovery.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))

class StartupTypesTests(unittest.TestCase):
    def fixture(self):
        string, twist, scan = type('String', (), {}), type('Twist', (), {}), type('Scan', (), {})
        ns = dict(String=string, Twist=twist, MONITORS=[types.SimpleNamespace(msg_type=t) for t in (scan, string, scan)])
        functions = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in ('prepare_message_types', 'main')]
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), ns)
        return ns, [string, twist, scan]

    def test_each_required_type_once(self):
        ns, expected = self.fixture(); check = Mock()
        with patch.dict(sys.modules, {'rclpy.type_support': types.SimpleNamespace(check_for_type_support=check)}):
            ns['prepare_message_types']()
        self.assertEqual([c.args[0] for c in check.call_args_list], expected)

    def test_all_loads_precede_ros_init_and_node(self):
        ns, expected = self.fixture(); events = []
        node = Mock(); node.destroy_node.side_effect = lambda: events.append('destroy')
        ns.update(rclpy=types.SimpleNamespace(init=lambda: events.append('init'), spin=lambda n: events.append('spin'), ok=lambda: False),
                  AtlasRecovery=lambda: events.append('node') or node, ExternalShutdownException=RuntimeError)
        with patch.dict(sys.modules, {'rclpy.type_support': types.SimpleNamespace(check_for_type_support=lambda t: events.append(t))}):
            ns['main']()
        self.assertEqual(events, expected + ['init', 'node', 'spin', 'destroy'])

    def test_import_failure_never_starts_ros(self):
        ns, _ = self.fixture(); init = Mock(); node = Mock()
        ns.update(rclpy=types.SimpleNamespace(init=init), AtlasRecovery=node)
        with patch.dict(sys.modules, {'rclpy.type_support': types.SimpleNamespace(check_for_type_support=Mock(side_effect=ImportError('missing')))}):
            with self.assertRaises(ImportError): ns['main']()
        init.assert_not_called(); node.assert_not_called()

    def test_no_new_entities_sleep_or_subprocess(self):
        fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare_message_types')
        calls = [ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        self.assertEqual(sorted(calls), ['check_for_type_support', 'dict.fromkeys'])

if __name__ == '__main__': unittest.main()