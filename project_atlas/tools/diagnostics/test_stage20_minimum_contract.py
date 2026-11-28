from pathlib import Path
import unittest
from stage20_minimum_contract import verify_unit,partial_status

class MinimumTests(unittest.TestCase):
    def setUp(self):
        self.text=Path(__file__).with_name('stage20_public_capture.service.in').read_text()
    def test_no_startup_or_safety_dependency(self):
        self.assertEqual(verify_unit(self.text,{'atlas-ekf.service':{'After':['basic.target']}})['startup_blocking_edges'],[])
    def test_live_reverse_dependency_rejected(self):
        with self.assertRaises(ValueError):verify_unit(self.text,{'atlas-remote.service':{'Requires':['atlas-stage20-public-capture.service']}})
    def test_delay_and_autostart_rejected(self):
        for text in (self.text.replace('Before=shutdown.target','Before=atlas-ekf.service'),
                     self.text+'\n[Install]\nWantedBy=default.target\n'):
            with self.assertRaises(ValueError):verify_unit(text,{})
    def test_limits_mandatory(self):
        with self.assertRaises(ValueError):verify_unit(self.text.replace('MemoryMax=192M','MemoryMax=infinity'),{})
    def test_partial_not_checkpoint(self):
        result=partial_status({'/scan':10},['/scan','/odom'])
        self.assertEqual(result['missing_required_topics'],['/odom'])
        self.assertFalse(result['replay_fidelity_verified'])
if __name__=='__main__':unittest.main()
