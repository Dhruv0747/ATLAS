"""Dashboard motion chip vs the Stage 25 recorded round trip (display logic only, needs node)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
JS = ROOT / 'web' / 'v2' / 'motion-status.js'
FRAMES = json.loads((Path(__file__).parent / 'data' / 'stage25_motion_frames.json').read_text())['frames']
NODE = shutil.which('node')


def classify(status):
    code = ("const m=require(process.argv[1]);"
            "process.stdout.write(JSON.stringify(m.classify(JSON.parse(process.argv[2]))))")
    out = subprocess.run([NODE, '-e', code, str(JS), json.dumps(status)], capture_output=True, text=True, timeout=20)
    if out.returncode:
        raise RuntimeError(out.stderr)
    return json.loads(out.stdout)


def legacy(status):
    """The pre-Stage-25 chip: odometry velocity only."""
    value = status['ros']['odom']['value']
    return 'Moving' if abs(value['vx']) > 0.01 or abs(value['wz']) > 0.02 else 'Stopped'


def status(frame, **override):
    ros = {'odom': dict(frame['odom']), 'encoder_health': dict(frame['encoder_health'])}
    ros.update(override)
    return {'ros': ros}


@unittest.skipUnless(NODE, 'node is required to run the dashboard logic')
class MotionChipRecordedRoundTrip(unittest.TestCase):
    def test_recorded_frames_match_expected_chip(self):
        for frame in FRAMES:
            text, tone, _ = classify(status(frame))
            self.assertEqual(text, frame['expect'], frame['label'])

    def test_defect_reproduced_by_legacy_logic(self):
        blind = [f for f in FRAMES if f['expect'].startswith('Moving ·')]
        self.assertGreaterEqual(len(blind), 3)
        for frame in blind:
            self.assertEqual(legacy(status(frame)), 'Stopped', frame['label'])  # the recorded defect

    def test_never_turns_moving_into_stopped_or_ok(self):
        moving = next(f for f in FRAMES if f['expect'] == 'Moving')
        health = json.loads(moving['encoder_health']['value'])
        health['last_change_age_s'] = [30, 30, 30, 30]
        frame = dict(moving, encoder_health={'age': 0.2, 'value': json.dumps(health)})
        self.assertEqual(classify(status(frame))[0], 'Moving')  # odometry says moving: encoders cannot veto

    def test_single_flickering_wheel_at_rest_stays_stopped(self):
        rest = FRAMES[0]
        health = json.loads(rest['encoder_health']['value'])
        health['last_change_age_s'] = [0.0, 30, 30, 30]
        frame = dict(rest, encoder_health={'age': 0.2, 'value': json.dumps(health)})
        self.assertEqual(classify(status(frame))[0], 'Stopped')

    def test_stale_or_unreadable_encoder_evidence_does_not_raise_a_warning(self):
        blind = next(f for f in FRAMES if f['expect'].startswith('Moving ·'))
        stale = dict(blind, encoder_health={'age': 9.0, 'value': blind['encoder_health']['value']})
        self.assertEqual(classify(status(stale))[0], 'Stopped')
        junk = dict(blind, encoder_health={'age': 0.1, 'value': '{not json'})
        self.assertEqual(classify(status(junk))[0], 'Stopped')
        notfresh = json.loads(blind['encoder_health']['value']); notfresh['packet_fresh'] = False
        self.assertEqual(classify(status(dict(blind, encoder_health={'age': 0.1, 'value': json.dumps(notfresh)})))[0], 'Stopped')

    def test_unknown_states_unchanged(self):
        self.assertEqual(classify(None)[0], 'Motion unknown')
        frame = FRAMES[0]
        old = status(frame); old['ros']['odom']['age'] = 5
        self.assertEqual(classify(old)[0], 'Motion unknown')

    def test_display_only_no_control_references(self):
        source = JS.read_text()
        for word in ('fetch(', 'XMLHttpRequest', 'post(', 'cmd_vel', 'e_stop', 'localStorage'):
            self.assertNotIn(word, source)


if __name__ == '__main__':
    unittest.main()
