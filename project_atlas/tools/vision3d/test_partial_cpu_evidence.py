import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import startup_cpu_attribution as c
import recovery_attribution_trial as guard
from test_snapshot_benchmark_once import status
from snapshot_benchmark_once import THERMAL

class Tests(unittest.TestCase):
    def partial(self,d):
        p=Path(d);(p/'stat').write_text('cpu 200 0 0 100 0 0 0 0\n')
        for pid in ('1','2','9'):
            (p/pid).mkdir();f=['0']*22;f[0]='S';f[11]='10';f[19]=pid;f[21]='4';(p/pid/'stat').write_text(pid+' (test) '+' '.join(f))
        g=p/'group';g.mkdir();(g/'cpu.stat').write_text('usage_usec 1234\n')
        clock=[10.];read=c.read;order=[]
        def slow(path):
            value=read(path)
            if path.name=='stat' and path.parent.name.isdigit():
                order.append(path.parent.name);clock[0]+=.2 if path.parent.name=='1' else .01
            return value
        with patch.object(c,'read',side_effect=slow),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]):
            sample=c.snapshot(p,[('recovery',g,2)],priority_pids=['9'])
        self.assertEqual(order,['9','1']);return sample
    def test_partial_preserves_cpu_target_group_and_completed_records(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.partial(d);self.assertFalse(s['complete']);self.assertEqual(s['cpu'],[200,0,0,100,0,0,0,0]);self.assertEqual(s['unread_pids'],['2']);self.assertIn('9',s['processes']);self.assertEqual(s['groups']['recovery']['usage_ns'],1234000)
    def test_safe_partial_persisted_without_false_cpu_failure(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.partial(d);old=copy.deepcopy(s);old.update(mono=9.,processes={},groups={});old['cpu']=[140,0,0,60,0,0,0,0]
            out=Path(d)/'evidence';out.mkdir()
            with patch.object(guard,'resources',return_value=(50,dict.fromkeys(THERMAL,60))),patch.object(guard,'fetch',return_value=status()):
                guard.sample(out,1,old,collect=lambda **_:s)
            r=json.loads((out/'001.json').read_text());self.assertTrue(r['safe']);self.assertEqual(r['delta']['cpu_pct'],60);self.assertFalse(r['snapshot']['complete']);self.assertFalse(json.loads((out/'health.json').read_text())['attribution_complete'])
    def test_true_cpu_spike_still_rejected_and_saved(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.partial(d);old=copy.deepcopy(s);old.update(mono=9.,processes={},groups={});old['cpu']=[110,0,0,90,0,0,0,0]
            out=Path(d)/'evidence';out.mkdir()
            with patch.object(guard,'resources',side_effect=AssertionError('no later probe')):
                with self.assertRaisesRegex(ValueError,'CPU guard'):guard.sample(out,1,old,collect=lambda **_:s)
            r=json.loads((out/'001.json').read_text());self.assertEqual(r['failure_kind'],'CPU_LIMIT');self.assertEqual(r['delta']['cpu_pct'],90);self.assertFalse(r['safe'])
    def test_skipped_pid_is_not_claimed_exited(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.partial(d);old=copy.deepcopy(s);old.update(mono=9.,groups={},processes={'2':{}});old['cpu'][3]-=10
            delta=c.differences(old,s);self.assertEqual(delta['exited'],[]);self.assertEqual(delta['not_observed'],['2'])
    def test_late_cpu_interval_remains_diagnostic_failure(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.partial(d);old=copy.deepcopy(s);old.update(mono=8.,groups={},processes={});old['cpu'][3]-=10
            out=Path(d)/'evidence';out.mkdir()
            with self.assertRaisesRegex(ValueError,'interval'):guard.sample(out,1,old,collect=lambda **_:s)
            r=json.loads((out/'001.json').read_text());self.assertEqual(r['failure_kind'],'SAMPLING_INTERVAL');self.assertEqual(r['delta']['cpu_pct'],0)

if __name__=='__main__':unittest.main()
