import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rejected_cpu_evidence import record_cpu_rejection

class Tests(unittest.TestCase):
    def test_raw_counter_retention_without_attribution_claim(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);record_cpu_rejection(p,[1000,400],[1600,438],10,11,93.6666667)
            row=json.loads((p/'rejected-cpu.json').read_text())
            self.assertEqual(row['before_ticks'],[1000,400]);self.assertEqual(row['interval_s'],1)
            self.assertEqual(row['decision'],'ABORT');self.assertFalse(row['retry'])
            self.assertFalse(json.loads((p/'health.json').read_text())['safe'])
    def test_failure_signal_precedes_evidence_failure(self):
        calls=[]
        def save(path,data):
            calls.append((path.name,data))
            if path.name=='rejected-cpu.json':raise OSError('disk full')
        with patch('rejected_cpu_evidence.save',side_effect=save):
            with self.assertRaises(OSError):record_cpu_rejection(Path('/unused'),[1,0],[2,0],1,2,100)
        self.assertEqual(calls[0][0],'health.json');self.assertFalse(calls[0][1]['safe'])
    def test_watcher_stops_before_more_probes_on_rejection(self):
        import recovery_snapshot_supervisor as m
        from restart_policy import save
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save(p/'watcher-baseline.json',{'ticks':[100,50],'mono':10})
            with patch.object(m.time,'monotonic',return_value=11),patch.object(m.time,'sleep'),patch.object(m,'ticks',return_value=(200,50)),patch.object(m,'resources',side_effect=AssertionError('must not collect after CPU failure')),patch.object(m,'fetch',side_effect=AssertionError('must not poll after CPU failure')):
                with self.assertRaisesRegex(ValueError,'CPU guard'):m.watch(p)
            self.assertEqual(json.loads((p/'rejected-cpu.json').read_text())['cpu_pct'],100)
            self.assertFalse(json.loads((p/'health.json').read_text())['safe'])

if __name__=='__main__':unittest.main()
