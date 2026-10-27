"""Offline tests: Stage 28 independent safety observer against a fake foxglove bridge (real sockets/processes)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage28_base_maintenance'
sys.path.insert(0, str(PKG))
import atlas_safety_observer as so  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Rig:
    def __init__(self, proto='foxglove.sdk.v1', ctl=None):
        self.dir = Path(tempfile.mkdtemp())
        self.ctl_path = self.dir / 'ctl.json'
        self.ctl_path.write_text(json.dumps(ctl or {}))
        self.port = free_port()
        self.srv = subprocess.Popen([sys.executable, str(PKG / 'sim/fake_foxglove.py'), str(self.port),
                                     str(self.ctl_path), proto])
        self.odom = self.dir / 'odom.json'
        self.pose = [-0.0035, 0.0, 0.0]
        self.write_odom = True
        self._stop = threading.Event()
        threading.Thread(target=self._writer, daemon=True).start()
        self.base = subprocess.Popen(['sleep', '300'])
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', self.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.05)

    def _writer(self):
        while not self._stop.is_set():
            if self.write_odom:
                tmp = self.odom.with_suffix('.tmp')
                tmp.write_text(json.dumps(dict(zip(('x', 'y', 'yaw'), self.pose))))
                os.replace(tmp, self.odom)
            time.sleep(0.3)

    def set(self, **kw):
        d = json.loads(self.ctl_path.read_text())
        d.update(kw)
        tmp = self.ctl_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(d))
        os.replace(tmp, self.ctl_path)

    def observer(self):
        return so.SafetyObserver(port=self.port, base_pid=self.base.pid, odom_path=self.odom)

    def close(self):
        self._stop.set()
        for p in (self.srv, self.base):
            p.kill()
            p.wait()


def wait_ok(obs, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = obs.evaluate()
        if v['ok']:
            return v
        time.sleep(0.05)
    raise AssertionError(f'never ok: {[k for k, s in v["signals"].items() if not s["ok"]]}')


def detect(obs, signal, timeout=3.0, period=0.25):
    """Seconds until `signal` fails, evaluating at the deployer's 0.25 s cadence."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        v = obs.evaluate()
        if not v['signals'][signal]['ok']:
            return time.monotonic() - t0, v['signals'][signal]
        time.sleep(period)
    raise AssertionError(f'{signal} never failed')


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.obs = self.rig.observer().start()
        wait_ok(self.obs)

    def tearDown(self):
        self.obs.stop()
        self.rig.close()

    def test_all_signals_ok_and_sourced(self):
        v = wait_ok(self.obs)
        self.assertEqual(set(v['signals']), {'observer_connected', 'estop_latched', 'manual_only', 'commission_off',
                                             'source_stopped', 'cmd_zero', 'motor_output_zero', 'telemetry_live',
                                             'base_loop_alive', 'base_still', 'base_identity'})
        self.assertTrue(all(s['age_s'] is None or s['age_s'] <= so.MAX_AGE_S for s in v['signals'].values()))

    def test_value_faults_detected_on_next_message(self):
        for ctl, sig, bound in ((dict(stop_latched=False), 'estop_latched', 0.6),
                                (dict(source='MANUAL'), 'source_stopped', 0.6),
                                (dict(cmd_lin=0.05), 'cmd_zero', 0.7),
                                (dict(encoder_state='CRITICAL'), 'telemetry_live', 0.6),
                                (dict(motor=0.1), 'motor_output_zero', 1.1)):
            with self.subTest(sig):
                wait_ok(self.obs)
                self.rig.set(**ctl)
                dt, s = detect(self.obs, sig)
                self.assertLessEqual(dt, bound, (sig, dt, s))
                self.rig.ctl_path.write_text('{}')

    def test_stalled_topics_fail_within_freshness_plus_one_tick(self):
        for topic, sig in (('/atlas/control_policy', 'estop_latched'), ('/cmd_vel', 'cmd_zero'),
                           ('/motor_speed', 'motor_output_zero'), ('/atlas/encoder_health', 'telemetry_live')):
            with self.subTest(topic):
                wait_ok(self.obs)
                self.rig.set(stall=[topic])
                dt, s = detect(self.obs, sig)
                self.assertIn('stale', s['why'])
                self.assertLessEqual(dt, so.MAX_AGE_S + 0.25 + 0.15)
                self.rig.ctl_path.write_text('{}')

    def test_malformed_payload_and_json_fail(self):
        self.rig.set(malformed='/cmd_vel')
        dt, s = detect(self.obs, 'cmd_zero')
        self.assertIn('malformed', s['why'])
        self.rig.ctl_path.write_text('{}')
        wait_ok(self.obs)
        self.rig.set(bad_json='/atlas/control_policy')
        dt, s = detect(self.obs, 'estop_latched')
        self.assertIn('malformed policy JSON', s['why'])

    def test_bridge_crash_fails_closed(self):
        self.rig.set(crash=True)
        dt, s = detect(self.obs, 'observer_connected')
        self.assertLess(dt, 0.6)
        dt2, _ = detect(self.obs, 'estop_latched')
        self.assertLessEqual(dt2, so.MAX_AGE_S + 0.4)

    def test_unadvertise_fails_signal_then_readvertise_recovers(self):
        self.rig.set(unadvertise=True, unadvertise_id=13)           # /motor_speed (base restarting)
        dt, s = detect(self.obs, 'motor_output_zero')
        self.assertIn('unadvertised', s['why'])
        self.assertTrue(self.obs.evaluate()['signals']['observer_connected']['ok'])
        time.sleep(1.2)
        self.assertFalse(self.obs.evaluate()['signals']['motor_output_zero']['ok'])   # stays failed, not stale-ok
        self.rig.set(readvertise=True)
        wait_ok(self.obs, timeout=4.0)

    def test_odom_stale_pose_change_and_base_replaced(self):
        self.rig.write_odom = False
        dt, s = detect(self.obs, 'base_loop_alive')
        self.assertLessEqual(dt, so.MAX_AGE_S + 0.25 + 0.35)
        self.rig.write_odom = True
        wait_ok(self.obs)
        self.rig.pose = [0.01, 0.0, 0.0]
        detect(self.obs, 'base_still')
        self.rig.pose = [-0.0035, 0.0, 0.0]
        wait_ok(self.obs)
        self.rig.base.kill()
        self.rig.base.wait()
        detect(self.obs, 'base_identity')


