import ast
import importlib.util
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate', ROOT / 'tools/diagnostics/benchmark_safety_scan_transform.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class CandidateTest(unittest.TestCase):
    def test_wrong_baseline_rejected(self):
        with self.assertRaises(ValueError):
            C.candidate(b'unknown source')

    @unittest.skipUnless(os.environ.get('ATLAS_SAFETY_BASELINE'), 'captured baseline required')
    def test_other_methods_unchanged(self):
        raw = pathlib.Path(os.environ['ATLAS_SAFETY_BASELINE']).read_bytes()
        patched = C.candidate(raw)
        def methods(data):
            return {n.name: ast.dump(n) for n in ast.walk(ast.parse(data))
                    if isinstance(n, ast.FunctionDef) and n.name != 'on_scan'}
        self.assertEqual(methods(raw), methods(patched))
        self.assertTrue(patched.startswith(b'#!/usr/bin/env python3'))

    @unittest.skipUnless(os.environ.get('ATLAS_SAFETY_BASELINE'), 'captured baseline required')
    def test_equivalence_and_benchmark(self):
        result = C.run(pathlib.Path(os.environ['ATLAS_SAFETY_BASELINE']).read_bytes())
        self.assertEqual(result['equivalence_cases'], 335)


if __name__ == '__main__':
    unittest.main()
