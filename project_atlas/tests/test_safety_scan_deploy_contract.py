"""Static deployment scope checks; not a substitute for live admission."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/diagnostics/deploy_safety_scan_once.py'


class ScopeTest(unittest.TestCase):
    def test_compiles_and_restart_is_scoped(self):
        tree = ast.parse(SOURCE.read_bytes())
        compile(tree, str(SOURCE), 'exec')
        units = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'UNIT' for t in n.targets)]
        self.assertEqual(units, ['atlas-safety-status.service'])
        restart = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'restart')
        self.assertIn("['systemctl', '--user', 'restart', UNIT]", ast.unparse(restart))

    def test_strict_cpu_and_rollback(self):
        text = SOURCE.read_text()
        self.assertIn("G.require_cpu(latest['cpu'])", text)
        self.assertIn("G.check(latest['cpu'] if enforce_cpu else None, snap)", text)
        self.assertIn("if sha(target) != NEW or sha(backup) != BASE:", text)
        self.assertIn("shutil.copy2(backup, target)", text)
        self.assertIn("result['baseline'] = window('baseline')", text)
        self.assertIn("result['post'] = window('post')", text)
        self.assertNotIn('report-only', text)


if __name__ == '__main__':
    unittest.main()
