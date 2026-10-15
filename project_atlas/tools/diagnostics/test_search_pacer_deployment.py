import unittest
from unittest.mock import Mock
from apply_background_search_budget import observe_ready


class ReadyTests(unittest.TestCase):
    def setUp(self): self.now = 0.
    def pause(self, duration): self.now += duration
    def call(self, check):
        return observe_ready(check, clock=lambda: self.now, pause=self.pause, seconds=2)
    def test_timeout_then_fresh(self):
        check = Mock(side_effect=[TimeoutError('HTTP timeout'), {'safe': True}])
        self.assertEqual(self.call(check), {'safe': True})
        self.assertEqual(check.call_count, 2)
    def test_stale_then_fresh(self):
        self.assertEqual(self.call(Mock(side_effect=[ValueError('stale stop/command'), 1])), 1)
    def test_unsafe_not_retried(self):
        check = Mock(side_effect=ValueError('latched stop required'))
        with self.assertRaises(ValueError): self.call(check)
        self.assertEqual(check.call_count, 1)
    def test_timeout_remains_failure(self):
        with self.assertRaises(TimeoutError): self.call(Mock(side_effect=TimeoutError()))
        self.assertEqual(self.now, 2.)


if __name__ == '__main__': unittest.main()
