import unittest
from stage20_public_preflight import validate

class PreflightTests(unittest.TestCase):
    def fixture(self):return {'ros':{'control_policy':{'age':.1,'value':{'source':'STOPPED','stop_latched':True}},
        'cmd_vel':{'age':.1,'value':{'lin':0.,'ang':0.}}},
        'system':{'cpu_percent':70,'ram_percent':70,'temp':'60 C'}}
    def test_parked(self):self.assertTrue(validate(self.fixture())['zero_command'])
    def test_fail_closed_for_diagnostic_not_control(self):
        for name in ('control_policy','cmd_vel'):
            s=self.fixture();s['ros'][name]['age']=10
            with self.assertRaises(ValueError):validate(s)
        s=self.fixture();s['ros']['cmd_vel']['value']['lin']=.1
        with self.assertRaises(ValueError):validate(s)
    def test_resources(self):
        for key,value in (('cpu_percent',90),('ram_percent',90),('temp','80 C')):
            s=self.fixture();s['system'][key]=value
            with self.assertRaises(ValueError):validate(s)
if __name__=='__main__':unittest.main()
