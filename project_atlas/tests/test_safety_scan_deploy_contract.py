"""Static deployment scope checks; not a substitute for live admission."""
import ast
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/diagnostics/deploy_safety_scan_once.py'
spec = importlib.util.spec_from_file_location('installer', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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
        self.assertIn("validate_cpu_sample(latest['cpu'], report_only, G.require_cpu)", text)
        self.assertIn("G.check(latest['cpu'] if enforce_cpu and not report_only else None, snap)", text)
        self.assertIn("if sha(target) != NEW or sha(backup) != BASE:", text)
        self.assertIn("shutil.copy2(backup, target)", text)
        self.assertIn("result['baseline'] = window('baseline')", text)
        self.assertIn("result['post'] = window('post')", text)
        self.assertIn("P.extra_safety(snap['ros'])", text)

    def test_cpu_exception_explicit_and_narrow(self):
        self.assertFalse(module.cpu_report_only([]))
        self.assertTrue(module.cpu_report_only(['--installation-cpu-report-only']))
        with self.assertRaises(ValueError):
            module.cpu_report_only(['--ignore-safety'])
        def strict(cpu):
            if cpu > 75:
                raise RuntimeError('CPU')
        with self.assertRaises(RuntimeError):
            module.validate_cpu_sample(86, False, strict)
        module.validate_cpu_sample(86, True, strict)
        for bad in [float('nan'), float('inf'), -1, 101]:
            with self.assertRaises(RuntimeError):
                module.validate_cpu_sample(bad, True, strict)


if __name__ == '__main__':
    unittest.main()
