"""Stage 29 stop-response recorder: CDR decoding, event detection and PASS/FAIL measurement on synthetic recordings,
plus a real recording against the fake foxglove bridge."""
import json
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage29_flysky_drive'
sys.path.insert(0, str(PKG)); sys.path.insert(0, str(ROOT / 'scripts'))
import stage29_stop_recorder as R   # noqa: E402
import atlas_flysky_core as core    # noqa: E402

ENC = (b'\x00\x01\x00\x00')


def joy_cdr(axes, buttons, frame='joy'):
    fid = frame.encode() + b'\x00'
    b = struct.pack('<iI', 1, 2) + struct.pack('<I', len(fid)) + fid
    b += b'\x00' * ((-len(b)) % 4)
    b += struct.pack('<I', len(axes)) + struct.pack('<%df' % len(axes), *axes)
    b += struct.pack('<I', len(buttons)) + struct.pack('<%di' % len(buttons), *buttons)
    return ENC + b


class Decode(unittest.TestCase):
    def test_joy_int32_and_rc(self):
        v = R.decode('sensor_msgs/msg/Joy', joy_cdr([0.0, -1.0, 0.5], [0, 1, 0, 0, 1]))
        self.assertEqual(v['buttons'], [0, 1, 0, 0, 1]); self.assertEqual(v['axes'], [0.0, -1.0, 0.5])
        self.assertEqual(R.decode('std_msgs/msg/Int32', ENC + struct.pack('<i', -14198)), -14198)
        vals = [1024] * 16; vals[4], vals[5] = 1807, 240
        f = R.rc_frame(json.dumps({'proto': 'sbus', 'hex': core.encode_sbus(vals, failsafe=True).hex(), 'seq': 1}))
        self.assertEqual((f['ch'][5], f['ch'][6], f['failsafe']), (1807, 240, True))


def synth(event, stop_after=0.15, wheels_coast=0.3, latch=True, cmd_zero=True, extra_motion=None):
    """A 10 s recording: wheels spin until `stop_after` after the event at t=105, then coast `wheels_coast`."""
    rows, t0 = [], 105.0
    stop_t = t0 + stop_after
    for k in range(100):                                   # 10 Hz encoders, rc frames, policy; 16 Hz joy
        t = 100.0 + k * 0.1
        moving = t < stop_t + wheels_coast or (extra_motion and extra_motion[0] <= t <= extra_motion[1])
        for i in (1, 2, 3, 4):
            rows.append({'t': t, 'topic': f'/yahboom/encoder/m{i}', 'v': int(k * 10) if moving else 999999})
        ch = {'1': 1024, '2': 1500, '5': 1807, '6': 240, '7': 1807}
        fs = False
        if event == 'swb_stop' and t >= t0:
            ch['6'] = 1807
        if event == 'swa_off' and t >= t0:
            ch['5'] = 240
        if event == 'stick_release' and t >= t0:
            ch['2'] = 1024
        if event == 'tx_off' and t >= t0:
            fs = True
        rows.append({'t': t + 0.01, 'topic': '/atlas/rc/frames', 'v': {'ch': ch, 'failsafe': fs, 'frame_lost': False}})
        lat = latch and t >= stop_t
        rows.append({'t': t + 0.02, 'topic': '/atlas/control_policy', 'v': {'stop_latched': lat, 'stop_reason': 'x'}})
        rows.append({'t': t + 0.03, 'topic': '/cmd_vel', 'v': [0.0 if (t >= stop_t and cmd_zero) else 0.05, 0, 0, 0, 0, 0.0]})
        rows.append({'t': t + 0.04, 'topic': '/motor_speed', 'v': 0.0 if t >= stop_t + 0.2 else 0.3})
    for k in range(160):
        t = 100.0 + k * 0.0625
        b = 1 if (event == 'xbox_b' and t0 <= t < t0 + 0.2) else 0
        rows.append({'t': t, 'topic': '/joy', 'v': {'axes': [0.0] * 6, 'buttons': [0, b] + [0] * 9}})
    return rows


def write(rows):
    p = Path(tempfile.mkdtemp()) / 'rec.jsonl'
    p.write_text('\n'.join(json.dumps(r) for r in sorted(rows, key=lambda r: r['t'])) + '\n')
    return p


class Analysis(unittest.TestCase):
    def test_each_event_detected_and_passes(self):
        for kind, latch in (('xbox_b', True), ('swb_stop', True), ('swa_off', False), ('stick_release', False), ('tx_off', True)):
            r = R.analyze(write(synth(kind, latch=latch)))
            kinds = [e['event'] for e in r['events']]
            self.assertIn(kind, kinds, kind)
            e = next(e for e in r['events'] if e['event'] == kind)
            self.assertTrue(e['pass'], e); self.assertLessEqual(e['wheels_still_s'], 1.0)

    def test_slow_stop_fails(self):
        e = next(e for e in R.analyze(write(synth('xbox_b', wheels_coast=1.5)))['events'] if e['event'] == 'xbox_b')
        self.assertFalse(e['pass']); self.assertGreater(e['wheels_still_s'], 1.0)

    def test_missing_latch_fails_and_unexpected_latch_fails(self):
        e = next(e for e in R.analyze(write(synth('swb_stop', latch=False)))['events'] if e['event'] == 'swb_stop')
        self.assertFalse(e['pass'])
        e = next(e for e in R.analyze(write(synth('swa_off', latch=True)))['events'] if e['event'] == 'swa_off')
        self.assertFalse(e['pass'])

    def test_motion_after_stop_is_seen(self):
        e = next(e for e in R.analyze(write(synth('xbox_b', extra_motion=(107.0, 107.5))))['events'] if e['event'] == 'xbox_b')
        self.assertGreater(e['wheels_still_s'], 1.0); self.assertFalse(e['pass'])

    def test_xbox_off_and_receiver_silent_detected(self):
        rows = [r for r in synth('none') if not (r['topic'] == '/joy' and r['t'] > 105.0)]
        self.assertIn('xbox_off', [e['event'] for e in R.analyze(write(rows))['events']])
        rows = [r for r in synth('none') if not (r['topic'] == '/atlas/rc/frames' and 105.0 < r['t'] < 106.0)]
        self.assertIn('rx_silent', [e['event'] for e in R.analyze(write(rows))['events']])


class RecordReal(unittest.TestCase):
    def test_records_through_fake_bridge_without_blocking(self):
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        ctl = Path(tempfile.mkdtemp()) / 'ctl.json'; ctl.write_text('{}')
        srv = subprocess.Popen([sys.executable, str(ROOT / 'tools/deploy/stage28_base_maintenance/sim/fake_foxglove.py'),
                                str(port), str(ctl), 'foxglove.sdk.v1'])
        try:
            for _ in range(100):
                try:
                    socket.create_connection(('127.0.0.1', port), 0.2).close(); break
                except OSError:
                    time.sleep(0.05)
            out = Path(tempfile.mkdtemp()) / 'r.jsonl'
            t0 = time.time(); counts = R.record(out, 1.5, port=port)
            self.assertLess(time.time() - t0, 3.5)
            self.assertGreater(counts['/atlas/control_policy'], 5); self.assertGreater(counts['/cmd_vel'], 2)
            rows = R.load(out)
            pol = next(r for r in rows if r['topic'] == '/atlas/control_policy')
            self.assertIn('stop_latched', pol['v'])
        finally:
            srv.terminate(); srv.wait(5)


if __name__ == '__main__':
    unittest.main()
