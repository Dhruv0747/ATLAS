import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import startup_cpu_attribution as m


def row():
    return {'mono':1.,'cpu':[100,0,0,100,0,0,0,0],'hz':100,
            'processes':{'7':{'name':'recovery (node)','mono':1.,'start_ticks':1,'user_ticks':10,'system_ticks':0}},
            'groups':{'recovery':{'mono':1.,'path':'/a','inode':1,'device':1,'usage_ns':100000000}}}

class Tests(unittest.TestCase):
    def test_attribution_and_genuine_spike(self):
        a=row();b=copy.deepcopy(a);b['mono']=2.;b['cpu']=[190,0,0,110,0,2,3,0]
        b['processes']['7'].update(mono=2.,user_ticks=40)
        b['groups']['recovery'].update(mono=2.,usage_ns=400000000)
        d=m.differences(a,b)
        self.assertGreater(d['cpu_pct'],75);self.assertEqual(d['processes']['7']['one_core_pct'],30)
        self.assertEqual(d['groups']['recovery']['one_core_pct'],30)
        self.assertEqual((d['irq_ticks'],d['softirq_ticks']),(2,3))
    def test_pid_reuse_and_exit_not_false_delta(self):
        a=row();b=copy.deepcopy(a);b['mono']=2.;b['cpu'][0]+=1;b['processes']['7']['start_ticks']=2;b['groups']={}
        self.assertIn('7',m.differences(a,b)['new_or_reused'])
        b['processes']={};self.assertEqual(m.differences(a,b)['exited'],['7'])
    def test_cgroup_replacement_not_delta(self):
        a=row();b=copy.deepcopy(a);b['mono']=2.;b['cpu'][0]+=1;b['groups']['recovery']['inode']=2
        b['processes']={};self.assertEqual(m.differences(a,b)['groups'],{})
    def test_invalid_intervals_and_counter_reset(self):
        a=row();b=copy.deepcopy(a)
        with self.assertRaises(ValueError):m.differences(a,b)
        b['mono']=2.;b['cpu'][0]-=1
        with self.assertRaises(ValueError):m.differences(a,b)
    def test_proc_and_both_cgroup_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'stat').write_text('cpu 100 0 20 500 2 3 4 0 0 0\n')
            (p/'7').mkdir();f=['0']*22;f[0]='S';f[11]='12';f[12]='3';f[19]='50';f[21]='99'
            (p/'7'/'stat').write_text('7 (name with ) bracket) '+' '.join(f))
            (p/'v1').mkdir();(p/'v1'/'cpuacct.usage').write_text('123000')
            (p/'v2').mkdir();(p/'v2'/'cpu.stat').write_text('usage_usec 456\nuser_usec 400\n')
            s=m.snapshot(p,[('one',p/'v1',1),('two',p/'v2',2),('absent',p/'missing',2)])
            self.assertEqual(s['processes']['7']['user_ticks'],12)
            self.assertEqual(s['groups']['two']['usage_ns'],456000)
            self.assertEqual(s['gaps'][0]['group'],'absent')
    def test_inventory_and_budget_failure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'stat').write_text('cpu 1 2 3 4 5 6 7 8\n');(p/'1').mkdir()
            with patch.object(m,'MAX_PIDS',0):
                with self.assertRaises(ValueError):m.snapshot(p)
            with self.assertRaises(ValueError):m.snapshot(p,budget=-1)
    def test_atomic_evidence_quota_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);h=m.persist(p,0,{'a':1});self.assertEqual(len(h),64)
            with self.assertRaises(ValueError):m.persist(p,0,{'a':2})
            with patch.object(m,'MAX_BYTES',1):
                with self.assertRaises(ValueError):m.persist(p,1,{'a':2})
            self.assertEqual(json.loads((p/'000.json').read_text()),{'a':1})
    def test_native_sigkill_keeps_durable_samples(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'capture'
            code='import startup_cpu_attribution as m; m.run('+repr(str(p))+',duration=10)'
            proc=subprocess.Popen([sys.executable,'-c',code],cwd=Path(m.__file__).parent)
            try:
                deadline=time.monotonic()+5
                while not (p/'001.json').exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue((p/'001.json').exists());proc.kill();proc.wait(timeout=2)
                for f in p.glob('*.json'):self.assertIn('snapshot',json.loads(f.read_text()))
                # READY may survive SIGKILL; explicitly never an authorization.
                self.assertIn('Not a safety approval',json.loads((p/'READY').read_text())['warning'])
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
    def test_collection_failure_records_abort(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'capture'
            with patch.object(m,'snapshot',side_effect=TimeoutError('budget')):
                with self.assertRaises(TimeoutError):m.run(p,duration=1)
            self.assertEqual(json.loads((p/'000.json').read_text())['error_type'],'TimeoutError')
            self.assertFalse((p/'READY').exists())
    def test_stop_marker_does_not_touch_services(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'capture';real=m.persist
            def stop(directory,index,data):
                result=real(directory,index,data);(directory/'STOP').touch();return result
            with patch.object(m,'persist',side_effect=stop):self.assertEqual(m.run(p,duration=10),1)
            self.assertFalse((p/'READY').exists())
    def test_bounded_completion_and_stop(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'capture';count=m.run(p,duration=1)
            self.assertEqual(count,1);self.assertFalse((p/'READY').exists())
            with self.assertRaises(ValueError):m.run(Path(d)/'bad',duration=31)

if __name__=='__main__':unittest.main()
