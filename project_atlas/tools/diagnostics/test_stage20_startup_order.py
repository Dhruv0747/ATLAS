import unittest
from stage20_startup_order import cycle,validate
class OrderingTests(unittest.TestCase):
    def test_existing_chain_with_optional_early_collector(self):
        self.assertFalse(cycle([('capture','base'),('base','ekf'),('capture','ekf'),('ekf','localization')]))
    def test_cycle_rejected(self):
        self.assertTrue(cycle([('capture','base'),('base','capture')]))
    def test_safety_requires_rejected(self):
        self.assertTrue(validate([], [('rover-base-telemetry.service','atlas-checkpoint-capture.service')])['safety_depends_on_collector'])
    def test_no_requirement_on_safety(self):
        self.assertFalse(validate([],[])['safety_depends_on_collector'])
if __name__=='__main__':unittest.main()
