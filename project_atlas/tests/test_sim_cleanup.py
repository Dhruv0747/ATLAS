"""Offline: the simulation harness never leaves helper processes or open output pipes behind (no scenario is run)."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SIM = Path(__file__).resolve().parents[1] / 'tools/deploy/stage28_base_maintenance/sim/run_sim.py'


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:                                   # a zombie is not "alive" for our purposes
        return Path(f'/proc/{pid}/stat').read_text().split(') ')[1][0] != 'Z'
    except OSError:
        return False


class CleanupTests(unittest.TestCase):
    def run_mode(self, mode, kill=None, wrapper=()):
        d = Path(tempfile.mkdtemp())
        p = subprocess.Popen([*wrapper, sys.executable, str(SIM), '--cleanup-selftest', mode, str(d)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        line = p.stdout.readline()
        self.assertIn(b'READY', line)
        if kill:
            time.sleep(0.3)
            p.send_signal(kill)
        t0 = time.monotonic()
        out, _ = p.communicate(timeout=20)            # returns only at EOF: no process may hold the pipe
        eof_s = time.monotonic() - t0
        pids = json.loads((d / 'pids.json').read_text())
        time.sleep(0.2)
        still = [x for x in pids['children'] + [pids['grandchild']] if alive(x)]
        report = json.loads((d / 'cleanup.json').read_text())
        return p.returncode, eof_s, still, report, out

    def check(self, mode, rc_expected, reason_part, **kw):
        rc, eof_s, still, report, out = self.run_mode(mode, **kw)
        self.assertEqual(still, [], f'{mode}: processes left behind')
        self.assertLess(eof_s, 8.0, f'{mode}: output pipe held open')
        self.assertIn(reason_part, report['reason'])
        self.assertEqual(len(report['children']), 3)
        if rc_expected is not None:
            self.assertEqual(rc, rc_expected, out[-400:])

    def test_normal_exit(self):
        self.check('normal', 0, 'normal exit')

    def test_exception(self):
        self.check('exception', 1, 'RuntimeError')

    def test_sigterm(self):
        self.check('sigterm', 128 + signal.SIGTERM, 'SIGTERM', kill=signal.SIGTERM)

    def test_interrupt(self):
        self.check('sigint', 128 + signal.SIGINT, 'SIGINT', kill=signal.SIGINT)

    def test_outer_timeout(self):
        self.check('timeout', 124, 'SIGTERM', wrapper=('timeout', '2'))

    def test_only_spawn_creates_processes(self):
        src = SIM.read_text()
        self.assertEqual(src.count('subprocess.Popen('), 1)
        self.assertIn('start_new_session=True', src)
        self.assertIn('stdin=subprocess.DEVNULL', src)


if __name__ == '__main__':
    unittest.main()
