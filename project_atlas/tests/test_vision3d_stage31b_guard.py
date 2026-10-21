"""Stage31b candidate guard: >=1 s CPU windows, unchanged 75/80/70 single-sample fail-closed decision.
Simulated worker runs with a fake clock (no camera, ROS, network or services)."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_vision3d_runtime as R   # noqa: E402

SRC = (ROOT / 'scripts/atlas_vision3d_runtime.py').read_text()


class Clock:
    def __init__(self): self.t = 5000.0
    def now(self): return self.t
    def sleep(self, s): self.t += max(0.0, s)


class Sim:
    """Drives R.worker('depth'). cpu(i, window) -> CPU % for guard sample i; ram/thermal likewise; lease every 0.2 s."""
    def __init__(self, cpu=lambda i, w: 65.0, ram=lambda i: 69.0, temp=lambda i: 60.0, snapshot_delay=lambda i: 0.0,
                 lease_eof_at=None, extra_safety=None, services_change_at=None):
        self.clock = Clock(); self.samples = []; self.i = 0
        self.cpu, self.ram, self.temp, self.delay = cpu, ram, temp, snapshot_delay
        self.lease_eof_at, self.extra, self.services_change_at = lease_eof_at, extra_safety, services_change_at
        self.next_lease = 0.0; self.launched_at = None

    def run(self,mode='depth'):
        clock = self.clock
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'rt'; runtime.mkdir(); files = []
            for k in range(458):
                (runtime / str(k)).write_bytes(b'x'); files.append({'path': str(k), 'sha256': hashlib.sha256(b'x').hexdigest()})
            (runtime / 'manifest.json').write_text(json.dumps({'files': files}))
            last = {'t': None}

            class AdmissionError(RuntimeError):
                def __init__(s, m, e): super().__init__(m); s.evidence = e

            def ticks(): return clock.now()
            def cpu_delta(a, b):
                w = b - a; v = self.cpu(self.i, w); self.samples.append({'i': self.i, 'window': w, 'cpu': v, 't': clock.now()}); return v
            def require_cpu(cpu):
                if cpu > 75: raise AdmissionError('CPU resource limit failed', {'cpu': cpu})
            def check(cpu, observation=None):
                require_cpu(cpu); row = {'ram_percent': self.ram(self.i), 'thermal_c': {'tj': self.temp(self.i)}, 'cpu_percent': cpu}; self.i += 1; return row
            def services():
                return {'changed': True} if self.services_change_at is not None and self.i >= self.services_change_at else {}
            gate = SimpleNamespace(ticks=ticks, cpu_delta=cpu_delta, require_cpu=require_cpu, check=check, services=services, AdmissionError=AdmissionError)
            def snapshot():
                clock.sleep(self.delay(self.i)); return {'ros': {}}
            def extra(ros=None):
                if self.extra: self.extra(self.i)
            probe = SimpleNamespace(safety_snapshot=snapshot, extra_safety=extra)

            def select(r, w, x, timeout):
                start = clock.now()
                if self.next_lease <= start + timeout:
                    clock.t = max(start, self.next_lease); self.next_lease = clock.now() + 0.2; return ([1], [], [])
                clock.sleep(timeout); return ([], [], [])
            def read(fd, n):
                if self.lease_eof_at is not None and self.launched_at is not None and clock.now() - self.launched_at >= self.lease_eof_at: return b''
                return b'1\n'
            child = MagicMock(pid=4242,returncode=None); child.poll.return_value = None
            def wait(timeout):
                child.returncode=-2;child.poll.return_value=-2;return -2
            child.wait.side_effect=wait
            def popen(*a, **k):
                self.launched_at = clock.now(); return child
            with patch.object(R, 'RUNTIME', runtime), patch.object(R, 'STATE', Path(tmp) / 'state.json'), \
                 patch.dict(sys.modules, {'stationary_gate': gate, 'stationary_ros_probe': probe}), \
                 patch.object(R.time, 'monotonic', side_effect=clock.now), patch.object(R.time, 'sleep', side_effect=clock.sleep), \
                 patch.object(R.signal, 'signal'), patch.object(R.subprocess, 'run', return_value=SimpleNamespace(returncode=1)), \
                 patch.object(R.subprocess, 'Popen', side_effect=popen), patch.object(R, 'domain_in_use', return_value=False), \
                 patch('select.select', side_effect=select), patch.object(R.os, 'read', side_effect=read), \
                 patch.object(R, 'process_metrics', return_value=({'pid': 1, 'rss_kib': 1, 'cpu_one_core_percent': 1.0}, (0, 0))), \
                 patch.object(R.os, 'killpg') as kill:
                R.worker(mode)
                self.state = json.loads((Path(tmp) / 'state.json').read_text()); self.killed = kill.call_args_list
        return self


class Window(unittest.TestCase):
    def test_window_rules(self):
        w = R.CpuWindow(100.0)
        self.assertFalse(w.due(100.99)); self.assertTrue(w.due(101.0))
        self.assertLessEqual(w.wait(100.0), 0.25); self.assertGreater(w.wait(100.999), 0)
        self.assertAlmostEqual(w.close(101.2), 1.2)
        with self.assertRaisesRegex(RuntimeError, 'shorter'): w.close(101.5)
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE BLOCKED.*failing closed'): w.close(103.8)

    def test_policy_values_unchanged(self):
        self.assertEqual((R.MIN_CPU_WINDOW_S, R.MAX_CPU_WINDOW_S), (1.0, 2.0))
        R.limits(75, 80, 70)
        for v in ((75.01, 50, 60), (50, 80.01, 60), (50, 50, 70.01)):
            with self.assertRaises(ValueError): R.limits(*v)
        gate = (ROOT / 'tools/vision3d/stationary_gate.py').read_bytes()
        self.assertEqual(hashlib.sha256(gate).hexdigest(), '0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9')   # deployed, unchanged


class GuardSimulation(unittest.TestCase):
    def test_concurrent_cpu_failure_during_start_has_ordered_cleanup(self):
        s=Sim(cpu=lambda i,w:78.4615 if i==3 else 70).run('concurrent')
        self.assertEqual(s.state['state'],'RESOURCE BLOCKED')
        self.assertTrue(s.state['driver_stopped'])
        names=[e['event'] for e in s.state['lifecycle']]
        self.assertLess(names.index('driver_spawned'),names.index('resource_guard_failed'))
        self.assertLess(names.index('resource_guard_failed'),names.index('signal_send'))
        self.assertEqual(s.state['failed_resources']['cpu'],78.4615)

    def test_full_session_samples_every_window_between_1_and_2_s(self):
        s = Sim().run()
        self.assertEqual(s.state['state'], 'OFF'); self.assertIn('session complete', s.state['reason'])
        w = [x['window'] for x in s.samples]
        self.assertGreaterEqual(min(w), 1.0); self.assertLessEqual(max(w), 1.3)
        self.assertGreaterEqual(len(s.samples), 55)            # guardian keeps sampling through the whole 60 s (>= ~1 Hz)
        launch = s.launched_at
        self.assertTrue(any(0 < x['t'] - launch <= 1.3 for x in s.samples), 'first post-launch sample within 1.3 s')
        self.assertEqual(s.killed[0].args, (4242, R.signal.SIGINT))   # camera stopped at session end

    def test_single_sample_over_75_during_streaming_blocks_and_stops_camera(self):
        s = Sim(cpu=lambda i, w: 75.2 if i == 20 else 66.0).run()
        self.assertEqual(s.state['state'], 'RESOURCE BLOCKED'); self.assertAlmostEqual(s.state['failed_resources']['cpu'], 75.2)
        self.assertEqual(s.samples[-1]['i'], 20); self.assertTrue(s.state['driver_stopped']); self.assertTrue(s.killed)

    def test_startup_sample_over_75_still_blocks(self):
        s = Sim(cpu=lambda i, w: 76.0 if i == 3 else 64.0).run()      # first post-launch sample (no grace period)
        self.assertEqual(s.state['state'], 'RESOURCE BLOCKED'); self.assertTrue(s.killed)

    def test_admission_failure_never_launches(self):
        s = Sim(cpu=lambda i, w: 80.0 if i == 1 else 64.0).run()
        self.assertEqual(s.state['state'], 'RESOURCE BLOCKED'); self.assertIsNone(s.launched_at)

    def test_ram_and_thermal_are_checked_every_window(self):
        for kw in ({'ram': lambda i: 80.5 if i >= 12 else 69}, {'temp': lambda i: 70.5 if i >= 12 else 60}):
            s = Sim(**kw).run()
            self.assertEqual(s.state['state'], 'RESOURCE BLOCKED', kw); self.assertEqual(len(s.samples), 13); self.assertTrue(s.killed)

    def test_policy_or_freshness_failure_stops(self):
        def stale(i):
            if i >= 9: raise RuntimeError('stale or missing control_policy')
        s = Sim(extra_safety=stale).run()
        self.assertEqual(s.state['state'], 'OFF'); self.assertIn('stale', s.state['reason']); self.assertTrue(s.killed)

    def test_stalled_guardian_fails_closed(self):
        s = Sim(snapshot_delay=lambda i: 2.5 if i == 15 else 0.0).run()   # a slow safety snapshot widens the next window
        self.assertEqual(s.state['state'], 'RESOURCE BLOCKED'); self.assertIn('failing closed', s.state['reason']); self.assertTrue(s.killed)

    def test_lease_eof_stops_camera(self):
        s = Sim(lease_eof_at=7.0).run()
        self.assertIn('paused or closed', s.state['reason']); self.assertTrue(s.killed)
        self.assertLess(s.clock.now() - s.launched_at, 7.0 + 0.5)

    def test_service_identity_change_stops(self):
        s = Sim(services_change_at=10).run()
        self.assertIn('service identity', s.state['reason']); self.assertTrue(s.killed)


class Independence(unittest.TestCase):
    def test_no_control_or_service_management_in_runtime(self):
        for bad in ('create_publisher', 'cmd_vel', 'e_stop', '/api/estop', 'systemctl', 'os.kill(', 'SIGSTOP', 'nice', 'cgroup'):
            self.assertNotIn(bad, SRC, bad)
        import re   # signals only ever go to the viewer's own camera child / own worker
        self.assertEqual(set(re.findall(r'os\.killpg\(([a-z_.]+)', SRC)), {'child.pid'})   # helper argument only
        self.assertIn("(('cloud',cloud_child),('driver',child))",SRC)
        self.assertIn('shutdown_owned_process(owned,state,role)',SRC)
        self.assertEqual(set(re.findall(r'([a-z_.]+)\.(?:kill|terminate)\(\)', SRC)), {'child'})


if __name__ == '__main__':
    unittest.main()
