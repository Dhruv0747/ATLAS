import ast
import hashlib
import json
import os
from pathlib import Path
import unittest
from prepare_production_snapshot import apply_changes,BASELINE

class ExactLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['ATLAS_SNAPSHOT_REVIEW'])
        cls.before=(cls.root/'live.py').read_bytes()
        cls.after=(cls.root/'package/atlas_sensor_recovery.py').read_bytes()
        cls.plan=json.loads((cls.root/'package/plan.json').read_text())
    def test_baseline_and_byte_exact_rollback(self):
        self.assertEqual(hashlib.sha256(self.before).hexdigest(),BASELINE)
        self.assertEqual(apply_changes(self.after.decode(),self.plan['changes'],True).encode(),self.before)
    def test_all_unrelated_functions_preserved(self):
        def methods(raw):return {n.name:ast.dump(n) for n in ast.walk(ast.parse(raw)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        old,new=methods(self.before),methods(self.after)
        for name,body in old.items():
            if name not in {'__init__','on_velocity','on_control_policy','on_message'}:self.assertEqual(body,new[name],name)
        self.assertIn('_atlas_base_dispatch_enter',new)
        self.assertIn('_atlas_base_maint_tick',new)
    def test_no_extra_ros_entities(self):
        def calls(raw):return [ast.dump(n) for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {'create_subscription','create_timer','create_publisher'}]
        self.assertEqual(calls(self.before),calls(self.after))
    def test_opt_in_and_compile(self):
        self.assertIn("if os.environ.get('ATLAS_RESTART_SNAPSHOT') == '1':",self.after.decode())
        compile(self.after,'candidate','exec')
        self.assertFalse(self.plan['restart_authorized'])
    def test_hash_manifest(self):
        for line in (self.root/'package/SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1)
            self.assertEqual(hashlib.sha256((self.root/'package'/name).read_bytes()).hexdigest(),h)

if __name__=='__main__':unittest.main()
