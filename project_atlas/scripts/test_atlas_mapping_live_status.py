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

    def state(self, pose_age=0.3, amcl_age=0.8, uncertain=False, verdict='VERIFIED', current_boot=True,
              check='VERIFIED', check_age=10.0, monitor_age=0.5):
        s = {'map': {'width': 100}, 'pose': {'value': {'x': 1}, 'age': pose_age},
             'localization': {'value': {'uncertain': uncertain}, 'age': amcl_age}}
        if verdict:
            s['start_verdict'] = {'value': {'state': verdict, 'current_boot': current_boot}, 'age': 5}
        if check:
            s['localization_check'] = {'value': {'state': check, 'check_age_s': check_age}, 'age': monitor_age}
        return s

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
        self.assertEqual(st['text'], '● LIVE / LOCALIZATION VERIFIED BY LIDAR')
        self.assertEqual(st['cls'], 'ok')

    def test_amcl_states_without_monitor_unchanged(self):
        self.assertEqual(self.status(self.state(uncertain=True, check=None), 0.5)['text'], '● LIVE / AMCL UNCERTAIN')
        self.assertEqual(self.status(self.state(amcl_age=3.0, check=None), 0.5)['text'], '● LIVE / AMCL UNVERIFIED')

    def test_low_covariance_without_verified_start_is_not_green(self):
        # Hall cold start: tiny covariance at a pose seeded without the LiDAR.
        for verdict, boot in ((None, True), ('UNVERIFIED', True), ('VERIFIED', False)):
            st = self.status(self.state(verdict=verdict, current_boot=boot, check=None), 0.5)
            self.assertEqual(st['text'], '● AMCL CONFIDENT - START POSE NOT VERIFIED')
            self.assertEqual(st['cls'], 'warn')
            self.assertFalse(st['trusted'])

    def test_unknown_start_is_reported_even_with_a_pose(self):
        for pose_age in (0.3, 9.0):
            st = self.status(self.state(pose_age=pose_age, verdict='UNKNOWN'), 0.5)
            self.assertEqual(st['text'], '● LOCALIZATION UNKNOWN - LIDAR DID NOT CONFIRM START POSE')
            self.assertEqual(st['cls'], 'fail')

    def test_start_verified_is_not_continuous_proof(self):
        # 2026-10-10 moving failure: start was verified, AMCL later 4 m wrong.
        st = self.status(self.state(check=None), 0.5)
        self.assertEqual(st['text'], '● AMCL CONFIDENT - START VERIFIED ONLY, NOT RE-CHECKED')
        self.assertEqual(st['cls'], 'warn')
        self.assertFalse(st['trusted'])

    def test_lost_check_overrides_everything(self):
        st = self.status(self.state(check='LOST'), 0.5)
        self.assertEqual(st['text'], '● LOCALIZATION LOST - LIDAR DISAGREES WITH AMCL')
        self.assertEqual(st['cls'], 'fail')
        self.assertFalse(st['trusted'])

    def test_moving_old_or_stale_checks_are_not_green(self):
        self.assertEqual(self.status(self.state(check='MOVING_UNVERIFIED'), 0.5)['text'],
                         '● MOVING - LOCALIZATION NOT VERIFIED')
        for kw in ({'check_age': 90.0}, {'check': 'DEGRADED'}):
            st = self.status(self.state(**kw), 0.5)
            self.assertEqual(st['text'], '● LOCALIZATION NOT CONFIRMED - PARK TO CHECK')
            self.assertFalse(st['trusted'])
        st = self.status(self.state(monitor_age=30.0), 0.5)   # monitor stopped writing
        self.assertNotEqual(st['cls'], 'ok')

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
