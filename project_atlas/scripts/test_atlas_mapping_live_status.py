"""Dashboard live-status classification (atlas_mapping.html), run under Node.

Guards the 2026-10-10 fix: a browser/network stall must be reported as a
connection problem with rover state unknown, never as a rover-side
"POSE DELAYED" or AMCL state; rover-side states use the server's own ages.
Skipped when Node.js is unavailable. No ROS, network or actuators.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

HTML = Path(__file__).with_name('atlas_mapping.html')


def extract_js():
    text = HTML.read_text()
    start = text.index('const LINK_STALE_S=')
    end = text.index('function linkAgeS()')
    return text[start:end]


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class LiveStatusTests(unittest.TestCase):
    def status(self, state, link_age):
        script = extract_js() + f'\nconsole.log(JSON.stringify(liveStatus({json.dumps(state)}, {link_age})));'
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def state(self, pose_age=0.3, amcl_age=0.8, uncertain=False):
        return {'map': {'width': 100}, 'pose': {'value': {'x': 1}, 'age': pose_age},
                'localization': {'value': {'uncertain': uncertain}, 'age': amcl_age}}

    def test_network_stall_is_not_pose_delayed(self):
        # Rover data was perfectly fresh at the last snapshot; the link then stalled.
        st = self.status(self.state(), 4.0)
        self.assertIn('CONNECTION DELAYED', st['text'])
        self.assertIn('ROVER STATE UNKNOWN', st['text'])
        self.assertNotIn('POSE DELAYED', st['text'])
        self.assertNotIn('AMCL', st['text'])
        self.assertEqual(st['cls'], 'fail')

    def test_no_contact_yet_is_connection_delayed(self):
        self.assertIn('CONNECTION DELAYED', self.status(self.state(), 'Infinity')['text'])
        self.assertIn('CONNECTION DELAYED', self.status(None, 0.1)['text'])

    def test_rover_side_pose_stale_on_live_link_is_pose_delayed(self):
        st = self.status(self.state(pose_age=3.0), 0.5)
        self.assertEqual(st['text'], '● POSE DELAYED ON ATLAS')
        self.assertEqual(st['cls'], 'warn')

    def test_short_link_lag_does_not_downgrade_confident(self):
        # 1.9 s link lag + 0.9 s server age used to exceed the 2.5 s AMCL window.
        st = self.status(self.state(amcl_age=0.9), 1.9)
        self.assertEqual(st['text'], '● LIVE / AMCL CONFIDENT')
        self.assertEqual(st['cls'], 'ok')

    def test_amcl_states_unchanged(self):
        self.assertEqual(self.status(self.state(uncertain=True), 0.5)['text'], '● LIVE / AMCL UNCERTAIN')
        self.assertEqual(self.status(self.state(amcl_age=3.0), 0.5)['text'], '● LIVE / AMCL UNVERIFIED')

    def test_map_waiting(self):
        st = self.state(pose_age=9.0)
        st['map'] = {}
        self.assertEqual(self.status(st, 0.5)['text'], '● MAP WAITING')

    def test_render_and_fetch_failure_use_classifier(self):
        text = HTML.read_text()
        self.assertEqual(text.count("'● POSE DELAYED ON ATLAS'"), 1)  # only inside liveStatus
        self.assertNotIn("'● POSE DELAYED'", text)
        self.assertIn("catch(e){let st=liveStatus(null,Infinity)", text)
        self.assertIn("$('liveState').textContent=status.text", text)
        self.assertIsNone(re.search(r"fresh\(state\.(pose|localization)", text))


if __name__ == '__main__':
    unittest.main()
