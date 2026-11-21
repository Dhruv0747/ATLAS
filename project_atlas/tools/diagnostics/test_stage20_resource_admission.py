import copy
import json
import tempfile
from pathlib import Path
import unittest
from stage20_resource_probe import cpu_delta
from stage20_resource_admission import LIMITS,decide,check,AdmissionRefused
from stage20_install_evidence import Evidence
import test_stage20_install_failure as failure


def fixture():
    measured={'timestamp':'2026-10-14T14:00:05+00:00','duration_s':5.1,'method':'fixture /proc/stat',
              'cpu_samples':[{'duration_s':1.01,'timestamp':'2026-10-14T14:00:0%s+00:00'%i,
                              'utilization_percent':{'cpu':70.0,'cpu0':80.0}} for i in range(5)],
              'ram_percent':70.0,'temperature_c':59.0,'free_disk_bytes':3*1024**3,
              'per_process':[{'pid':11,'name':'amcl','cpu_percent_one_core':10.0}]}
    status={'ros':{'control_policy':{'age':.1,'value':{'source':'STOPPED','stop_latched':True}},
                   'cmd_vel':{'age':.1,'value':{'lin':0.,'ang':0.}}},
            'system':{'cpu_percent':'70.0','ram_percent':70,'temp':'59 C'}}
    return measured,status


class ResourceTests(unittest.TestCase):
    def test_cpu_accounting(self):
        self.assertEqual(cpu_delta({'cpu':(100,40),'cpu0':(100,40)},
                                   {'cpu':(200,65),'cpu0':(200,60)}),{'cpu':75.,'cpu0':80.})
        with self.assertRaises(ValueError):cpu_delta({'cpu':(100,40)},{'cpu':(100,40)})
        with self.assertRaises(ValueError):cpu_delta({'cpu':(100,40)},{'cpu':(200,65),'cpu1':(200,60)})
    def test_exact_boundaries_pass(self):
        m,s=fixture()
        for x in m['cpu_samples']:x['utilization_percent']['cpu']=75.
        m.update(ram_percent=80.,temperature_c=70.,free_disk_bytes=2*1024**3)
        self.assertTrue(decide(m,s,'preflight',False)['allowed'])
        self.assertEqual(LIMITS,{'cpu_percent':75.,'ram_percent':80.,'temperature_c':70.,'free_disk_bytes':2147483648})
    def test_spike_not_dismissed_by_later_low_sample(self):
        m,s=fixture();m['cpu_samples'][1]['utilization_percent']['cpu']=79.7
        d=decide(m,s,'postflight',True)
        self.assertFalse(d['allowed']);self.assertTrue(d['rollback_required'])
        self.assertIn('79.700000',d['reasons'][0]);self.assertEqual(d['measured'],m)
    def test_dashboard_guard_is_preserved(self):
        m,s=fixture();s['system']['cpu_percent']='79.7'
        self.assertFalse(decide(m,s,'preflight',False)['allowed'])
    def test_ram_temp_disk_nan_rejected(self):
        for key,value in (('ram_percent',80.01),('temperature_c',70.01),('free_disk_bytes',2147483647),('ram_percent',float('nan'))):
            m,s=fixture();m[key]=value
            self.assertFalse(decide(m,s,'preflight',False)['allowed'])
    def test_stale_safety_unlatched_and_command_refused(self):
        for mode in range(3):
            m,s=fixture()
            if mode==0:s['ros']['control_policy']['age']=3
            if mode==1:s['ros']['control_policy']['value']['stop_latched']=False
            if mode==2:s['ros']['cmd_vel']['value']['lin']=.1
            self.assertFalse(decide(m,s,'postflight',True)['allowed'])
    def test_missing_or_delayed_cpu_refused(self):
        for mode in range(3):
            m,s=fixture()
            if mode==0:m['cpu_samples'].pop()
            if mode==1:m['cpu_samples'][0]['duration_s']=3
            if mode==2:m['cpu_samples'][0]['utilization_percent']['cpu']=float('nan')
            self.assertFalse(decide(m,s,'preflight',False)['allowed'])
    def test_failure_is_logged_before_exception(self):
        m,s=fixture();m['cpu_samples'][0]['utilization_percent']['cpu']=76
        with tempfile.TemporaryDirectory() as temp:
            e=Evidence(Path(temp)/'evidence.jsonl',{'manifest':'fixture'})
            with self.assertRaises(AdmissionRefused) as caught:
                check(temp,'postflight',True,e.emit,sampler=lambda *a,**k:m,fetch=lambda:s)
            records=[json.loads(x) for x in e.path.read_text().splitlines()]
            self.assertEqual(records[-1]['decision']['measured']['cpu_samples'][0]['utilization_percent']['cpu'],76)
            self.assertTrue(records[-1]['decision']['rollback_required'])
            e.finish(caught.exception)
    def test_sensor_read_and_bad_response_errors_logged(self):
        m,s=fixture();events=[]
        def emit(name,**data):events.append(data)
        def broken(*a,**k):raise OSError('sensor unavailable')
        with self.assertRaises(AdmissionRefused):check('.', 'preflight',False,emit,sampler=broken)
        self.assertIn('sensor unavailable',events[-1]['decision']['reasons'][0])
        with self.assertRaises(AdmissionRefused):check('.', 'preflight',False,emit,sampler=lambda *a,**k:m,fetch=lambda:[])
        self.assertFalse(events[-1]['decision']['allowed'])


class TransactionResourceTests(unittest.TestCase):
    def setUp(self):
        self.helper=failure.FailureTests(methodName='test_missing_approval');self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
    def test_preflight_refusal_writes_nothing(self):
        def admission(phase,begun):
            self.assertEqual((phase,begun),('preflight',False));raise ValueError('resource refusal')
        with self.assertRaises(ValueError):self.helper.run_deploy(admission=admission)
        self.helper.unchanged();self.assertFalse((self.helper.root/'data/backups').exists())
    def test_postflight_refusal_rolls_back(self):
        seen=[]
        def admission(phase,begun):
            seen.append((phase,begun))
            if begun:raise ValueError('CPU interval0: 79.7 > 75')
        with self.assertRaisesRegex(ValueError,'79.7'):self.helper.run_deploy(admission=admission)
        self.assertEqual(seen,[('preflight',False),('postflight',True)])
        self.helper.unchanged();self.assertIn('unit_rollback_complete',[x[0] for x in self.helper.events])
    def test_success_both_phases_same_callable(self):
        seen=[]
        result=self.helper.run_deploy(admission=lambda phase,begun:seen.append((phase,begun)))
        self.assertEqual(seen,[('preflight',False),('postflight',True)]);self.assertFalse(result['activated'])
    def test_each_installation_phase_failure_restores_targets(self):
        cases=[('backup_create',1)]+[('payload_copy',i) for i in range(1,10)]+[
            ('unit_copy',1),('unit_registration',1),('resource_postflight',1)]
        for phase,occurrence in cases:
            with self.subTest(phase=phase,occurrence=occurrence):
                h=failure.FailureTests(methodName='test_missing_approval');h.setUp()
                count=0
                def event(step,**data):
                    nonlocal count
                    if step==phase:
                        count+=1
                        if count==occurrence:raise OSError('injected phase failure')
                try:
                    with self.assertRaises(OSError):h.run_deploy(event=event,admission=lambda *a:None)
                    h.unchanged()
                finally:h.doCleanups()

if __name__=='__main__':unittest.main()
