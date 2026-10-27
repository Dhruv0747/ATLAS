"""Offline: the complete Stage 28 DDS storm rehearsal procedure (real supervisor + real probe under a stub rclpy,
fake foxglove bridge, scripted CPU/RAM gates, optional real CPU load). No ROS, no Jetson."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage28_base_maintenance'
STUB = PKG / 'sim/stub_ros'
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage28_storm_rehearsal as R  # noqa: E402
import atlas_safety_observer as so  # noqa: E402
from test_safety_observer import Rig  # noqa: E402

R.HOLD_S = 2.0                       # shorter hold keeps the offline suite fast; limits/logic unchanged
SPIKE = [(0.0, 64.0), (2.0, 99.5), (7.0, 66.0)]   # (seconds after spawn, CPU %) shaped like Stage A


def status(n, latched=True, cmd=0.0):
    ros = {
        'control_policy': {'age': 0.1, 'value': json.dumps({'stop_latched': latched, 'manual_only': True,
                                                             'commission_armed': False, 'source': 'STOPPED'})},
        'cmd_vel': {'age': 0.1, 'value': {'lin': cmd, 'ang': 0.0}},
        'motor_speed': {'age': 0.2, 'value': 0.0}, 'web_drive': {'age': 0.1, 'value': 'STOP'},
        'drive_pid': {'age': 0.1, 'value': json.dumps({'active': False})},
        'odom': {'age': 0.1, 'value': {'vx': 0.0, 'wz': 0.0}},
        **{f'enc_m{i}': {'age': 0.0, 'value': v} for i, v in zip(range(1, 5), (-11, 28, -40, 9))},
        'encoder_health': {'age': 0.0, 'value': json.dumps({'state': 'READY', 'packet_fresh': True, 'packet_age_s': 0.02,
                                                             'serial_encoder_packets': n})}}
    return {'ros': ros}


class OfflineEnv(R.RehearsalEnv):
    def __init__(self, rig, tmp, cpu_profile=SPIKE, ram_profile=None, probe_env=None, inject=None, **kw):
        super().__init__(evidence_root=Path(tmp) / 'ev', preflight_s=3, steady_s=5, observer_warmup_s=1.0,
                         protected=['svc-a.service'], **kw)
        self.rig, self.tmp = rig, Path(tmp)
        self.cpu_profile, self.ram_profile, self.probe_env = cpu_profile, ram_profile or [(0.0, 60.0)], probe_env or {}
        self.t_spawn = None
        self.inject = inject                      # (seconds after probe spawn, fake-bridge control dict)
        self.n = 0
        self.shm_dir = self.tmp / 'shm'
        self.shm_dir.mkdir(exist_ok=True)
        self.mains = {'rover-base-telemetry.service': rig.base.pid, 'atlas-sensor-recovery.service': 4242,
                      'svc-a.service': 4343}

    # system access
    def systemctl(self, *args, timeout=30, check=True):
        if args[0] == 'show':
            out = f'ActiveState=active\nSubState=running\nMainPID={self.mains.get(args[1], 1)}\nNRestarts=0\nInvocationID=x\n'
        else:
            out = ''
        return subprocess.CompletedProcess(args, 0, out, '')

    def get(self, path):
        if path == '/api/estop/state':
            return {'latched': True}
        self.n += 1
        return status(self.n)

    def make_observer(self, base_pid):
        return so.SafetyObserver(port=self.rig.port, base_pid=base_pid, odom_path=self.rig.odom)

    def _at(self, profile):
        if self.t_spawn is None:
            return profile[0][1]
        d = time.time() - self.t_spawn
        return [v for t, v in profile if d >= t][-1]

    def cpu_samples(self, n):
        out = []
        for _ in range(n):
            time.sleep(1.0)
            out.append(self._at(self.cpu_profile))
        return out

    def ram_temp(self):
        return self._at(self.ram_profile), {'cpu-thermal': 64.0}

    def spawn_probe(self, hb, report, log):
        self.t_spawn = time.time()
        if self.inject:
            delay, ctl = self.inject
            threading.Timer(delay, lambda: self.rig.set(**ctl)).start()
        env = dict(os.environ, PYTHONPATH=str(STUB), FASTDDS_BUILTIN_TRANSPORTS='UDPv4', **self.probe_env)
        with open(log, 'ab') as out:
            return subprocess.Popen([sys.executable, str(R.PROBE), '--hold-s', str(R.HOLD_S), '--hard-s', '14',
                                     '--heartbeat', str(hb), '--report', str(report)],
                                    stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True, env=env)

    def shm_segments(self):
        return set(os.listdir(self.shm_dir))

    def lease_present(self):
        return False


def busy_load(n, seconds):
    code = f'import time\nend=time.time()+{seconds}\nwhile time.time()<end: pass\n'
    return [subprocess.Popen([sys.executable, '-c', code]) for _ in range(n)]


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.tmp = tempfile.mkdtemp()
        os.environ['OWNER_APPROVED'] = 'yes'

    def tearDown(self):
        self.rig.close()
        left = [p for p in R.RehearsalEnv().probe_processes()]
        for p in left:
            os.kill(p, signal.SIGKILL)
        self.assertEqual(left, [], 'probe processes left behind')

    def run_r(self, args, **kw):
        env = OfflineEnv(self.rig, self.tmp, **kw)
        rc = R.main(args, env=env)
        ev = sorted((Path(self.tmp) / 'ev').glob('stage28-storm-rehearsal-*'))[-1]
        res = json.loads(sorted(ev.glob('*-result.json'))[-1].read_text())
        return rc, res, ev, env

    def assert_clean(self, res):
        self.assertTrue(res['cleanup']['ok'], res['cleanup'])

    def test_pass_with_bounded_spike_and_real_load(self):
        load = busy_load(2 * os.cpu_count(), 25)              # real CPU contention while the observer runs
        try:
            rc, res, ev, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'])
        finally:
            for p in load:
                p.kill()
                p.wait()
        self.assertEqual((rc, res['result']), (0, 'PASS'), res)
        self.assertEqual(res['probe_report']['inventory']['endpoint_count'], 32)
        self.assertTrue(res['probe_report']['inventory_ok'])
        self.assertEqual(res['observer_summary']['not_ok'], 0)
        self.assertLessEqual(res['observer_summary']['max_gap_s'], 1.0)
        self.assert_clean(res)
        rep = json.loads(next(ev.glob('*-resources-R-post-transient.json')).read_text())
        self.assertGreater(len(rep['over_limit_inside_bound']), 0)        # spike recorded, not hidden

    def test_unjudged_pre_window_sample_refuses(self):
        """A >75 % sample while the observer subscribes/warms up (before any probe) -> refused, no probe."""
        prof = [(0.0, 64.0)]
        env = OfflineEnv(self.rig, self.tmp, cpu_profile=prof)
        calls = {'n': 0}
        real = env.cpu_samples

        def samples(n):
            calls['n'] += 1
            out = real(n)
            return [76.0] if calls['n'] == 2 else out            # 2nd call = first recorder sample, before the spawn
        env.cpu_samples = samples
        spawned = []
        env.spawn_probe = lambda *a: spawned.append(a)
        rc = R.main(['--cpu-rule', 'transient', '--transient-bound-s', '10'], env=env)
        ev = sorted((Path(self.tmp) / 'ev').glob('stage28-storm-rehearsal-*'))[-1]
        res = json.loads(sorted(ev.glob('*-result.json'))[-1].read_text())
        self.assertEqual((rc, res['result']), (3, 'REFUSED_NO_CHANGE'), res)
        self.assertIn('pre-window not clean', res['error'])
        self.assertEqual(spawned, [])

    def test_mild_storm_is_inconclusive_not_pass(self):
        rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                   cpu_profile=[(0.0, 64.0), (2.0, 74.0), (5.0, 66.0)])
        self.assertEqual((rc, res['result']), (1, 'INCONCLUSIVE'), res)
        self.assert_clean(res)

    def test_strict_rule_aborts_on_spike(self):
        rc, res, _, _ = self.run_r(['--cpu-rule', 'strict'])
        self.assertEqual(res['result'], 'FAIL')
        self.assertIn('IMMEDIATE ABORT', res['error'])
        self.assert_clean(res)

    def test_cpu_after_bound_aborts(self):
        rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '3'])
        self.assertIn('after the 3.0 s bound', res['error'])
        self.assert_clean(res)

    def test_ram_violation_aborts(self):
        rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                   ram_profile=[(0.0, 60.0), (1.5, 80.5)])
        self.assertIn('RAM/temperature', res['error'])
        self.assert_clean(res)

    def test_motor_speed_stale_aborts_and_kills_probe(self):
        rc, res, ev, env = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                      inject=(1.5, {'stall': ['/motor_speed']}))
        self.assertEqual(res['result'], 'FAIL')
        self.assertIn('motor_output_zero', res['error'])
        ab = json.loads(next(ev.glob('*-abort-R.json')).read_text())
        self.assertTrue(ab['reasons'])
        self.assert_clean(res)

    def test_estop_release_aborts(self):
        rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                   inject=(1.5, {'stop_latched': False}))
        self.assertIn('estop_latched', res['error'])
        self.assert_clean(res)

    def test_probe_hang_is_killed_at_limit(self):
        old = R.MAX_TEST_S
        R.MAX_TEST_S = 4.0
        try:
            rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                       probe_env={'STUB_HANG_NODE': '1'})
        finally:
            R.MAX_TEST_S = old
        self.assertIn('still alive', res['error'])
        self.assert_clean(res)

    def test_inventory_mismatch_fails(self):
        rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                   probe_env={'STUB_CLIENT': '1'})
        self.assertEqual(res['result'], 'FAIL')
        self.assertFalse(res['probe_report']['inventory_ok'])
        self.assert_clean(res)

    def test_shm_leak_detected(self):
        shm = Path(self.tmp) / 'shm'
        rc, res, _, _ = self.run_r(['--cpu-rule', 'transient', '--transient-bound-s', '10'],
                                   probe_env={'STUB_LEAK_SHM': str(shm)})
        self.assertEqual(res['result'], 'FAIL')
        self.assertTrue(res['cleanup']['new_shm_segments'])

    def test_refusals_before_any_probe(self):
        os.environ.pop('OWNER_APPROVED')
        self.assertEqual(R.main(['--cpu-rule', 'strict'], env=OfflineEnv(self.rig, self.tmp)), 2)
        os.environ['OWNER_APPROVED'] = 'yes'
        for args in (['--cpu-rule', 'transient'], ['--cpu-rule', 'transient', '--transient-bound-s', '12'],
                     ['--cpu-rule', 'strict', '--transient-bound-s', '5']):
            self.assertEqual(R.main(args, env=OfflineEnv(self.rig, self.tmp)), 2)
        env = OfflineEnv(self.rig, self.tmp)
        env.lease_present = lambda: True
        self.assertEqual(R.main(['--cpu-rule', 'strict'], env=env), 3)
        env = OfflineEnv(self.rig, self.tmp)
        env.probe_processes = lambda: [12345]
        self.assertEqual(R.main(['--cpu-rule', 'strict'], env=env), 3)


class EvidenceSurvivalTests(unittest.TestCase):
    def test_streamed_evidence_survives_sigkill_of_supervisor(self):
        """The recorder streams every sample to disk at once: a supervisor killed mid-spike keeps its evidence."""
        d = Path(tempfile.mkdtemp())
        code = (f'import sys,os,signal,time\nsys.path.insert(0,{str(PKG)!r})\nimport deploy_rc_bridge as D\n'
                f'env=D.Env(evidence_root=__import__("pathlib").Path({str(d)!r}),thermal_root={str(d)!r})\n'
                f'env.ram_temp=lambda:(60.0,{{"cpu-thermal":64.0}})\n'
                f'ev=D.Evidence(env,"kill-test")\nr=D.CpuRecorder(env,ev.stream("cpu")).__enter__()\n'
                f'time.sleep(3.6)\nos.kill(os.getpid(),signal.SIGKILL)\n')
        p = subprocess.run([sys.executable, '-c', code], timeout=30)
        self.assertEqual(p.returncode, -signal.SIGKILL)
        lines = next(d.glob('stage28-kill-test-*/stream-cpu.jsonl')).read_text().splitlines()
        rows = [json.loads(x) for x in lines]
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all({'wall', 'cpu', 'ram', 'temp_max'} <= set(r) for r in rows))


class ProbeFailSafeTests(unittest.TestCase):
    def probe(self, hb, extra_env=None, hard='14', hold='5'):
        d = Path(tempfile.mkdtemp())
        env = dict(os.environ, PYTHONPATH=str(STUB), **(extra_env or {}))
        return subprocess.Popen([sys.executable, str(R.PROBE), '--hold-s', hold, '--hard-s', hard,
                                 '--heartbeat', str(hb), '--report', str(d / 'r.json')], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True), d

    def test_refuses_without_live_supervisor(self):
        hb = Path(tempfile.mkdtemp()) / 'hb'
        p, _ = self.probe(hb)
        self.assertNotEqual(p.wait(timeout=10), 0)
        hb.touch()
        os.utime(hb, (time.time() - 5, time.time() - 5))
        p, _ = self.probe(hb)
        self.assertNotEqual(p.wait(timeout=10), 0)

    def test_exits_when_supervisor_heartbeat_stops(self):
        hb = Path(tempfile.mkdtemp()) / 'hb'
        hb.touch()
        p, d = self.probe(hb)
        time.sleep(0.6)
        os.utime(hb)                                     # last beat, then silence
        t0 = time.time()
        p.wait(timeout=10)
        self.assertLess(time.time() - t0, 2.0)
        self.assertEqual(json.loads((d / 'r.json').read_text())['exit_reason'], 'supervisor heartbeat stale')

    def test_hard_alarm_ends_a_hung_import(self):
        hb = Path(tempfile.mkdtemp()) / 'hb'
        hb.touch()
        p, _ = self.probe(hb, {'STUB_HANG_IMPORT': '1'}, hard='2', hold='1')
        t0 = time.time()
        rc = p.wait(timeout=10)
        self.assertEqual(rc, -signal.SIGALRM)
        self.assertLess(time.time() - t0, 3.5)

    def test_dies_with_supervisor(self):
        """Supervisor (a stand-in parent that keeps the heartbeat fresh) is SIGKILLed: the probe must die at once
        via PR_SET_PDEATHSIG, even though its heartbeat file is still fresh."""
        d = Path(tempfile.mkdtemp())
        hb = d / 'hb'
        hb.touch()
        code = (f'import subprocess,sys,os,time\n'
                f'p=subprocess.Popen([sys.executable,{str(R.PROBE)!r},"--hold-s","8","--hard-s","14",'
                f'"--heartbeat",{str(hb)!r},"--report",{str(d / "r.json")!r}],env=dict(os.environ,PYTHONPATH={str(STUB)!r}))\n'
                f'open({str(d / "pid")!r},"w").write(str(p.pid))\n'
                f'while True:\n    os.utime({str(hb)!r}); time.sleep(0.2)\n')
        sup = subprocess.Popen([sys.executable, '-c', code])
        for _ in range(50):
            if (d / 'pid').exists():
                break
            time.sleep(0.1)
        time.sleep(1.0)
        pid = int((d / 'pid').read_text())
        os.utime(hb)
        sup.kill()
        sup.wait()
        t0 = time.time()
        while time.time() - t0 < 3:
            try:
                st = Path(f'/proc/{pid}/stat').read_text().split(') ')[1][0]
                if st == 'Z':
                    break
            except OSError:
                break
            time.sleep(0.05)
        self.assertLess(time.time() - t0, 1.0, 'probe survived its supervisor')

    def test_topics_isolated(self):
        import atlas_dds_storm_probe as P
        subs, pubs = P.planned_topics()
        P.check_isolated(subs + pubs)
        with self.assertRaises(SystemExit):
            P.check_isolated(['/cmd_vel'])
        with self.assertRaises(SystemExit):
            P.check_isolated(['/atlas_storm_probe_x/a'])
        self.assertEqual((len(subs), len(pubs)), (16, 2))


if __name__ == '__main__':
    unittest.main()
