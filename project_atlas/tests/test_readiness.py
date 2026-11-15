from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_readiness import checklist

POL = {'autonomy': {'armed': False}, 'stop_latched': True}
ENC = {'autonomy_ready': True, 'navigation_validated': True, 'state': 'DEGRADED'}
LOC = {'state': 'VERIFIED'}
EV_OK = {'enabled': True, 'missing': [], 'passed': [0.1, 0.15], 'latest': {}}
EV_MISS = {'enabled': True, 'missing': [0.15], 'passed': [0.1],
           'latest': {0.15: {'verdict': 'FAIL', 'fresh': True, 'failed_checks': ['steady_mean_within_0.04']}}}


def run(**kw):
    args = dict(policy=POL, encoder_health=ENC, encoder_age_s=0.2, loc_check=LOC, loc_age_s=10, astra_age_s=0.1,
                bridge_active=True, speed_ev=EV_OK, gate={'speed_validated': True}, places_count=2)
    args.update(kw)
    return checklist(**args)


def item(r, i):
    return next(x for x in r['items'] if x['id'] == i)


class ReadinessTests(unittest.TestCase):
    def test_all_green(self):
        r = run()
        self.assertTrue(all(i['ok'] for i in r['items']))
        self.assertTrue(r['ready_to_switch_on'])
        self.assertFalse(r['ready_to_drive'])              # not armed yet

    def test_speed_blocker_explains_and_links(self):
        r = run(speed_ev=EV_MISS, gate={'speed_validated': False})
        s = item(r, 'speed')
        self.assertFalse(s['ok']); self.assertIn('0.15', s['why']); self.assertIn('FAIL', s['why'])
        self.assertEqual(s['action']['href'], '/v2/readiness#speed')
        self.assertTrue(s['steps']); self.assertFalse(r['ready_to_switch_on'])

    def test_speed_loop_disabled_has_no_test_button(self):
        s = item(run(speed_ev={'enabled': False, 'missing': [0.1, 0.15], 'latest': {}},
                     gate={'speed_validated': False}), 'speed')
        self.assertIsNone(s['action']); self.assertIn('बंद', s['why'])

    def test_encoder_stale_and_not_validated(self):
        self.assertFalse(item(run(encoder_age_s=None), 'encoders')['ok'])
        e = item(run(encoder_health=dict(ENC, autonomy_ready=False, navigation_validated=False)), 'encoders')
        self.assertFalse(e['ok']); self.assertIn('validated', e['why']); self.assertEqual(e['action']['href'], '/v2/testlab')

    def test_localization_and_camera_and_waypoints(self):
        self.assertFalse(item(run(loc_check={'state': 'DEGRADED'}), 'localization')['ok'])
        self.assertFalse(item(run(loc_age_s=999), 'localization')['ok'])
        c = item(run(astra_age_s=None, bridge_active=False), 'camera')
        self.assertFalse(c['ok']); self.assertEqual(c['action']['api'], '/api/readiness/bridge')
        r = run(places_count=0, policy={'autonomy': {'armed': True}, 'stop_latched': False})
        self.assertFalse(item(r, 'waypoints')['ok']); self.assertTrue(item(r, 'waypoints')['optional'])
        self.assertTrue(r['ready_to_drive'])                 # waypoints never block (Move here works without)

    def test_estop_needed_only_to_switch_on(self):
        r = run(policy={'autonomy': {'armed': False}, 'stop_latched': False})
        self.assertFalse(item(r, 'estop')['ok']); self.assertFalse(r['ready_to_switch_on'])
        r = run(policy={'autonomy': {'armed': True}, 'stop_latched': False})
        self.assertTrue(item(r, 'estop')['ok']); self.assertTrue(r['ready_to_drive'])

    def test_no_mux(self):
        r = run(policy=None)
        self.assertFalse(item(r, 'mux')['ok']); self.assertFalse(r['ready_to_switch_on'])


if __name__ == '__main__':
    unittest.main()
