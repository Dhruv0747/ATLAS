import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/'tools/diagnostics/analyze_tagged_cpu_capture.py'
spec = importlib.util.spec_from_file_location('tagged_cpu', path)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def event(t, ticks, phase='baseline', birth=3):
    return dict(monotonic=t, phase=phase, cpu=60, observer_cpu_s=t*.01,
                threads={'7': dict(ticks=ticks, birth=birth)})


class TaggedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'shared': {'frames': [dict(name='_wait_for_ready_callbacks',
                            file='/opt/rclpy/executors.py', line=678)]},
                        'profiles': [dict(name='Thread 0xAB', type='sampled', unit='seconds',
                                          samples=[[0], [0]], weights=[.05, .05])]}

    def test_cpu_uses_ticks_not_sample_weights(self):
        out = M.analyze(self.profile, [event(1, 100), event(3, 150)])
        self.assertEqual(out['windows']['baseline']['threads']['7']['one_core_percent'], 25)
        self.assertIn('UNAVAILABLE', out['native_tid_mapping'])

    def test_wait_mapping_requires_exact_source(self):
        for sha, expected in [(None, 0), ('wrong', 0), (M.EXECUTOR_SHA, 100)]:
            out = M.analyze(self.profile, [], executor_sha=sha)
            self.assertEqual(out['python_profiles'][0]['wait_boundary_observation_percent'], expected)

    def test_pid_reuse_and_missing_thread_are_excluded(self):
        out = M.analyze(self.profile, [event(1, 100), event(2, 900, birth=4)])
        self.assertEqual(out['windows']['baseline']['threads'], {})

    def test_phase_boundaries_not_mixed(self):
        rows = [event(1, 100), event(2, 120), event(3, 500, 'profile'), event(4, 530, 'profile')]
        out = M.analyze(self.profile, rows)
        self.assertEqual(out['windows']['profile']['threads']['7']['one_core_percent'], 30)

    def test_bad_time_rejected(self):
        with self.assertRaises(ValueError):
            M.analyze(self.profile, [event(1, 100), event(1, 120)])

    def test_bad_weights_rejected(self):
        self.profile['profiles'][0]['weights'] = [float('nan'), .05]
        with self.assertRaises(ValueError):
            M.analyze(self.profile, [])

    def test_health_only_rows_do_not_corrupt_intervals(self):
        out = M.analyze(self.profile, [event(1, 100), {'health': {}}, event(2, 120)])
        self.assertAlmostEqual(out['windows']['baseline']['observer_one_core_percent'], 1)

    def test_invalid_cpu_rejected(self):
        row = event(2, 120)
        row['cpu'] = float('nan')
        with self.assertRaises(ValueError):
            M.analyze(self.profile, [event(1, 100), row])
