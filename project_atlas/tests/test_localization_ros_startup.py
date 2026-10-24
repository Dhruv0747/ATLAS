import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).parents[1] / 'tools/diagnostics/benchmark_localization_ros_startup.py'
spec = importlib.util.spec_from_file_location('ros_startup', PATH)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class IsolationTests(unittest.TestCase):
    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            B.constructor_module(b'def main(): pass')

    def test_main_actions_excluded(self):
        # Actual captured source is private evidence, not required on other PCs.
        raw = b'def main():\n class Monitor: pass\n launch_robot()\n'
        with patch.object(B, 'SOURCE_SHA', B.hashlib.sha256(raw).hexdigest()):
            tree = B.constructor_module(raw)
        self.assertTrue(all(isinstance(x, (ast.ClassDef, ast.FunctionDef, ast.Import, ast.ImportFrom)) for x in tree.body))
        self.assertNotIn('launch_robot', ast.dump(tree))

    def test_private_domain_required(self):
        with patch.object(B.platform, 'machine', return_value='x86_64'):
            with patch.dict(B.os.environ, {'ROS_LOCALHOST_ONLY':'1','ROS_DOMAIN_ID':'214'}, clear=True):
                B.isolation()
                with patch.dict(B.os.environ, {'ROS_DOMAIN_ID':'0'}):
                    with self.assertRaises(RuntimeError): B.isolation()
                with patch.dict(B.os.environ, {'ROS_DISCOVERY_SERVER':'remote'}):
                    with self.assertRaises(RuntimeError): B.isolation()

    def test_jetson_refused(self):
        with patch.object(B.platform, 'machine', return_value='aarch64'):
            with self.assertRaises(RuntimeError): B.isolation()

    def test_no_application_spin_and_service_calls(self):
        text = PATH.read_text()
        self.assertNotIn('ex.add_node(app)', text)
        self.assertIn('Client.call_async = forbidden', text)
        self.assertIn('value.cancel()', text)
        self.assertIn('timeout=30', text)


if __name__ == '__main__':
    unittest.main()
