import unittest
from unittest.mock import Mock
from apply_parked_cpu_manual_fix import observe_startup


class StartupTests(unittest.TestCase):
    def setUp(self):self.now=0.;self.observations=[]
    def sleep(self,seconds):self.now+=seconds
    def call(self,check):
        return observe_startup(check,self.observations,clock=lambda:self.now,pause=self.sleep,seconds=2)
    def test_stale_then_fresh_only_observes_without_restarting(self):
        check=Mock(side_effect=[ValueError('stale stop/command'),{'policy':'fresh'}])
        self.assertEqual(self.call(check),{'policy':'fresh'})
        self.assertEqual(len(self.observations),2)
    def test_stale_forever_refuses_at_deadline(self):
        with self.assertRaisesRegex(ValueError,'stale'):
            self.call(Mock(side_effect=ValueError('stale stop/command')))
        self.assertEqual(self.now,2.)
    def test_unsafe_values_fail_immediately(self):
        for reason in ('latched stop required','zero commands required','manual-only required'):
            check=Mock(side_effect=ValueError(reason))
            with self.assertRaisesRegex(ValueError,reason):self.call(check)
            check.assert_called_once()
