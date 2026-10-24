import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools/diagnostics'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('localization_benchmark', TOOLS/'benchmark_localization_executor.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


class CandidateTests(unittest.TestCase):
    def test_unknown_live_source_rejected(self):
        with self.assertRaises(ValueError): M.candidate(b'print(1)')

    def test_only_spin_call_changes(self):
        raw = b'def main():\n    try:\n        rclpy.spin(node)\n    finally:\n        node.destroy_node()\n        rclpy.shutdown()\n'
        with patch.object(M, 'MONITOR_SHA', hashlib.sha256(raw).hexdigest()):
            actual = M.candidate(raw).decode()
        replacement = '        from atlas_dashboard_executor import spin as private_spin\n        private_spin(node)'
        self.assertEqual(actual.replace(replacement, '        rclpy.spin(node)'), raw.decode())

    def test_ambiguous_source_rejected(self):
        raw = b'def main():\n        rclpy.spin(node)\n        rclpy.spin(node)\n'
        with patch.object(M, 'MONITOR_SHA', hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
            M.candidate(raw)


if __name__ == '__main__': unittest.main()