class StartTests(unittest.TestCase):
    def test_subprotocol_fallback_and_refusal(self):
        rig = Rig(proto='foxglove.websocket.v1')
        try:
            with rig.observer() as o:
                self.assertEqual(o.subprotocol, 'foxglove.websocket.v1')
                wait_ok(o)
        finally:
            rig.close()
        rig = Rig(proto='something.else')
        try:
            with self.assertRaises(so.ObserverError):
                rig.observer().start()
        finally:
            rig.close()

    def test_missing_topic_or_wrong_encoding_refused(self):
        for ctl in ({'not_advertised': ['/motor_speed']}, {'encoding': 'json'}):
            rig = Rig(ctl=ctl)
            try:
                with self.assertRaises(so.ObserverError):
                    rig.observer().start(timeout=2.0)
            finally:
                rig.close()

    def test_no_bridge_refused(self):
        with self.assertRaises(OSError):
            so.SafetyObserver(port=free_port()).start()

    def test_cdr_decoding(self):
        import struct
        self.assertEqual(so.decode('std_msgs/msg/String', b'\x00\x01\x00\x00' + struct.pack('<I', 3) + b'hi\0'), 'hi')
        for bad in (b'', b'\x01\x00\x00\x00abcd', b'\x00\x01\x00\x00' + struct.pack('<I', 9) + b'hi\0',
                    b'\x00\x01\x00\x00' + struct.pack('<I', 3) + b'hix'):
            with self.assertRaises(ValueError):
                so.decode('std_msgs/msg/String', bad)
        with self.assertRaises(ValueError):
            so.decode('geometry_msgs/msg/Twist', b'\x00\x01\x00\x00' + b'\0' * 40)


if __name__ == '__main__':
    unittest.main()
