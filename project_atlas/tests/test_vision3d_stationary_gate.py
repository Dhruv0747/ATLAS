"""Offline guard arithmetic/policy tests. Never executes a build or contacts ATLAS."""
import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import stationary_gate as G


def good():
    return {'control_policy':{'age':.1,'value':{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'}},
            'cmd_vel':{'age':.1,'value':{'lin':0.,'ang':0.}}}


class StationaryGate(unittest.TestCase):
    def test_stopped(self):self.assertTrue(G.validate_policy(good())['stop_latched'])
    def test_stop_released(self):
        r=good();r['control_policy']['value']['stop_latched']=False
        with self.assertRaises(RuntimeError):G.validate_policy(r)
    def test_manual_only_required(self):
        r=good();r['control_policy']['value']['manual_only']=False
        with self.assertRaises(RuntimeError):G.validate_policy(r)
    def test_commission_disarmed_required(self):
        r=good();r['control_policy']['value']['commission_armed']=True
        with self.assertRaises(RuntimeError):G.validate_policy(r)
    def test_nonzero_command(self):
        r=good();r['cmd_vel']['value']['lin']=.01
        with self.assertRaises(RuntimeError):G.validate_policy(r)
    def test_nan_command(self):
        r=good();r['cmd_vel']['value']['ang']=math.nan
        with self.assertRaises(RuntimeError):G.validate_policy(r)
    def test_stale_command(self):
        r=good();r['cmd_vel']['age']=3
        with self.assertRaises(RuntimeError):G.validate_policy(r)
    def test_missing_policy(self):
        with self.assertRaises(RuntimeError):G.validate_policy({})
    def test_cpu_valid(self):self.assertEqual(G.cpu_delta((100,40),(200,80)),60)
    def test_cpu_zero_interval(self):
        with self.assertRaises(RuntimeError):G.cpu_delta((100,40),(100,40))
    def test_cpu_impossible_idle(self):
        with self.assertRaises(RuntimeError):G.cpu_delta((100,40),(200,150))
    def test_error_preserves_failed_sample(self):
        e=G.AdmissionError('failed',{'cpu':75.88});self.assertEqual(e.evidence['cpu'],75.88)
    def test_supervisor_no_implicit_retry_or_camera(self):
        s=(Path(G.__file__).parent/'supervise_build.py').read_text(encoding='utf8')
        self.assertIn('no automatic repeat',s);self.assertIn('systemctl',s);self.assertNotIn('VideoCapture',s)
    def test_build_has_no_global_installer(self):
        s=(Path(G.__file__).parent/'build_isolated.sh').read_text(encoding='utf8')
        self.assertNotIn('sudo ',s);self.assertNotIn('apt-get install',s);self.assertIn('set +u',s)


if __name__=='__main__':unittest.main()
