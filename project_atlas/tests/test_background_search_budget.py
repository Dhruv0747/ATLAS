import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('budget', Path(__file__).parents[1] / 'scripts/atlas_background_search_budget.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.wall = self.cpu = 0.0
        self.sleeps = []
        self.deadline = 30.0

    def check(self):
        if self.wall >= self.deadline:
            raise TimeoutError('original deadline')

    def sleep(self, amount):
        self.sleeps.append(amount)
        self.wall += amount

    def budget(self, **kwargs):
        return module.BackgroundSearchBudget(self.check, wall=lambda: self.wall,
            cpu=lambda: self.cpu, pause=self.sleep, **kwargs)

    def test_paces_only_consumed_worker_cpu(self):
        budget = self.budget()
        self.wall = self.cpu = .1
        budget()
        self.assertAlmostEqual(self.wall, 1.)
        self.assertTrue(all(x <= .05 for x in self.sleeps))
        self.assertEqual(self.cpu, .1)

    def test_no_sleep_when_already_idle(self):
        budget = self.budget()
        self.cpu, self.wall = .1, 1.
        budget()
        self.assertEqual(self.sleeps, [])

    def test_deadline_checked_during_wait(self):
        budget = self.budget()
        self.deadline = .2
        self.wall = self.cpu = .1
        with self.assertRaises(TimeoutError): budget()
        self.assertLessEqual(self.wall, .25)

    def test_expired_deadline_never_waits(self):
        budget = self.budget()
        self.wall = 31
        with self.assertRaises(TimeoutError): budget()
        self.assertEqual(self.sleeps, [])

    def test_repeated_work_retains_budget(self):
        budget = self.budget()
        for _ in range(10):
            self.wall += .01
            self.cpu += .01
            budget()
        self.assertAlmostEqual(self.wall, 1.)

    def test_invalid_fraction_rejected(self):
        for fraction in (0, -1, 1.1):
            with self.assertRaises(ValueError): self.budget(fraction=fraction)


if __name__ == '__main__': unittest.main()
