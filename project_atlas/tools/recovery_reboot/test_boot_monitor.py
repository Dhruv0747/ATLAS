"""Focused offline tests for boot_monitor.py (fake /proc and /sys tree; no systemd, ROS or Jetson)."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class Fake:
    """Advances a fake /proc tree by one second per sleep()."""
    def __init__(self, root, cpu, recovery_from=None, restarts_at=None, failed_at=None, ram=60.0, temp=60.0, usage0=0):
        self.root, self.cpu, self.i, self.usage0 = root, cpu, 0, usage0
        self.recovery_from, self.restarts_at, self.failed_at = recovery_from, restarts_at, failed_at
        self.total = self.busy = 0
        self.ram, self.temp = ram, temp
        cg = root / 'sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/atlas-sensor-recovery.service'
        cg.mkdir(parents=True)
        self.cg = cg
        (root / 'proc/sys/kernel/random').mkdir(parents=True)
        (root / 'proc/sys/kernel/random/boot_id').write_text('abcdef12-0000\n')
        (root / 'sys/class/thermal/thermal_zone0').mkdir(parents=True)
        self.write()

    def write(self):
        r = self.root
        idle = self.total - self.busy
        (r / 'proc/stat').write_text(f'cpu  {self.busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 2\n')
        total_kb = 8000000
        (r / 'proc/meminfo').write_text(f'MemTotal: {total_kb} kB\nMemAvailable: {int(total_kb * (1 - self.ram / 100))} kB\n')
        (r / 'sys/class/thermal/thermal_zone0/temp').write_text(str(int(self.temp * 1000)))
        (r / 'proc/uptime').write_text(f'{10 + self.i}.00 0\n')
        present = self.recovery_from is not None and self.i >= self.recovery_from
        (self.cg / 'cgroup.procs').write_text('4242\n' if present else '')
        (self.cg / 'cpu.stat').write_text(f'usage_usec {self.usage0 + self.i * 1000}\n')

    def sleep(self, _):
        pct = self.cpu[min(self.i, len(self.cpu) - 1)]
        self.total += 600
        self.busy += int(round(600 * pct / 100))
        self.i += 1
        self.write()

    def show(self):
        failed = self.failed_at is not None and self.i >= self.failed_at
        restarted = self.restarts_at is not None and self.i >= self.restarts_at
        return {'ActiveState': 'failed' if failed else 'active', 'NRestarts': '1' if restarted else '0', 'MainPID': '4242'}


class BootMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / 'home'
        self.pkg = self.home / 'project-atlas-migration/recovery-reboot-4af4ddad'
        self.pkg.mkdir(parents=True)
        shutil.copy(HERE / 'boot_monitor.py', self.pkg / 'boot_monitor.py')
        (self.home / 'project_atlas/scripts').mkdir(parents=True)
        self.live, self.cand = b'original-bytes\n', b'candidate-bytes\n'
        os.environ['ATLAS_BOOT_ROOT'] = str(self.tmp / 'root')
        os.environ['HOME'] = str(self.home)
        sys.path.insert(0, str(self.pkg))
        sys.modules.pop('boot_monitor', None)
        self.m = importlib.import_module('boot_monitor')
        self.m.LIVE = hashlib.sha256(self.live).hexdigest()
        self.m.CAND = hashlib.sha256(self.cand).hexdigest()
        self.m.EVAL_S = 5.0
        (self.pkg / 'atlas_sensor_recovery.rollback.py').write_bytes(self.live)
        self.target = self.home / 'project_atlas/scripts/atlas_sensor_recovery.py'

    def tearDown(self):
        sys.path.remove(str(self.pkg))
        shutil.rmtree(self.tmp)

    def run_n(self, mode, script, n, **kw):
        """Drive exactly n one-second samples with a fake monotonic clock."""
        self.target.write_bytes(script)
        if mode:
            (self.pkg / 'ARMED').write_text(mode + '\n')
        fake, calls, orig = Fake(self.tmp / 'root', **kw), {'n': 0}, self.m.time.monotonic

        def sleep(x):
            calls['n'] += 1
            fake.sleep(x)
        self.m.time.monotonic = lambda: float(calls['n'])
        try:
            return self.m.run(show=fake.show, sleep=sleep, duration=float(n)), fake
        finally:
            self.m.time.monotonic = orig

    def test_not_armed_does_nothing_and_arming_is_one_shot(self):
        self.assertIsNone(self.m.run(show=lambda: {}, sleep=lambda _: None, duration=0))
        s, _ = self.run_n('baseline', self.live, 10, cpu=[60] * 10, recovery_from=2)
        self.assertEqual(s['verdict'], 'PASS')
        self.assertFalse((self.pkg / 'ARMED').exists())
        self.assertTrue((self.pkg / 'ARMED.consumed').exists())
        self.assertIsNone(self.m.run(show=lambda: {}, sleep=lambda _: None, duration=0))

    def test_cpu_breach_after_recovery_start_fails_unchanged_limit(self):
        s, _ = self.run_n('baseline', self.live, 10, cpu=[60, 60, 60, 75, 60, 60, 60, 60, 60, 60], recovery_from=2)
        self.assertEqual(s['verdict'], 'FAIL')
        self.assertEqual(len(s['breaches_in_eval_window']), 1)
        self.assertAlmostEqual(s['breaches_in_eval_window'][0]['cpu'], 75.0)   # exactly 75 is a breach

    def test_ram_and_temperature_limits(self):
        self.assertEqual(self.run_n('baseline', self.live, 10, cpu=[50] * 10, recovery_from=2, ram=80.0)[0]['verdict'], 'FAIL')
        self.tearDown(); self.setUp()
        self.assertEqual(self.run_n('baseline', self.live, 10, cpu=[50] * 10, recovery_from=2, temp=70.0)[0]['verdict'], 'FAIL')

    def test_pre_recovery_peak_reported_and_start_window_must_be_observed(self):
        s, _ = self.run_n('baseline', self.live, 10, cpu=[95, 50, 50, 50, 50, 50, 50, 50, 50, 50], recovery_from=3)
        self.assertGreaterEqual(s['pre_recovery_peak_cpu'], 95)
        self.assertEqual(s['verdict'], 'PASS')
        self.tearDown(); self.setUp()
        # Forked just before sampling began (normal Before= ordering): observed when <= 50 ms CPU used.
        s, _ = self.run_n('baseline', self.live, 10, cpu=[50] * 10, recovery_from=0, usage0=40000)
        self.assertTrue(s['start_window_observed'])
        self.assertEqual(s['verdict'], 'PASS')
        self.tearDown(); self.setUp()
        s, _ = self.run_n('baseline', self.live, 10, cpu=[50] * 10, recovery_from=0, usage0=60000)  # startup partly missed
        self.assertFalse(s['start_window_observed'])
        self.assertEqual(s['verdict'], 'FAIL')

    def test_incomplete_eval_window_fails(self):
        s, _ = self.run_n('baseline', self.live, 5, cpu=[50] * 5, recovery_from=2)
        self.assertFalse(s['eval_window_complete'])
        self.assertEqual(s['verdict'], 'FAIL')

    def test_candidate_restart_restores_exact_original_once(self):
        s, _ = self.run_n('candidate', self.cand, 10, cpu=[50] * 10, recovery_from=2, restarts_at=4)
        self.assertEqual(self.target.read_bytes(), self.live)
        self.assertEqual(oct(self.target.stat().st_mode & 0o777), '0o644')
        self.assertEqual(self.target.stat().st_mtime_ns, self.m.MTIME_NS)
        self.assertEqual(s['actions'], ['fail-closed:restored'])
        self.assertEqual(s['verdict'], 'FAIL')

    def test_candidate_cpu_breach_restores_original_without_service_action(self):
        s, _ = self.run_n('candidate', self.cand, 10, cpu=[60, 60, 60, 80, 60, 60, 60, 60, 60, 60], recovery_from=2)
        self.assertEqual(s['verdict'], 'FAIL')
        self.assertEqual(s['actions'], ['fail-closed:restored'])
        self.assertEqual(self.target.read_bytes(), self.live)

    def test_candidate_pass_keeps_candidate(self):
        s, _ = self.run_n('candidate', self.cand, 10, cpu=[60] * 10, recovery_from=2)
        self.assertEqual((s['verdict'], s['actions']), ('PASS', []))
        self.assertEqual(self.target.read_bytes(), self.cand)

    def test_candidate_failed_state_and_unknown_bytes_refused(self):
        s, _ = self.run_n('candidate', b'someone-else\n', 10, cpu=[50] * 10, recovery_from=2, failed_at=4)
        self.assertEqual(s['actions'], ['fail-closed:refused-unknown-bytes'])
        self.assertEqual(self.target.read_bytes(), b'someone-else\n')

    def test_baseline_mode_never_touches_script(self):
        s, _ = self.run_n('baseline', self.cand, 10, cpu=[50] * 10, recovery_from=2, restarts_at=4)
        self.assertEqual(self.target.read_bytes(), self.cand)
        self.assertEqual(s['actions'], [])
        self.assertEqual(s['verdict'], 'FAIL')

    def test_systemctl_timeout_is_recorded_not_fatal_and_never_triggers_restore(self):
        import subprocess
        fake_show, n = None, {'i': 0}
        def flaky():
            n['i'] += 1
            if n['i'] in (3, 4):
                raise subprocess.TimeoutExpired('systemctl', 2)
            return fake_show()
        self.target.write_bytes(self.cand)
        (self.pkg / 'ARMED').write_text('candidate\n')
        fake, calls, orig = Fake(self.tmp / 'root', cpu=[60] * 10, recovery_from=2), {'n': 0}, self.m.time.monotonic
        fake_show = fake.show
        def sleep(x):
            calls['n'] += 1
            fake.sleep(x)
        self.m.time.monotonic = lambda: float(calls['n'])
        try:
            s = self.m.run(show=flaky, sleep=sleep, duration=10.0)
        finally:
            self.m.time.monotonic = orig
        rows = [json.loads(l) for l in (self.home / 'project-atlas-migration/boot-evidence-abcdef12/samples.jsonl').read_text().splitlines()]
        self.assertEqual([r['show_error'] for r in rows].count('TimeoutExpired'), 2)
        self.assertEqual((s['verdict'], s['actions']), ('PASS', []))
        self.assertEqual(self.target.read_bytes(), self.cand)

    def test_evidence_written_per_boot(self):
        self.run_n('baseline', self.live, 10, cpu=[50] * 10, recovery_from=2)
        out = self.home / 'project-atlas-migration/boot-evidence-abcdef12'
        rows = [json.loads(l) for l in (out / 'samples.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows), 10)
        self.assertEqual(json.loads((out / 'summary.json').read_text())['boot_id'], 'abcdef12-0000')

    def test_monitor_issues_no_service_control(self):
        src = (HERE / 'boot_monitor.py').read_text()
        for word in ("'start'", "'stop'", "'restart'", 'daemon-reload', "'reboot'", 'kill('):
            self.assertNotIn(word, src)


if __name__ == '__main__':
    unittest.main()
