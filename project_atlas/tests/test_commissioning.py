import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from atlas_commissioning import Console, configuration, distance_result, fresh, hardware_check, imu_result

class CommissioningTests(unittest.TestCase):
    def test_configuration_uses_driver_not_obsolete_yaml(self):
        c=configuration(SCRIPTS.parent)
        self.assertEqual(c['motor_locations'],['back_left','back_right','front_left','front_right'])
        self.assertEqual(c['steering']['front']['servo_id'],2)
        self.assertEqual(c['steering']['rear']['servo_id'],1)
        self.assertFalse(c['actuator_commissioning_enabled'])

    def test_empty_hardware_check_cannot_pass(self):
        r=hardware_check({})
        self.assertEqual(r['state'],'ATTENTION REQUIRED')
        self.assertTrue(all(c['state']=='FAIL' for c in r['checks']))

    def test_stale_disabled_is_not_current_inventory(self):
        r=hardware_check({'us_status':{'age':99,'value':'USTAT,F=DISABLED,L=DISABLED,R=DISABLED,B=DISABLED'}})
        self.assertTrue(all(c['state']=='FAIL' for c in r['checks'] if 'ultrasonic' in c['name']))

    def test_disabled_channels_not_pass(self):
        r=hardware_check({'us_status':{'age':.1,'value':'USTAT,F=ONLINE,L=DISABLED,R=DISABLED,B=ONLINE'}})
        self.assertEqual(sum(c['state']=='NOT TESTED' for c in r['checks']),2)

    def test_freshness_rejects_invalid_age(self):
        for a in (None,-1,float('nan'),100):
            self.assertFalse(fresh({'x':{'age':a}},'x'))

    def test_no_fix_not_pass(self):
        r=hardware_check({'gps_diagnostics':{'age':0,'value':json.dumps({'transport_open':True,'fix_valid':False})}})
        self.assertEqual(next(c['state'] for c in r['checks'] if c['name']=='GNSS'),'WARNING')

    def test_invalid_known_distance(self):
        for d in (0,True,'100',float('nan'),float('inf')):
            with self.assertRaises(ValueError):distance_result(d,[100,100,100])

    def test_distance_comparison_not_calibration(self):
        r=distance_result(1000,[1100,1100,1100,-1])
        self.assertEqual(r['state'],'OBSERVED')
        self.assertEqual(r['error_percent'],10)

    def test_insufficient_samples_fail(self):
        self.assertEqual(imu_result([])['state'],'FAIL')
        self.assertEqual(distance_result(100,[])['state'],'FAIL')

    def test_imu_noise_statistics_and_no_physical_pass(self):
        vals=[(i*.1,dict(gx=.01,gy=0.,gz=0.,ax=0.,ay=0.,az=9.81)) for i in range(100)]
        r=imu_result(vals)
        self.assertEqual(r['state'],'WARNING')
        self.assertAlmostEqual(r['statistics']['gx']['mean'],.01)
        self.assertEqual(r['statistics']['gz']['stddev'],0.)
        self.assertTrue(r['freshness_pass'])

    def test_history_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'results.db'
            a=Console(SCRIPTS.parent,path,lambda:{})
            a.save({'kind':'hardware','state':'WARNING'})
            b=Console(SCRIPTS.parent,path,lambda:{})
            self.assertEqual(len(b.history()),1)
            self.assertFalse(b.history()[0]['physical_calibration_pass'])

    def test_actuator_and_calibration_actions_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Console(SCRIPTS.parent,Path(folder)/'db',lambda:{})
            for action in ('motor','steering','camera','calibrate','restore','drive'):
                with self.assertRaises(ValueError):c.start(action)

    def test_no_hardware_import_or_ros_publisher_in_core(self):
        text=(SCRIPTS/'atlas_commissioning.py').read_text()
        for forbidden in ('import serial','Rosmaster(', 'create_publisher(', 'subprocess.', 'os.system('):
            self.assertNotIn(forbidden,text)

    def test_configuration_failure_does_not_kill_web(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Console(folder,Path(folder)/'db',lambda:{})
            self.assertIn('configuration_error',c.config)

if __name__=='__main__':unittest.main()
