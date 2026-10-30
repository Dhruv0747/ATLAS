import json
import tempfile
import time
from pathlib import Path
import unittest
from recovery_snapshot_supervisor import health
from restart_policy import save

class WatcherTests(unittest.TestCase):
    def test_missing_failed_stale_independent_watcher(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with self.assertRaises(OSError):health(p)
            for row in ({'safe':False,'mono':time.monotonic()}, {'safe':True,'mono':time.monotonic()-2},{'safe':True,'mono':time.monotonic()+1}):
                save(p/'health.json',row)
                with self.assertRaises(ValueError):health(p)
            save(p/'health.json',{'safe':True,'mono':time.monotonic()})
            self.assertTrue(health(p)['safe'])
    def test_watcher_has_no_recovery_safety_dependency(self):
        import ast
        source=Path(__file__).with_name('recovery_snapshot_supervisor.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='watch')
        text=ast.get_source_segment(source,node)
        self.assertNotIn('state.json',text)
        self.assertNotIn('Consumer',text)
        self.assertIn("fetch('/api/status')",text)
        self.assertIn("if cpu>75",text)

    def test_watcher_includes_startup_counters(self):
        from unittest.mock import patch
        import recovery_snapshot_supervisor as m
        from snapshot_benchmark_once import THERMAL
        from test_snapshot_benchmark_once import status
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save(root/'watcher-baseline.json',{'ticks':[100,50],'mono':10})
            with patch.object(m.time,'monotonic',return_value=11),patch.object(m.time,'sleep',side_effect=[None,KeyboardInterrupt()]),patch.object(m,'ticks',return_value=(200,100)),patch.object(m,'resources',return_value=(60,dict.fromkeys(THERMAL,60))),patch.object(m,'fetch',return_value=status()),patch.object(m.subprocess,'check_output',return_value='0'):
                with self.assertRaises(KeyboardInterrupt):m.watch(root)
            row=json.loads((root/'samples.jsonl').read_text())
            self.assertEqual(row['cpu'],50)
            self.assertFalse(json.loads((root/'health.json').read_text())['safe'])

if __name__=='__main__':unittest.main()
