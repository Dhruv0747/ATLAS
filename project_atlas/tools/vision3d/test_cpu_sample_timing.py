"""Focused sampler regressions. Native case runs on PC WSL only, never Jetson."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import tempfile
import time
import unittest
from unittest.mock import patch
from web_activation_supervisor import sample_deadline,interval_valid,measure_cpu_interval

path=Path(os.environ['ATLAS_CPU_COLLECTOR'])
assert hashlib.sha256(path.read_bytes()).hexdigest()=='a93ae9d0a8486a843b1648f764c2e34dda84916d20750712413a81a9f25a7021'
spec=importlib.util.spec_from_file_location('existing_cpu',path);cpu=importlib.util.module_from_spec(spec);spec.loader.exec_module(cpu)

def pair(elapsed=1,busy=60):
    a={'cpu':[100,0,0,100,0,0,0,0],'cpu_started':10.,'processes':{},'groups':{}}
    b=copy.deepcopy(a);b['cpu']=[100+busy,0,0,200-busy,0,0,0,0];b['cpu_started']=10+elapsed
    return a,b

class TimingTests(unittest.TestCase):
    def test_saved_187ms_overhead(self):
        a={'cpu_started':25071.332245102};finished=25071.518948531
        self.assertAlmostEqual(sample_deadline(a)-finished,.813296571,places=6)
        self.assertGreater(finished+1-a['cpu_started'],1.1) # old scheduling fails
        self.assertTrue(interval_valid(a,{'cpu_started':sample_deadline(a)}))

    def test_setup_cpu_is_not_subtracted(self):
        a,b=pair(busy=79)
        with tempfile.TemporaryDirectory() as d:
            delta=measure_cpu_interval(cpu,a,b,100,Path(d))
        self.assertEqual(delta['cpu_pct'],79)
        self.assertEqual(cpu.resource_check(delta['cpu_pct'],{'MemTotal':100,'MemAvailable':50},{'thermal_zones_c':{'cpu':60}})['failed'],['cpu'])

    def test_unchanged_threshold(self):
        for busy,failed in [(75,[]),(76,['cpu'])]:
            a,b=pair(busy=busy);delta=cpu.differences(a,b,100)
            self.assertEqual(cpu.resource_check(delta['cpu_pct'],{'MemTotal':100,'MemAvailable':50},{'thermal_zones_c':{'cpu':60}})['failed'],failed)

    def test_delayed_and_short_intervals_preserved_before_abort(self):
        for elapsed in (.8,1.187,2.0):
            with self.subTest(elapsed=elapsed),tempfile.TemporaryDirectory() as d:
                a,b=pair(elapsed,busy=79)
                with self.assertRaisesRegex(ValueError,'CPU sample interval failed'):
                    measure_cpu_interval(cpu,a,b,100,Path(d))
                row=json.loads((Path(d)/'process-cpu.jsonl').read_text())
                self.assertEqual(row['snapshot'],b);self.assertEqual(row['delta']['cpu_pct'],79)

    def test_small_delay_reanchors_without_counter_reset(self):
        a,b=pair(1.05)
        self.assertTrue(interval_valid(a,b));self.assertEqual(sample_deadline(b),12.05)
        # Next interval starts at b's actual timestamp, not a catch-up deadline.
        c=copy.deepcopy(b);c['cpu_started']=sample_deadline(b);c['cpu'][0]+=80;c['cpu'][3]+=20
        self.assertEqual(cpu.differences(b,c,100)['cpu_pct'],80)

    def test_invalid_clock(self):
        for value in [float('nan'),float('inf'),'10',None]:
            with self.subTest(value=value),self.assertRaises(ValueError):sample_deadline({'cpu_started':value})
        self.assertFalse(interval_valid({'cpu_started':10},{'cpu_started':9}))

    def test_wall_clock_not_used(self):
        with patch('time.time',side_effect=RuntimeError('wall clock not allowed')):
            self.assertEqual(sample_deadline({'cpu_started':10}),11)
            self.assertTrue(interval_valid({'cpu_started':10},{'cpu_started':11}))

    @unittest.skipUnless('microsoft' in platform.release().lower(),'native PC WSL only')
    def test_native_counters_with_initial_cpu_work(self):
        evidence=[]
        with tempfile.TemporaryDirectory() as d:
            before=cpu.snapshot();start=time.monotonic()
            # Actual CPU work during the former setup-overhead gap must be counted.
            while time.monotonic()-start<.187:pass
            for _ in range(3):
                time.sleep(max(0,sample_deadline(before)-time.monotonic()))
                after=cpu.snapshot();delta=measure_cpu_interval(cpu,before,after,os.sysconf('SC_CLK_TCK'),Path(d))
                evidence.append({'interval':delta['aggregate_interval_s'],'cpu':delta['cpu_pct'],'own_cpu':delta['processes'].get(str(os.getpid()))})
                before=after
        self.assertGreater(evidence[0]['own_cpu']['delta_ticks'],0)
        print('NATIVE_TIMING_EVIDENCE',json.dumps(evidence))

if __name__=='__main__':unittest.main()
